import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import pprint
import re

from database import init_db, is_new, save_project

from bot import send_message

async def get_projects(max_pages=30):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        })

        result = []


        if max_pages == 30:
            await page.goto(f"https://kwork.ru/projects?c=11", wait_until="networkidle")
            await page.wait_for_timeout(3000)
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            page_count = soup.find_all("div", class_="pagination__item")
            last_page = int(page_count[-2].text.strip())
            print(f"Всего страниц: {last_page}")
            max_pages=last_page

        for page_num in range(1, max_pages + 1):
            print(f"Идёт парсинг страницы: {page_num}...")
            await page.goto(f"https://kwork.ru/projects?c=11&page={page_num}", wait_until="networkidle")
            await page.wait_for_timeout(2000)

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            projects = soup.find_all("div", class_="want-card--list")

            if not projects:
                print(f"Страница {page_num} пустая")
                break

            current_url = page.url
            if f"page={page_num}" not in current_url:
                print(f"Парсер дошёл до конца.")
                break

            for project in projects:
                title_el = project.find("a", href=lambda x: x and "/projects/" in x)
                title = title_el.text.strip() if title_el else "Без названия"
                link = "https://kwork.ru" + title_el["href"] if title_el else ""
                project_id = int(title_el["href"].split("/")[-1])


                desc_el = project.find("div", class_="wants-card__description-text")
                if desc_el:
                    full_desc = desc_el.find("div", style=lambda s: s and "display: none" in s)
                    if full_desc:
                        desc = full_desc.text.strip()
                    else:
                        desc = desc_el.text.strip()
                else:
                    desc = ""

                wanted_budget = -1
                budget_el = project.find("div", class_="wants-card__price")

                if budget_el:
                    budget = budget_el.text.strip()
                    formated_w_budget = re.search(r'\n\t\t(.*?)\n\t ₽', budget)
                    if formated_w_budget:
                        temp_w_budget = str(formated_w_budget.group(1)).strip().replace(' ', '')
                        if temp_w_budget.isdigit():
                            wanted_budget = int(temp_w_budget)

                max_budget = -1
                max_budget_el = project.find("div", class_="wants-card__description-higher-price")

                if max_budget_el:
                    max_budget_text = max_budget_el.text.strip()
                    formated_max_budget = re.search(r'\n\t\t(.*?)\n\t ₽', max_budget_text)
                    if formated_max_budget:
                        temp_max_budget = str(formated_max_budget.group(1)).strip().replace(' ', '')
                        if temp_max_budget.isdigit():
                            max_budget = int(temp_max_budget)

                formated_all_projects = 0
                formated_hire_percent = 0
                info_el = project.find("div", class_="dib v-align-t")

                if info_el:
                    all_projects_text = info_el.text.strip()
                    if 'Размещено проектов на бирже: ' in all_projects_text:
                        formated_info = all_projects_text.split('Размещено проектов на бирже: ')[1].strip().replace('\n','').replace('\t','')
                        numbers = re.findall(r'\d+', formated_info)
                        if numbers:
                            formated_all_projects = int(numbers[0])
                            formated_hire_percent = int(numbers[-1])

                offers = 0
                active = False
                offers_el = project.find("div", class_="want-card__informers-row")

                if offers_el:
                    formated_offers = offers_el.text.strip()
                    number_offer = re.findall(r'\d+', formated_offers)
                    if len(number_offer) > 1:
                        offers = int(number_offer[1])
                        active = True
                    elif len(number_offer) == 1:
                        offers = int(number_offer[0])
                        active = False

                result.append({
                    "id": project_id,
                    "title": title,
                    "link": link,
                    "wanted_budget": wanted_budget,
                    "max_budget": max_budget,
                    "description": desc,
                    "all_projects": formated_all_projects,
                    "hire_percent": formated_hire_percent,
                    "offers": offers,
                    "is_active": active
                })

        await browser.close()
        return result


async def parse_single_project(url: str) -> dict | None:
    """
    Парсит ОДИН заказ по прямой ссылке на его страницу.
    """
    match = re.search(r"/projects/(\d+)", url)
    if not match:
        return None
    project_id = int(match.group(1))

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        })

        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(2000)
        html = await page.content()
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")

    title = "Без названия"
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    elif soup.find("h1"):
        title = soup.find("h1").text.strip()

    description = ""
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        description = og_desc["content"].strip()

    page_text = soup.get_text(" ", strip=True)
    wanted_budget = -1
    max_budget = -1

    budget_idx = page_text.find("Бюджет")
    search_zone = page_text[budget_idx:budget_idx + 200] if budget_idx != -1 else page_text

    numbers = [
        int(n.replace(" ", ""))
        for n in re.findall(r"(\d[\d\s]{0,9})\s*₽", search_zone)
        if n.strip()
    ]

    if numbers:
        wanted_budget = min(numbers)
        max_budget = max(numbers)

    return {
        "id": project_id,
        "title": title,
        "link": url,
        "wanted_budget": wanted_budget,
        "max_budget": max_budget,
        "description": description,
        "all_projects": 0,
        "hire_percent": 0,
        "offers": 0,
        "is_active": True,
    }


async def main():
    init_db()
    projects = await get_projects()
    print(f"\nНайдено заказов: {len(projects)}\n")
    for p in projects[:10]:
        print(f"📌 Название: {p['title']}")
        print(f"💰 Желаемый бюджет: {p['wanted_budget']}")
        print(f"💵 Допустимый бюджет: {p['max_budget']}")
        print(f"🔗 Ссылка: {p['link']}")
        print(f"📝 Описание: {p['description']}")
        print(f"📂 Проектов на бирже: {p['all_projects']}")
        print(f"📊 Процент нанятых: {p['hire_percent']}")
        print(f"📋 Предложений: {p['offers']}")
        print("-" * 50)

    for p in projects:
        new = save_project(p)

        if new:
            print(f"🆕 Новый заказ: {p['title']}")
        else:
            print(f"🔄 Обновлён: {p['title']}")

if __name__ == "__main__":
    asyncio.run(main())