from datetime import date
from zoneinfo import ZoneInfo

import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db import DB_PATH
from app.payment_flow import (
    find_income_event,
    start_income_event,
)


TIMEZONE = ZoneInfo("Europe/Moscow")

scheduler = AsyncIOScheduler(
    timezone=TIMEZONE
)


async def get_users():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT telegram_id
            FROM users
            ORDER BY id
            """
        )

        rows = await cursor.fetchall()

    return [
        row[0]
        for row in rows
    ]


async def get_today_income_event():
    today = date.today()

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
            WHERE substr(event_date, 1, 7) = ?
              AND planned_day = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                today.strftime("%Y-%m"),
                today.day,
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


async def build_income_message(
    planned_day: int,
):
    message_date = date.today()

    income_event = await find_income_event(
        planned_day=planned_day,
        month=message_date.strftime("%Y-%m"),
    )

    if income_event:
        if income_event["status"] == "income_received":
            return None

        event_id = income_event["id"]
        planned_income = income_event["planned_income"]

        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                """
                SELECT name
                FROM income_plans
                WHERE day_of_month = ?
                  AND is_active = 1
                ORDER BY id
                LIMIT 1
                """,
                (planned_day,),
            )

            row = await cursor.fetchone()

        income_name = (
            row[0]
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
            await bot.send_message(
                telegram_id,
                text,
            )
        except Exception:
            continue


async def daily_income_check(bot):
    today = date.today()

    if today.day in (10, 15, 25, 30):
        await send_income_prompt(
            bot=bot,
            planned_day=today.day,
        )

    last_day = (
        today.replace(
            day=28
        )
        .replace(
            day=calendar_last_day(
                today.year,
                today.month,
            )
        )
    )

    if (
        last_day.day == 31
        and today.day == 31
    ):
        await send_income_prompt(
            bot=bot,
            planned_day=30,
        )


def calendar_last_day(
    year: int,
    month: int,
):
    import calendar

    return calendar.monthrange(
        year,
        month,
    )[1]


def start_scheduler(bot):
    if scheduler.running:
        return

    scheduler.add_job(
        daily_income_check,
        trigger="cron",
        hour=14,
        minute=0,
        args=[bot],
        id="daily_income_check",
        replace_existing=True,
    )

    scheduler.start()
