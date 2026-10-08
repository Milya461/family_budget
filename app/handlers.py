from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.db import execute
from app.budget import (
    add_income,
    check_expense,
    get_monthly_report,
    save_expense,
)
from app.keyboards import (
    categories_keyboard,
    cancel_keyboard,
    confirm_expense_keyboard,
    main_menu,
    mandatory_payments_keyboard,
)
from app.payment_flow import (
    get_current_balance,
    record_actual_payment,
)
from app.allocation import get_monthly_budget_summary
from app.payments import (
    get_mandatory_payment,
    get_month_mandatory_payments,
)


router = Router()


class IncomeStates(StatesGroup):
    waiting_for_amount = State()


class ExpenseStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_description = State()
    waiting_for_confirmation = State()


class MandatoryPaymentStates(StatesGroup):
    waiting_for_amount = State()


async def ensure_user(
    telegram_id: int,
    name: str,
):
    await execute(
        """
        INSERT OR IGNORE INTO users (
            telegram_id
        )
        VALUES (?)
        """,
        telegram_id,
    )


def format_money(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ")


def get_current_month() -> str:
    return datetime.now(
        ZoneInfo("Europe/Moscow")
    ).strftime("%Y-%m")


# =========================================================
# START
# =========================================================

@router.message(CommandStart())
async def start_command(
    message: Message,
    state: FSMContext,
):
    await state.clear()

    user_name = (
        message.from_user.full_name
        if message.from_user
        else "Пользователь"
    )

    await ensure_user(
        telegram_id=message.from_user.id,
        name=user_name,
    )

    await message.answer(
        "👋 Привет!\n\n"
        "Это семейный бюджет.\n\n"
        "Здесь можно записывать доходы и расходы, "
        "следить за обязательными платежами, "
        "бюджетом на жизнь и копилкой.\n\n"
        "Выбери действие в меню ниже.",
        reply_markup=main_menu(),
    )


# =========================================================
# ДОБАВИТЬ ДОХОД
# =========================================================

@router.message(
    lambda message: message.text == "💰 Добавить доход"
)
async def add_income_start(
    message: Message,
    state: FSMContext,
):
    await state.clear()

    await ensure_user(
        telegram_id=message.from_user.id,
        name=message.from_user.full_name,
    )

    await state.set_state(
        IncomeStates.waiting_for_amount
    )

    await message.answer(
        "💰 Введи сумму дохода.\n\n"
        "Например: 50000",
        reply_markup=cancel_keyboard(),
    )


@router.message(
    IncomeStates.waiting_for_amount
)
async def add_income_amount(
    message: Message,
    state: FSMContext,
):
    text = (message.text or "").strip()

    try:
        amount = float(
            text.replace(" ", "")
            .replace(",", ".")
        )
    except ValueError:
        await message.answer(
            "❌ Не смогла распознать сумму.\n\n"
            "Введи только число, например:\n"
            "50000"
        )
        return

    if amount <= 0:
        await message.answer(
            "❌ Сумма должна быть больше нуля.\n\n"
            "Попробуй ещё раз."
        )
        return

    await state.update_data(
        income_amount=amount,
    )

    await state.clear()

    result = await add_income(
        telegram_id=message.from_user.id,
        amount=amount,
        description="Доход",
    )

    if not result["success"]:
        await message.answer(
            f"❌ {result['error']}",
            reply_markup=main_menu(),
        )
        return

    balance = await get_current_balance()

    await message.answer(
        "✅ Доход записан.\n\n"
        f"Сумма: {format_money(amount)} ₽\n"
        f"Основной счёт: {format_money(balance)} ₽",
        reply_markup=main_menu(),
    )


# =========================================================
# ДОБАВИТЬ РАСХОД
# =========================================================

@router.message(
    lambda message: message.text == "💸 Добавить расход"
)
async def add_expense_start(
    message: Message,
    state: FSMContext,
):
    await state.clear()

    await ensure_user(
        telegram_id=message.from_user.id,
        name=message.from_user.full_name,
    )

    await state.set_state(
        ExpenseStates.waiting_for_amount
    )

    await message.answer(
        "💸 Сначала введи сумму расхода.\n\n"
        "Например: 1250",
        reply_markup=cancel_keyboard(),
    )


@router.message(
    ExpenseStates.waiting_for_amount
)
async def add_expense_amount(
    message: Message,
    state: FSMContext,
):
    text = (message.text or "").strip()

    try:
        amount = float(
            text.replace(" ", "")
            .replace(",", ".")
        )
    except ValueError:
        await message.answer(
            "❌ Не смогла распознать сумму.\n\n"
            "Введи только число, например:\n"
            "1250"
        )
        return

    if amount <= 0:
        await message.answer(
            "❌ Сумма должна быть больше нуля.\n\n"
            "Попробуй ещё раз."
        )
        return

    await state.update_data(
        expense_amount=amount,
    )

    await message.answer(
        "📂 Выбери категорию расхода:",
        reply_markup=categories_keyboard(),
    )


# =========================================================
# ВЫБОР КАТЕГОРИИ
# =========================================================

@router.callback_query(
    lambda callback:
        callback.data
        and callback.data.startswith(
            "expense_category:"
        )
)
async def select_expense_category(
    callback: CallbackQuery,
    state: FSMContext,
):
    category = callback.data.split(
        ":",
        1,
    )[1]

    data = await state.get_data()

    amount = data.get(
        "expense_amount"
    )

    if amount is None:
        await callback.answer(
            "Сессия добавления расхода закончилась.",
            show_alert=True,
        )

        await state.clear()
        return

    check = await check_expense(
        telegram_id=callback.from_user.id,
        amount=amount,
        category_name=category,
    )

    if not check["success"]:
        await callback.answer()

        await state.clear()

        await callback.message.answer(
            f"❌ {check['error']}",
            reply_markup=main_menu(),
        )
        return

    await state.update_data(
        expense_category=category,
        expense_remaining=check["remaining"],
        expense_exceeded=check["exceeded"],
    )

    await state.set_state(
        ExpenseStates.waiting_for_description
    )

    await callback.answer()

    await callback.message.edit_text(
        f"📂 Категория: {category}\n"
        f"💸 Сумма: {format_money(amount)} ₽\n\n"
        "Напиши, на что потрачено.\n"
        "Например: «Продукты на неделю».\n\n"
        "Если описание не нужно — напиши «-».",
    )


# =========================================================
# ОПИСАНИЕ РАСХОДА
# =========================================================

@router.message(
    ExpenseStates.waiting_for_description
)
async def add_expense_description(
    message: Message,
    state: FSMContext,
):
    description = (message.text or "").strip()

    if description == "-":
        description = ""

    data = await state.get_data()

    amount = data.get("expense_amount")
    category = data.get("expense_category")
    remaining = data.get("expense_remaining", 0)
    exceeded = data.get("expense_exceeded", False)

    if amount is None or category is None:
        await state.clear()

        await message.answer(
            "❌ Не удалось продолжить добавление расхода.",
            reply_markup=main_menu(),
        )
        return

    await state.update_data(
        expense_description=description,
    )

    await state.set_state(
        ExpenseStates.waiting_for_confirmation
    )

    warning = ""

    if exceeded:
        warning = (
            "\n\n⚠️ Внимание: этот расход "
            "превышает оставшийся лимит категории.\n"
            f"После расхода: {format_money(remaining)} ₽"
        )

    description_text = (
        description
        if description
        else "без описания"
    )

    await message.answer(
        "🧾 Проверь расход:\n\n"
        f"Сумма: {format_money(amount)} ₽\n"
        f"Категория: {category}\n"
        f"Описание: {description_text}"
        f"{warning}\n\n"
        "Записать расход?",
        reply_markup=confirm_expense_keyboard(),
    )


# =========================================================
# ПОДТВЕРЖДЕНИЕ РАСХОДА
# =========================================================

@router.callback_query(
    lambda callback:
        callback.data == "confirm_expense"
)
async def confirm_expense(
    callback: CallbackQuery,
    state: FSMContext,
):
    data = await state.get_data()

    amount = data.get("expense_amount")
    category = data.get("expense_category")
    description = data.get(
        "expense_description",
        "",
    )

    if amount is None or category is None:
        await callback.answer(
            "Сессия добавления расхода закончилась.",
            show_alert=True,
        )

        await state.clear()
        return

    result = await save_expense(
        telegram_id=callback.from_user.id,
        amount=amount,
        category_name=category,
        description=description,
    )

    await state.clear()

    if not result["success"]:
        await callback.answer()

        await callback.message.edit_text(
            f"❌ {result['error']}",
        )

        await callback.message.answer(
            "Вернулась в главное меню.",
            reply_markup=main_menu(),
        )
        return

    balance = await get_current_balance()

    await callback.answer(
        "Расход записан!"
    )

    await callback.message.edit_text(
        "✅ Расход записан.\n\n"
        f"Сумма: {format_money(amount)} ₽\n"
        f"Категория: {category}"
    )

    await callback.message.answer(
        f"💳 Основной счёт: "
        f"{format_money(balance)} ₽",
        reply_markup=main_menu(),
    )


# =========================================================
# ОБЯЗАТЕЛЬНЫЕ ПЛАТЕЖИ
# =========================================================

@router.message(
    lambda message:
        message.text == "🏦 Обязательные платежи"
)
async def mandatory_payments_button(
    message: Message,
    state: FSMContext,
):
    await state.clear()

    month = get_current_month()

    payments = await get_month_mandatory_payments(
        month
    )

    if not payments:
        await message.answer(
            "🏦 ОБЯЗАТЕЛЬНЫЕ ПЛАТЕЖИ\n\n"
            "На текущий месяц платежи ещё не созданы.\n\n"
            "Они появятся после создания событий "
            "доходов по графику.",
            reply_markup=main_menu(),
        )
        return

    lines = [
        "🏦 ОБЯЗАТЕЛЬНЫЕ ПЛАТЕЖИ",
        "",
    ]

    current_event_date = None

    for payment in payments:
        event_date = payment["event_date"]

        if event_date != current_event_date:
            current_event_date = event_date

            date_text = datetime.strptime(
                event_date,
                "%Y-%m-%d",
            ).strftime("%d.%m")

            lines.extend(
                [
                    f"📅 {date_text}",
                    "",
                ]
            )

        if payment["status"] == "paid":
            status = (
                f"✅ Оплачено: "
                f"{format_money(payment['actual_amount'])} ₽"
            )
        else:
            status = "⏳ Не оплачено"

        lines.extend(
            [
                f"• {payment['payment_name']}",
                f"  План: "
                f"{format_money(payment['planned_amount'])} ₽",
                f"  {status}",
                "",
            ]
        )

    lines.append(
        "Нажми на платёж ниже, чтобы записать "
        "фактическую сумму."
    )

    await message.answer(
        "\n".join(lines),
        reply_markup=mandatory_payments_keyboard(
            payments
        ),
    )


@router.callback_query(
    lambda callback:
        callback.data
        and callback.data.startswith(
            "mandatory_payment:"
        )
)
async def select_mandatory_payment(
    callback: CallbackQuery,
    state: FSMContext,
):
    try:
        payment_id = int(
            callback.data.split(
                ":",
                1,
            )[1]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Не удалось определить платёж.",
            show_alert=True,
        )
        return

    payment = await get_mandatory_payment(
        payment_id
    )

    if not payment:
        await callback.answer(
            "Платёж не найден.",
            show_alert=True,
        )
        return

    if payment["status"] == "paid":
        await callback.answer(
            "Этот платёж уже записан.",
            show_alert=True,
        )
        return

    await state.clear()

    await state.update_data(
        mandatory_payment_id=payment_id,
        mandatory_payment_name=payment["payment_name"],
        mandatory_payment_planned=payment["planned_amount"],
    )

    await state.set_state(
        MandatoryPaymentStates.waiting_for_amount
    )

    await callback.answer()

    await callback.message.edit_text(
        "🏦 ОБЯЗАТЕЛЬНЫЙ ПЛАТЁЖ\n\n"
        f"Платёж: {payment['payment_name']}\n"
        f"План: "
        f"{format_money(payment['planned_amount'])} ₽\n\n"
        "Введи фактическую сумму, которую "
        "ты реально заплатила.\n\n"
        "Например: 14870",
        reply_markup=cancel_keyboard(),
    )


@router.message(
    MandatoryPaymentStates.waiting_for_amount
)
async def mandatory_payment_amount(
    message: Message,
    state: FSMContext,
):
    text = (message.text or "").strip()

    try:
        amount = float(
            text.replace(" ", "")
            .replace(",", ".")
        )
    except ValueError:
        await message.answer(
            "❌ Не смогла распознать сумму.\n\n"
            "Введи только число, например:\n"
            "14870"
        )
        return

    if amount <= 0:
        await message.answer(
            "❌ Сумма должна быть больше нуля.\n\n"
            "Попробуй ещё раз."
        )
        return

    data = await state.get_data()

    payment_id = data.get(
        "mandatory_payment_id"
    )
    payment_name = data.get(
        "mandatory_payment_name"
    )
    planned_amount = data.get(
        "mandatory_payment_planned"
    )

    if payment_id is None:
        await state.clear()

        await message.answer(
            "❌ Сессия платежа закончилась.",
            reply_markup=main_menu(),
        )
        return

    result = await record_actual_payment(
        payment_id=payment_id,
        actual_amount=amount,
    )

    await state.clear()

    if not result["success"]:
        await message.answer(
            f"❌ {result['error']}",
            reply_markup=main_menu(),
        )
        return

    difference = amount - planned_amount

    if difference > 0:
        difference_text = (
            f"Переплата относительно плана: "
            f"+{format_money(difference)} ₽"
        )
    elif difference < 0:
        difference_text = (
            f"Меньше плана на: "
            f"{format_money(abs(difference))} ₽"
        )
    else:
        difference_text = "Ровно по плану."

    balance = await get_current_balance()

    await message.answer(
        "✅ Платёж записан.\n\n"
        f"Платёж: {payment_name}\n"
        f"План: {format_money(planned_amount)} ₽\n"
        f"Фактически: {format_money(amount)} ₽\n"
        f"{difference_text}\n\n"
        f"💳 Основной счёт: "
        f"{format_money(balance)} ₽",
        reply_markup=main_menu(),
    )


# =========================================================
# ОТМЕНА ТЕКУЩЕГО ДЕЙСТВИЯ
# =========================================================

@router.callback_query(
    lambda callback:
        callback.data == "cancel_action"
)
async def cancel_action(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()

    await callback.answer(
        "Отменено"
    )

    try:
        await callback.message.edit_text(
            "❌ Действие отменено."
        )
    except Exception:
        pass

    await callback.message.answer(
        "Главное меню:",
        reply_markup=main_menu(),
    )


# =========================================================
# БАЛАНСЫ
# =========================================================

@router.message(
    lambda message: message.text == "📊 Балансы"
)
async def balances_button(
    message: Message,
):
    report = await get_monthly_report()
    budget = await get_monthly_budget_summary()

    lines = [
        "📊 БАЛАНСЫ",
        "",
        "💳 ОСНОВНОЙ СЧЁТ",
        f"Реальные деньги: "
        f"{format_money(report['main_account'])} ₽",
        "",
        "🐷 КОПИЛКА",
        f"Накоплено всего: "
        f"{format_money(report['savings_balance'])} ₽",
        f"Отложено в этом месяце: "
        f"{format_money(report['monthly_savings'])} ₽",
        f"Цель месяца: "
        f"{format_money(report['savings_target'])} ₽",
        f"До цели осталось: "
        f"{format_money(report['savings_remaining'])} ₽",
        "",
        "🛒 БЮДЖЕТ ЖИЗНИ",
        f"Всего на месяц: "
        f"{format_money(budget['life_budget'])} ₽",
        f"Распределено: "
        f"{format_money(budget['allocated'])} ₽",
        f"Реально потрачено: "
        f"{format_money(budget['spent'])} ₽",
        f"Осталось потратить: "
        f"{format_money(budget['remaining_to_spend'])} ₽",
        f"Осталось распределить: "
        f"{format_money(budget['remaining_to_allocate'])} ₽",
        "",
        "📊 КАТЕГОРИИ",
    ]

    for category in report["categories"]:
        lines.extend(
            [
                "",
                f"• {category['name']}",
                f"  Лимит: "
                f"{format_money(category['limit'])} ₽",
                f"  Распределено: "
                f"{format_money(category['allocated'])} ₽",
                f"  Потрачено: "
                f"{format_money(category['spent'])} ₽",
                f"  Доступно: "
                f"{format_money(max(category['allocated'] - category['spent'], 0))} ₽",
            ]
        )

    await message.answer(
        "\n".join(lines),
        reply_markup=main_menu(),
    )


# =========================================================
# ОТЧЁТ ЗА МЕСЯЦ
# =========================================================

@router.message(
    lambda message: message.text == "📅 Отчёт за месяц"
)
async def monthly_report_button(
    message: Message,
):
    report = await get_monthly_report()

    month = report["month"]

    lines = [
        f"📅 Отчёт за {month}",
        "",
        "💰 ДОХОДЫ",
        f"За месяц: "
        f"{format_money(report['month_income'])} ₽",
        "",
        "🏦 ОБЯЗАТЕЛЬНЫЕ ПЛАТЕЖИ",
        f"💳 Кредиты: "
        f"{format_money(report['credit_expenses'])} ₽",
        f"🏠 Ипотека: "
        f"{format_money(report['mortgage_expenses'])} ₽",
        f"🧾 Коммуналка: "
        f"{format_money(report['utilities_expenses'])} ₽",
        "────────────────",
        f"Всего: "
        f"{format_money(report['mandatory_expenses'])} ₽",
        "",
        "🛒 РАСХОДЫ НА ЖИЗНЬ",
        f"Бюджет: "
        f"{format_money(report['life_budget'])} ₽",
        f"Потрачено: "
        f"{format_money(report['life_expenses'])} ₽",
        f"Осталось: "
        f"{format_money(report['life_remaining'])} ₽",
        "",
        "📊 ПО КАТЕГОРИЯМ",
    ]

    for category in report["categories"]:
        lines.extend(
            [
                "",
                f"• {category['name']}",
                f"  Лимит: "
                f"{format_money(category['limit'])} ₽",
                f"  Распределено: "
                f"{format_money(category['allocated'])} ₽",
                f"  Потрачено: "
                f"{format_money(category['spent'])} ₽",
                f"  Осталось: "
                f"{format_money(category['remaining'])} ₽",
            ]
        )

    lines.extend(
        [
            "",
            "📦 РАСПРЕДЕЛЕНИЕ",
            f"Распределено по категориям: "
            f"{format_money(report['category_allocations'])} ₽",
            f"Осталось распределить: "
            f"{format_money(report['life_remaining_to_allocate'])} ₽",
            "",
            "🐷 НАКОПЛЕНИЯ",
            f"Отложено в этом месяце: "
            f"{format_money(report['monthly_savings'])} ₽",
            f"Цель месяца: "
            f"{format_money(report['savings_target'])} ₽",
            f"До цели осталось: "
            f"{format_money(report['savings_remaining'])} ₽",
            f"Всего в копилке: "
            f"{format_money(report['savings_balance'])} ₽",
            "",
            "💳 ДЕНЬГИ",
            f"Основной счёт: "
            f"{format_money(report['main_account'])} ₽",
        ]
    )

    await message.answer(
        "\n".join(lines),
        reply_markup=main_menu(),
    )
