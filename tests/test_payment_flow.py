from datetime import date

import pytest

from app.db import init_db
from app.setup import setup
from app.payment_flow import (
    get_current_balance,
    start_income_event,
)
from app.payments import (
    get_event_payments,
    save_actual_payment,
)


@pytest.mark.asyncio
async def test_start_income_event():
    await init_db()
    await setup()

    result = await start_income_event(
        date(2026, 10, 10)
    )

    assert result["planned_income"] == 50000

    assert len(result["income_plans"]) == 1
    assert result["income_plans"][0]["name"] == "Зарплата мужа"

    assert len(result["payments"]) == 2

    payment_names = [
        payment["name"]
        for payment in result["payments"]
    ]

    assert "Кредитная карта" in payment_names
    assert "Кредит на машину" in payment_names


@pytest.mark.asyncio
async def test_last_day_of_month_uses_day_30():
    await init_db()
    await setup()

    result = await start_income_event(
        date(2026, 10, 31)
    )

    assert result["planned_income"] == 27500

    assert result["income_plans"][0]["name"] == "Аванс пользователя"


@pytest.mark.asyncio
async def test_current_balance():
    await init_db()
    await setup()

    balance = await get_current_balance()

    assert balance >= 0


@pytest.mark.asyncio
async def test_save_actual_mandatory_payment():
    await init_db()
    await setup()

    result = await start_income_event(
        date(2026, 10, 10)
    )

    event_id = result["event_id"]

    payments = await get_event_payments(event_id)

    assert len(payments) == 2

    credit_card = next(
        payment
        for payment in payments
        if payment["payment_name"] == "Кредитная карта"
    )

    assert credit_card["planned_amount"] == 18000
    assert credit_card["actual_amount"] is None
    assert credit_card["status"] == "pending"

    saved = await save_actual_payment(
        payment_id=credit_card["id"],
        actual_amount=17642,
    )

    assert saved["success"] is True
    assert saved["payment_id"] == credit_card["id"]
    assert saved["payment_name"] == "Кредитная карта"
    assert saved["planned_amount"] == 18000
    assert saved["actual_amount"] == 17642
    assert saved["difference"] == -358
    assert saved["status"] == "paid"

    payments_after = await get_event_payments(event_id)

    credit_card_after = next(
        payment
        for payment in payments_after
        if payment["payment_name"] == "Кредитная карта"
    )

    assert credit_card_after["actual_amount"] == 17642
    assert credit_card_after["status"] == "paid"


@pytest.mark.asyncio
async def test_actual_payment_can_be_different_from_plan():
    await init_db()
    await setup()

    result = await start_income_event(
        date(2026, 10, 10)
    )

    payments = await get_event_payments(
        result["event_id"]
    )

    car_payment = next(
        payment
        for payment in payments
        if payment["payment_name"] == "Кредит на машину"
    )

    saved = await save_actual_payment(
        payment_id=car_payment["id"],
        actual_amount=14983,
    )

    assert saved["success"] is True
    assert saved["planned_amount"] == 15000
    assert saved["actual_amount"] == 14983
    assert saved["difference"] == -17
