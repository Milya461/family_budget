from datetime import date

import pytest
import pytest_asyncio

from app import db
from app.db import init_db
from app.setup import setup
from app.payment_flow import (
    get_current_balance,
    record_actual_income,
    record_actual_payment,
    start_income_event,
)
from app.payments import get_event_payments
from app.budget import get_monthly_report
from app.allocation import get_monthly_budget_summary


@pytest_asyncio.fixture(autouse=True)
async def clean_database(tmp_path, monkeypatch):
    test_db = tmp_path / "test_family_budget.db"

    monkeypatch.setattr(
        db,
        "DB_PATH",
        test_db,
    )

    import app.payment_flow
    import app.payments
    import app.setup
    import app.budget
    import app.allocation

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

    monkeypatch.setattr(
        app.budget,
        "DB_PATH",
        test_db,
    )

    monkeypatch.setattr(
        app.allocation.db,
        "DB_PATH",
        test_db,
    )

    await init_db()
    await setup()


async def create_test_user():
    async with db.aiosqlite.connect(
        db.DB_PATH
    ) as connection:
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


async def record_income_and_payments(
    event_date,
    actual_income,
    payments,
):
    income = await start_income_event(
        event_date
    )

    recorded_income = await record_actual_income(
        event_id=income["event_id"],
        actual_income=actual_income,
        actual_date=event_date,
    )

    assert recorded_income["success"] is True

    event_payments = await get_event_payments(
        income["event_id"]
    )

    for payment_name, actual_amount in payments.items():
        payment = next(
            payment
            for payment in event_payments
            if payment["payment_name"]
            == payment_name
        )

        saved = await record_actual_payment(
            payment_id=payment["id"],
            actual_amount=actual_amount,
        )

        assert saved["success"] is True

    return income


@pytest.mark.asyncio
async def test_full_monthly_budget_flow():
    """
    Полный сценарий месяца.

    Доходы:

    10 число  — 50 000 ₽
    15 число  — 27 500 ₽
    25 число  — 45 000 ₽
    30 число  — 27 500 ₽

    Всего доходов:
    150 000 ₽.

    Обязательные платежи:

    Кредитная карта — 18 000 ₽
    Машина          — 15 000 ₽
    Машина          — 15 000 ₽
    Ипотека         — 9 000 ₽
    Коммуналка      — 10 000 ₽

    Всего:
    67 000 ₽.

    После обязательных платежей:

    150 000 - 67 000 = 83 000 ₽.

    Из них:

    60 000 ₽ — виртуальные бюджеты жизни.
    23 000 ₽ — физически в копилку.

    Поэтому реальные деньги на основном счёте:

    150 000
    - 67 000
    - 23 000
    = 60 000 ₽.

    Виртуальное распределение 60 000 ₽
    основной счёт не уменьшает.
    """

    await create_test_user()

    # 10 октября.
    await record_income_and_payments(
        event_date=date(2026, 10, 10),
        actual_income=50000,
        payments={
            "Кредитная карта": 18000,
            "Кредит на машину": 15000,
        },
    )

    # 15 октября.
    await record_income_and_payments(
        event_date=date(2026, 10, 15),
        actual_income=27500,
        payments={},
    )

    # 25 октября.
    await record_income_and_payments(
        event_date=date(2026, 10, 25),
        actual_income=45000,
        payments={
            "Кредит на машину": 15000,
            "Ипотека": 9000,
            "Коммунальные услуги": 10000,
        },
    )

    # 30 октября.
    await record_income_and_payments(
        event_date=date(2026, 10, 30),
        actual_income=27500,
        payments={},
    )

    report = await get_monthly_report(
        month="2026-10"
    )

    budget = await get_monthly_budget_summary(
        month="2026-10"
    )

    # -------------------------------------------------
    # Доходы.
    # -------------------------------------------------

    assert report["month_income"] == 150000

    # -------------------------------------------------
    # Обязательные платежи.
    # -------------------------------------------------

    assert report["credit_expenses"] == 48000

    assert report["mortgage_expenses"] == 9000

    assert report["utilities_expenses"] == 10000

    assert report["mandatory_expenses"] == 67000

    # -------------------------------------------------
    # Бюджет жизни.
    # -------------------------------------------------

    assert report["life_budget"] == 60000

    assert budget["life_budget"] == 60000

    assert report["category_allocations"] == 60000

    assert budget["allocated"] == 60000

    # -------------------------------------------------
    # Реальные расходы на жизнь.
    # -------------------------------------------------

    assert report["life_expenses"] == 0

    assert budget["spent"] == 0

    assert budget["remaining_to_spend"] == 60000

    assert budget["remaining_to_allocate"] == 0

    # -------------------------------------------------
    # Накопления.
    # -------------------------------------------------

    assert report["monthly_savings"] == 23000

    assert report["savings_target"] == 23000

    assert report["savings_remaining"] == 0

    assert report["savings_balance"] == 23000

    # -------------------------------------------------
    # Реальный основной счёт.
    # -------------------------------------------------

    assert report["main_account"] == 60000

    balance = await get_current_balance()

    assert balance == 60000

    # -------------------------------------------------
    # Виртуальное распределение
    # не считается расходом.
    # -------------------------------------------------

    assert report["month_expenses"] == 67000

    assert report["total_expenses"] == 67000

    # -------------------------------------------------
    # Проверяем все категории.
    # -------------------------------------------------

    total_category_allocations = sum(
        category["allocated"]
        for category in report["categories"]
    )

    assert total_category_allocations == 60000

    total_category_limits = sum(
        category["limit"]
        for category in report["categories"]
    )

    assert total_category_limits == 60000

    for category in report["categories"]:
        assert (
            category["allocated"]
            <= category["limit"]
        )

    for category in report["categories"]:
        assert category["spent"] == 0

        assert (
            category["allocated"]
            == category["limit"]
        )

    # -------------------------------------------------
    # Финальная арифметическая проверка.
    # -------------------------------------------------

    assert (
        report["month_income"]
        - report["mandatory_expenses"]
        - report["monthly_savings"]
        == report["main_account"]
    )

    assert (
        report["main_account"]
        == report["life_budget"]
    )
