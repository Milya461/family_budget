from datetime import date

import pytest

from app import payment_flow


@pytest.mark.asyncio
async def test_start_income_event(monkeypatch):
    async def fake_get_income_plan(day):
        assert day == 10

        return [
            ("Зарплата мужа", 50000),
        ]

    async def fake_get_planned_payments(day):
        assert day == 10

        return [
            ("Кредитная карта", 18000),
            ("Кредит на машину", 15000),
        ]

    async def fake_fetch_one(query, *params):
        return None

    async def fake_create_salary_event(
        event_date,
        planned_income,
    ):
        assert event_date == "2026-10-10"
        assert planned_income == 50000

        return 1

    async def fake_execute(query, *params):
        return None

    async def fake_create_mandatory_payment(
        salary_event_id,
        payment_name,
        planned_amount,
    ):
        assert salary_event_id == 1
        assert planned_amount > 0

    monkeypatch.setattr(
        payment_flow,
        "get_income_plan",
        fake_get_income_plan,
    )

    monkeypatch.setattr(
        payment_flow,
        "get_planned_payments",
        fake_get_planned_payments,
    )

    monkeypatch.setattr(
        payment_flow,
        "fetch_one",
        fake_fetch_one,
    )

    monkeypatch.setattr(
        payment_flow,
        "create_salary_event",
        fake_create_salary_event,
    )

    monkeypatch.setattr(
        payment_flow,
        "execute",
        fake_execute,
    )

    monkeypatch.setattr(
        payment_flow,
        "create_mandatory_payment",
        fake_create_mandatory_payment,
    )

    result = await payment_flow.start_income_event(
        event_date=date(2026, 10, 10)
    )

    assert result["event_id"] == 1
    assert result["date"] == "2026-10-10"
    assert result["planned_day"] == 10
    assert result["planned_income"] == 50000

    assert result["income_plans"] == [
        {
            "name": "Зарплата мужа",
            "planned_amount": 50000,
        }
    ]

    assert result["payments"] == [
        {
            "name": "Кредитная карта",
            "planned_amount": 18000,
        },
        {
            "name": "Кредит на машину",
            "planned_amount": 15000,
        },
    ]


@pytest.mark.asyncio
async def test_start_income_event_last_day_uses_day_30(
    monkeypatch,
):
    async def fake_get_income_plan(day):
        assert day == 30

        return [
            ("Аванс пользователя", 27500),
        ]

    async def fake_get_planned_payments(day):
        return []

    async def fake_fetch_one(query, *params):
        return None

    async def fake_create_salary_event(
        event_date,
        planned_income,
    ):
        return 10

    async def fake_execute(query, *params):
        return None

    async def fake_create_mandatory_payment(
        salary_event_id,
        payment_name,
        planned_amount,
    ):
        raise AssertionError(
            "На день 30 обязательных платежей нет."
        )

    monkeypatch.setattr(
        payment_flow,
        "get_income_plan",
        fake_get_income_plan,
    )

    monkeypatch.setattr(
        payment_flow,
        "get_planned_payments",
        fake_get_planned_payments,
    )

    monkeypatch.setattr(
        payment_flow,
        "fetch_one",
        fake_fetch_one,
    )

    monkeypatch.setattr(
        payment_flow,
        "create_salary_event",
        fake_create_salary_event,
    )

    monkeypatch.setattr(
        payment_flow,
        "execute",
        fake_execute,
    )

    monkeypatch.setattr(
        payment_flow,
        "create_mandatory_payment",
        fake_create_mandatory_payment,
    )

    result = await payment_flow.start_income_event(
        event_date=date(2026, 10, 31)
    )

    assert result["planned_day"] == 30
    assert result["planned_income"] == 27500

    assert result["income_plans"] == [
        {
            "name": "Аванс пользователя",
            "planned_amount": 27500,
        }
    ]


@pytest.mark.asyncio
async def test_find_income_event(monkeypatch):
    async def fake_fetch_one(query, *params):
        assert params == (10, "2026-10")

        return {
            "id": 5,
            "event_date": "2026-10-08",
            "planned_day": 10,
            "planned_income": 50000,
            "actual_income": 50000,
            "status": "income_received",
        }

    monkeypatch.setattr(
        payment_flow,
        "fetch_one",
        fake_fetch_one,
    )

    result = await payment_flow.find_income_event(
        planned_day=10,
        month="2026-10",
    )

    assert result == {
        "id": 5,
        "event_date": "2026-10-08",
        "planned_day": 10,
        "planned_income": 50000,
        "actual_income": 50000,
        "status": "income_received",
    }


