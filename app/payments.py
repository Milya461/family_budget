from datetime import date, datetime, timedelta, timezone
import calendar

from app.db import (
    execute,
    execute_many,
    fetch_all,
    fetch_one,
    fetch_value,
    to_python,
)


MOSCOW_TIMEZONE = timezone(timedelta(hours=3))


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


def get_moscow_today() -> date:
    return datetime.now(MOSCOW_TIMEZONE).date()


def _month_shift(year: int, month: int, shift: int):
    index = year * 12 + month - 1 + shift
    return index // 12, index % 12 + 1


def _scheduled_date(event_date: str, planned_day: int) -> date:
    year, month = map(int, event_date[:7].split("-"))
    last_day = calendar.monthrange(year, month)[1]
    day = min(int(planned_day or int(event_date[8:10])), last_day)
    return date(year, month, day)


async def get_planned_payments(day: int):
    return PAYMENT_PLANS.get(day, [])


async def get_income_plan(day: int):
    if day == 31:
        day = 30

    rows = await fetch_all(
        """
        SELECT name, planned_amount
        FROM income_plans
        WHERE day_of_month = ?
          AND is_active = 1
        ORDER BY id
        """,
        day,
    )

    return [
        (row["name"], row["planned_amount"])
        for row in rows
    ]


async def create_salary_event(
    event_date: str,
    planned_income: float = 0,
):
    result = await execute(
        """
        INSERT INTO salary_events (
            event_date,
            planned_day,
            planned_income,
            status
        )
        VALUES (?, ?, ?, 'pending')
        """,
        event_date,
        int(event_date[8:10]),
        planned_income,
    )

    return result.meta.last_row_id


