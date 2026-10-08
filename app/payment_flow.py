from datetime import date, datetime
import calendar

import aiosqlite

from app.db import DB_PATH
from app.payments import (
    create_salary_event,
    create_mandatory_payment,
    get_event,
    get_event_payments,
    get_income_plan,
    get_planned_payments,
    save_actual_income,
    save_actual_payment,
)


MOSCOW_TIMEZONE = "Europe/Moscow"


def get_moscow_today():
    from zoneinfo import ZoneInfo

    return datetime.now(
        ZoneInfo(MOSCOW_TIMEZONE)
    ).date()


async def start_income_event(
    event_date: date,
    planned_day: int | None = None,
):
    day = event_date.day

    last_day = calendar.monthrange(
        event_date.year,
        event_date.month,
    )[1]

    if planned_day is None:
        if day == last_day:
            planned_day = 30
        else:
            planned_day = day

    income_plans = await get_income_plan(
        planned_day
    )

    planned_income = sum(
        amount
        for _, amount in income_plans
    )

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id
            FROM salary_events
            WHERE event_date = ?
              AND planned_day = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                event_date.isoformat(),
                planned_day,
            ),
        )

        existing = await cursor.fetchone()

    if existing:
        return {
            "event_id": existing[0],
            "date": event_date.isoformat(),
            "planned_day": planned_day,
            "planned_income": planned_income,
            "income_plans": [
                {
                    "name": name,
                    "planned_amount": amount,
                }
                for name, amount in income_plans
            ],
            "payments": [
                {
                    "name": name,
                    "planned_amount": amount,
                }
                for name, amount
                in await get_planned_payments(
                    planned_day
                )
            ],
        }

    event_id = await create_salary_event(
        event_date=event_date.isoformat(),
        planned_income=planned_income,
    )

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE salary_events
            SET planned_day = ?
            WHERE id = ?
            """,
            (
                planned_day,
                event_id,
            ),
        )

        await db.commit()

    planned_payments = await get_planned_payments(
        planned_day
    )

    for payment_name, planned_amount in planned_payments:
        await create_mandatory_payment(
            salary_event_id=event_id,
            payment_name=payment_name,
            planned_amount=planned_amount,
        )

    return {
        "event_id": event_id,
        "date": event_date.isoformat(),
        "planned_day": planned_day,
        "planned_income": planned_income,
        "income_plans": [
            {
                "name": name,
                "planned_amount": amount,
            }
            for name, amount in income_plans
        ],
        "payments": [
            {
                "name": name,
                "planned_amount": amount,
            }
            for name, amount in planned_payments
        ],
    }


async def find_income_event(
    planned_day: int,
    month: str,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                id,
                event_date,
                planned_day,
                planned_income,
                actual_income,
                status
            FROM salary_events
            WHERE planned_day = ?
              AND substr(event_date, 1, 7) = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                planned_day,
                month,
            ),
        )

        row = await cursor.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "event_date": row[1],
        "planned_day": row[2],
        "planned_income": row[3],
        "actual_income": row[4],
        "status": row[5],
    }


async def start_early_income_event(
    actual_date: date,
    planned_day: int,
):
    month = actual_date.strftime("%Y-%m")

    existing = await find_income_event(
        planned_day=planned_day,
        month=month,
    )

    if existing:
        return existing

    result = await start_income_event(
        event_date=actual_date,
        planned_day=planned_day,
    )

    return await get_event(
        result["event_id"]
    )


async def record_actual_income(
    event_id: int,
    actual_income: float,
    actual_date: date | None = None,
):
    if actual_income < 0:
        return {
            "success": False,
            "error": (
                "Сумма дохода не может быть "
                "отрицательной."
            ),
        }

    event = await get_event(event_id)

    if not event:
        return {
            "success": False,
            "error": "Событие дохода не найдено.",
        }

    if actual_date is None:
        actual_date = get_moscow_today()

    result = await save_actual_income(
        event_id=event_id,
        actual_income=actual_income,
        actual_date=actual_date,
    )

    if not result["success"]:
        return result

    payments = await get_event_payments(
        event_id
    )

    pending_payments = [
        payment
        for payment in payments
        if payment["status"] != "paid"
    ]

    allocation = None

    if not pending_payments:
        from app.allocation import (
            allocate_income_remainder
        )

        allocation = await allocate_income_remainder(
            amount=actual_income,
            allocation_date=actual_date,
        )

    return {
        **result,
        "planned_income": event[
            "planned_income"
        ],
        "planned_day": event.get(
            "planned_day"
        ),
        "difference": (
            actual_income
            - event["planned_income"]
        ),
        "allocation": allocation,
    }


async def record_actual_payment(
    payment_id: int,
    actual_amount: float,
):
    if actual_amount < 0:
        return {
            "success": False,
            "error": (
                "Сумма платежа не может быть "
                "отрицательной."
            ),
        }

    saved = await save_actual_payment(
        payment_id=payment_id,
        actual_amount=actual_amount,
    )

    if not saved:
        return {
            "success": False,
            "error": "Обязательный платёж не найден.",
        }

    if not saved["success"]:
        return saved

    event_id = await get_payment_event_id(
        payment_id
    )

    if not event_id:
        return {
            "success": False,
            "error": (
                "Событие дохода для платежа "
                "не найдено."
            ),
        }

    summary = await get_event_summary(
        event_id
    )

    allocation = None

    if (
        summary
        and summary["event"]["actual_income"]
        is not None
        and summary["all_payments_paid"]
    ):
        from app.allocation import (
            allocate_income_remainder
        )

        allocation = await allocate_income_remainder(
            amount=summary["remaining"],
            allocation_date=date.fromisoformat(
                summary["event"]["event_date"]
            ),
        )

    return {
        **saved,
        "event_id": event_id,
        "remaining": (
            summary["remaining"]
            if summary
            else None
        ),
        "allocation": allocation,
    }


async def get_payment_event_id(
    payment_id: int,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT salary_event_id
            FROM mandatory_payments
            WHERE id = ?
            """,
            (payment_id,),
        )

        row = await cursor.fetchone()

    return row[0] if row else None


