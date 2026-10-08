from datetime import date

import aiosqlite

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.budget import (
    add_income,
    check_expense,
    save_expense,
)
from app.db import DB_PATH
from app.keyboards import (
    confirm_expense_keyboard,
    main_menu,
)
from app.parser import (
    detect_category,
    detect_income,
    extract_amount,
)
from app.payment_flow import (
    get_current_balance,
    record_actual_income,
    record_actual_payment,
    start_income_event,
)
from app.payments import (
    get_event,
    get_event_payments,
    get_income_plan,
    get_planned_payments,
)


router = Router()

pending_expenses = {}
pending_income_events = {}


PAYMENT_KEYWORDS = {
    "Кредитная карта": [
        "кредитка",
        "кредитная карта",
    ],
    "Кредит на машину": [
        "кредит на машину",
        "автокредит",
        "машина кредит",
    ],
    "Ипотека": [
        "ипотека",
    ],
    "Коммунальные услуги": [
        "коммунальные",
        "коммуналка",
        "коммунальные услуги",
        "жкх",
    ],
}


def detect_payment(text: str):
    normalized = text.lower()

    for payment_name, keywords in PAYMENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in normalized:
                return payment_name

    return None


async def find_pending_payment(payment_name: str):
    today = date.today().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                mp.id,
                mp.salary_event_id,
                mp.payment_name,
                mp.planned_amount,
                mp.actual_amount,
                mp.status
            FROM mandatory_payments mp
            JOIN salary_events se
              ON se.id = mp.salary_event_id
            WHERE mp.payment_name = ?
              AND se.event_date = ?
              AND mp.status = 'pending'
            ORDER BY mp.id DESC
            LIMIT 1
            """,
            (
                payment_name,
                today,
            ),
        )

        row = await cursor.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "salary_event_id": row[1],
        "payment_name": row[2],
        "planned_amount": row[3],
        "actual_amount": row[4],
        "status": row[5],
    }


async def create_today_payment_if_needed(payment_name: str):
    today = date.today()

    planned_payments = await get_planned_payments(
        today.day
    )

    planned_amount = None

    for name, amount in planned_payments:
        if name == payment_name:
            planned_amount = amount
            break

    if planned_amount is None:
        return None

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id
            FROM salary_events
            WHERE event_date = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (today.isoformat(),),
        )

        event = await cursor.fetchone()

    if not event:
        result = await start_income_event(today)

        event_id = result["event_id"]
    else:
        event_id = event[0]

    payment = await find_pending_payment(
        payment_name
    )

    if payment:
        return payment

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id
            FROM debts
            WHERE name = ?
            """,
            (payment_name,),
        )

        debt = await cursor.fetchone()

        debt_id = debt[0] if debt else None

        cursor = await db.execute(
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
            (
                event_id,
                payment_name,
                debt_id,
                planned_amount,
            ),
        )

        payment_id = cursor.lastrowid

        await db.commit()

    return {
        "id": payment_id,
        "salary_event_id": event_id,
        "payment_name": payment_name,
        "planned_amount": planned_amount,
        "actual_amount": None,
        "status": "pending",
    }


async def get_or_create_today_income_event():
    today = date.today()

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                id,
                event_date,
                planned_income,
                actual_income,
                status
            FROM salary_events
            WHERE event_date = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (today.isoformat(),),
        )

        row = await cursor.fetchone()

    if row:
        return {
            "id": row[0],
            "event_date": row[1],
            "planned_income": row[2],
            "actual_income": row[3],
            "status": row[4],
        }

    result = await start_income_event(today)

    return await get_event(
        result["event_id"]
    )


async def send_income_question(message: Message):
    event = await get_or_create_today_income_event()

    if not event:
        return

    if event["status"] == "income_received":
        return

    pending_income_events[
        message.from_user.id
    ] = event["id"]

    income_plan = await get_income_plan(
        date.today().day
    )

    if not income_plan:
        return

    income_name = income_plan[0][0]

    await message.answer(
        (
            f"💰 Сегодня ожидается: {income_name}\n\n"
            f"План: {event['planned_income']:,.0f} ₽\n\n"
            "Сколько фактически получили?"
        ).replace(",", " ")
    )


