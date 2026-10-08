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
    """
    Возвращает план обязательных платежей на указанную дату.
    """
    return PAYMENT_PLANS.get(day, [])


async def get_income_plan(day: int):
    """
    Возвращает плановый доход на указанную дату.
    Для 30/31 используется последний день месяца.
    """
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
    """
    Создаёт событие получения дохода.
    """
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
            (
                event_date,
                planned_income,
            ),
        )

        event_id = cursor.lastrowid

        await db.commit()

    return event_id


async def save_actual_income(
    event_id: int,
    actual_income: float,
):
    """
    Сохраняет фактически полученный доход.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE salary_events
            SET actual_income = ?,
                status = 'income_received'
            WHERE id = ?
            """,
            (
                actual_income,
                event_id,
            ),
        )

        await db.commit()


async def create_mandatory_payment(
    salary_event_id: int,
    payment_name: str,
    planned_amount: float,
):
    """
    Создаёт обязательный платёж.
    """
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
    """
    Сохраняет фактически внесённую сумму обязательного платежа.
    """
    async with aiosqlite.connect(DB_PATH) as db:
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

        await db.commit()


async def get_event(event_id: int):
    """
    Возвращает информацию о событии дохода.
    """
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
    """
    Возвращает обязательные платежи конкретного события.
    """
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
    """
    Возвращает день месяца.
    Для 30/31 учитывается фактический последний день месяца.
    """
    last_day = calendar.monthrange(
        event_date.year,
        event_date.month,
    )[1]

    if event_date.day == last_day:
        return 30

    return event_date.day
