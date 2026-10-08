from datetime import date

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


async def start_income_event(event_date: date):
    """
    Создаёт событие получения дохода на конкретную дату.

    Возвращает:
    - дату события;
    - плановый доход;
    - список обязательных платежей.
    """

    day = event_date.day

    # Для последнего дня месяца используем план на 30-е.
    import calendar

    last_day = calendar.monthrange(
        event_date.year,
        event_date.month,
    )[1]

    if day == last_day:
        plan_day = 30
    else:
        plan_day = day

    income_plans = await get_income_plan(plan_day)

    planned_income = sum(
        amount
        for _, amount in income_plans
    )

    event_id = await create_salary_event(
        event_date=event_date.isoformat(),
        planned_income=planned_income,
    )

    planned_payments = await get_planned_payments(plan_day)

    for payment_name, planned_amount in planned_payments:
        await create_mandatory_payment(
            salary_event_id=event_id,
            payment_name=payment_name,
            planned_amount=planned_amount,
        )

    return {
        "event_id": event_id,
        "date": event_date.isoformat(),
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


async def record_actual_income(
    event_id: int,
    actual_income: float,
):
    """
    Записывает фактически полученный доход.

    Возвращает сумму, которая реально осталась
    после получения денег.
    """

    if actual_income < 0:
        return {
            "success": False,
            "error": "Сумма дохода не может быть отрицательной.",
        }

    event = await get_event(event_id)

    if not event:
        return {
            "success": False,
            "error": "Событие дохода не найдено.",
        }

    await save_actual_income(
        event_id=event_id,
        actual_income=actual_income,
    )

    return {
        "success": True,
        "event_id": event_id,
        "actual_income": actual_income,
        "planned_income": event["planned_income"],
        "difference": actual_income - event["planned_income"],
    }


async def record_actual_payment(
    payment_id: int,
    actual_amount: float,
):
    """
    Записывает фактически внесённую сумму
    обязательного платежа.
    """

    if actual_amount < 0:
        return {
            "success": False,
            "error": "Сумма платежа не может быть отрицательной.",
        }

    await save_actual_payment(
        payment_id=payment_id,
        actual_amount=actual_amount,
    )

    return {
        "success": True,
        "payment_id": payment_id,
        "actual_amount": actual_amount,
    }


async def get_event_summary(event_id: int):
    """
    Возвращает полную сводку по событию:
    плановый доход,
    фактический доход,
    обязательные платежи,
    фактическая сумма платежей
    и свободный остаток.
    """

    event = await get_event(event_id)

    if not event:
        return None

    payments = await get_event_payments(event_id)

    total_planned_payments = sum(
        payment["planned_amount"]
        for payment in payments
    )

    total_actual_payments = sum(
        payment["actual_amount"] or 0
        for payment in payments
    )

    actual_income = event["actual_income"] or 0

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
        "total_planned_payments": total_planned_payments,
        "total_actual_payments": total_actual_payments,
        "planned_remaining": planned_remaining,
        "remaining": remaining,
    }


async def get_current_balance():
    """
    Возвращает общий фактический баланс
    по всем записанным операциям.
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

        row = await cursor.fetchone()

    return row[0] or 0
