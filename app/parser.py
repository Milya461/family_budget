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
        "супермаркет",
    ],
    "Бензин": [
        "бензин",
        "заправка",
        "азс",
        "топливо",
        "заправился",
        "заправилась",
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
        "животные",
        "животным",
    ],
    "Дом и быт": [
        "дом",
        "быт",
        "хозяйствен",
        "уборка",
        "моющее",
        "порошок",
        "ремонт",
        "бытовая химия",
    ],
    "Развлечения и кафе": [
        "кафе",
        "ресторан",
        "бар",
        "кино",
        "театр",
        "развлеч",
        "доставка еды",
        "доставку еды",
    ],
    "Личные покупки": [
        "одежда",
        "обувь",
        "косметика",
        "личн",
        "покупка",
        "маникюр",
        "парикмахер",
    ],
    "Здоровье": [
        "аптека",
        "лекар",
        "врач",
        "здоров",
        "анализ",
        "стоматолог",
        "лечение",
    ],
    "Подарки и праздники": [
        "подар",
        "праздник",
        "день рождения",
        "торт",
        "цветы",
    ],
    "Непредвиденные": [
        "непредвид",
        "срочно",
        "прочее",
        "неожидан",
    ],
}


DEBT_KEYWORDS = {
    "Кредитная карта": [
        "кредитка",
        "кредитную карту",
        "кредитная карта",
        "кредитной карте",
        "кредитная",
        "кредитке",
    ],
    "Кредит на машину": [
        "кредит на машину",
        "кредит за машину",
        "автокредит",
        "машина кредит",
        "машинный кредит",
    ],
    "Ипотека": [
        "ипотека",
        "ипотеку",
        "ипотеке",
    ],
}


INCOME_KEYWORDS = [
    "зарплата",
    "аванс",
    "доход",
    "кэшбек",
    "кешбек",
    "кешбэк",
    "кеш-бэк",
    "кэш-бэк",
    "подарили",
    "подарок деньгами",
    "подарочные деньги",
    "родители прислали",
    "мама прислала",
    "папа прислал",
    "мама дала",
    "папа дал",
    "прислали родители",
    "попутчик",
    "попутчики",
    "подработка",
    "вернули деньги",
    "возврат денег",
    "вернулся кэшбек",
]


def normalize_text(text: str) -> str:
    """Приводит текст к единому формату для распознавания."""
    return " ".join((text or "").lower().strip().split())


def extract_amount(text: str):
    """
    Извлекает денежную сумму из сообщения.

    Поддерживает варианты:
    599
    2 490
    2490,50
    2 490,50
    2.490,50
    """
    if not text:
        return None

    normalized = text.replace("\u00a0", " ").strip()

    pattern = (
        r"(?<!\w)"
        r"\d{1,3}(?:[ \u00a0]\d{3})+(?:[.,]\d{1,2})?"
        r"|"
        r"\d+(?:[.,]\d{1,2})?"
    )

    matches = re.findall(pattern, normalized)

    if not matches:
        return None

    value = matches[-1]
    value = value.replace(" ", "").replace("\u00a0", "")

    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    else:
        value = value.replace(",", ".")

    try:
        amount = float(value)
    except ValueError:
        return None

    if amount <= 0:
        return None

    return amount


def _find_keyword(text: str, keyword: str) -> bool:
    """
    Проверяет наличие ключевого слова.
    Для коротких слов использует границы слов,
    чтобы не было лишних совпадений.
    """
    if len(keyword) <= 4:
        pattern = rf"(?<!\w){re.escape(keyword)}(?!\w)"
        return re.search(pattern, text) is not None

    return keyword in text


def detect_category(text: str):
    """Определяет категорию обычного расхода."""
    normalized = normalize_text(text)

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if _find_keyword(normalized, keyword):
                return category

    return None


def detect_debt(text: str):
    """Определяет долг или обязательный платёж."""
    normalized = normalize_text(text)

    for debt, keywords in DEBT_KEYWORDS.items():
        for keyword in keywords:
            if _find_keyword(normalized, keyword):
                return debt

    return None


def detect_income(text: str) -> bool:
    """Проверяет, похож ли текст на описание дохода."""
    normalized = normalize_text(text)

    return any(
        _find_keyword(normalized, keyword)
        for keyword in INCOME_KEYWORDS
    )


def remove_amount(text: str) -> str:
    """Удаляет денежную сумму из текста, сохраняя описание операции."""
    if not text:
        return ""

    pattern = (
        r"(?<!\w)"
        r"\d{1,3}(?:[ \u00a0]\d{3})+(?:[.,]\d{1,2})?"
        r"|"
        r"\d+(?:[.,]\d{1,2})?"
    )

    result = re.sub(pattern, " ", text, count=1)
    result = re.sub(r"\s+", " ", result)
    result = result.strip(" \t\n\r,.;:-")

    return result


def parse_operation(text: str):
    """
    Разбирает короткое сообщение пользователя.

    Примеры:
        продукты 599
        бензин 2490
        корм котам 1800
        кредит на машину 15000
        ипотека 9000
        кэшбек 250
        мама прислала 5000

    Возвращает словарь с типом операции, суммой,
    категорией или названием платежа и описанием.

    Функция только распознаёт сообщение.
    Она не записывает операции в базу данных.
    """
    if not text or not text.strip():
        return None

    amount = extract_amount(text)

    if amount is None:
        return None

    normalized = normalize_text(text)
    description = remove_amount(text)

    # Доходы проверяем первыми, чтобы, например,
    # «подарили 1000» не записался как расход на подарок.
    if detect_income(normalized):
        return {
            "type": "income",
            "amount": amount,
            "category": None,
            "debt": None,
            "description": description or "Дополнительный доход",
        }

    # Обязательные платежи и долги должны распознаваться
    # отдельно от обычных расходов.
    debt = detect_debt(normalized)

    if debt:
        return {
            "type": "payment",
            "amount": amount,
            "category": None,
            "debt": debt,
            "description": description or debt,
        }

    category = detect_category(normalized)

    if category:
        return {
            "type": "expense",
            "amount": amount,
            "category": category,
            "debt": None,
            "description": description or category,
        }

    # Если категорию нельзя определить уверенно,
    # не записываем операцию автоматически.
    return {
        "type": "unknown",
        "amount": amount,
        "category": None,
        "debt": None,
        "description": description,
    }
