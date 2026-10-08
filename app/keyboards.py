from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="💸 Добавить расход"),
                KeyboardButton(text="💰 Добавить доход"),
            ],
            [
                KeyboardButton(text="🏦 Обязательные платежи"),
                KeyboardButton(text="📊 Балансы"),
            ],
            [
                KeyboardButton(text="📅 Отчёт за месяц"),
                KeyboardButton(text="🐷 Копилка"),
            ],
            [
                KeyboardButton(text="⚙️ Настройки"),
                KeyboardButton(text="↩️ Отменить последнюю операцию"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
