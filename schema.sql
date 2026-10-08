CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    monthly_limit REAL NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    planned_amount REAL NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS income_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_of_month INTEGER NOT NULL,
    name TEXT NOT NULL,
    planned_amount REAL NOT NULL,
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    balance REAL NOT NULL DEFAULT 0,
    monthly_target REAL NOT NULL DEFAULT 23000
);

CREATE TABLE IF NOT EXISTS monthly_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    category_id INTEGER,
    amount REAL NOT NULL DEFAULT 0,
    savings_amount REAL NOT NULL DEFAULT 0,
    source TEXT,
    allocation_date TEXT,
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS salary_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date TEXT NOT NULL,
    planned_day INTEGER,
    planned_income REAL NOT NULL,
    actual_income REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS mandatory_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    salary_event_id INTEGER NOT NULL,
    payment_name TEXT NOT NULL,
    debt_id INTEGER,
    planned_amount REAL NOT NULL,
    actual_amount REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    FOREIGN KEY (salary_event_id) REFERENCES salary_events(id),
    FOREIGN KEY (debt_id) REFERENCES debts(id)
);

CREATE TABLE IF NOT EXISTS pending_income (
    telegram_id INTEGER PRIMARY KEY,
    salary_event_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (salary_event_id) REFERENCES salary_events(id)
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
VALUES ('monthly_savings_target', '23000');

INSERT OR IGNORE INTO bot_settings (key, value)
VALUES ('currency', 'RUB');
