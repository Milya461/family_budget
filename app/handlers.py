from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.budget import add_expense, add_income
from app.db import DB_PATH
from app.keyboards import main_menu
from app.parser import (
    detect_category,
    detect_income,
    extract_amount,
)

import aiosqlite


router = Router()


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

    result = await add_expense(
        telegram_id=message.from_user.id,
        amount=amount,
        category_name=category,
        description=text,
    )

    if not result["success"]:
        await message.answer(result["error"])
        return

    remaining = result["remaining"]

    if result["exceeded"]:
        await message.answer(
            f"⚠️ Расход записан.\n\n"
            f"Категория: {result['category']}\n"
            f"Сумма: {amount:,.0f} ₽\n\n"
            f"Лимит: {result['limit']:,.0f} ₽\n"
            f"Потрачено: {result['spent']:,.0f} ₽\n"
            f"Превышение: {abs(remaining):,.0f} ₽".replace(",", " "),
            reply_markup=main_menu(),
        )
        return

    await message.answer(
        f"✅ Расход записан.\n\n"
        f"Категория: {result['category']}\n"
        f"Сумма: {amount:,.0f} ₽\n\n"
        f"Потрачено за месяц: {result['spent']:,.0f} ₽\n"
        f"Остаток категории: {remaining:,.0f} ₽".replace(",", " "),
        reply_markup=main_menu(),
    )
