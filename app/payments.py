from datetime import date
import calendar

from app.db import (
    execute,
    fetch_all,
    fetch_one,
    fetch_value,
)


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

    rows = await fetch_all(
        """
        SELECT
            name,
            planned_amount
        FROM income_plans
        WHERE day_of_month = ?
          AND is_active = 1
        ORDER BY id
        """,
        day,
    )

    return [
        (
            row["name"],
            row["planned_amount"],
        )
        for row in rows
    ]


async def create_salary_event(
    event_date: str,
    planned_income: float,
):
    result = await execute(
        """
        INSERT INTO salary_events (
            event_date,
            planned_income,
            status
        )
        VALUES (?, ?, 'pending')
        """,
        event_date,
        planned_income,
    )

    return result.meta.last_row_id


async def save_actual_income(
    event_id: int,
    actual_income: float,
    actual_date: date | None = None,
):
    event = await fetch_one(
        """
        SELECT
            event_date,
            actual_income,
            status
        FROM salary_events
        WHERE id = ?
        """,
        event_id,
    )

    if not event:
        return {
            "success": False,
            "error": "Событие дохода не найдено.",
        }

    if event["status"] == "income_received":
        return {
            "success": False,
            "error": "Этот доход уже был записан.",
        }

    if actual_date is None:
        operation_date = event["event_date"]
    else:
        operation_date = actual_date.isoformat()

    user_id = await fetch_value(
        """
        SELECT id
        FROM users
        ORDER BY id
        LIMIT 1
        """
    )

    if user_id is None:
        return {
            "success": False,
            "error": "Пользователь не найден.",
        }

    description = "Получение дохода"

    if actual_date is not None:
        description = (
            "Получение дохода "
            "(фактическая дата)"
        )

    await execute(
        """
        UPDATE salary_events
        SET actual_income = ?,
            status = 'income_received',
            completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        actual_income,
        event_id,
    )

    await execute(
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
        user_id,
        actual_income,
        description,
        operation_date,
    )

    return {
        "success": True,
        "event_id": event_id,
        "actual_income": actual_income,
        "actual_date": operation_date,
    }


async def create_mandatory_payment(
    salary_event_id: int,
    payment_name: str,
    planned_amount: float,
):
    debt_id = None

    if payment_name != "Коммунальные услуги":
        debt_id = await fetch_value(
            """
            SELECT id
            FROM debts
            WHERE name = ?
            """,
            payment_name,
        )

    await execute(
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
        salary_event_id,
        payment_name,
        debt_id,
        planned_amount,
    )


async def save_actual_payment(
    payment_id: int,
    actual_amount: float,
):
    payment = await fetch_one(
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
        payment_id,
    )

    if not payment:
        return None

    if payment["status"] == "paid":
        return {
            "success": False,
            "error": "Этот платёж уже был записан.",
        }

    event = await fetch_one(
        """
        SELECT
            event_date
        FROM salary_events
        WHERE id = ?
        """,
        payment["salary_event_id"],
    )

    if not event:
        return {
            "success": False,
            "error": (
                "Событие дохода для платежа "
                "не найдено."
            ),
        }

    user_id = await fetch_value(
        """
        SELECT id
        FROM users
        ORDER BY id
        LIMIT 1
        """
    )

    if user_id is None:
        return {
            "success": False,
            "error": "Пользователь не найден.",
        }

    await execute(
        """
        UPDATE mandatory_payments
        SET actual_amount = ?,
            status = 'paid'
        WHERE id = ?
        """,
        actual_amount,
        payment_id,
    )

    await execute(
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
        user_id,
        actual_amount,
        payment["debt_id"],
        payment["payment_name"],
        event["event_date"],
    )

    return {
        "success": True,
        "payment_id": payment["id"],
        "payment_name": payment["payment_name"],
        "planned_amount": payment["planned_amount"],
        "actual_amount": actual_amount,
        "difference": (
            actual_amount
            - payment["planned_amount"]
        ),
        "status": "paid",
    }


async def get_event(event_id: int):
    return await fetch_one(
        """
        SELECT
            id,
            event_date,
            planned_day,
            planned_income,
            actual_income,
            status
        FROM salary_events
        WHERE id = ?
        """,
        event_id,
    )


async def get_event_payments(event_id: int):
    rows = await fetch_all(
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
        event_id,
    )

    return [
        {
            "id": row["id"],
            "payment_name": row["payment_name"],
            "planned_amount": row["planned_amount"],
            "actual_amount": row["actual_amount"],
            "status": row["status"],
        }
        for row in rows
    ]


async def get_month_mandatory_payments(
    month: str,
):
    rows = await fetch_all(
        """
        SELECT
            mandatory_payments.id,
            mandatory_payments.salary_event_id,
            mandatory_payments.payment_name,
            mandatory_payments.planned_amount,
            mandatory_payments.actual_amount,
            mandatory_payments.status,
            salary_events.event_date,
            salary_events.planned_day,
            salary_events.actual_income
        FROM mandatory_payments
        JOIN salary_events
            ON salary_events.id =
               mandatory_payments.salary_event_id
        WHERE substr(salary_events.event_date, 1, 7) = ?
        ORDER BY
            salary_events.event_date,
            mandatory_payments.id
        """,
        month,
    )

    return [
        {
            "id": row["id"],
            "salary_event_id": row["salary_event_id"],
            "payment_name": row["payment_name"],
            "planned_amount": row["planned_amount"],
            "actual_amount": row["actual_amount"],
            "status": row["status"],
            "event_date": row["event_date"],
            "planned_day": row["planned_day"],
            "actual_income": row["actual_income"],
        }
        for row in rows
    ]


async def get_mandatory_payment(
    payment_id: int,
):
    row = await fetch_one(
        """
        SELECT
            mandatory_payments.id,
            mandatory_payments.salary_event_id,
            mandatory_payments.payment_name,
            mandatory_payments.planned_amount,
            mandatory_payments.actual_amount,
            mandatory_payments.status,
            salary_events.event_date
        FROM mandatory_payments
        JOIN salary_events
            ON salary_events.id =
               mandatory_payments.salary_event_id
        WHERE mandatory_payments.id = ?
        """,
        payment_id,
    )

    if not row:
        return None

    return {
        "id": row["id"],
        "salary_event_id": row["salary_event_id"],
        "payment_name": row["payment_name"],
        "planned_amount": row["planned_amount"],
        "actual_amount": row["actual_amount"],
        "status": row["status"],
        "event_date": row["event_date"],
    }


def get_event_day(event_date: date) -> int:
    last_day = calendar.monthrange(
        event_date.year,
        event_date.month,
    )[1]

    if event_date.day == last_day:
        return 30

    return event_date.day
