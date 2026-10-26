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
CATEGORY_SETUP_VERSION = "2026-10-category-groups-v2-expense-remap"
SAVINGS_RESET_VERSION = "2026-10-26-reset-savings-on-request"


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

    reset_version = await fetch_value(
        "SELECT value FROM bot_settings WHERE key = ?",
        "savings_reset_version",
    )

    if reset_version != SAVINGS_RESET_VERSION:
        await execute(
            """
            UPDATE savings
            SET balance = 0
            WHERE id = 1
            """
        )

        await execute(
            """
            DELETE FROM monthly_allocations
            WHERE source = 'savings'
              AND month = strftime('%Y-%m', 'now', '+3 hours')
            """
        )

        await execute(
            """
            INSERT INTO bot_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            "savings_reset_version",
            SAVINGS_RESET_VERSION,
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

    # Переносим уже записанные траты в новые категории по их описанию.
    # Исторические операции не удаляются и их суммы не меняются.
    beauty_patterns = (
        "%маникюр%", "%Маникюр%", "%МАНИКЮР%",
    )
    await execute(
        """
        UPDATE operations
        SET category_id = (
            SELECT id FROM categories WHERE name = 'Красота' LIMIT 1
        )
        WHERE operation_type = 'expense'
          AND description IS NOT NULL
          AND (
              description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
          )
        """,
        *beauty_patterns,
    )

    transport_patterns = (
        "%такси%", "%Такси%", "%ТАКСИ%",
        "%транспорт%", "%Транспорт%", "%ТРАНСПОРТ%",
        "%платная дорога%", "%Платная дорога%", "%ПЛАТНАЯ ДОРОГА%",
        "%платные дороги%", "%Платные дороги%", "%ПЛАТНЫЕ ДОРОГИ%",
        "%платной дороге%", "%Платной дороге%", "%ПЛАТНОЙ ДОРОГЕ%",
        "%платная трасса%", "%Платная трасса%", "%ПЛАТНАЯ ТРАССА%",
        "%платные трассы%", "%Платные трассы%", "%ПЛАТНЫЕ ТРАССЫ%",
    )
    await execute(
        """
        UPDATE operations
        SET category_id = (
            SELECT id FROM categories WHERE name = 'Транспорт' LIMIT 1
        )
        WHERE operation_type = 'expense'
          AND description IS NOT NULL
          AND (
              description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
              OR description LIKE ?
          )
        """,
        *transport_patterns,
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