async def get_event_summary(
    event_id: int,
):
    event = await get_event(event_id)

    if not event:
        return None

    payments = await get_event_payments(
        event_id
    )

    total_planned_payments = sum(
        payment["planned_amount"]
        for payment in payments
    )

    total_actual_payments = sum(
        payment["actual_amount"] or 0
        for payment in payments
    )

    actual_income = (
        event["actual_income"] or 0
    )

    all_payments_paid = all(
        payment["status"] == "paid"
        for payment in payments
    )

    remaining = (
        actual_income
        - total_actual_payments
    )

    planned_remaining = (
        event["planned_income"]
        - total_planned_payments
    )

    return {
        "event": event,
        "payments": payments,
        "total_planned_payments": (
            total_planned_payments
        ),
        "total_actual_payments": (
            total_actual_payments
        ),
        "planned_remaining": (
            planned_remaining
        ),
        "remaining": remaining,
        "all_payments_paid": (
            all_payments_paid
        ),
    }


async def get_current_balance():
    """
    Реальные деньги на основном счёте.

    Формула:

    все доходы
    - все реальные расходы
    - деньги, физически отправленные в копилку.

    Виртуальное распределение по категориям
    здесь НЕ учитывается как расход.
    """

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                COALESCE(
                    SUM(
                        CASE
                            WHEN operation_type = 'income'
                            THEN amount
                            ELSE 0
                        END
                    ),
                    0
                ) -
                COALESCE(
                    SUM(
                        CASE
                            WHEN operation_type = 'expense'
                            THEN amount
                            ELSE 0
                        END
                    ),
                    0
                )
            FROM operations
            """
        )

        operations_row = await cursor.fetchone()

        cursor = await db.execute(
            """
            SELECT balance
            FROM savings
            WHERE id = 1
            """
        )

        savings_row = await cursor.fetchone()

    operations_balance = (
        operations_row[0]
        if operations_row
        else 0
    )

    savings_balance = (
        savings_row[0]
        if savings_row
        else 0
    )

    return (
        operations_balance
        - savings_balance
    )
