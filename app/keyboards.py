from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


CATEGORIES = [
    "Продукты",
    "Бензин",
    "Питомцы",
    "Дом и быт",
    "Развлечения и кафе",
    "Личные покупки",
    "Здоровье",
    "Подарки и праздники",
    "Непредвиденные",
]


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


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="cancel_action",
                )
            ]
        ]
    )


def categories_keyboard() -> InlineKeyboardMarkup:
    buttons = []

    for category in CATEGORIES:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=category,
                    callback_data=f"expense_category:{category}",
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="cancel_action",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=buttons,
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
                    callback_data="cancel_action",
                ),
            ]
        ]
    )
