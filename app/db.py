import aiosqlite
from pathlib import Path


DB_PATH = Path("family_budget.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                monthly_limit REAL NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                planned_amount REAL NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS income_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day_of_month INTEGER NOT NULL,
                name TEXT NOT NULL,
                planned_amount REAL NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                operation_type TEXT NOT NULL,
                amount REAL NOT NULL,
                category_id INTEGER,
                debt_id INTEGER,
                description TEXT,
                operation_date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (category_id) REFERENCES categories(id),
                FOREIGN KEY (debt_id) REFERENCES debts(id)
            );

            CREATE TABLE IF NOT EXISTS savings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                balance REAL NOT NULL DEFAULT 0,
                monthly_target REAL NOT NULL DEFAULT 23000
            );

            CREATE TABLE IF NOT EXISTS monthly_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL,
                category_id INTEGER,
                debt_id INTEGER,
                amount REAL NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (category_id) REFERENCES categories(id),
                FOREIGN KEY (debt_id) REFERENCES debts(id)
            );

            CREATE TABLE IF NOT EXISTS salary_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                planned_income REAL NOT NULL DEFAULT 0,
                actual_income REAL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS mandatory_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                salary_event_id INTEGER NOT NULL,
                debt_id INTEGER,
                planned_amount REAL NOT NULL DEFAULT 0,
                actual_amount REAL,
                status TEXT NOT NULL DEFAULT 'pending',

                FOREIGN KEY (salary_event_id) REFERENCES salary_events(id),
                FOREIGN KEY (debt_id) REFERENCES debts(id)
            );

            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            INSERT OR IGNORE INTO savings (id, balance, monthly_target)
            VALUES (1, 0, 23000);

            INSERT OR IGNORE INTO bot_settings (key, value)
            VALUES ('monthly_life_budget', '60000');

            INSERT OR IGNORE INTO bot_settings (key, value)
            VALUES ('currency', 'RUB');
            """
        )

        await db.commit()
