from app.parser import (
    detect_category,
    detect_income,
    detect_debt,
    classify_mandatory_payment,
    extract_amount,
)


def test_extract_amount():
    assert extract_amount("продукты 599") == 599
    assert extract_amount("бензин 2490") == 2490


def test_detect_categories():
    assert detect_category("продукты 599") == "Продукты"
    assert detect_category("бензин 2490") == "Бензин"
    assert detect_category("корм котам 1200") == "Питомцы"
    assert detect_category("аптека 850") == "Здоровье"


def test_detect_new_expense_categories():
    assert detect_category("такси 150") == "Транспорт"
    assert detect_category("платная трасса 500") == "Транспорт"
    assert detect_category("маникюр 1500") == "Красота"
    assert detect_category("куртка 4500") == "Одежда"
    assert detect_category("подписка на Яндекс Плюс 399") == "Подписки"


def test_removed_categories_are_not_detected():
    assert detect_category("непредвиденное 100") is None
    assert detect_category("личные покупки 100") is None


def test_detect_income():
    assert detect_income("зарплата 50000")
    assert detect_income("родители прислали 5000")
    assert detect_income("кэшбек 300")
    assert detect_income("отвезли попутчиков 1000")


def test_detect_debt():
    assert detect_debt("кредитка 18000") == "Кредитная карта"
    assert detect_debt("кредит на машину 15000") == "Кредит на машину"
    assert detect_debt("ипотека 9000") == "Ипотека"



def test_classify_mandatory_payments_for_dashboard_totals():
    assert classify_mandatory_payment("кредитка 18000") == "Кредитная карта"
    assert classify_mandatory_payment("платёж за машину 15000") == "Кредит на машину"
    assert classify_mandatory_payment("ипотека 9000") == "Ипотека"
    assert classify_mandatory_payment("коммуналка 10000") == "Коммунальные услуги"
    assert classify_mandatory_payment("обычные продукты 1200") is None


def test_classify_mandatory_payment_uses_debt_name_when_description_is_generic():
    assert classify_mandatory_payment("обязательный платёж", "Ипотека") == "Ипотека"
