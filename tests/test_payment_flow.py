from datetime import date

import pytest

from app.db import init_db
from app.setup import setup
from app.payment_flow import (
    get_current_balance,
    start_income_event,
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
