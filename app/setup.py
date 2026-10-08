from app.db import DB_PATH, init_db
import aiosqlite


CATEGORIES = {
    "Продукты": 25000,
    "Бензин": 7000,
    "Питомцы": 6000,
    "Дом и быт": 5000,
    "Развлечения и кафе": 4000,
    "Личные покупки": 4000,
    "Здоровье": 3000,
    "Подарки и праздники": 2000,
    "Непредвиденные": 4000,
}


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
    await init_db()

    async with aiosqlite.connect(DB_PATH) as db:

        for name, limit in CATEGORIES.items():
            await db.execute(
                """
                INSERT OR IGNORE INTO categories
                (name, monthly_limit)
                VALUES (?, ?)
                """,
                (name, limit),
            )

        for name, amount in DEBTS.items():
            await db.execute(
                """
                INSERT OR IGNORE INTO debts
                (name, planned_amount)
                VALUES (?, ?)
                """,
                (name, amount),
            )

        for day, name, amount in INCOME_PLANS:
            await db.execute(
                """
                INSERT OR IGNORE INTO income_plans
                (day_of_month, name, planned_amount)
                VALUES (?, ?, ?)
                """,
                (day, name, amount),
            )

        await db.execute(
            """
            INSERT OR IGNORE INTO bot_settings (key, value)
            VALUES ('monthly_savings_target', '23000')
            """
        )

        await db.commit()


if __name__ == "__main__":
    import asyncio

    asyncio.run(setup())
