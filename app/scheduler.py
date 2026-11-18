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


async def daily_activity_check(bot):
    """
    Каждый день в 21:00 по Москве отправляет напоминание всем
    пользователям независимо от наличия доходов и расходов.
    """
    await ensure_reminder_tables()

    today_str = get_moscow_today().isoformat()

    # Не отправляем повторное уведомление за тот же день,
    # если Cloudflare повторно вызовет scheduled event.
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
        print("DAILY_ACTIVITY_REMINDER_SKIPPED: already sent or acknowledged", today_str)
        return

    users = await get_users()
    if not users:
        print("DAILY_ACTIVITY_REMINDER_SKIPPED: no Telegram users in database")
        return

    message = (
        "⏰ Ежедневное напоминание о семейном бюджете\n\n"
        "Проверь, все ли доходы и расходы за сегодня записаны.\n\n"
        "Если что-то забыла внести — добавь запись сейчас. "
        "Если сегодня операций не было или всё уже записано — просто отметь это кнопкой ниже."
    )

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Проверила, всё записано",
                    "callback_data": "daily_expenses:none",
                }
            ],
            [
                {
                    "text": "✍️ Нужно внести операции",
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
            is_ok = bool(result and result.get("ok", False))
            print(
                "DAILY_ACTIVITY_REMINDER_DELIVERY:",
                {"telegram_id": telegram_id, "ok": is_ok, "result": result},
            )
            if is_ok:
                sent_to_anyone = True
        except Exception as error:
            print(
                "DAILY_ACTIVITY_REMINDER_ERROR:",
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
        print("DAILY_ACTIVITY_REMINDER_SENT:", today_str)
    else:
        print("DAILY_ACTIVITY_REMINDER_NOT_SENT: no Telegram delivery succeeded")
