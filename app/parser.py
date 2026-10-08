import re


CATEGORY_KEYWORDS = {
    "Продукты": [
        "продукт",
        "продукты",
        "магазин",
        "еда",
        "пятерочка",
        "перекресток",
        "магнит",
        "ашан",
    ],
    "Бензин": [
        "бензин",
        "заправка",
        "азс",
        "топливо",
    ],
    "Питомцы": [
        "кот",
        "коты",
        "кош",
        "корм",
        "наполнитель",
        "ветеринар",
        "вет",
        "питомец",
    ],
    "Дом и быт": [
        "дом",
        "быт",
        "хозяйствен",
        "уборка",
        "моющее",
        "порошок",
        "ремонт",
    ],
    "Развлечения и кафе": [
        "кафе",
        "ресторан",
        "бар",
        "кино",
        "театр",
        "развлеч",
        "доставка еды",
    ],
    "Личные покупки": [
        "одежда",
        "обувь",
        "косметика",
        "личн",
        "покупка",
    ],
    "Здоровье": [
        "аптека",
        "лекар",
        "врач",
        "здоров",
        "анализ",
        "стоматолог",
    ],
    "Подарки и праздники": [
        "подар",
        "праздник",
        "день рождения",
        "торт",
    ],
    "Непредвиденные": [
        "непредвид",
        "срочно",
        "прочее",
    ],
}


DEBT_KEYWORDS = {
    "Кредитная карта": [
        "кредитка",
        "кредитная карта",
    ],
    "Кредит на машину": [
        "кредит на машину",
        "автокредит",
        "автокредит",
        "машина кредит",
    ],
    "Ипотека": [
        "ипотека",
    ],
}


def extract_amount(text: str):
    text = text.replace(",", ".")
    matches = re.findall(r"\d+(?:\.\d+)?", text)

    if not matches:
        return None

    return float(matches[-1])


def detect_category(text: str):
    normalized = text.lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in normalized:
                return category

    return None


def detect_debt(text: str):
    normalized = text.lower()

    for debt, keywords in DEBT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in normalized:
                return debt

    return None


def detect_income(text: str):
    normalized = text.lower()

    income_keywords = [
        "зарплата",
        "аванс",
        "доход",
        "кэшбек",
        "кешбек",
        "кешбэк",
        "подарочные деньги",
        "подарили",
        "родители прислали",
        "попутчики",
        "подработка",
    ]

    return any(keyword in normalized for keyword in income_keywords)
