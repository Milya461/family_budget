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
    В 21:00 по Москве проверяет доходы и расходы за текущий день.
    Напоминает отдельно о каждом типе операций, которого не хватает.
    """
    await ensure_reminder_tables()

    today_str = get_moscow_today().isoformat()
    activity = await fetch_one(
        """
        SELECT
            SUM(CASE WHEN operation_type = 'expense' THEN 1 ELSE 0 END)
                AS expense_count,
            SUM(CASE WHEN operation_type = 'income' THEN 1 ELSE 0 END)
                AS income_count
        FROM operations
        WHERE operation_type IN ('income', 'expense')
          AND operation_date = ?
        """,
        today_str,
    )

    expense_count = int((activity or {}).get("expense_count") or 0)
    income_count = int((activity or {}).get("income_count") or 0)

    missing = []
    if expense_count == 0:
        missing.append("расходы")
    if income_count == 0:
        missing.append("доходы")

    print(
        "DAILY_ACTIVITY_CHECK_COUNTS:",
        {
            "date": today_str,
            "expense_count": expense_count,
            "income_count": income_count,
            "missing": missing,
        },
    )

    if not missing:
        print("DAILY_ACTIVITY_REMINDER_SKIPPED: both operation types recorded")
        return

    # Не отправляем повторное напоминание за этот день.
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
        print("DAILY_ACTIVITY_REMINDER_SKIPPED: already handled", today_str)
        return

    users = await get_users()
    if not users:
        print("DAILY_ACTIVITY_REMINDER_SKIPPED: no Telegram users in database")
        return

    missing_text = " и ".join(missing)
    message = (
        "⏰ Напоминание о семейном бюджете\n\n"
        f"За сегодня пока не записаны: {missing_text}.\n\n"
        "Если сегодня были поступления или траты — внеси их в бюджет.\n"
        "Например: «продукты 599» или «зарплата 50000»."
    )

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Сегодня больше нечего записывать",
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
