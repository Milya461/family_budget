import json
import traceback
from urllib.parse import urlparse

from workers import WorkerEntrypoint, Response, fetch

from app.db import configure_d1, execute, fetch_one
from app.budget import (
    add_income,
    check_expense,
    get_monthly_report,
    save_expense,
)
from app.payment_flow import (
    get_current_balance,
    get_moscow_today,
    start_income_event,
    record_actual_income,
    record_actual_payment,
)
from app.payments import (
    get_mandatory_payment,
    get_month_mandatory_payments,
)
from app.allocation import get_monthly_budget_summary
from app.scheduler import daily_income_check
from app.parser import parse_operation


CATEGORIES = [
    "Продукты",
    "Бензин",
    "Питомцы",
    "Дом и быт",
    "Развлечения и кафе",
    "Личные покупки",
    "Здоровье",
    "Подарки и праздники",
    "Непредвиденные",
]


def money(value):
    return f"{float(value or 0):,.0f}".replace(",", " ")


def main_menu():
    return {
        "keyboard": [
            [
                {"text": "💸 Добавить расход"},
                {"text": "💰 Добавить доход"},
            ],
            [
                {"text": "🏦 Обязательные платежи"},
                {"text": "📊 Балансы"},
            ],
            [
                {"text": "📅 Отчёт за месяц"},
                {"text": "🐷 Копилка"},
            ],
            [
                {"text": "⚙️ Настройки"},
                {"text": "↩️ Отменить последнюю операцию"},
            ],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def inline(buttons):
    return {"inline_keyboard": buttons}


def cancel_keyboard():
    return inline([
        [{
            "text": "❌ Отмена",
            "callback_data": "cancel_action",
        }]
    ])


def categories_keyboard():
    buttons = [
        [{
            "text": category,
            "callback_data": f"expense_category:{category}",
        }]
        for category in CATEGORIES
    ]

    buttons.append([{
        "text": "❌ Отмена",
        "callback_data": "cancel_action",
    }])

    return inline(buttons)


def confirm_keyboard():
    return inline([
        [
            {
                "text": "✅ Да, записать",
                "callback_data": "confirm_expense",
            },
            {
                "text": "❌ Нет",
                "callback_data": "cancel_action",
            },
        ]
    ])


async def telegram_call(token, method, payload):
    response = await fetch(
        f"https://api.telegram.org/bot{token}/{method}",
        method="POST",
        headers={"Content-Type": "application/json"},
        body=json.dumps(payload, ensure_ascii=False),
    )
    return await response.json()


class TelegramBot:
    def __init__(self, token):
        self.token = token

    async def send_message(self, chat_id, text, reply_markup=None):
        payload = {"chat_id": chat_id, "text": text}

        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        return await telegram_call(
            self.token,
            "sendMessage",
            payload,
        )

    async def answer_callback(
        self,
        callback_id,
        text=None,
        show_alert=False,
    ):
        payload = {"callback_query_id": callback_id}

        if text:
            payload["text"] = text

        if show_alert:
            payload["show_alert"] = True

        return await telegram_call(
            self.token,
            "answerCallbackQuery",
            payload,
        )

    async def edit_message(
        self,
        chat_id,
        message_id,
        text,
        reply_markup=None,
    ):
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }

        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        return await telegram_call(
            self.token,
            "editMessageText",
            payload,
        )


async def ensure_runtime_tables():
    await execute("""
        CREATE TABLE IF NOT EXISTS bot_state (
            telegram_id INTEGER PRIMARY KEY,
            state TEXT,
            data TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)


async def ensure_user(telegram_id):
    await execute("""
        INSERT OR IGNORE INTO users (telegram_id)
        VALUES (?)
    """, telegram_id)


async def get_state(telegram_id):
    row = await fetch_one("""
        SELECT state, data
        FROM bot_state
        WHERE telegram_id = ?
    """, telegram_id)

    if not row:
        return None, {}

    try:
        data = json.loads(row["data"] or "{}")
    except Exception:
        data = {}

    return row["state"], data


async def set_state(telegram_id, state, data=None):
    await execute("""
        INSERT INTO bot_state (
            telegram_id, state, data, updated_at
        )
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(telegram_id)
        DO UPDATE SET
            state = excluded.state,
            data = excluded.data,
            updated_at = CURRENT_TIMESTAMP
    """,
        telegram_id,
        state,
        json.dumps(data or {}, ensure_ascii=False),
    )


async def clear_state(telegram_id):
    await execute("""
        DELETE FROM bot_state
        WHERE telegram_id = ?
    """, telegram_id)


async def get_pending_income(telegram_id):
    row = await fetch_one("""
        SELECT salary_event_id
        FROM pending_income
        WHERE telegram_id = ?
    """, telegram_id)

    if not row:
        return None

    return row["salary_event_id"]


async def remove_pending_income(telegram_id):
    await execute("""
        DELETE FROM pending_income
        WHERE telegram_id = ?
    """, telegram_id)


async def send_start(bot, chat_id):
    await bot.send_message(
        chat_id,
        "👋 Привет!\n\n"
        "Это семейный бюджет.\n\n"
        "Записывай расходы и дополнительные доходы обычным текстом.\n\n"
        "Также можно пользоваться меню ниже.",
        main_menu(),
    )


async def send_balances(bot, chat_id):
    report = await get_monthly_report()
    budget = await get_monthly_budget_summary()

    lines = [
        "📊 БАЛАНСЫ",
        "",
        "💳 ОСНОВНОЙ СЧЁТ",
        f"Реальные деньги: {money(report['main_account'])} ₽",
        "",
        "🐷 КОПИЛКА",
        f"Накоплено всего: {money(report['savings_balance'])} ₽",
        f"Отложено в этом месяце: {money(report['monthly_savings'])} ₽",
        f"Цель месяца: {money(report['savings_target'])} ₽",
        f"До цели осталось: {money(report['savings_remaining'])} ₽",
        "",
        "🛒 БЮДЖЕТ ЖИЗНИ",
        f"Всего на месяц: {money(budget['life_budget'])} ₽",
        f"Распределено: {money(budget['allocated'])} ₽",
        f"Реально потрачено: {money(budget['spent'])} ₽",
        f"Осталось потратить по бюджету: {money(budget['remaining_to_spend'])} ₽",
        f"Осталось распределить: {money(budget['remaining_to_allocate'])} ₽",
        "",
        "📊 КАТЕГОРИИ",
    ]

    for category in report["categories"]:
        available_to_spend = max(
            category["limit"] - category["spent"],
            0,
        )

        remaining_to_allocate = max(
            category["limit"] - category["allocated"],
            0,
        )

        lines.extend([
            "",
            f"• {category['name']}",
            f"  Лимит на месяц: {money(category['limit'])} ₽",
            f"  Распределено: {money(category['allocated'])} ₽",
            f"  Потрачено: {money(category['spent'])} ₽",
            f"  Осталось потратить по лимиту: {money(available_to_spend)} ₽",
            f"  Осталось распределить: {money(remaining_to_allocate)} ₽",
        ])

    await bot.send_message(
        chat_id,
        "\n".join(lines),
        main_menu(),
    )


async def send_report(bot, chat_id):
    report = await get_monthly_report()

    lines = [
        f"📅 Отчёт за {report['month']}",
        "",
        "💰 ДОХОДЫ",
        f"За месяц: {money(report['month_income'])} ₽",
        "",
        "🏦 ОБЯЗАТЕЛЬНЫЕ ПЛАТЕЖИ",
        f"💳 Кредиты: {money(report['credit_expenses'])} ₽",
        f"🏠 Ипотека: {money(report['mortgage_expenses'])} ₽",
        f"🧾 Коммуналка: {money(report['utilities_expenses'])} ₽",
        "────────────────",
        f"Всего: {money(report['mandatory_expenses'])} ₽",
        "",
        "🛒 РАСХОДЫ НА ЖИЗНЬ",
        f"Бюджет: {money(report['life_budget'])} ₽",
        f"Потрачено: {money(report['life_expenses'])} ₽",
        f"Осталось: {money(report['life_remaining'])} ₽",
        "",
        "📊 ПО КАТЕГОРИЯМ",
    ]

    for category in report["categories"]:
        lines.extend([
            "",
            f"• {category['name']}",
            f"  Лимит на месяц: {money(category['limit'])} ₽",
            f"  Распределено: {money(category['allocated'])} ₽",
            f"  Потрачено: {money(category['spent'])} ₽",
            f"  Осталось потратить по лимиту: {money(category['remaining'])} ₽",
            f"  Осталось распределить: {money(category['remaining_to_allocate'])} ₽",
        ])

    lines.extend([
        "",
        "📦 РАСПРЕДЕЛЕНИЕ",
        f"Распределено по категориям: {money(report['category_allocations'])} ₽",
        f"Осталось распределить: {money(report['life_remaining_to_allocate'])} ₽",
        "",
        "🐷 НАКОПЛЕНИЯ",
        f"Отложено в этом месяце: {money(report['monthly_savings'])} ₽",
        f"Цель месяца: {money(report['savings_target'])} ₽",
        f"До цели осталось: {money(report['savings_remaining'])} ₽",
        f"Всего в копилке: {money(report['savings_balance'])} ₽",
        "",
        "💳 ДЕНЬГИ",
        f"Основной счёт: {money(report['main_account'])} ₽",
    ])

    await bot.send_message(
        chat_id,
        "\n".join(lines),
        main_menu(),
    )


async def send_mandatory(bot, chat_id):
    month = get_moscow_today().strftime("%Y-%m")
    payments = await get_month_mandatory_payments(month)

    if not payments:
        await bot.send_message(
            chat_id,
            "🏦 ОБЯЗАТЕЛЬНЫЕ ПЛАТЕЖИ\n\n"
            "На текущий месяц платежи ещё не созданы.",
            main_menu(),
        )
        return

    lines = ["🏦 ОБЯЗАТЕЛЬНЫЕ ПЛАТЕЖИ", ""]
    current_date = None
    buttons = []

    for payment in payments:
        if payment["event_date"] != current_date:
            current_date = payment["event_date"]
            lines.extend([
                f"📅 {current_date[8:10]}.{current_date[5:7]}",
                "",
            ])

        if payment["status"] == "paid":
            status = (
                f"✅ Оплачено: "
                f"{money(payment['actual_amount'])} ₽"
            )
        else:
            status = "⏳ Не оплачено"

        lines.extend([
            f"• {payment['payment_name']}",
            f"  План: {money(payment['planned_amount'])} ₽",
            f"  {status}",
            "",
        ])

        if payment["status"] != "paid":
            buttons.append([{
                "text": (
                    f"💸 {payment['payment_name']} — "
                    f"{money(payment['planned_amount'])} ₽"
                ),
                "callback_data": f"mandatory_payment:{payment['id']}",
            }])

    buttons.append([{
        "text": "❌ Закрыть",
        "callback_data": "cancel_action",
    }])

    lines.append(
        "Нажми на платёж ниже, чтобы записать фактическую сумму."
    )

    await bot.send_message(
        chat_id,
        "\n".join(lines),
        inline(buttons),
    )


async def process_callback(bot, callback):
    callback_id = callback["id"]
    data = callback.get("data", "")
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    user_id = (callback.get("from") or {}).get("id")

    if user_id is None or chat_id is None:
        return

    await ensure_user(user_id)

    if data == "cancel_action":
        await clear_state(user_id)
        await bot.answer_callback(callback_id, "Отменено")

        if message_id:
            await bot.edit_message(
                chat_id,
                message_id,
                "❌ Действие отменено.",
            )

        await bot.send_message(
            chat_id,
            "Главное меню:",
            main_menu(),
        )
        return

    if data.startswith("expense_category:"):
        category = data.split(":", 1)[1]
        state, state_data = await get_state(user_id)

        if state != "expense_category":
            await bot.answer_callback(
                callback_id,
                "Сессия добавления расхода закончилась.",
                True,
            )
            return

        amount = state_data.get("amount")

        if amount is None:
            await clear_state(user_id)
            await bot.answer_callback(
                callback_id,
                "Сессия добавления расхода закончилась.",
                True,
            )
            return

        await set_state(
            user_id,
            "expense_description",
            {
                "amount": amount,
                "category": category,
            },
        )

        await bot.answer_callback(callback_id)
        await bot.edit_message(
            chat_id,
            message_id,
            f"📂 Категория: {category}\n"
            f"💸 Сумма: {money(amount)} ₽\n\n"
            "Напиши, на что потрачено.\n"
            "Если описание не нужно — напиши «-».",
        )
        return

    if data == "confirm_expense":
        state, state_data = await get_state(user_id)

        if state != "expense_confirm":
            await bot.answer_callback(
                callback_id,
                "Сессия добавления расхода закончилась.",
                True,
            )
            return

        result = await save_expense(
            telegram_id=user_id,
            amount=state_data["amount"],
            category_name=state_data["category"],
            description=state_data.get("description", ""),
        )

        await clear_state(user_id)

        if not result["success"]:
            await bot.answer_callback(callback_id)
            await bot.edit_message(
                chat_id,
                message_id,
                f"❌ {result['error']}",
            )
            await bot.send_message(
                chat_id,
                "Главное меню:",
                main_menu(),
            )
            return

        try:
            balance = await get_current_balance()
        except Exception:
            balance = None

        await bot.answer_callback(
            callback_id,
            "Расход записан!",
        )

        await bot.edit_message(
            chat_id,
            message_id,
            "✅ Расход записан.\n\n"
            f"Сумма: {money(state_data['amount'])} ₽\n"
            f"Категория: {state_data['category']}",
        )

        if balance is None:
            await bot.send_message(
                chat_id,
                "Главное меню:",
                main_menu(),
            )
        else:
            await bot.send_message(
                chat_id,
                f"💳 Основной счёт: {money(balance)} ₽",
                main_menu(),
            )
        return

    if data.startswith("mandatory_payment:"):
        try:
            payment_id = int(data.split(":", 1)[1])
        except (TypeError, ValueError):
            await bot.answer_callback(
                callback_id,
                "Не удалось определить платёж.",
                True,
            )
            return

        payment = await get_mandatory_payment(payment_id)

        if not payment:
            await bot.answer_callback(
                callback_id,
                "Платёж не найден.",
                True,
            )
            return

        if payment["status"] == "paid":
            await bot.answer_callback(
                callback_id,
                "Этот платёж уже записан.",
                True,
            )
            return

        await set_state(
            user_id,
            "payment_amount",
            {
                "payment_id": payment_id,
                "payment_name": payment["payment_name"],
                "planned": payment["planned_amount"],
            },
        )

        await bot.answer_callback(callback_id)
        await bot.edit_message(
            chat_id,
            message_id,
            "🏦 ОБЯЗАТЕЛЬНЫЙ ПЛАТЁЖ\n\n"
            f"Платёж: {payment['payment_name']}\n"
            f"План: {money(payment['planned_amount'])} ₽\n\n"
            "Введи фактическую сумму.",
            cancel_keyboard(),
        )
        return

    await bot.answer_callback(callback_id)


def is_planned_income_message(text):
    """Распознаёт зарплату или аванс, введённые обычным сообщением."""
    import re

    normalized = (text or "").lower().replace("ё", "е")
    return re.search(
        r"(?<!\w)(?:зп|зарплат\w*|аванс\w*)(?!\w)",
        normalized,
    ) is not None


async def process_message(bot, message):
    chat = message.get("chat") or {}
    user = message.get("from") or {}
    chat_id = chat.get("id")
    user_id = user.get("id")
    text = (message.get("text") or "").strip()

    if chat_id is None or user_id is None or not text:
        return

    await ensure_user(user_id)

    if text.startswith("/start"):
        await clear_state(user_id)
        await remove_pending_income(user_id)
        await send_start(bot, chat_id)
        return

    if text == "↩️ Отменить последнюю операцию":
        await clear_state(user_id)
        await remove_pending_income(user_id)
        await bot.send_message(
            chat_id,
            "↩️ Текущая операция отменена.",
            main_menu(),
        )
        return

    state, state_data = await get_state(user_id)
    pending_event_id = await get_pending_income(user_id)

    # Ожидаем фактическую сумму зарплаты или аванса.
    # Пока бот ждёт сумму, не пытаемся распознавать обычные операции.
    if (
        state != "income_amount"
        and pending_event_id is not None
    ):
        try:
            amount = float(
                text.replace(" ", "").replace(",", ".")
            )
        except ValueError:
            amount = None

        if amount is not None and amount > 0:
            result = await record_actual_income(
                event_id=pending_event_id,
                actual_income=amount,
                actual_date=get_moscow_today(),
                telegram_id=user_id,
            )

            await remove_pending_income(user_id)
            await clear_state(user_id)

            if result["success"]:
                try:
                    balance = await get_current_balance()
                except Exception:
                    balance = None

                response_text = (
                    "✅ Доход записан.\n\n"
                    f"Фактически: {money(amount)} ₽"
                )

                if balance is not None:
                    response_text += (
                        f"\nОсновной счёт: {money(balance)} ₽"
                    )

                await bot.send_message(
                    chat_id,
                    response_text,
                    main_menu(),
                )
            else:
                await bot.send_message(
                    chat_id,
                    f"❌ {result['error']}",
                    main_menu(),
                )
            return

    # Обработка пошагового ввода дохода из меню.
    if state == "income_amount":
        try:
            amount = float(
                text.replace(" ", "").replace(",", ".")
            )
        except ValueError:
            amount = 0

        if amount <= 0:
            await bot.send_message(
                chat_id,
                "❌ Введи сумму больше нуля.",
            )
            return

        result = await add_income(
            telegram_id=user_id,
            amount=amount,
            description="Доход",
        )

        await clear_state(user_id)

        if not result["success"]:
            await bot.send_message(
                chat_id,
                f"❌ {result['error']}",
                main_menu(),
            )
            return

        try:
            balance = await get_current_balance()
        except Exception:
            balance = None

        response_text = (
            "✅ Доход записан.\n\n"
            f"Сумма: {money(amount)} ₽"
        )

        if balance is not None:
            response_text += (
                f"\nОсновной счёт: {money(balance)} ₽"
            )

        await bot.send_message(
            chat_id,
            response_text,
            main_menu(),
        )
        return

    # Обработка пошагового ввода расхода из меню.
    if state == "expense_amount":
        try:
            amount = float(
                text.replace(" ", "").replace(",", ".")
            )
        except ValueError:
            amount = 0

        if amount <= 0:
            await bot.send_message(
                chat_id,
                "❌ Введи сумму больше нуля.",
            )
            return

        await set_state(
            user_id,
            "expense_category",
            {"amount": amount},
        )

        await bot.send_message(
            chat_id,
            "📂 Выбери категорию расхода:",
            categories_keyboard(),
        )
        return

    if state == "expense_description":
        description = "" if text == "-" else text

        await set_state(
            user_id,
            "expense_confirm",
            {
                **state_data,
                "description": description,
            },
        )

        check = await check_expense(
            telegram_id=user_id,
            amount=state_data["amount"],
            category_name=state_data["category"],
        )

        warning = ""

        if check.get("exceeded"):
            warning = (
                "\n\n⚠️ Внимание: расход превышает "
                "оставшийся лимит категории."
            )

        await bot.send_message(
            chat_id,
            "🧾 Проверь расход:\n\n"
            f"Сумма: {money(state_data['amount'])} ₽\n"
            f"Категория: {state_data['category']}\n"
            f"Описание: {description or 'без описания'}"
            f"{warning}\n\n"
            "Записать расход?",
            confirm_keyboard(),
        )
        return

    # Обработка фактической суммы обязательного платежа.
    if state == "payment_amount":
        try:
            amount = float(
                text.replace(" ", "").replace(",", ".")
            )
        except ValueError:
            amount = 0

        if amount <= 0:
            await bot.send_message(
                chat_id,
                "❌ Введи сумму больше нуля.",
            )
            return

        result = await record_actual_payment(
            payment_id=state_data["payment_id"],
            actual_amount=amount,
            telegram_id=user_id,
        )

        await clear_state(user_id)

        if not result["success"]:
            await bot.send_message(
                chat_id,
                f"❌ {result['error']}",
                main_menu(),
            )
            return

        try:
            balance = await get_current_balance()
        except Exception:
            balance = None

        response_text = (
            "✅ Платёж записан.\n\n"
            f"Платёж: {state_data['payment_name']}\n"
            f"Фактически: {money(amount)} ₽"
        )

        if balance is not None:
            response_text += (
                f"\n💳 Основной счёт: {money(balance)} ₽"
            )

        await bot.send_message(
            chat_id,
            response_text,
            main_menu(),
        )
        return

    # Команды меню.
    if text == "💰 Добавить доход":
        await set_state(user_id, "income_amount")
        await bot.send_message(
            chat_id,
            "💰 Введи сумму дохода.\n\nНапример: 50000",
            cancel_keyboard(),
        )
        return

    if text == "💸 Добавить расход":
        await set_state(user_id, "expense_amount")
        await bot.send_message(
            chat_id,
            "💸 Сначала введи сумму расхода.\n\nНапример: 1250",
            cancel_keyboard(),
        )
        return

    if text == "🏦 Обязательные платежи":
        await clear_state(user_id)
        await send_mandatory(bot, chat_id)
        return

    if text in ("📊 Балансы", "остаток", "баланс", "балансы"):
        await clear_state(user_id)
        await send_balances(bot, chat_id)
        return

    if text in (
        "📅 Отчёт за месяц",
        "отчёт",
        "отчет",
        "отчёт за месяц",
        "отчет за месяц",
    ):
        await clear_state(user_id)
        await send_report(bot, chat_id)
        return

    if text == "🐷 Копилка":
        report = await get_monthly_report()

        await bot.send_message(
            chat_id,
            "🐷 КОПИЛКА\n\n"
            f"Накоплено всего: {money(report['savings_balance'])} ₽\n"
            f"Отложено в этом месяце: {money(report['monthly_savings'])} ₽\n"
            f"Цель месяца: {money(report['savings_target'])} ₽\n"
            f"До цели осталось: {money(report['savings_remaining'])} ₽",
            main_menu(),
        )
        return

    if text == "⚙️ Настройки":
        await bot.send_message(
            chat_id,
            "⚙️ Настройки\n\n"
            "Основные параметры бюджета задаются в базе данных.",
            main_menu(),
        )
        return

    # Зарплата/аванс, введённые обычным текстом.
    # Дата поступления определяет план обязательных платежей.
    if is_planned_income_message(text):
        from app.parser import extract_amount

        amount = extract_amount(text)
        if amount is None or amount <= 0:
            await bot.send_message(
                chat_id,
                "Не удалось определить сумму дохода. Пример: 50000 зп",
                main_menu(),
            )
            return

        today = get_moscow_today()
        planned_day = 30 if today.day == 31 else today.day

        if planned_day not in (10, 15, 25, 30):
            await bot.send_message(
                chat_id,
                "Зарплату или аванс нужно записывать в день поступления: "
                "10, 15, 25 или 30/31 числа. "
                "Дополнительные доходы, например «2000 кэшбэк», "
                "можно записывать в любой день.",
                main_menu(),
            )
            return

        event = await start_income_event(
            event_date=today,
            planned_day=planned_day,
        )

        result = await record_actual_income(
            event_id=event["event_id"],
            actual_income=amount,
            actual_date=today,
            telegram_id=user_id,
        )

        if not result["success"]:
            await bot.send_message(
                chat_id,
                f"❌ {result['error']}",
                main_menu(),
            )
            return

        try:
            balance = await get_current_balance()
        except Exception:
            balance = None

        response_lines = [
            "✅ Доход записан.",
            "",
            f"💰 Сумма: {money(amount)} ₽",
            f"📅 Плановый день: {planned_day}-е число",
        ]

        planned_payments = event.get("payments") or []
        if planned_payments:
            response_lines.extend([
                "",
                "🏦 Обязательные платежи по этому дню:",
            ])
            for payment in planned_payments:
                response_lines.append(
                    f"• {payment['name']} — "
                    f"{money(payment['planned_amount'])} ₽"
                )
            response_lines.extend([
                "",
                "Платежи пока не отмечены оплаченными. "
                "Чтобы внести фактически оплаченную сумму, открой "
                "«🏦 Обязательные платежи».",
            ])
        else:
            response_lines.extend([
                "",
                "На этот день обязательных платежей по плану нет.",
            ])

        if balance is not None:
            response_lines.extend([
                "",
                f"💳 Основной счёт: {money(balance)} ₽",
            ])

        await bot.send_message(
            chat_id,
            "\n".join(response_lines),
            main_menu(),
        )
        return

    # Распознавание операций, введённых обычным текстом.
    # Не перехватываем сообщения, пока пользователь проходит
    # пошаговый сценарий из меню.
    operation = parse_operation(text)

    if operation and operation["type"] == "expense":
        result = await save_expense(
            telegram_id=user_id,
            amount=operation["amount"],
            category_name=operation["category"],
            description=operation["description"],
        )

        if not result["success"]:
            await bot.send_message(
                chat_id,
                f"❌ {result['error']}",
                main_menu(),
            )
            return

        try:
            balance = await get_current_balance()
        except Exception:
            balance = None

        response_text = (
            "✅ Расход записан!\n\n"
            f"💸 Сумма: {money(operation['amount'])} ₽\n"
            f"📂 Категория: {operation['category']}\n"
            f"📝 Описание: {operation['description'] or 'без описания'}"
        )

        if balance is not None:
            response_text += (
                f"\n\n💳 Основной счёт: {money(balance)} ₽"
            )

        await bot.send_message(
            chat_id,
            response_text,
            main_menu(),
        )
        return

    if operation and operation["type"] == "income":
        result = await add_income(
            telegram_id=user_id,
            amount=operation["amount"],
            description=operation["description"],
        )

        if not result["success"]:
            await bot.send_message(
                chat_id,
                f"❌ {result['error']}",
                main_menu(),
            )
            return

        try:
            balance = await get_current_balance()
        except Exception:
            balance = None

        response_text = (
            "✅ Дополнительный доход записан!\n\n"
            f"💰 Сумма: {money(operation['amount'])} ₽\n"
            f"📝 Описание: {operation['description']}"
        )

        if balance is not None:
            response_text += (
                f"\n\n💳 Основной счёт: {money(balance)} ₽"
            )

        await bot.send_message(
            chat_id,
            response_text,
            main_menu(),
        )
        return

    if operation and operation["type"] == "payment":
        await bot.send_message(
            chat_id,
            "🏦 Похоже, это обязательный платёж:\n\n"
            f"{operation['debt']} — {money(operation['amount'])} ₽\n\n"
            "Чтобы платёж попал в учёт обязательных платежей, "
            "открой меню «🏦 Обязательные платежи» и выбери "
            "соответствующий платёж. Так мы не создадим "
            "дублирующую запись.",
            main_menu(),
        )
        return

    await bot.send_message(
        chat_id,
        "Не удалось определить операцию.\n\n"
        "Примеры:\n"
        "• продукты 599\n"
        "• бензин 2490\n"
        "• корм котам 1800\n"
        "• кэшбек 250\n"
        "• мама прислала 5000\n\n"
        "Или выбери действие в меню.",
        main_menu(),
    )


async def process_update(bot, update):
    if update.get("callback_query"):
        await process_callback(bot, update["callback_query"])
        return

    if update.get("message"):
        await process_message(bot, update["message"])


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        configure_d1(self.env.DB)
        await ensure_runtime_tables()

        url = urlparse(request.url)
        token = getattr(self.env, "BOT_TOKEN", None)

        if url.path == "/health":
            return Response.json({
                "status": "ok",
                "worker": "familu-budget",
            })

        if not token:
            return Response(
                "BOT_TOKEN secret is not configured.",
                status=500,
            )

        if url.path == "/telegram/webhook":
            expected = getattr(
                self.env,
                "TELEGRAM_WEBHOOK_SECRET",
                None,
            )

            if expected:
                received = request.headers.get(
                    "x-telegram-bot-api-secret-token"
                )

                if received != expected:
                    return Response("Unauthorized", status=401)

            update = await request.json()
            bot = TelegramBot(token)

            try:
                await process_update(bot, update)

            except Exception as error:
                error_details = (
                    f"{type(error).__name__}: {error}"
                )
                trace = traceback.format_exc()

                print(
                    "TELEGRAM_WEBHOOK_ERROR:",
                    error_details,
                    trace,
                )

                message = update.get("message") or {}
                callback = update.get("callback_query") or {}
                callback_message = callback.get("message") or {}

                error_chat = (
                    message.get("chat")
                    or callback_message.get("chat")
                    or {}
                )
                error_chat_id = error_chat.get("id")

                if error_chat_id is not None:
                    try:
                        await bot.send_message(
                            error_chat_id,
                            "⚠️ Ошибка Worker\n\n"
                            f"{error_details}\n\n"
                            "Пока не проверим запись, "
                            "не отправляй эту операцию повторно.",
                            main_menu(),
                        )
                    except Exception as send_error:
                        print(
                            "TELEGRAM_ERROR_NOTIFICATION_FAILED:",
                            repr(send_error),
                            traceback.format_exc(),
                        )

            return Response("ok")

        return Response("Family Budget bot is running.")

    async def scheduled(self, controller, env, ctx):
        configure_d1(env.DB)
        await ensure_runtime_tables()

        token = getattr(env, "BOT_TOKEN", None)

        if not token:
            return

        bot = TelegramBot(token)
        await daily_income_check(bot)
