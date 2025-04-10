import os
import requests
from bs4 import BeautifulSoup
import pdfkit
from urllib.parse import urljoin, urlparse

# Настройки
BASE_URL = "https://yandex.ru/dev/direct/doc/ru/"
OUTPUT_DIR = "direct_create\direct_docs\docs_pdf"
WKHTMLTOPDF_PATH = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
config = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)

# Создаем папку для PDF
os.makedirs(OUTPUT_DIR, exist_ok=True)

def normalize_url(url):
    """Нормализация URL, устранение дублирования 'ru/ru'"""
    parsed = urlparse(url)
    path = parsed.path.replace('/ru/ru/', '/ru/')  # Исправляем дублирование
    return parsed._replace(path=path).geturl()

def get_html(url):
    """Загрузка HTML страницы"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(normalize_url(url), headers=headers, timeout=10)
        response.encoding = 'utf-8'
        return response.text if response.status_code == 200 else None
    except Exception as e:
        print(f"Ошибка загрузки {url}: {e}")
        return None

def clean_filename(text):
    """Очистка имени файла от спецсимволов"""
    invalid_chars = '<>:"/\\|?* '
    for char in invalid_chars:
        text = text.replace(char, '_')
    return text[:150]  # Ограничение длины

def get_full_breadcrumbs_name(soup):
    """Генерация имени файла из всех элементов хлебных крошек"""
    breadcrumbs = []
    breadcrumbs_div = soup.find("div", class_="dc-doc-page__breadcrumbs")
    
    if breadcrumbs_div:
        for item in breadcrumbs_div.find_all("li", class_="dc-breadcrumbs__item"):
            text = item.get_text(strip=True)
            if text and text.lower() not in ('руководство разработчика', 'документация'):
                breadcrumbs.append(clean_filename(text))
    
    return '-'.join(breadcrumbs) or 'document'

def parse_breadcrumbs(soup, base_url):
    """Форматирование хлебных крошек для HTML с абсолютными ссылками"""
    breadcrumbs_div = soup.find("div", class_="dc-doc-page__breadcrumbs")
    if not breadcrumbs_div:
        return ""
    
    items = []
    for item in breadcrumbs_div.find_all("li", class_="dc-breadcrumbs__item"):
        if item.find('a'):
            href = item.a["href"]
            absolute_href = urljoin(base_url, href)
            items.append(f'<a href="{absolute_href}">{item.get_text(strip=True)}</a>')
        else:
            items.append(f'<span>{item.get_text(strip=True)}</span>')
    
    return f'<div class="breadcrumbs">{" › ".join(items)}</div>'

def make_links_absolute(soup, base_url):
    """Преобразование всех относительных ссылок в абсолютные"""
    for tag in soup.find_all(['a', 'link', 'img', 'script'], href=True):
        tag['href'] = urljoin(base_url, tag['href'])
    for tag in soup.find_all(['img', 'script'], src=True):
        tag['src'] = urljoin(base_url, tag['src'])
    return soup

def parse_page(url):
    """Обработка страницы"""
    print(f"Обработка: {url}")
    html = get_html(url)
    if not html:
        return False

    soup = BeautifulSoup(html, 'html.parser')
    normalized_url = normalize_url(url)

    # Получаем хлебные крошки с абсолютными ссылками
    breadcrumbs_html = parse_breadcrumbs(soup, normalized_url)
    filename = get_full_breadcrumbs_name(soup)

    # Удаляем указанные блоки
    toc_panel = soup.find("div", class_="dc-nav-toc-panel dc-doc-page__toc-nav-panel")
    if toc_panel:
        toc_panel.decompose()
    
    feedback_block = soup.find("div", class_="dc-doc-page__feedback")
    if feedback_block:
        feedback_block.decompose()

    # Основной контент
    content = soup.find("div", class_="dc-doc-page__main")
    if not content:
        print(f"Контент не найден: {url}")
        return False

    # Преобразуем все ссылки в абсолютные
    content = make_links_absolute(content, normalized_url)

    # Генерация PDF
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <base href="{normalized_url}">
        <style>
            body {{ font-family: Arial; line-height: 1.6; padding: 20px; }}
            .breadcrumbs {{ 
                font-size: 0.9em; color: #666; 
                margin-bottom: 15px; padding-bottom: 5px;
                border-bottom: 1px solid #eee;
            }}
            .breadcrumbs a {{ color: #06c; text-decoration: none; }}
        </style>
    </head>
    <body>
        {breadcrumbs_html}
        {str(content)}
    </body>
    </html>
    """
    
    try:
        pdf_path = os.path.join(OUTPUT_DIR, f"{filename}.pdf")
        pdfkit.from_string(
            full_html, 
            pdf_path,
            configuration=config,
            options={
                'encoding': 'UTF-8',
                'margin-top': '15mm',
                'margin-right': '15mm',
                'margin-bottom': '15mm',
                'margin-left': '15mm',
                'quiet': ''
            }
        )
        print(f"Сохранено: {filename}.pdf")
        return True
    except Exception as e:
        print(f"Ошибка PDF: {e}")
        return False

def crawl_pages(start_url):
    """Обход всех страниц"""
    visited = set()
    queue = [normalize_url(start_url)]
    saved = 0

    while queue:
        url = queue.pop(0)
        
        if url in visited:
            continue
            
        visited.add(url)
        
        if parse_page(url):
            saved += 1

        # Поиск новых ссылок
        html = get_html(url)
        if not html:
            continue

        soup = BeautifulSoup(html, 'html.parser')
        for link in soup.find_all("a", href=True):
            href = link["href"].strip()
            if not href or href.startswith(('javascript:', '#')):
                continue
                
            full_url = normalize_url(urljoin(BASE_URL, href).split('?')[0].split('#')[0])
            if full_url.startswith(BASE_URL) and full_url not in visited and full_url not in queue:
                queue.append(full_url)
                print(f"Добавлено в очередь: {full_url}")

    print(f"\nЗавершено. Сохранено PDF: {saved}, всего страниц: {len(visited)}")

if __name__ == "__main__":
    if os.path.exists(WKHTMLTOPDF_PATH):
        crawl_pages(BASE_URL)
    else:
        print(f"Ошибка: wkhtmltopdf не найден по пути {WKHTMLTOPDF_PATH}")