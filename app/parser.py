
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
        "кредитной картой",
        "кредитке",
    ],
    "Кредит на машину": [
        "кредит на машину",
        "кредит за машину",
        "платеж за машину",
        "платёж за машину",
        "платеж по машине",
        "платёж по машине",
        "автокредит",
        "машина кредит",
    ],
    "Ипотека": [
        "ипотека",
        "ипотеку",
        "ипотеке",
        "ипотекой",
        "ипотечный",
        "ипотечный платеж",
        "ипотечный платёж",
        "за квартиру",
        "квартира",
        "квартиру",
    ],
    "Коммунальные услуги": [
        "коммуналка",
        "коммунальные услуги",
        "коммунальные",
        "жкх",
        "свет",
        "вода",
        "электричество",
        "за коммуналку",
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
    "кэшбэк",
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
    "попутчика",
    "попутчиков",
    "попутчики",
    "подработка",
    "вернули деньги",
    "возврат денег",
    "вернулся кэшбек",
]


# Поддерживаем суммы:
# 599
# 2490
# 2 490
# 2 490,50
# 2.490,50
# 2490.50
AMOUNT_PATTERN = re.compile(
    r"(?<!\w)"
    r"(?:\d{1,3}(?:[ .\u00a0]\d{3})+|\d+)"
    r"(?:[.,]\d{1,2})?"
    r"(?!\w)"
)


def normalize_text(text: str) -> str:
    """Приводит текст к единому формату для распознавания."""
    return " ".join(
        (text or "")
        .lower()
        .replace("ё", "е")
        .strip()
        .split()
    )


def extract_amount(text: str):
    """Извлекает денежную сумму из сообщения."""
    if not text:
        return None

    normalized = text.replace("\u00a0", " ").strip()
    matches = AMOUNT_PATTERN.findall(normalized)

    if not matches:
        return None

    # Обычно сумма стоит в конце сообщения.
    value = matches[-1]
    value = value.replace(" ", "").replace("\u00a0", "")

    # Если присутствуют и точка, и запятая,
    # последний разделитель считается десятичным.
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
    """Проверяет наличие ключевого слова."""
    keyword = normalize_text(keyword)

    if not keyword:
        return False

    # Короткие слова ищем только как отдельные слова,
    # чтобы, например, «кот» не находился внутри другого слова.
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
    """Определяет обязательный платёж."""
    normalized = normalize_text(text)

    for debt, keywords in DEBT_KEYWORDS.items():
        for keyword in keywords:
            if _find_keyword(normalized, keyword):
                return debt

    return None


def detect_income(text: str) -> bool:
    """Проверяет, похоже ли сообщение на описание дохода."""
    normalized = normalize_text(text)

    return any(
        _find_keyword(normalized, keyword)
        for keyword in INCOME_KEYWORDS
    )


def remove_amount(text: str) -> str:
    """Удаляет сумму из текста, сохраняя описание операции."""
    if not text:
        return ""

    result = AMOUNT_PATTERN.sub(" ", text, count=1)
    result = re.sub(r"\s+", " ", result)

    return result.strip(" \t\n\r,.;:-")


def parse_operation(text: str):
    """Разбирает сообщение пользователя без записи в базу данных."""
    if not text or not text.strip():
        return None

    amount = extract_amount(text)

    if amount is None:
        return None

    normalized = normalize_text(text)
    description = remove_amount(text)

    # Сначала проверяем доходы.
    if detect_income(normalized):
        return {
            "type": "income",
            "amount": amount,
            "category": None,
            "debt": None,
            "description": description or "Дополнительный доход",
        }

    # Обязательные платежи проверяем раньше обычных расходов.
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

    return {
        "type": "unknown",
        "amount": amount,
        "category": None,
        "debt": None,
        "description": description,
    }
