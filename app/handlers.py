from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

import aiosqlite

from app.db import DB_PATH
from app.keyboards import main_menu


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
        "Здесь мы будем учитывать:\n"
        "• доходы\n"
        "• расходы\n"
        "• кредитную карту\n"
        "• кредит на машину\n"
        "• ипотеку\n"
        "• коммунальные платежи\n"
        "• накопления\n\n"
        "Выбирай действие ниже или просто пиши расход/доход обычным текстом.",
        reply_markup=main_menu(),
    )