async def create_mandatory_payment(
    salary_event_id: int,
    payment_name: str,
    planned_amount: float,
):
    existing = await fetch_one(
        """
        SELECT id
        FROM mandatory_payments
        WHERE salary_event_id = ?
          AND payment_name = ?
        LIMIT 1
        """,
        salary_event_id,
        payment_name,
    )

    if existing:
        return existing["id"]

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

    if debt_id is None:
        result = await execute(
            """
            INSERT INTO mandatory_payments (
                salary_event_id,
                payment_name,
                planned_amount,
                status
            )
            VALUES (?, ?, ?, 'pending')
            """,
            salary_event_id,
            payment_name,
            planned_amount,
        )
    else:
        result = await execute(
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

    return result.meta.last_row_id


async def ensure_month_mandatory_payments(month: str):
    """
    Создаёт недостающие обязательные платежи.

    Сначала ищет событие соответствующего месяца по planned_day.
    Это позволяет повторно использовать существующее событие,
    даже если его event_date отличается от плановой даты.

    Существующие события и платежи не удаляются.
    """
    year, month_number = map(int, month.split("-"))
    last_day = calendar.monthrange(year, month_number)[1]
    result = []

    for day in (10, 25):
        actual_day = min(day, last_day)
        event_date = date(
            year,
            month_number,
            actual_day,
        ).isoformat()

        event = await fetch_one(
            """
            SELECT id
            FROM salary_events
            WHERE substr(event_date, 1, 7) = ?
              AND planned_day = ?
            ORDER BY
                CASE WHEN event_date = ? THEN 0 ELSE 1 END,
                id DESC
            LIMIT 1
            """,
            month,
            day,
            event_date,
        )

        if event:
            event_id = event["id"]
        else:
            event = await fetch_one(
                """
                SELECT id, planned_day
                FROM salary_events
                WHERE event_date = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                event_date,
            )

            if event:
                event_id = event["id"]

                if event["planned_day"] != day:
                    await execute(
                        """
                        UPDATE salary_events
                        SET planned_day = ?
                        WHERE id = ?
                        """,
                        day,
                        event_id,
                    )
            else:
                event_id = await create_salary_event(
                    event_date=event_date,
                    planned_income=0,
                )

                await execute(
                    """
                    UPDATE salary_events
                    SET planned_day = ?
                    WHERE id = ?
                    """,
                    day,
                    event_id,
                )

        for payment_name, planned_amount in (
            await get_planned_payments(day)
        ):
            payment_id = await create_mandatory_payment(
                salary_event_id=event_id,
                payment_name=payment_name,
                planned_amount=planned_amount,
            )

            result.append({
                "id": payment_id,
                "salary_event_id": event_id,
                "event_date": event_date,
                "planned_day": day,
                "payment_name": payment_name,
                "planned_amount": planned_amount,
            })

    return result


async def get_nearest_unpaid_payment(
    payment_name: str,
    current_date: date | None = None,
):
    """
    Ищет ближайший подходящий неоплаченный платёж.

    Кредитная карта: ближайшее 10-е число.
    Ипотека и коммунальные услуги: ближайшее 25-е число.
    Автокредит:
      до 10-го — платёж на 10-е;
      с 10-го по 24-е — платёж на 25-е;
      с 25-го — платёж на 10-е следующего месяца.
    """
    today = current_date or get_moscow_today()

    await ensure_month_mandatory_payments(
        today.strftime("%Y-%m")
    )

    next_year, next_month = _month_shift(
        today.year,
        today.month,
        1,
    )
    next_month_string = f"{next_year:04d}-{next_month:02d}"

    await ensure_month_mandatory_payments(next_month_string)

    rows = await fetch_all(
        """
        SELECT
            mp.id,
            mp.salary_event_id,
            mp.payment_name,
            mp.planned_amount,
            mp.actual_amount,
            mp.status,
            mp.debt_id,
            se.event_date,
            se.planned_day
        FROM mandatory_payments AS mp
        JOIN salary_events AS se
          ON se.id = mp.salary_event_id
        WHERE mp.payment_name = ?
          AND mp.status != 'paid'
          AND substr(se.event_date, 1, 7) IN (?, ?)
        ORDER BY se.event_date, mp.id
        """,
        payment_name,
        today.strftime("%Y-%m"),
        next_month_string,
    )

    candidates = []

    for row in rows:
        due_date = _scheduled_date(
            row["event_date"],
            row["planned_day"],
        )

        if payment_name == "Кредит на машину":
            if today.day < 10:
                if due_date.day != 10:
                    continue
            elif today.day < 25:
                if due_date.day != 25:
                    continue
            else:
                if due_date <= today or due_date.day != 10:
                    continue

        if due_date < today:
            continue

        candidate = dict(row)
        candidate["due_date"] = due_date.isoformat()
        candidates.append(candidate)

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            item["due_date"],
            item["id"],
        )
    )

    return candidates[0]


async def save_actual_income(
    event_id: int,
    actual_income: float,
    actual_date: date | None = None,
    telegram_id: int | None = None,
):
    event = await fetch_one(
        """
        SELECT event_date, actual_income, status
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

    if telegram_id is None:
        return {
            "success": False,
            "error": "Пользователь не определён.",
        }

    if actual_income <= 0:
        return {
            "success": False,
            "error": "Сумма дохода должна быть больше нуля.",
        }

    operation_date = (
        actual_date.isoformat()
        if actual_date is not None
        else get_moscow_today().isoformat()
    )

    user_id = await fetch_value(
        """
        SELECT id
        FROM users
        WHERE telegram_id = ?
        """,
        telegram_id,
    )

    if user_id is None:
        return {
            "success": False,
            "error": "Пользователь не найден.",
        }

    update_result = await execute(
        """
        UPDATE salary_events
        SET actual_income = ?,
            status = 'income_received',
            completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
          AND status != 'income_received'
        """,
        actual_income,
        event_id,
    )

    changes = getattr(
        getattr(update_result, "meta", None),
        "changes",
        None,
    )

    if changes != 1:
        return {
            "success": False,
            "error": "Не удалось подтвердить запись дохода.",
        }

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
        "Получение дохода",
        operation_date,
    )

    return {
        "success": True,
        "event_id": event_id,
        "actual_income": actual_income,
        "actual_date": operation_date,
    }


async def save_actual_payment(
    payment_id: int,
    actual_amount: float,
    telegram_id: int | None = None,
):
    """
    Подтверждает обязательный платёж и записывает расход.

    Изменение статуса и вставка расхода выполняются
    одним D1 batch. Расход добавляется только в том случае,
    если UPDATE изменил одну строку.
    """
    if actual_amount <= 0:
        return {
            "success": False,
            "error": "Сумма платежа должна быть больше нуля.",
        }

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

    if telegram_id is None:
        return {
            "success": False,
            "error": "Пользователь не определён.",
        }

    user_id = await fetch_value(
        """
        SELECT id
        FROM users
        WHERE telegram_id = ?
        """,
        telegram_id,
    )

    if user_id is None:
        return {
            "success": False,
            "error": "Пользователь не найден.",
        }

    operation_date = get_moscow_today().isoformat()

    update_sql = """
        UPDATE mandatory_payments
        SET actual_amount = ?,
            status = 'paid'
        WHERE id = ?
          AND status != 'paid'
    """

    if payment["debt_id"] is None:
        operation_sql = """
            INSERT INTO operations (
                user_id,
                operation_type,
                amount,
                description,
                operation_date
            )
            SELECT ?, 'expense', ?, ?, ?
            WHERE changes() = 1
        """

        operation_params = (
            user_id,
            actual_amount,
            payment["payment_name"],
            operation_date,
        )
    else:
        operation_sql = """
            INSERT INTO operations (
                user_id,
                operation_type,
                amount,
                debt_id,
                description,
                operation_date
            )
            SELECT ?, 'expense', ?, ?, ?, ?
            WHERE changes() = 1
        """

        operation_params = (
            user_id,
            actual_amount,
            payment["debt_id"],
            payment["payment_name"],
            operation_date,
        )

    batch_result = await execute_many([
        (
            update_sql,
            (actual_amount, payment_id),
        ),
        (
            operation_sql,
            operation_params,
        ),
    ])

    results = to_python(batch_result)

    try:
        update_result = results[0]
        meta = update_result.get("meta", {})
        changes = meta.get("changes")
    except (IndexError, AttributeError, TypeError):
        changes = None

    if changes != 1:
        return {
            "success": False,
            "error": (
                "Не удалось подтвердить запись платежа. "
                "Возможно, он уже оплачен. Проверь список "
                "обязательных платежей перед повторной отправкой."
            ),
        }

    return {
        "success": True,
        "payment_id": payment["id"],
        "payment_name": payment["payment_name"],
        "planned_amount": payment["planned_amount"],
        "actual_amount": actual_amount,
        "difference": actual_amount - payment["planned_amount"],
        "status": "paid",
        "operation_date": operation_date,
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


async def get_month_mandatory_payments(month: str):
    await ensure_month_mandatory_payments(month)

    rows = await fetch_all(
        """
        SELECT
            mp.id,
            mp.salary_event_id,
            mp.payment_name,
            mp.planned_amount,
            mp.actual_amount,
            mp.status,
            se.event_date,
            se.planned_day,
            se.actual_income
        FROM mandatory_payments AS mp
        JOIN salary_events AS se
          ON se.id = mp.salary_event_id
        WHERE substr(se.event_date, 1, 7) = ?
        ORDER BY se.event_date, mp.id
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


async def get_mandatory_payment(payment_id: int):
    row = await fetch_one(
        """
        SELECT
            mp.id,
            mp.salary_event_id,
            mp.payment_name,
            mp.planned_amount,
            mp.actual_amount,
            mp.status,
            se.event_date,
            se.planned_day
        FROM mandatory_payments AS mp
        JOIN salary_events AS se
          ON se.id = mp.salary_event_id
        WHERE mp.id = ?
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
        "planned_day": row["planned_day"],
    }


def get_event_day(event_date: date) -> int:
    last_day = calendar.monthrange(
        event_date.year,
        event_date.month,
    )[1]

    if event_date.day == last_day:
        return 30

    return event_date.day
