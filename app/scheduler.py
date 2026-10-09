
import calendar
from datetime import date, datetime, timedelta, timezone

from app.db import execute, fetch_all, fetch_one
from app.payment_flow import find_income_event, start_income_event


MOSCOW_TIMEZONE = timezone(timedelta(hours=3))

# Первый известный рабочий день в цикле 2/2.
WORK_CYCLE_ANCHOR = date(2026, 10, 3)

# После 27 декабря пользователь не работает.
NON_WORKING_OVERRIDES = {
    date(2026, 12, 28),
    date(2026, 12, 29),
    date(2026, 12, 30),
    date(2026, 12, 31),
}


def get_moscow_today():
    return datetime.now(MOSCOW_TIMEZONE).date()


def is_user_workday(day):
    if day in NON_WORKING_OVERRIDES:
        return False

    offset = (day - WORK_CYCLE_ANCHOR).days
    return offset >= 0 and offset % 4 in (0, 1)


def get_husband_payday(year, month, planned_day):
    """10-е и 25-е; выходной переносим на предыдущий будний день."""
    target = date(year, month, planned_day)

    while target.weekday() >= 5:
        target -= timedelta(days=1)

    return target


def get_user_payday(year, month, planned_day):
    """15-е и последний день месяца по рабочему графику 2/2."""
    last_day = calendar.monthrange(year, month)[1]

    if planned_day == 15:
        target = date(year, month, 15)
    else:
        target = date(year, month, last_day)

    while not is_user_workday(target):
        target -= timedelta(days=1)

    return target


def get_expected_payday(year, month, planned_day):
    if planned_day in (10, 25):
        return get_husband_payday(year, month, planned_day)

    if planned_day in (15, 30):
        return get_user_payday(year, month, planned_day)

    raise ValueError(f"Неизвестная плановая дата: {planned_day}")


async def get_users():
    rows = await fetch_all(
        """
        SELECT telegram_id
        FROM users
        ORDER BY id
        """
    )
    return [row["telegram_id"] for row in rows]


async def save_pending_income(telegram_id, salary_event_id):
    await execute(
        """
        INSERT INTO pending_income (telegram_id, salary_event_id)
        VALUES (?, ?)
        ON CONFLICT(telegram_id)
        DO UPDATE SET
            salary_event_id = excluded.salary_event_id,
            created_at = CURRENT_TIMESTAMP
        """,
        telegram_id,
        salary_event_id,
    )


async def build_income_message(planned_day):
    today = get_moscow_today()
    month = today.strftime("%Y-%m")

    event = await find_income_event(planned_day, month)

    if event and event["status"] == "income_received":
        return None

    # Всегда вызываем start_income_event:
    # он создаст событие, если его нет, или восстановит
    # отсутствующие обязательные платежи у существующего события.
    result = await start_income_event(
        event_date=(
            date.fromisoformat(event["event_date"])
            if event
            else today
        ),
        planned_day=planned_day,
    )

    event_id = result["event_id"]
    planned_income = result["planned_income"] or 0

    row = await fetch_one(
        """
        SELECT name
        FROM income_plans
        WHERE day_of_month = ? AND is_active = 1
        ORDER BY id
        LIMIT 1
        """,
        planned_day,
    )

    default_names = {
        10: "Зарплата мужа",
        15: "Моя зарплата",
        25: "Аванс мужа",
        30: "Моя зарплата",
    }

    return {
        "event_id": event_id,
        "income_name": (
            row["name"]
            if row
            else default_names[planned_day]
        ),
        "planned_income": planned_income,
    }


async def send_income_prompt(bot, planned_day):
    message_data = await build_income_message(planned_day)

    if not message_data:
        return

    users = await get_users()
    if not users:
        return

    text = (
        f"💰 Сегодня ожидается: {message_data['income_name']}\n\n"
    )

    if message_data["planned_income"] > 0:
        text += (
            f"План: {message_data['planned_income']:,.0f} ₽\n\n"
            .replace(",", " ")
        )

    text += "Сколько фактически получили?"

    for telegram_id in users:
        try:
            await save_pending_income(
                telegram_id,
                message_data["event_id"],
            )
            await bot.send_message(telegram_id, text)
        except Exception as error:
            print(
                "INCOME_PROMPT_ERROR:",
                telegram_id,
                planned_day,
                repr(error),
            )


async def daily_income_check(bot):
    today = get_moscow_today()

    for planned_day in (10, 15, 25, 30):
        expected_date = get_expected_payday(
            today.year,
            today.month,
            planned_day,
        )

        if today == expected_date:
            await send_income_prompt(bot, planned_day)
