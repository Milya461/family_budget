from app.parser import (
    detect_category,
    detect_income,
    detect_debt,
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


def test_detect_income():
    assert detect_income("зарплата 50000")
    assert detect_income("родители прислали 5000")
    assert detect_income("кэшбек 300")
    assert detect_income("отвезли попутчиков 1000")


def test_detect_debt():
    assert detect_debt("кредитка 18000") == "Кредитная карта"
    assert detect_debt("кредит на машину 15000") == "Кредит на машину"
    assert detect_debt("ипотека 9000") == "Ипотека"
