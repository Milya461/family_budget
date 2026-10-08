from datetime import date

import pytest
import pytest_asyncio

from app import db
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


@pytest_asyncio.fixture(autouse=True)
async def clean_database(tmp_path, monkeypatch):
    test_db = tmp_path / "test_family_budget.db"

    monkeypatch.setattr(db, "DB_PATH", test_db)

    import app.payment_flow
    import app.payments
    import app.setup

    monkeypatch.setattr(
        app.payment_flow,
        "DB_PATH",
        test_db,
    )
    monkeypatch.setattr(
        app.payments,
        "DB_PATH",
        test_db,
    )
    monkeypatch.setattr(
        app.setup,
        "DB_PATH",
        test_db,
    )

    await init_db()
    await setup()


@pytest.mark.asyncio
async def test_start_income_event():
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
    result = await start_income_event(
        date(2026, 10, 31)
    )

    assert result["planned_income"] == 27500

    assert result["income_plans"][0]["name"] == "Аванс пользователя"


@pytest.mark.asyncio
async def test_current_balance():
    balance = await get_current_balance()

    assert balance >= 0


@pytest.mark.asyncio
async def test_save_actual_mandatory_payment():
    async with db.aiosqlite.connect(db.DB_PATH) as connection:
        await connection.execute(
            """
            INSERT INTO users (
                telegram_id,
                name
            )
            VALUES (?, ?)
            """,
            (
                123456789,
                "Тестовый пользователь",
            ),
        )
        await connection.commit()

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
    async with db.aiosqlite.connect(db.DB_PATH) as connection:
        await connection.execute(
            """
            INSERT INTO users (
                telegram_id,
                name
            )
            VALUES (?, ?)
            """,
            (
                123456789,
                "Тестовый пользователь",
            ),
        )
        await connection.commit()

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


@pytest.mark.asyncio
async def test_mandatory_payment_reduces_balance():
    async with db.aiosqlite.connect(db.DB_PATH) as connection:
        await connection.execute(
            """
            INSERT INTO users (
                telegram_id,
                name
            )
            VALUES (?, ?)
            """,
            (
                123456789,
                "Тестовый пользователь",
            ),
        )
        await connection.commit()

    result = await start_income_event(
        date(2026, 10, 10)
    )

    payments = await get_event_payments(
        result["event_id"]
    )

    credit_card = next(
        payment
        for payment in payments
        if payment["payment_name"] == "Кредитная карта"
    )

    balance_before = await get_current_balance()

    saved = await save_actual_payment(
        payment_id=credit_card["id"],
        actual_amount=17642,
    )

    assert saved["success"] is True

    balance_after = await get_current_balance()

    assert balance_after == balance_before - 17642
