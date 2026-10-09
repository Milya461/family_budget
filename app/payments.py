from datetime import date, datetime, timedelta, timezone
import calendar

from app.db import (
    execute,
    fetch_all,
    fetch_one,
    fetch_value,
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
    """Возвращает год и месяц со сдвигом на указанное число месяцев."""
    index = year * 12 + month - 1 + shift
    return index // 12, index % 12 + 1


def _scheduled_date(event_date: str, planned_day: int) -> date:
    """
    Определяет плановую дату платежа.

    Использует planned_day, а не только event_date:
    существующее событие может быть создано немного раньше
    плановой даты платежа.
    """
    year, month = map(int, event_date[:7].split("-"))
    last_day = calendar.monthrange(year, month)[1]
    day = min(int(planned_day), last_day)

    return date(year, month, day)


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
    Создаёт план обязательных платежей на месяц.

    Не удаляет существующие события или платежи.
    Повторный вызов не создаёт повторный платёж
    внутри одного события.
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
            WHERE event_date = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            event_date,
        )

        if event:
            event_id = event["id"]
        else:
            event_id = await create_salary_event(
                event_date=event_date,
                planned_income=0,
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
                "payment_name": payment_name,
                "planned_amount": planned_amount,
            })

    return result


async def get_nearest_unpaid_payment(
    payment_name: str,
    current_date: date | None = None,
):
    """
    Находит ближайший подходящий неоплаченный платёж.

    Кредитная карта: плановая дата 10-го числа.
    Ипотека и коммунальные услуги: 25-е число.
    Автокредит:
      - до 10-го числа — платёж на 10-е;
      - с 10-го по 24-е — платёж на 25-е;
      - с 25-го числа — платёж на 10-е следующего месяца.

    Сумма платежа здесь не изменяется.
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

    await ensure_month_mandatory_payments(
        f"{next_year:04d}-{next_month:02d}"
    )

    rows = await fetch_all(
        """
        SELECT
            mandatory_payments.id,
            mandatory_payments.salary_event_id,
            mandatory_payments.payment_name,
            mandatory_payments.planned_amount,
            mandatory_payments.actual_amount,
            mandatory_payments.status,
            mandatory_payments.debt_id,
            salary_events.event_date,
            salary_events.planned_day
        FROM mandatory_payments
        JOIN salary_events
            ON salary_events.id =
               mandatory_payments.salary_event_id
        WHERE mandatory_payments.payment_name = ?
          AND mandatory_payments.status != 'paid'
          AND substr(salary_events.event_date, 1, 7) IN (?, ?)
        ORDER BY salary_events.event_date, mandatory_payments.id
        """,
        payment_name,
        today.strftime("%Y-%m"),
        f"{next_year:04d}-{next_month:02d}",
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

    await execute(
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
    Записывает фактически уплаченный обязательный платёж.

    Статус изменяется только для ещё не оплаченного платежа.
    Если другая обработка уже отметила его оплаченным,
    повторная операция не добавляется.
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
        return {
            "success": False,
            "error": "Обязательный платёж не найден.",
        }

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

    # Сначала пытаемся пометить платёж оплаченным.
    # Запрос обновляет только ещё не оплаченные записи.
    update_result = await execute(
        """
        UPDATE mandatory_payments
        SET actual_amount = ?,
            status = 'paid'
        WHERE id = ?
          AND status != 'paid'
        """,
        actual_amount,
        payment_id,
    )

    changes = getattr(
        getattr(update_result, "meta", None),
        "changes",
        None,
    )

    if changes != 1:
        return {
            "success": False,
            "error": (
                "Не удалось подтвердить запись платежа. "
                "Проверь список обязательных платежей "
                "перед повторной отправкой."
            ),
        }

    operation_date = get_moscow_today().isoformat()

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
        operation_date,
    )

    return {
        "success": True,
        "payment_id": payment["id"],
        "payment_name": payment["payment_name"],
        "planned_amount": payment["planned_amount"],
        "actual_amount": actual_amount,
        "difference": (
            actual_amount - payment["planned_amount"]
        ),
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


async def get_mandatory_payment(payment_id: int):
    row = await fetch_one(
        """
        SELECT
            mandatory_payments.id,
            mandatory_payments.salary_event_id,
            mandatory_payments.payment_name,
            mandatory_payments.planned_amount,
            mandatory_payments.actual_amount,
            mandatory_payments.status,
            salary_events.event_date,
            salary_events.planned_day
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
