from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

import aiosqlite

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


router = Router()

pending_expenses = {}


@router.message(CommandStart())
async def start_handler(message: Message):
    telegram_id = message.from_user.id
    name = message.from_user.first_name or "Пользователь"

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (telegram_id, name)
            VALUES (?, ?)
            ON CONFLICT(telegram_id)
            DO UPDATE SET name = excluded.name
            """,
            (telegram_id, name),
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

    if detect_income(text):
        result = await add_income(
            telegram_id=message.from_user.id,
            amount=amount,
            description=text,
        )

        if not result["success"]:
            await message.answer(result["error"])
            return

        await message.answer(
            f"💰 Доход записан: +{amount:,.0f} ₽".replace(",", " "),
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
        telegram_id=message.from_user.id,
        amount=amount,
        category_name=category,
    )

    if not result["success"]:
        await message.answer(result["error"])
        return

    if result["exceeded"]:
        pending_expenses[message.from_user.id] = {
            "amount": amount,
            "category": category,
            "description": text,
        }

        await message.answer(
            f"⚠️ Расход превысит лимит.\n\n"
            f"Категория: {category}\n"
            f"Сумма: {amount:,.0f} ₽\n"
            f"Лимит: {result['limit']:,.0f} ₽\n"
            f"Уже потрачено: {result['spent']:,.0f} ₽\n"
            f"После покупки будет превышение на "
            f"{abs(result['remaining']):,.0f} ₽.\n\n"
            "Записать расход всё равно?".replace(",", " "),
            reply_markup=confirm_expense_keyboard(),
        )
        return

    saved = await save_expense(
        telegram_id=message.from_user.id,
        amount=amount,
        category_name=category,
        description=text,
    )

    if not saved["success"]:
        await message.answer(saved["error"])
        return

    await message.answer(
        f"✅ Расход записан.\n\n"
        f"Категория: {saved['category']}\n"
        f"Сумма: {amount:,.0f} ₽\n"
        f"Потрачено за месяц: {saved['spent']:,.0f} ₽\n"
        f"Остаток категории: {saved['remaining']:,.0f} ₽".replace(
            ",", " "
        ),
        reply_markup=main_menu(),
    )


@router.callback_query(
    lambda callback: callback.data == "confirm_expense"
)
async def confirm_expense(callback: CallbackQuery):
    telegram_id = callback.from_user.id

    expense = pending_expenses.pop(telegram_id, None)

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
        f"✅ Расход записан с превышением.\n\n"
        f"Категория: {result['category']}\n"
        f"Сумма: {result['amount']:,.0f} ₽\n"
        f"Превышение: {abs(result['remaining']):,.0f} ₽".replace(
            ",", " "
        )
    )

    await callback.answer()


@router.callback_query(
    lambda callback: callback.data == "cancel_expense"
)
async def cancel_expense(callback: CallbackQuery):
    pending_expenses.pop(callback.from_user.id, None)

    await callback.message.edit_text(
        "❌ Расход не записан."
    )

    await callback.answer()
