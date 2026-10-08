from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


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


def confirm_expense_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, записать",
                    callback_data="confirm_expense",
                ),
                InlineKeyboardButton(
                    text="❌ Нет",
                    callback_data="cancel_expense",
                ),
            ]
        ]
    )
