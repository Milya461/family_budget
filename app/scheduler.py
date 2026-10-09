from datetime import datetime, timedelta, timezone

from app.db import fetch_all, fetch_one


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


async def daily_income_check(bot):
    """
    Старая функция сохранена для совместимости с worker.py.
    Теперь она проверяет только наличие расходов за день.
    Если расходов нет, отправляет напоминание.
    """
    today = get_moscow_today()
    today_str = today.isoformat()

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

    # Если за сегодня есть хотя бы один расход,
    # напоминание не отправляем.
    if expense:
        return

    users = await get_users()

    if not users:
        return

    message = (
        "⏰ Напоминание о расходах\n\n"
        "Сегодня ещё не записано ни одного расхода.\n"
        "Если были траты, внеси их в бюджетный бот.\n\n"
        "Если сегодня ничего не покупали, "
        "можно просто проигнорировать это сообщение."
    )

    for telegram_id in users:
        try:
            await bot.send_message(
                telegram_id,
                message,
            )
        except Exception as error:
            print(
                "DAILY_EXPENSE_REMINDER_ERROR:",
                telegram_id,
                repr(error),
            )
