from app.db import execute, fetch_value


CATEGORIES = {
    "Продукты": 25000,
    "Бензин": 7000,
    "Питомцы": 6000,
    "Дом и быт": 5000,
    "Развлечения и кафе": 4000,
    "Транспорт": 2500,
    "Красота": 1000,
    "Одежда": 4000,
    "Подписки": 500,
    "Здоровье": 3000,
    "Подарки и праздники": 2000,
}

DEPRECATED_CATEGORIES = ("Личные покупки", "Непредвиденные")
CATEGORY_SETUP_VERSION = "2026-10-category-groups-v1"


async def ensure_categories():
    """Updates category names while keeping historic operations intact."""
    await execute(
        """
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    version = await fetch_value(
        "SELECT value FROM bot_settings WHERE key = ?",
        "category_setup_version",
    )
    if version == CATEGORY_SETUP_VERSION:
        return

    await execute(
        """
        UPDATE categories
        SET is_active = 0
        WHERE name IN (?, ?)
        """,
        *DEPRECATED_CATEGORIES,
    )

    for name, limit in CATEGORIES.items():
        await execute(
            """
            INSERT INTO categories (name, monthly_limit, is_active)
            VALUES (?, ?, 1)
            ON CONFLICT(name) DO UPDATE SET
                monthly_limit = excluded.monthly_limit,
                is_active = 1
            """,
            name,
            limit,
        )

    await execute(
        """
        INSERT INTO bot_settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        "category_setup_version",
        CATEGORY_SETUP_VERSION,
    )



DEBTS = {
    "Кредитная карта": 18000,
    "Кредит на машину": 30000,
    "Ипотека": 9000,
}


INCOME_PLANS = [
    (10, "Зарплата мужа", 50000),
    (15, "Зарплата пользователя", 27500),
    (25, "Аванс мужа", 45000),
    (30, "Аванс пользователя", 27500),
]


async def setup():
    await ensure_categories()

    for name, amount in DEBTS.items():
        await execute(
            """
            INSERT OR IGNORE INTO debts (
                name,
                planned_amount,
                is_active
            )
            VALUES (?, ?, 1)
            """,
            name,
            amount,
        )

    for day, name, amount in INCOME_PLANS:
        await execute(
            """
            INSERT OR IGNORE INTO income_plans (
                day_of_month,
                name,
                planned_amount,
                is_active
            )
            VALUES (?, ?, ?, 1)
            """,
            day,
            name,
            amount,
        )

    await execute(
        """
        INSERT OR IGNORE INTO bot_settings (
            key,
            value
        )
        VALUES (
            'monthly_savings_target',
            '23000'
        )
        """
    )

    await execute(
        """
        INSERT OR IGNORE INTO bot_settings (
            key,
            value
        )
        VALUES (
            'monthly_life_budget',
            '60000'
        )
        """
    )

    await execute(
        """
        INSERT OR IGNORE INTO bot_settings (
            key,
            value
        )
        VALUES (
            'currency',
            'RUB'
        )
        """
    )

    await execute(
        """
        INSERT OR IGNORE INTO savings (
            id,
            balance,
            monthly_target
        )
        VALUES (1, 0, 23000)
        """
    )

    return {
        "success": True,
    }
