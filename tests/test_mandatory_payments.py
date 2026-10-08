import pytest

from app import payments


@pytest.mark.asyncio
async def test_get_planned_payments_for_10th():
    result = await payments.get_planned_payments(10)

    assert result == [
        ("Кредитная карта", 18000),
        ("Кредит на машину", 15000),
    ]


@pytest.mark.asyncio
async def test_get_planned_payments_for_25th():
    result = await payments.get_planned_payments(25)

    assert result == [
        ("Кредит на машину", 15000),
        ("Ипотека", 9000),
        ("Коммунальные услуги", 10000),
    ]


@pytest.mark.asyncio
async def test_get_planned_payments_for_other_day():
    result = await payments.get_planned_payments(15)

    assert result == []


@pytest.mark.asyncio
async def test_get_income_plan_for_31st_uses_day_30(
    monkeypatch,
):
    async def fake_fetch_all(query, *params):
        assert params == (30,)

        return [
            {
                "name": "Аванс пользователя",
                "planned_amount": 27500,
            }
        ]

    monkeypatch.setattr(
        payments,
        "fetch_all",
        fake_fetch_all,
    )

    result = await payments.get_income_plan(31)

    assert result == [
        ("Аванс пользователя", 27500)
    ]


@pytest.mark.asyncio
async def test_get_income_plan_for_10th(
    monkeypatch,
):
    async def fake_fetch_all(query, *params):
        assert params == (10,)

        return [
            {
                "name": "Зарплата мужа",
                "planned_amount": 50000,
            }
        ]

    monkeypatch.setattr(
        payments,
        "fetch_all",
        fake_fetch_all,
    )

    result = await payments.get_income_plan(10)

    assert result == [
        ("Зарплата мужа", 50000)
    ]


@pytest.mark.asyncio
async def test_get_income_plan_returns_multiple_income_sources(
    monkeypatch,
):
    async def fake_fetch_all(query, *params):
        return [
            {
                "name": "Доход 1",
                "planned_amount": 30000,
            },
            {
                "name": "Доход 2",
                "planned_amount": 20000,
            },
        ]

    monkeypatch.setattr(
        payments,
        "fetch_all",
        fake_fetch_all,
    )

    result = await payments.get_income_plan(10)

    assert result == [
        ("Доход 1", 30000),
        ("Доход 2", 20000),
    ]


@pytest.mark.asyncio
async def test_get_event_payments(monkeypatch):
    async def fake_fetch_all(query, *params):
        assert params == (5,)

        return [
            {
                "id": 1,
                "payment_name": "Кредитная карта",
                "planned_amount": 18000,
                "actual_amount": None,
                "status": "pending",
            },
            {
                "id": 2,
                "payment_name": "Кредит на машину",
                "planned_amount": 15000,
                "actual_amount": 14983,
                "status": "paid",
            },
        ]

    monkeypatch.setattr(
        payments,
        "fetch_all",
        fake_fetch_all,
    )

    result = await payments.get_event_payments(5)

    assert result == [
        {
            "id": 1,
            "payment_name": "Кредитная карта",
            "planned_amount": 18000,
            "actual_amount": None,
            "status": "pending",
        },
        {
            "id": 2,
            "payment_name": "Кредит на машину",
            "planned_amount": 15000,
            "actual_amount": 14983,
            "status": "paid",
        },
    ]


@pytest.mark.asyncio
async def test_get_mandatory_payment_returns_none(
    monkeypatch,
):
    async def fake_fetch_one(query, *params):
        return None

    monkeypatch.setattr(
        payments,
        "fetch_one",
        fake_fetch_one,
    )

    result = await payments.get_mandatory_payment(999)

    assert result is None


@pytest.mark.asyncio
async def test_get_event_returns_none(
    monkeypatch,
):
    async def fake_fetch_one(query, *params):
        return None

    monkeypatch.setattr(
        payments,
        "fetch_one",
        fake_fetch_one,
    )

    result = await payments.get_event(999)

    assert result is None


@pytest.mark.asyncio
async def test_save_actual_payment_returns_none_for_missing_payment(
    monkeypatch,
):
    async def fake_fetch_one(query, *params):
        return None

    monkeypatch.setattr(
        payments,
        "fetch_one",
        fake_fetch_one,
    )

    result = await payments.save_actual_payment(
        payment_id=999,
        actual_amount=1000,
    )

    assert result is None


@pytest.mark.asyncio
async def test_save_actual_income_returns_error_for_missing_event(
    monkeypatch,
):
    async def fake_fetch_one(query, *params):
        return None

    monkeypatch.setattr(
        payments,
        "fetch_one",
        fake_fetch_one,
    )

    result = await payments.save_actual_income(
        event_id=999,
        actual_income=50000,
    )

    assert result["success"] is False
    assert (
        result["error"]
        == "Событие дохода не найдено."
    )