@pytest.mark.asyncio
async def test_find_income_event_returns_none(
    monkeypatch,
):
    async def fake_fetch_one(query, *params):
        return None

    monkeypatch.setattr(
        payment_flow,
        "fetch_one",
        fake_fetch_one,
    )

    result = await payment_flow.find_income_event(
        planned_day=10,
        month="2026-10",
    )

    assert result is None


@pytest.mark.asyncio
async def test_record_actual_income_rejects_negative_amount():
    result = await payment_flow.record_actual_income(
        event_id=1,
        actual_income=-100,
    )

    assert result["success"] is False
    assert (
        result["error"]
        == "Сумма дохода не может быть отрицательной."
    )


@pytest.mark.asyncio
async def test_record_actual_payment_rejects_negative_amount():
    result = await payment_flow.record_actual_payment(
        payment_id=1,
        actual_amount=-100,
    )

    assert result["success"] is False
    assert (
        result["error"]
        == "Сумма платежа не может быть отрицательной."
    )


@pytest.mark.asyncio
async def test_get_payment_event_id(monkeypatch):
    async def fake_fetch_value(query, *params):
        assert params == (17,)

        return 8

    monkeypatch.setattr(
        payment_flow,
        "fetch_value",
        fake_fetch_value,
    )

    result = await payment_flow.get_payment_event_id(
        payment_id=17
    )

    assert result == 8


@pytest.mark.asyncio
async def test_get_event_summary(monkeypatch):
    async def fake_get_event(event_id):
        assert event_id == 8

        return {
            "id": 8,
            "event_date": "2026-10-10",
            "planned_day": 10,
            "planned_income": 50000,
            "actual_income": 50000,
            "status": "income_received",
        }

    async def fake_get_event_payments(event_id):
        assert event_id == 8

        return [
            {
                "id": 1,
                "payment_name": "Кредитная карта",
                "planned_amount": 18000,
                "actual_amount": 17642,
                "status": "paid",
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
        payment_flow,
        "get_event",
        fake_get_event,
    )

    monkeypatch.setattr(
        payment_flow,
        "get_event_payments",
        fake_get_event_payments,
    )

    result = await payment_flow.get_event_summary(8)

    assert result["total_planned_payments"] == 33000
    assert result["total_actual_payments"] == 32625
    assert result["planned_remaining"] == 17000
    assert result["remaining"] == 17375
    assert result["all_payments_paid"] is True


@pytest.mark.asyncio
async def test_get_event_summary_returns_none(
    monkeypatch,
):
    async def fake_get_event(event_id):
        return None

    monkeypatch.setattr(
        payment_flow,
        "get_event",
        fake_get_event,
    )

    result = await payment_flow.get_event_summary(999)

    assert result is None


@pytest.mark.asyncio
async def test_start_early_income_event(
    monkeypatch,
):
    async def fake_find_income_event(
        planned_day,
        month,
    ):
        assert planned_day == 10
        assert month == "2026-10"

        return None

    async def fake_start_income_event(
        event_date,
        planned_day,
    ):
        assert event_date == date(2026, 10, 8)
        assert planned_day == 10

        return {
            "event_id": 20,
        }

    async def fake_get_event(event_id):
        assert event_id == 20

        return {
            "id": 20,
            "event_date": "2026-10-08",
            "planned_day": 10,
            "planned_income": 50000,
            "actual_income": None,
            "status": "pending",
        }

    monkeypatch.setattr(
        payment_flow,
        "find_income_event",
        fake_find_income_event,
    )

    monkeypatch.setattr(
        payment_flow,
        "start_income_event",
        fake_start_income_event,
    )

    monkeypatch.setattr(
        payment_flow,
        "get_event",
        fake_get_event,
    )

    result = await payment_flow.start_early_income_event(
        actual_date=date(2026, 10, 8),
        planned_day=10,
    )

    assert result["event_date"] == "2026-10-08"
    assert result["planned_day"] == 10
    assert result["planned_income"] == 50000


def test_get_event_day_for_regular_date():
    result = payment_flow.get_moscow_today()

    assert result is not None


@pytest.mark.asyncio
async def test_get_current_balance(monkeypatch):
    values = iter([150000, 23000])

    async def fake_fetch_value(query, *params):
        return next(values)

    monkeypatch.setattr(
        payment_flow,
        "fetch_value",
        fake_fetch_value,
    )

    result = await payment_flow.get_current_balance()

    assert result == 127000
