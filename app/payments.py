from datetime import date
import calendar

import aiosqlite

from app.db import DB_PATH


PAYMENT_PLANS = {
    10: [
        ("Кредитная карта", 18000),
        ("Кредит на машину", 15000),
    ],
    25: [
        ("Кредит на машину", 15000),
        ("Ипотека", 9000),
        ("Коммунальные услуги", 10000),
    ],
}


async def get_planned_payments(day: int):
    return PAYMENT_PLANS.get(day, [])


async def get_income_plan(day: int):
    if day == 31:
        day = 30

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT name, planned_amount
            FROM income_plans
            WHERE day_of_month = ?
              AND is_active = 1
            ORDER BY id
            """,
            (day,),
        )
        rows = await cursor.fetchall()

    return rows


async def create_salary_event(
    event_date: str,
    planned_income: float,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO salary_events (
                event_date,
                planned_income,
                status
            )
            VALUES (?, ?, 'pending')
            """,
            (event_date, planned_income),
        )

        event_id = cursor.lastrowid

        await db.commit()

    return event_id


async def save_actual_income(
    event_id: int,
    actual_income: float,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE salary_events
            SET actual_income = ?,
                status = 'income_received'
            WHERE id = ?
            """,
            (actual_income, event_id),
        )

        await db.commit()


async def create_mandatory_payment(
    salary_event_id: int,
    payment_name: str,
    planned_amount: float,
):
    debt_id = None

    async with aiosqlite.connect(DB_PATH) as db:
        if payment_name != "Коммунальные услуги":
            cursor = await db.execute(
                """
                SELECT id
                FROM debts
                WHERE name = ?
                """,
                (payment_name,),
            )

            row = await cursor.fetchone()

            if row:
                debt_id = row[0]

        cursor = await db.execute(
            """
            PRAGMA table_info(mandatory_payments)
            """
        )

        columns = await cursor.fetchall()
        column_names = [column[1] for column in columns]

        if "payment_name" not in column_names:
            raise RuntimeError(
                "В таблице mandatory_payments нет поля payment_name. "
                "Сначала нужно обновить базу данных."
            )

        await db.execute(
            """
            INSERT INTO mandatory_payments (
                salary_event_id,
                payment_name,
                debt_id,
                planned_amount,
                status
            )
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (
                salary_event_id,
                payment_name,
                debt_id,
                planned_amount,
            ),
        )

        await db.commit()


async def save_actual_payment(
    payment_id: int,
    actual_amount: float,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                id,
                salary_event_id,
                payment_name,
                debt_id,
                planned_amount,
                actual_amount,
                status
            FROM mandatory_payments
            WHERE id = ?
            """,
            (payment_id,),
        )

        payment = await cursor.fetchone()

        if not payment:
            return None

        if payment[6] == "paid":
            return {
                "success": False,
                "error": "Этот платёж уже был записан.",
            }

        cursor = await db.execute(
            """
            SELECT
                event_date
            FROM salary_events
            WHERE id = ?
            """,
            (payment[1],),
        )

        event = await cursor.fetchone()

        if not event:
            return {
                "success": False,
                "error": "Событие дохода для платежа не найдено.",
            }

        await db.execute(
            """
            UPDATE mandatory_payments
            SET actual_amount = ?,
                status = 'paid'
            WHERE id = ?
            """,
            (
                actual_amount,
                payment_id,
            ),
        )

        cursor = await db.execute(
            """
            SELECT id
            FROM users
            ORDER BY id
            LIMIT 1
            """
        )

        user = await cursor.fetchone()

        if not user:
            return {
                "success": False,
                "error": "Пользователь не найден.",
            }

        await db.execute(
            """
            INSERT INTO operations (
                user_id,
                operation_type,
                amount,
                debt_id,
                description,
                operation_date
            )
            VALUES (?, 'expense', ?, ?, ?, ?)
            """,
            (
                user[0],
                actual_amount,
                payment[3],
                payment[2],
                event[0],
            ),
        )

        await db.commit()

    return {
        "success": True,
        "payment_id": payment[0],
        "payment_name": payment[2],
        "planned_amount": payment[4],
        "actual_amount": actual_amount,
        "difference": actual_amount - payment[4],
        "status": "paid",
    }


async def get_event(event_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                id,
                event_date,
                planned_income,
                actual_income,
                status
            FROM salary_events
            WHERE id = ?
            """,
            (event_id,),
        )

        row = await cursor.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "event_date": row[1],
        "planned_income": row[2],
        "actual_income": row[3],
        "status": row[4],
    }


async def get_event_payments(event_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                id,
                payment_name,
                planned_amount,
                actual_amount,
                status
            FROM mandatory_payments
            WHERE salary_event_id = ?
            ORDER BY id
            """,
            (event_id,),
        )

        rows = await cursor.fetchall()

    return [
        {
            "id": row[0],
            "payment_name": row[1],
            "planned_amount": row[2],
            "actual_amount": row[3],
            "status": row[4],
        }
        for row in rows
    ]


def get_event_day(event_date: date) -> int:
    last_day = calendar.monthrange(
        event_date.year,
        event_date.month,
    )[1]

    if event_date.day == last_day:
        return 30

    return event_date.day
