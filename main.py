import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.startup()
async def on_startup():
    logging.info("Family Budget Bot started")


@dp.shutdown()
async def on_shutdown():
    await bot.session.close()
    logging.info("Family Budget Bot stopped")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
