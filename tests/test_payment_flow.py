from datetime import date

import pytest
import pytest_asyncio

from app import db
from app.db import init_db
from app.setup import setup
from app.payment_flow import (
    find_income_event,
    get_current_balance,
    get_event_summary,
    record_actual_income,
    record_actual_payment,
    start_early_income_event,
    start_income_event,
)
from app.payments import (
    get_event,
    get_event_payments,
    save_actual_payment,
)


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


@pytest.mark.asyncio
async def test_start_income_event():
    result = await start_income_event(
        date(2026, 10, 10)
    )

    assert result["planned_income"] == 50000

    assert len(result["income_plans"]) == 1

    assert (
        result["income_plans"][0]["name"]
        == "Зарплата мужа"
    )

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

    assert (
        result["income_plans"][0]["name"]
        == "Аванс пользователя"
    )


@pytest.mark.asyncio
async def test_current_balance():
    balance = await get_current_balance()

    assert balance >= 0


@pytest.mark.asyncio
async def test_save_actual_mandatory_payment():
    await create_test_user()

    result = await start_income_event(
        date(2026, 10, 10)
    )

    event_id = result["event_id"]

    payments = await get_event_payments(
        event_id
    )

    assert len(payments) == 2

    credit_card = next(
        payment
        for payment in payments
        if payment["payment_name"]
        == "Кредитная карта"
    )

    assert credit_card["planned_amount"] == 18000
    assert credit_card["actual_amount"] is None
    assert credit_card["status"] == "pending"

    saved = await save_actual_payment(
        payment_id=credit_card["id"],
        actual_amount=17642,
    )

    assert saved["success"] is True

    assert (
        saved["payment_id"]
        == credit_card["id"]
    )

    assert (
        saved["payment_name"]
        == "Кредитная карта"
    )

    assert saved["planned_amount"] == 18000
    assert saved["actual_amount"] == 17642
    assert saved["difference"] == -358
    assert saved["status"] == "paid"

    payments_after = await get_event_payments(
        event_id
    )

    credit_card_after = next(
        payment
        for payment in payments_after
        if payment["payment_name"]
        == "Кредитная карта"
    )

    assert (
        credit_card_after["actual_amount"]
        == 17642
    )

    assert (
        credit_card_after["status"]
        == "paid"
    )


