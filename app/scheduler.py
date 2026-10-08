from datetime import datetime
from zoneinfo import ZoneInfo

from app.db import (
    execute,
    fetch_all,
    fetch_one,
)

from app.payment_flow import (
    find_income_event,
    start_income_event,
)


MOSCOW_TIMEZONE = ZoneInfo("Europe/Moscow")


def get_moscow_today():
    return datetime.now(
        MOSCOW_TIMEZONE
    ).date()


async def get_users():
    rows = await fetch_all(
        """
        SELECT telegram_id
        FROM users
        ORDER BY id
        """
    )

    return [
        row["telegram_id"]
        for row in rows
    ]


async def get_pending_income(
    telegram_id: int,
):
    row = await fetch_one(
        """
        SELECT
            telegram_id,
            salary_event_id
        FROM pending_income
        WHERE telegram_id = ?
        """,
        telegram_id,
    )

    if not row:
        return None

    return {
        "telegram_id": row["telegram_id"],
        "salary_event_id": row["salary_event_id"],
    }


async def save_pending_income(
    telegram_id: int,
    salary_event_id: int,
):
    await execute(
        """
        INSERT INTO pending_income (
            telegram_id,
            salary_event_id
        )
        VALUES (?, ?)
        ON CONFLICT(telegram_id)
        DO UPDATE SET
            salary_event_id =
                excluded.salary_event_id,
            created_at = CURRENT_TIMESTAMP
        """,
        telegram_id,
        salary_event_id,
    )


async def remove_pending_income(
    telegram_id: int,
):
    await execute(
        """
        DELETE FROM pending_income
        WHERE telegram_id = ?
        """,
        telegram_id,
    )


async def build_income_message(
    planned_day: int,
):
    message_date = get_moscow_today()

    income_event = await find_income_event(
        planned_day=planned_day,
        month=message_date.strftime(
            "%Y-%m"
        ),
    )

    if income_event:
        if (
            income_event["status"]
            == "income_received"
        ):
            return None

        event_id = income_event["id"]
        planned_income = income_event[
            "planned_income"
        ]

        row = await fetch_one(
            """
            SELECT name
            FROM income_plans
            WHERE day_of_month = ?
              AND is_active = 1
            ORDER BY id
            LIMIT 1
            """,
            planned_day,
        )

        income_name = (
            row["name"]
            if row
            else "Доход"
        )

        return {
            "event_id": event_id,
            "income_name": income_name,
            "planned_income": planned_income,
        }

    result = await start_income_event(
        event_date=message_date,
        planned_day=planned_day,
    )

    income_name = (
        result["income_plans"][0]["name"]
        if result["income_plans"]
        else "Доход"
    )

    return {
        "event_id": result["event_id"],
        "income_name": income_name,
        "planned_income": result["planned_income"],
    }


async def send_income_prompt(
    bot,
    planned_day: int,
):
    message_data = await build_income_message(
        planned_day
    )

    if not message_data:
        return

    users = await get_users()

    if not users:
        return

    text = (
        f"💰 Сегодня ожидается: "
        f"{message_data['income_name']}\n\n"
        f"План: "
        f"{message_data['planned_income']:,.0f} ₽\n\n"
        "Сколько фактически получили?"
    ).replace(",", " ")

    for telegram_id in users:
        try:
            await save_pending_income(
                telegram_id=telegram_id,
                salary_event_id=message_data[
                    "event_id"
                ],
            )

            await bot.send_message(
                telegram_id,
                text,
            )
        except Exception:
            continue


async def daily_income_check(bot):
    today = get_moscow_today()

    if today.day in (10, 15, 25, 30):
        await send_income_prompt(
            bot=bot,
            planned_day=today.day,
        )

    last_day = (
        __import__("calendar")
        .monthrange(
            today.year,
            today.month,
        )[1]
    )

    if (
        today.day == last_day
        and today.day == 31
    ):
        await send_income_prompt(
            bot=bot,
            planned_day=30,
        )
