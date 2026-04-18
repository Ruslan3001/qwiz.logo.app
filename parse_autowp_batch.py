import os
import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from urllib.parse import urljoin

INPUT_FILE = 'PhotoTable.md'
OUTPUT_FILE = 'autowp_gallery.md'

def get_last_processed_brand(filepath):
    """Считывает выходной файл и возвращает название последней обработанной марки."""
    if not os.path.exists(filepath):
        return None
    
    last_brand = None
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('|') and not line.startswith('| Марка') and not line.startswith('|---'):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) > 2 and parts[1]:
                    last_brand = parts[1]
    return last_brand

def get_processed_brands(filepath):
    """Считывает выходной файл и возвращает множество всех обработанных марок."""
    processed = set()
    if not os.path.exists(filepath):
        return processed
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('|') and not line.startswith('| Марка') and not line.startswith('|---'):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) > 2 and parts[1]:
                    processed.add(parts[1])
    return processed

def parse_input_table(filepath):
    """Парсит исходный Markdown-файл и возвращает список словарей с задачами."""
    tasks = []
    if not os.path.exists(filepath):
        print(f"[-] Файл {filepath} не найден!")
        return tasks
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            match = re.search(r'\|\[(.*?)\]\((.*?)\)\|', line)
            if match:
                tasks.append({
                    'brand': match.group(1).strip(),
                    'url': match.group(2).strip()
                })
    return tasks

def scrape_tasks(tasks_list, page, out_file):
    """Функция для обработки переданного списка задач."""
    for task in tasks_list:
        brand = task['brand']
        url = task['url']
        print(f"-> Обработка: {brand} ({url})", end="", flush=True)
        
        try:
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_timeout(1000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            
            images = page.locator('img').all()
            saved_count = 0
            
            for img in images:
                img_url = img.get_attribute('src') or img.get_attribute('data-src')
                
                # Строгий фильтр: берем только фото с CDN wheelsage
                if not img_url or 'wheelsage.org' not in img_url:
                    continue
                    
                alt_text = img.get_attribute('alt') or img.get_attribute('title') or brand
                img_url = urljoin(url, img_url)
                
                # ОПРЕДЕЛЯЕМ ЛОГОТИП
                is_logo = 1 if '/brand/logo' in img_url.lower() else 0
                
                # Добавили колонку {is_logo} в запись
                out_file.write(f"| {brand} | {is_logo} | {url} | ![{alt_text}]({img_url}) |\n")
                saved_count += 1
                
            out_file.flush()
            print(f" [+] Найдено: {saved_count}")
            
        except PlaywrightTimeoutError:
            print(" [-] Таймаут загрузки, пропускаем...")
            continue
        except Exception as e:
            print(f" [-] Ошибка: {e}")
            continue

def process_gallery():
    tasks = parse_input_table(INPUT_FILE)
    if not tasks:
        return

    last_brand = get_last_processed_brand(OUTPUT_FILE)
    start_index = 0
    
    if last_brand:
        print(f"[*] Найдена предыдущая сессия. Последняя обработанная марка: '{last_brand}'")
        for i, task in enumerate(tasks):
            if task['brand'] == last_brand:
                start_index = i + 1
                break
    
    tasks_to_process = tasks[start_index:]

    is_new_file = not os.path.exists(OUTPUT_FILE) or os.path.getsize(OUTPUT_FILE) == 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Глобальный таймаут 30 секунд
        page.set_default_timeout(30000)

        # --- Основной проход ---
        if tasks_to_process:
            print(f"[*] Осталось обработать марок (основной проход): {len(tasks_to_process)} из {len(tasks)}")
            with open(OUTPUT_FILE, 'a', encoding='utf-8') as out_file:
                if is_new_file:
                    out_file.write("| Марка автомобиля | Лого | Источник | Изображение |\n")
                    out_file.write("|---|---|---|---|\n")

                try:
                    scrape_tasks(tasks_to_process, page, out_file)
                except KeyboardInterrupt:
                    print("\n\n[!] Парсинг прерван пользователем. Прогресс сохранен.")
                    browser.close()
                    return

        # --- Сверка и повторный проход ---
        print("\n[*] Сверка списков и поиск пропущенных марок...")
        processed_brands = get_processed_brands(OUTPUT_FILE)
        missing_tasks = [t for t in tasks if t['brand'] not in processed_brands]

        if missing_tasks:
            print(f"[*] Найдено пропущенных марок: {len(missing_tasks)}. Начинаем повторную обработку...")
            with open(OUTPUT_FILE, 'a', encoding='utf-8') as out_file:
                if not os.path.exists(OUTPUT_FILE) or os.path.getsize(OUTPUT_FILE) == 0:
                    out_file.write("| Марка автомобиля | Лого | Источник | Изображение |\n")
                    out_file.write("|---|---|---|---|\n")
                try:
                    scrape_tasks(missing_tasks, page, out_file)
                except KeyboardInterrupt:
                    print("\n\n[!] Повторный парсинг прерван пользователем.")
        else:
            print("[*] Все марки успешно обработаны, пропущенных нет.")

        browser.close()
    
    print("Работа завершена.")

if __name__ == '__main__':
    process_gallery()