@pytest.mark.asyncio
async def test_actual_payment_can_be_different_from_plan():
    await create_test_user()

    result = await start_income_event(
        date(2026, 10, 10)
    )

    payments = await get_event_payments(
        result["event_id"]
    )

    car_payment = next(
        payment
        for payment in payments
        if payment["payment_name"]
        == "Кредит на машину"
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
    await create_test_user()

    result = await start_income_event(
        date(2026, 10, 10)
    )

    payments = await get_event_payments(
        result["event_id"]
    )

    credit_card = next(
        payment
        for payment in payments
        if payment["payment_name"]
        == "Кредитная карта"
    )

    balance_before = await get_current_balance()

    saved = await save_actual_payment(
        payment_id=credit_card["id"],
        actual_amount=17642,
    )

    assert saved["success"] is True

    balance_after = await get_current_balance()

    assert (
        balance_after
        == balance_before - 17642
    )


@pytest.mark.asyncio
async def test_early_income_keeps_planned_day():
    early_date = date(2026, 10, 8)

    result = await start_early_income_event(
        actual_date=early_date,
        planned_day=10,
    )

    assert result["event_date"] == "2026-10-08"
    assert result["planned_day"] == 10
    assert result["planned_income"] == 50000


@pytest.mark.asyncio
async def test_early_income_is_recorded_once():
    early_date = date(2026, 10, 8)

    result = await start_early_income_event(
        actual_date=early_date,
        planned_day=10,
    )

    event_id = result["id"]

    await create_test_user()

    recorded = await record_actual_income(
        event_id=event_id,
        actual_income=50000,
        actual_date=early_date,
    )

    assert recorded["success"] is True
    assert recorded["actual_income"] == 50000

    assert (
        recorded["actual_date"]
        == "2026-10-08"
    )

    second_record = await record_actual_income(
        event_id=event_id,
        actual_income=50000,
        actual_date=date(2026, 10, 10),
    )

    assert second_record["success"] is False

    assert (
        "уже был записан"
        in second_record["error"]
    )


@pytest.mark.asyncio
async def test_planned_date_finds_early_income():
    early_date = date(2026, 10, 8)

    result = await start_early_income_event(
        actual_date=early_date,
        planned_day=10,
    )

    event_id = result["id"]

    await create_test_user()

    recorded = await record_actual_income(
        event_id=event_id,
        actual_income=50000,
        actual_date=early_date,
    )

    assert recorded["success"] is True

    found = await find_income_event(
        planned_day=10,
        month="2026-10",
    )

    assert found is not None
    assert found["id"] == event_id

    assert (
        found["event_date"]
        == "2026-10-08"
    )

    assert found["planned_day"] == 10
    assert found["actual_income"] == 50000

    assert (
        found["status"]
        == "income_received"
    )

    event = await get_event(event_id)

    assert event is not None
    assert event["planned_day"] == 10

    assert (
        event["event_date"]
        == "2026-10-08"
    )


@pytest.mark.asyncio
async def test_early_income_full_payment_flow():
    """
    Полный сценарий:

    8 октября:
    - зарплата мужа 50 000 ₽ пришла раньше;
    - плановая дата — 10 октября;
    - доход записан.

    Затем:
    - кредитная карта — 17 642 ₽;
    - кредит на машину — 14 983 ₽.

    После оплаты обоих платежей
    оставшиеся деньги должны быть переданы
    в распределение бюджета.
    """

    early_date = date(2026, 10, 8)

    await create_test_user()

    income = await start_early_income_event(
        actual_date=early_date,
        planned_day=10,
    )

    event_id = income["id"]

    assert (
        income["event_date"]
        == "2026-10-08"
    )

    assert income["planned_day"] == 10
    assert income["planned_income"] == 50000

    recorded_income = await record_actual_income(
        event_id=event_id,
        actual_income=50000,
        actual_date=early_date,
    )

    assert recorded_income["success"] is True

    payments = await get_event_payments(
        event_id
    )

    assert len(payments) == 2

    credit_card = next(
        payment
        for payment in payments
        if payment["payment_name"]
        == "Кредитная карта"
    )

    car_payment = next(
        payment
        for payment in payments
        if payment["payment_name"]
        == "Кредит на машину"
    )

    assert (
        credit_card["status"]
        == "pending"
    )

    assert (
        car_payment["status"]
        == "pending"
    )

    first_payment = await record_actual_payment(
        payment_id=credit_card["id"],
        actual_amount=17642,
    )

    assert first_payment["success"] is True
    assert first_payment["allocation"] is None

    second_payment = await record_actual_payment(
        payment_id=car_payment["id"],
        actual_amount=14983,
    )

    assert second_payment["success"] is True
    assert (
        second_payment["allocation"]
        is not None
    )

    summary = await get_event_summary(
        event_id
    )

    assert summary is not None

    assert (
        summary["event"]["actual_income"]
        == 50000
    )

    assert (
        summary["total_actual_payments"]
        == 32625
    )

    assert summary["remaining"] == 17375

    assert (
        summary["all_payments_paid"]
        is True
    )

    assert (
        second_payment["remaining"]
        == 17375
    )


@pytest.mark.asyncio
async def test_early_income_does_not_create_second_event_on_planned_date():
    """
    Если доход за 10 октября фактически
    пришёл 8 октября, поиск события 10 октября
    должен находить уже существующее событие
    от 8 октября.
    """

    early_date = date(2026, 10, 8)

    await create_test_user()

    early_income = await start_early_income_event(
        actual_date=early_date,
        planned_day=10,
    )

    event_id = early_income["id"]

    recorded = await record_actual_income(
        event_id=event_id,
        actual_income=50000,
        actual_date=early_date,
    )

    assert recorded["success"] is True

    planned_date_event = await find_income_event(
        planned_day=10,
        month="2026-10",
    )

    assert planned_date_event is not None

    assert (
        planned_date_event["id"]
        == event_id
    )

    assert (
        planned_date_event["event_date"]
        == "2026-10-08"
    )

    assert (
        planned_date_event["status"]
        == "income_received"
    )


@pytest.mark.asyncio
async def test_allocation_is_not_counted_as_expense():
    """
    Виртуальное распределение по категориям
    не должно уменьшать реальный баланс.

    50 000 ₽ доход
    - 18 000 ₽ кредитная карта
    - 15 000 ₽ машина
    = 17 000 ₽.

    Эти 17 000 ₽ распределяются виртуально
    по категориям, но остаются реальными деньгами
    на основном счёте.
    """

    await create_test_user()

    income = await start_income_event(
        date(2026, 10, 10)
    )

    recorded = await record_actual_income(
        event_id=income["event_id"],
        actual_income=50000,
        actual_date=date(2026, 10, 10),
    )

    assert recorded["success"] is True

    payments = await get_event_payments(
        income["event_id"]
    )

    credit_card = next(
        payment
        for payment in payments
        if payment["payment_name"]
        == "Кредитная карта"
    )

    car_payment = next(
        payment
        for payment in payments
        if payment["payment_name"]
        == "Кредит на машину"
    )

    await record_actual_payment(
        payment_id=credit_card["id"],
        actual_amount=18000,
    )

    final_payment = await record_actual_payment(
        payment_id=car_payment["id"],
        actual_amount=15000,
    )

    assert (
        final_payment["allocation"]
        is not None
    )

    balance = await get_current_balance()

    assert balance == 17000


@pytest.mark.asyncio
async def test_savings_reduces_main_account_balance():
    """
    Деньги, физически отправленные в копилку,
    должны уменьшать основной счёт.
    """

    await create_test_user()

    income = await start_income_event(
        date(2026, 10, 10)
    )

    recorded = await record_actual_income(
        event_id=income["event_id"],
        actual_income=100000,
        actual_date=date(2026, 10, 10),
    )

    assert recorded["success"] is True

    payments = await get_event_payments(
        income["event_id"]
    )

    for payment in payments:
        await record_actual_payment(
            payment_id=payment["id"],
            actual_amount=payment[
                "planned_amount"
            ],
        )

    from app.allocation import (
        get_savings_balance,
        save_allocation,
    )

    savings_before = await get_savings_balance()

    await save_allocation(
        month="2026-10",
        categories=[],
        savings=23000,
        source="test_savings",
    )

    savings_after = await get_savings_balance()

    assert (
        savings_after
        == savings_before + 23000
    )

    balance = await get_current_balance()

    # 100 000 ₽ доход
    # - 33 000 ₽ обязательные платежи
    # - 23 000 ₽ копилка
    # = 44 000 ₽ на основном счёте.
    assert balance == 44000
