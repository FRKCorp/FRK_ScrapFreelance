import sqlite3
from datetime import datetime

DB_FILE = "projects.db"

def init_db():
    """Создаём таблицу если не существует"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id            INTEGER PRIMARY KEY,
            title         TEXT,
            description   TEXT,
            link          TEXT,
            wanted_budget INTEGER,
            max_budget    INTEGER,
            all_projects  INTEGER,
            hire_percent  INTEGER,
            offers        INTEGER,
            category      INTEGER,
            analiz        TEXT,
            is_active     BOOLEAN,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def is_new(project_id: int) -> bool:
    """Возвращает True если заказ ещё не видели"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
    result = cursor.fetchone()
    conn.close()
    return result is None


def save_project(project: dict):
    """Сохраняем или обновляем заказ в БД"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Проверяем существование внутри того же соединения
    cursor.execute("SELECT id FROM projects WHERE id = ?", (project["id"],))
    exists = cursor.fetchone() is not None

    if not exists:
        # Новый заказ — вставляем с текущим временем
        cursor.execute("""
            INSERT INTO projects 
            (id, title, description, link, wanted_budget, max_budget, all_projects, hire_percent, offers, category, analiz, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            project["id"], project["title"], project["description"],
            project["link"], project["wanted_budget"], project["max_budget"],
            project["all_projects"], project["hire_percent"], project["offers"],
            0, "", project["is_active"]
        ))
    else:
        # Старый заказ — обновляем только изменяемые поля
        # created_at и analiz не трогаем
        cursor.execute("""
            UPDATE projects SET
                title = ?,
                description = ?,
                wanted_budget = ?,
                max_budget = ?,
                all_projects = ?,
                hire_percent = ?,
                offers = ?,
                is_active = ?
            WHERE id = ?
        """, (
            project["title"], project["description"],
            project["wanted_budget"], project["max_budget"],
            project["all_projects"], project["hire_percent"],
            project["offers"], project["is_active"], project["id"]
        ))

    conn.commit()
    conn.close()
    return not exists