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
                # Заголовок и ссылка
                title_el = project.find("a", href=lambda x: x and "/projects/" in x)
                title = title_el.text.strip() if title_el else "Без названия"
                link = "https://kwork.ru" + title_el["href"] if title_el else ""
                project_id = int(title_el["href"].split("/")[-1])


                # Описание
                desc_el = project.find("div", class_="wants-card__description-text")
                if desc_el:
                    # Внутри ищем скрытый блок с полным текстом
                    full_desc = desc_el.find("div", style=lambda s: s and "display: none" in s)
                    if full_desc:
                        desc = full_desc.text.strip()
                    else:
                        # Если скрытого блока нет — берём обычный (короткое описание)
                        desc = desc_el.text.strip()
                else:
                    desc = ""

                # Бюджет
                budget_el = project.find("div", class_="wants-card__price")

                if budget_el:
                    budget = budget_el.text.strip()
                    formated_w_budget = re.search(r'\n\t\t(.*?)\n\t ₽', budget)
                    if formated_w_budget:
                        temp_w_budget = str(formated_w_budget.group(1)).strip().replace(' ', '')

                    wanted_budget = int(temp_w_budget)
                else:
                    wanted_budget = -1

                max_budget_el = project.find("div", class_="wants-card__description-higher-price")

                if max_budget_el:
                    max_budget = max_budget_el.text.strip()
                    formated_max_budget = re.search(r'\n\t\t(.*?)\n\t ₽', max_budget)
                    if formated_max_budget:
                        temp_max_budget = str(formated_max_budget.group(1)).strip().replace(' ', '')

                    max_budget = int(temp_max_budget)
                else:
                    max_budget = -1

                info_el = project.find("div", class_="dib v-align-t")

                if info_el:
                    all_projects = info_el.text.strip()
                    formated_info = all_projects.split('Размещено проектов на бирже: ')[1].strip().replace('\n','').replace('\t','')

                    numbers = re.findall(r'\d+', formated_info)
                    formated_all_projects = int(numbers[0])
                    formated_hire_percent = int(numbers[-1])

                offers_el = project.find("div", class_="want-card__informers-row")

                if offers_el:
                    formated_offers = offers_el.text.strip()
                    number_offer = re.findall(r'\d+', formated_offers)
                    if len(number_offer) > 1:
                        offers = int(number_offer[1])
                        active = True
                    else:
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