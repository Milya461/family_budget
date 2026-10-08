from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.db import DB_PATH
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
        "Это семейный бюджет.\n\n"
        "Я буду помогать вам учитывать доходы, "
        "расходы, кредиты, накопления и бюджет семьи.\n\n"
        "Сейчас мы только начинаем настройку."
    )
