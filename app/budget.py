from datetime import date

import aiosqlite

from app.db import DB_PATH


async def get_category_id(db, category_name):
    cursor = await db.execute(
        """
        SELECT id
        FROM categories
        WHERE name = ?
        """,
        (category_name,),
    )
    row = await cursor.fetchone()
    return row[0] if row else None


async def get_debt_id(db, debt_name):
    cursor = await db.execute(
        """
        SELECT id
        FROM debts
        WHERE name = ?
        """,
        (debt_name,),
    )
    row = await cursor.fetchone()
    return row[0] if row else None


async def get_category_limit(db, category_id):
    cursor = await db.execute(
        """
        SELECT monthly_limit
        FROM categories
        WHERE id = ?
        """,
        (category_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def get_category_spent(db, category_id, month):
    cursor = await db.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM operations
        WHERE category_id = ?
          AND operation_type = 'expense'
          AND substr(operation_date, 1, 7) = ?
        """,
        (category_id, month),
    )
    row = await cursor.fetchone()
    return row[0] or 0


async def add_expense(
    telegram_id: int,
    amount: float,
    category_name: str,
    description: str,
):
    current_month = date.today().strftime("%Y-%m")

    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute(
            """
            SELECT id
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )

        user = await cursor.fetchone()

        if not user:
            return {
                "success": False,
                "error": "Пользователь не найден. Отправьте /start.",
            }

        user_id = user[0]

        category_id = await get_category_id(
            db,
            category_name,
        )

        if not category_id:
            return {
                "success": False,
                "error": "Категория не найдена.",
            }

        limit = await get_category_limit(
            db,
            category_id,
        )

        spent = await get_category_spent(
            db,
            category_id,
            current_month,
        )

        remaining_before = limit - spent
        remaining_after = remaining_before - amount

        await db.execute(
            """
            INSERT INTO operations (
                user_id,
                operation_type,
                amount,
                category_id,
                description,
                operation_date
            )
            VALUES (?, 'expense', ?, ?, ?, ?)
            """,
            (
                user_id,
                amount,
                category_id,
                description,
                date.today().isoformat(),
            ),
        )

        await db.commit()

        return {
            "success": True,
            "category": category_name,
            "amount": amount,
            "limit": limit,
            "spent": spent + amount,
            "remaining": remaining_after,
            "exceeded": remaining_after < 0,
        }


async def add_income(
    telegram_id: int,
    amount: float,
    description: str,
):
    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute(
            """
            SELECT id
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )

        user = await cursor.fetchone()

        if not user:
            return {
                "success": False,
                "error": "Пользователь не найден. Отправьте /start.",
            }

        await db.execute(
            """
            INSERT INTO operations (
                user_id,
                operation_type,
                amount,
                description,
                operation_date
            )
            VALUES (?, 'income', ?, ?, ?)
            """,
            (
                user[0],
                amount,
                description,
                date.today().isoformat(),
            ),
        )

        await db.commit()

        return {
            "success": True,
            "amount": amount,
        }
