from datetime import datetime, timedelta, timezone

from app.db import execute, fetch_all, fetch_one


MOSCOW_TIMEZONE = timezone(timedelta(hours=3))


def get_moscow_today():
    return datetime.now(MOSCOW_TIMEZONE).date()


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
        if row["telegram_id"] is not None
    ]


async def ensure_reminder_tables():
    await execute(
        """
        CREATE TABLE IF NOT EXISTS daily_expense_checks (
            check_date TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'reminded',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


async def daily_income_check(bot):
    """
    Ежедневно проверяет расходы за текущий день
    по московскому времени и отправляет напоминание,
    если расходов ещё нет.
    """
    await ensure_reminder_tables()

    today_str = get_moscow_today().isoformat()

    expense = await fetch_one(
        """
        SELECT id
        FROM operations
        WHERE operation_type = 'expense'
          AND operation_date = ?
        LIMIT 1
        """,
        today_str,
    )

    if expense:
        return

    # Не отправляем повторное напоминание за этот день,
    # если оно уже было отправлено ранее.
    previous_check = await fetch_one(
        """
        SELECT check_date
        FROM daily_expense_checks
        WHERE check_date = ?
        LIMIT 1
        """,
        today_str,
    )

    if previous_check:
        return

    users = await get_users()

    if not users:
        return

    message = (
        "⏰ Напоминание о расходах\n\n"
        "За сегодня пока не записано ни одного расхода.\n\n"
        "Если были траты — внеси их в бюджет.\n"
        "Если сегодня ничего не покупали — отметь это кнопкой ниже."
    )

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Сегодня без расходов",
                    "callback_data": "daily_expenses:none",
                }
            ],
            [
                {
                    "text": "✍️ Забыла внести расходы",
                    "callback_data": "daily_expenses:forgot",
                }
            ],
        ]
    }

    sent_to_anyone = False

    for telegram_id in users:
        try:
            result = await bot.send_message(
                telegram_id,
                message,
                keyboard,
            )

            if result and result.get("ok", True):
                sent_to_anyone = True

        except Exception as error:
            print(
                "DAILY_EXPENSE_REMINDER_ERROR:",
                telegram_id,
                repr(error),
            )

    if sent_to_anyone:
        await execute(
            """
            INSERT OR IGNORE INTO daily_expense_checks (
                check_date,
                status
            )
            VALUES (?, 'reminded')
            """,
            today_str,
        )
