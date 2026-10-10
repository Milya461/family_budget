from datetime import datetime, timedelta, timezone

from app.db import execute, fetch_one


MOSCOW_TIMEZONE = timezone(timedelta(hours=3))


def get_moscow_today():
    return datetime.now(MOSCOW_TIMEZONE).date()


async def ensure_reminder_table():
    await execute(
        """
        CREATE TABLE IF NOT EXISTS daily_expense_checks (
            check_date TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'reminded',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


async def handle_daily_expenses_callback(bot, callback):
    callback_id = callback["id"]
    data = callback.get("data", "")
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")

    if chat_id is None or message_id is None:
        await bot.answer_callback(
            callback_id,
            "Не удалось определить сообщение. Попробуй ещё раз.",
            show_alert=True,
        )
        return

    await ensure_reminder_table()

    today = get_moscow_today().isoformat()

    if data == "daily_expenses:none":
        await execute(
            """
            INSERT INTO daily_expense_checks (
                check_date,
                status,
                updated_at
            )
            VALUES (?, 'no_expenses', CURRENT_TIMESTAMP)
            ON CONFLICT(check_date) DO UPDATE SET
                status = 'no_expenses',
                updated_at = CURRENT_TIMESTAMP
            """,
            today,
        )

        await bot.answer_callback(
            callback_id,
            "Отмечено: сегодня без расходов.",
        )

        await bot.edit_message(
            chat_id,
            message_id,
            "✅ Отмечено: сегодня расходов не было.",
        )
        return

    if data == "daily_expenses:forgot":
        await execute(
            """
            INSERT INTO daily_expense_checks (
                check_date,
                status,
                updated_at
            )
            VALUES (?, 'forgot', CURRENT_TIMESTAMP)
            ON CONFLICT(check_date) DO UPDATE SET
                status = 'forgot',
                updated_at = CURRENT_TIMESTAMP
            """,
            today,
        )

        await bot.answer_callback(
            callback_id,
            "Хорошо, внеси пропущенные расходы.",
        )

        await bot.edit_message(
            chat_id,
            message_id,
            "✍️ Хорошо, внеси пропущенные расходы сообщениями "
            "в обычном формате, например:\n\n"
            "• продукты 599\n"
            "• бензин 2490\n"
            "• корм котам 1800\n\n"
            "Я обработаю их как обычные расходы.",
        )
        return

    await bot.answer_callback(
        callback_id,
        "Неизвестный вариант ответа.",
        show_alert=True,
    )
