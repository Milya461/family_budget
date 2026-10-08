@pytest.mark.asyncio
async def test_allocation_is_not_counted_as_expense():
    """
    Виртуальное распределение по категориям
    не должно уменьшать реальный баланс.
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

    assert final_payment["allocation"] is not None

    balance = await get_current_balance()

    # 50 000 доход
    # - 33 000 обязательные платежи
    # = 17 000 реальных денег.
    #
    # Виртуальное распределение этих 17 000
    # не должно уменьшать основной счёт,
    # если они не были отправлены в копилку.
    assert balance == 17000


@pytest.mark.asyncio
async def test_savings_reduces_main_account_balance():
    """
    Деньги, физически отправленные в копилку,
    должны исчезать с основного счёта.
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
            actual_amount=payment["planned_amount"],
        )

    from app.allocation import (
        allocate_income_remainder,
        get_savings_balance,
    )

    allocation = await allocate_income_remainder(
        amount=10000,
        allocation_date=date(2026, 10, 10),
    )

    assert allocation["savings"] == 0

    savings_before = await get_savings_balance()

    await allocate_income_remainder(
        amount=23000,
        allocation_date=date(2026, 10, 10),
    )

    savings_after = await get_savings_balance()

    assert savings_after == savings_before + 23000

    balance = await get_current_balance()

    # 100 000 доход
    # - 33 000 платежи
    # - 23 000 копилка
    # = 44 000 основной счёт.
    assert balance == 44000