@router.message(CommandStart())
async def start_handler(message: Message):
    telegram_id = message.from_user.id
    name = message.from_user.first_name or "Пользователь"

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (
                telegram_id,
                name
            )
            VALUES (?, ?)
            ON CONFLICT(telegram_id)
            DO UPDATE SET name = excluded.name
            """,
            (
                telegram_id,
                name,
            ),
        )

        await db.commit()

    await message.answer(
        f"Привет, {name}! 👋\n\n"
        "Это ваш семейный бюджет.\n\n"
        "Можно писать операции обычным текстом.\n\n"
        "Например:\n"
        "• продукты 599\n"
        "• бензин 2490\n"
        "• корм котам 1200\n"
        "• родители прислали 5000",
        reply_markup=main_menu(),
    )


@router.message(
    lambda message: message.text == "💸 Добавить расход"
)
async def add_expense_button(message: Message):
    await message.answer(
        "Напиши расход обычным текстом.\n\n"
        "Например:\n"
        "• продукты 599\n"
        "• бензин 2490\n"
        "• корм котам 1200\n"
        "• аптека 850"
    )


@router.message(
    lambda message: message.text == "💰 Добавить доход"
)
async def add_income_button(message: Message):
    await message.answer(
        "Напиши доход обычным текстом.\n\n"
        "Например:\n"
        "• зарплата 50000\n"
        "• родители прислали 5000\n"
        "• кэшбек 300"
    )


@router.message(
    lambda message: message.text == "🏦 Обязательные платежи"
)
async def mandatory_payments_button(message: Message):
    payments_10 = await get_planned_payments(10)
    payments_25 = await get_planned_payments(25)

    lines = [
        "🏦 Обязательные платежи",
        "",
        "📅 10 числа:",
    ]

    for name, amount in payments_10:
        lines.append(
            f"• {name} — {amount:,.0f} ₽".replace(",", " ")
        )

    lines.extend(
        [
            "",
            "📅 25 числа:",
        ]
    )

    for name, amount in payments_25:
        lines.append(
            f"• {name} — {amount:,.0f} ₽".replace(",", " ")
        )

    lines.extend(
        [
            "",
            "Чтобы записать фактический платёж, "
            "напиши его названием и суммой.",
            "",
            "Например:",
            "• ипотека 8937",
            "• кредитка 17642",
            "• кредит на машине 14983",
            "• коммунальные услуги 9780",
        ]
    )

    await message.answer(
        "\n".join(lines)
    )


@router.message(
    lambda message: message.text == "📊 Балансы"
)
async def balances_button(message: Message):
    balance = await get_current_balance()

    await message.answer(
        "📊 Балансы\n\n"
        f"💳 Основной счёт: {balance:,.0f} ₽".replace(
            ",",
            " ",
        )
    )


@router.message(
    lambda message: message.text == "📅 Отчёт за месяц"
)
async def monthly_report_button(message: Message):
    await message.answer(
        "📅 Отчёт за месяц\n\n"
        "Раздел отчётов пока находится в разработке."
    )


@router.message(
    lambda message: message.text == "🐷 Копилка"
)
async def savings_button(message: Message):
    await message.answer(
        "🐷 Копилка\n\n"
        "Цель накоплений: 23 000 ₽ в месяц.\n"
        "Подробный баланс копилки добавим следующим этапом."
    )


@router.message(
    lambda message: message.text == "⚙️ Настройки"
)
async def settings_button(message: Message):
    await message.answer(
        "⚙️ Настройки\n\n"
        "Раздел настроек пока находится в разработке."
    )


@router.message(
    lambda message: (
        message.text
        == "↩️ Отменить последнюю операцию"
    )
)
async def undo_button(message: Message):
    await message.answer(
        "↩️ Отмена последней операции пока находится "
        "в разработке."
    )


@router.message()
async def operation_handler(message: Message):
    text = message.text.strip()

    amount = extract_amount(text)

    if amount is None or amount <= 0:
        await message.answer(
            "Не смог найти сумму.\n\n"
            "Напиши, например:\n"
            "продукты 599"
        )
        return

    telegram_id = message.from_user.id

    pending_event_id = pending_income_events.get(
        telegram_id
    )

    if pending_event_id:
        result = await record_actual_income(
            event_id=pending_event_id,
            actual_income=amount,
        )

        if not result["success"]:
            await message.answer(
                result["error"]
            )
            return

        pending_income_events.pop(
            telegram_id,
            None,
        )

        event = await get_event(
            pending_event_id
        )

        payments = await get_event_payments(
            pending_event_id
        )

        pending_payments = [
            payment
            for payment in payments
            if payment["status"] != "paid"
        ]

        if pending_payments:
            lines = [
                "💰 Доход записан!",
                "",
                f"Фактически: {amount:,.0f} ₽",
                f"План: {result['planned_income']:,.0f} ₽",
                "",
                "Теперь нужно записать обязательные платежи:",
            ]

            for payment in pending_payments:
                lines.append(
                    f"• {payment['payment_name']} — "
                    f"напиши фактическую сумму"
                )

            await message.answer(
                "\n".join(lines).replace(",", " "),
                reply_markup=main_menu(),
            )
            return

        allocation = result.get(
            "allocation"
        )

        if allocation:
            await message.answer(
                (
                    "💰 Доход записан!\n\n"
                    f"Фактически: {amount:,.0f} ₽\n"
                    f"План: {result['planned_income']:,.0f} ₽\n\n"
                    "📊 Остаток распределён по бюджету."
                ).replace(",", " "),
                reply_markup=main_menu(),
            )
        else:
            await message.answer(
                "💰 Доход записан!",
                reply_markup=main_menu(),
            )

        return

    payment_name = detect_payment(text)

    if payment_name:
        payment = await create_today_payment_if_needed(
            payment_name
        )

        if not payment:
            await message.answer(
                f"Платёж «{payment_name}» "
                "не запланирован на сегодня."
            )
            return

        result = await record_actual_payment(
            payment_id=payment["id"],
            actual_amount=amount,
        )

        if not result["success"]:
            await message.answer(
                result["error"]
            )
            return

        difference = (
            amount - payment["planned_amount"]
        )

        if difference > 0:
            difference_text = (
                f"На {difference:,.0f} ₽ больше плана."
            )
        elif difference < 0:
            difference_text = (
                f"На {abs(difference):,.0f} ₽ меньше плана."
            )
        else:
            difference_text = "Точно по плану."

        await message.answer(
            (
                f"🏦 Платёж записан.\n\n"
                f"Платёж: {payment_name}\n"
                f"Фактически: {amount:,.0f} ₽\n"
                f"План: {payment['planned_amount']:,.0f} ₽\n"
                f"{difference_text}"
            ).replace(",", " "),
            reply_markup=main_menu(),
        )
        return

    if detect_income(text):
        result = await add_income(
            telegram_id=telegram_id,
            amount=amount,
            description=text,
        )

        if not result["success"]:
            await message.answer(
                result["error"]
            )
            return

        await message.answer(
            f"💰 Доход записан: +{amount:,.0f} ₽".replace(
                ",",
                " ",
            ),
            reply_markup=main_menu(),
        )
        return

    category = detect_category(text)

    if not category:
        await message.answer(
            "Не смог определить категорию расхода.\n\n"
            "Попробуй написать подробнее, например:\n"
            "• продукты 599\n"
            "• бензин 2490\n"
            "• корм котам 1200\n"
            "• аптека 850"
        )
        return

    result = await check_expense(
        telegram_id=telegram_id,
        amount=amount,
        category_name=category,
    )

    if not result["success"]:
        await message.answer(
            result["error"]
        )
        return

    if result["exceeded"]:
        pending_expenses[telegram_id] = {
            "amount": amount,
            "category": category,
            "description": text,
        }

        await message.answer(
            (
                f"⚠️ Расход превысит лимит.\n\n"
                f"Категория: {category}\n"
                f"Сумма: {amount:,.0f} ₽\n"
                f"Лимит: {result['limit']:,.0f} ₽\n"
                f"Уже потрачено: {result['spent']:,.0f} ₽\n"
                f"После покупки будет превышение на "
                f"{abs(result['remaining']):,.0f} ₽.\n\n"
                "Записать расход всё равно?"
            ).replace(",", " "),
            reply_markup=confirm_expense_keyboard(),
        )
        return

    saved = await save_expense(
        telegram_id=telegram_id,
        amount=amount,
        category_name=category,
        description=text,
    )

    if not saved["success"]:
        await message.answer(
            saved["error"]
        )
        return

    await message.answer(
        (
            f"✅ Расход записан.\n\n"
            f"Категория: {saved['category']}\n"
            f"Сумма: {amount:,.0f} ₽\n"
            f"Потрачено за месяц: {saved['spent']:,.0f} ₽\n"
            f"Остаток категории: {saved['remaining']:,.0f} ₽"
        ).replace(",", " "),
        reply_markup=main_menu(),
    )


@router.callback_query(
    lambda callback: (
        callback.data == "confirm_expense"
    )
)
async def confirm_expense(
    callback: CallbackQuery
):
    telegram_id = callback.from_user.id

    expense = pending_expenses.pop(
        telegram_id,
        None,
    )

    if not expense:
        await callback.answer(
            "Операция уже обработана.",
            show_alert=True,
        )
        return

    result = await save_expense(
        telegram_id=telegram_id,
        amount=expense["amount"],
        category_name=expense["category"],
        description=expense["description"],
    )

    if not result["success"]:
        await callback.answer(
            "Не удалось записать расход.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        (
            f"✅ Расход записан с превышением.\n\n"
            f"Категория: {result['category']}\n"
            f"Сумма: {result['amount']:,.0f} ₽\n"
            f"Превышение: "
            f"{abs(result['remaining']):,.0f} ₽"
        ).replace(",", " ")
    )

    await callback.answer()


@router.callback_query(
    lambda callback: (
        callback.data == "cancel_expense"
    )
)
async def cancel_expense(
    callback: CallbackQuery
):
    pending_expenses.pop(
        callback.from_user.id,
        None,
    )

    await callback.message.edit_text(
        "❌ Расход не записан."
    )

    await callback.answer()
