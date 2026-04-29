import sqlite3
from datetime import datetime
import json

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
            is_active     BOOLEAN DEFAULT 1,
            is_analyzed   BOOLEAN DEFAULT 0,
            category      INTEGER DEFAULT 0,
            real_price_min INTEGER DEFAULT 0,
            real_price_max INTEGER DEFAULT 0,
            deadline_days  INTEGER DEFAULT 0,
            risks          TEXT DEFAULT '',
            summary        TEXT DEFAULT '',
            analiz         TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def search_by_keyword(keyword: str) -> list:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, link, wanted_budget, max_budget,
               real_price_min, real_price_max, deadline_days,
               risks, summary, offers, hire_percent, tags
        FROM projects
        WHERE is_analyzed = 1 AND (
            title LIKE ? OR
            description LIKE ? OR
            tags LIKE ?
        )
        ORDER BY created_at DESC
    """, (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"))
    rows = cursor.fetchall()
    conn.close()
    return rows

def search_by_filters(category=None, min_budget=None, max_budget=None, tag=None) -> list:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    query = """
        SELECT id, title, link, wanted_budget, max_budget,
               real_price_min, real_price_max, deadline_days,
               risks, summary, offers, hire_percent, tags
        FROM projects
        WHERE is_analyzed = 1
    """
    params = []

    if category is not None:
        query += " AND category = ?"
        params.append(category)
    if min_budget is not None:
        query += " AND wanted_budget >= ?"
        params.append(min_budget)
    if max_budget is not None:
        query += " AND wanted_budget <= ?"
        params.append(max_budget)
    if tag is not None:
        query += " AND tags LIKE ?"
        params.append(f"%{tag}%")

    query += " ORDER BY created_at DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_stats() -> dict:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Всего заказов
    cursor.execute("SELECT COUNT(*) FROM projects")
    total = cursor.fetchone()[0]

    # По категориям
    cursor.execute("SELECT category, COUNT(*) FROM projects WHERE is_analyzed = 1 GROUP BY category")
    by_category = {row[0]: row[1] for row in cursor.fetchall()}

    # Непроанализированные
    cursor.execute("SELECT COUNT(*) FROM projects WHERE is_analyzed = 0")
    unanalyzed = cursor.fetchone()[0]

    # Средний бюджет
    cursor.execute("SELECT AVG(wanted_budget) FROM projects WHERE wanted_budget > 0")
    avg_budget = cursor.fetchone()[0]

    conn.close()
    return {
        "total": total,
        "by_category": by_category,
        "unanalyzed": unanalyzed,
        "avg_budget": round(avg_budget) if avg_budget else 0
    }

def is_new(project_id: int) -> bool:
    """Возвращает True если заказ ещё не видели"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
    result = cursor.fetchone()
    conn.close()
    return result is None

def get_unanalyzed():
    """Получить все непроанализированные заказы"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects WHERE is_analyzed = 0")
    rows = cursor.fetchall()
    conn.close()
    return rows

def mark_analyzed(project_id: int, result: dict):
    """Пометить заказ как проанализированный и записать результаты"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE projects SET
            is_analyzed   = 1,
            category      = ?,
            real_price_min = ?,
            real_price_max = ?,
            deadline_days  = ?,
            risks          = ?,
            summary        = ?,
            tags           = ?
        WHERE id = ?
    """, (
        result["category"],
        result["real_price_min"],
        result["real_price_max"],
        result["deadline_days"],
        json.dumps(result["risks"], ensure_ascii=False),
        result["summary"],
        json.dumps(result.get("tags", []), ensure_ascii=False),
        project_id
    ))
    conn.commit()
    conn.close()

def delete_old_projects():
    """Удалить заказы старше 3 дней"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM projects 
        WHERE created_at < datetime('now', '-3 days')
    """)
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    print(f"Удалено старых заказов: {deleted}")

def get_projects_by_category(category: int) -> list:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, link, wanted_budget, max_budget,
               real_price_min, real_price_max, deadline_days,
               risks, summary, offers, hire_percent, tags
        FROM projects 
        WHERE category = ? AND is_analyzed = 1
        ORDER BY created_at DESC
    """, (category,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_top_tags(limit: int = 5) -> list:
    """Возвращает топ тегов по количеству заказов"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT tags FROM projects WHERE is_analyzed = 1 AND tags != ''")
    rows = cursor.fetchall()
    conn.close()

    tag_count = {}
    for row in rows:
        try:
            tags = json.loads(row[0])
            for tag in tags:
                tag = tag.strip()
                if tag:
                    tag_count[tag] = tag_count.get(tag, 0) + 1
        except Exception:
            continue

    sorted_tags = sorted(tag_count.items(), key=lambda x: x[1], reverse=True)
    return sorted_tags[:limit]

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
            (id, title, description, link, wanted_budget, max_budget, all_projects, hire_percent, offers)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            project["id"], project["title"], project["description"],
            project["link"], project["wanted_budget"], project["max_budget"],
            project["all_projects"], project["hire_percent"], project["offers"]
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