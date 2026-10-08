from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import aiosqlite

from app.db import DB_PATH
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
)
from app.payment_flow import get_current_balance
from app.allocation import get_monthly_budget_summary


router = Router()


class IncomeStates(StatesGroup):
    waiting_for_amount = State()


class ExpenseStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_description = State()
    waiting_for_confirmation = State()


async def ensure_user(
    telegram_id: int,
    name: str,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO users (
                telegram_id,
                name
            )
            VALUES (?, ?)
            """,
            (
                telegram_id,
                name,
            ),
        )

        await db.execute(
            """
            UPDATE users
            SET name = ?
            WHERE telegram_id = ?
            """,
            (
                name,
                telegram_id,
            ),
        )

        await db.commit()


def format_money(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ")


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
