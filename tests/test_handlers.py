from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import handlers


class FakeState:
    def __init__(self, data=None):
        self.data = data or {}
        self.set_state_calls = []
        self.clear_calls = 0

    async def clear(self):
        self.clear_calls += 1
        self.data = {}

    async def set_state(self, state):
        self.set_state_calls.append(state)

    async def update_data(self, **kwargs):
        self.data.update(kwargs)

    async def get_data(self):
        return dict(self.data)


class FakeMessage:
    def __init__(self, text="", telegram_id=123456):
        self.text = text
        self.from_user = SimpleNamespace(
            id=telegram_id,
            full_name="Тестовый пользователь",
        )
        self.answer = AsyncMock()


class FakeCallbackMessage:
    def __init__(self):
        self.edit_text = AsyncMock()
        self.answer = AsyncMock()


class FakeCallback:
    def __init__(self, data, telegram_id=123456):
        self.data = data
        self.from_user = SimpleNamespace(
            id=telegram_id,
            full_name="Тестовый пользователь",
        )
        self.message = FakeCallbackMessage()
        self.answer = AsyncMock()


def test_format_money():
    assert handlers.format_money(50000) == "50 000"
    assert handlers.format_money(1250) == "1 250"
    assert handlers.format_money(0) == "0"


@pytest.mark.asyncio
async def test_add_income_amount_records_income(monkeypatch):
    message = FakeMessage("50000")
    state = FakeState()

    monkeypatch.setattr(
        handlers,
        "add_income",
        AsyncMock(
            return_value={
                "success": True,
            }
        ),
    )

    monkeypatch.setattr(
        handlers,
        "get_current_balance",
        AsyncMock(return_value=50000),
    )

    await handlers.add_income_amount(
        message,
        state,
    )

    handlers.add_income.assert_awaited_once_with(
        telegram_id=123456,
        amount=50000,
        description="Доход",
    )

    handlers.get_current_balance.assert_awaited_once()

    assert state.clear_calls == 1

    message.answer.assert_awaited_once()

    text = message.answer.call_args.args[0]

    assert "Доход записан" in text
    assert "50 000 ₽" in text
    assert "Основной счёт: 50 000 ₽" in text


@pytest.mark.asyncio
async def test_add_income_amount_rejects_invalid_value(monkeypatch):
    message = FakeMessage("не число")
    state = FakeState()

    add_income_mock = AsyncMock()

    monkeypatch.setattr(
        handlers,
        "add_income",
        add_income_mock,
    )

    await handlers.add_income_amount(
        message,
        state,
    )

    add_income_mock.assert_not_awaited()

    message.answer.assert_awaited_once()

    text = message.answer.call_args.args[0]

    assert "Не смогла распознать сумму" in text


@pytest.mark.asyncio
async def test_expense_amount_saves_amount_and_shows_categories():
    message = FakeMessage("1250")
    state = FakeState()

    await handlers.add_expense_amount(
        message,
        state,
    )

    assert state.data["expense_amount"] == 1250
    assert message.answer.await_count == 1

    text = message.answer.call_args.args[0]

    assert "Выбери категорию расхода" in text


@pytest.mark.asyncio
async def test_select_expense_category_checks_expense(monkeypatch):
    callback = FakeCallback(
        "expense_category:Продукты"
    )

    state = FakeState(
        {
            "expense_amount": 1250,
        }
    )

    monkeypatch.setattr(
        handlers,
        "check_expense",
        AsyncMock(
            return_value={
                "success": True,
                "remaining": 23750,
                "exceeded": False,
            }
        ),
    )

    await handlers.select_expense_category(
        callback,
        state,
    )

    handlers.check_expense.assert_awaited_once_with(
        telegram_id=123456,
        amount=1250,
        category_name="Продукты",
    )

    assert state.data["expense_category"] == "Продукты"
    assert state.data["expense_remaining"] == 23750
    assert state.data["expense_exceeded"] is False

    assert (
        handlers.ExpenseStates.waiting_for_description
        in state.set_state_calls
    )

    callback.answer.assert_awaited_once()

    callback.message.edit_text.assert_awaited_once()

    text = callback.message.edit_text.call_args.args[0]

    assert "Продукты" in text
    assert "1 250 ₽" in text


@pytest.mark.asyncio
async def test_confirm_expense_saves_expense(monkeypatch):
    callback = FakeCallback(
        "confirm_expense"
    )

    state = FakeState(
        {
            "expense_amount": 1250,
            "expense_category": "Продукты",
            "expense_description": "Продукты на неделю",
        }
    )

    monkeypatch.setattr(
        handlers,
        "save_expense",
        AsyncMock(
            return_value={
                "success": True,
            }
        ),
    )

    monkeypatch.setattr(
        handlers,
        "get_current_balance",
        AsyncMock(return_value=48750),
    )

    await handlers.confirm_expense(
        callback,
        state,
    )

    handlers.save_expense.assert_awaited_once_with(
        telegram_id=123456,
        amount=1250,
        category_name="Продукты",
        description="Продукты на неделю",
    )

    handlers.get_current_balance.assert_awaited_once()

    assert state.clear_calls == 1

    callback.answer.assert_awaited_once_with(
        "Расход записан!"
    )

    callback.message.edit_text.assert_awaited_once()

    text = callback.message.edit_text.call_args.args[0]

    assert "Расход записан" in text
    assert "1 250 ₽" in text
    assert "Продукты" in text


@pytest.mark.asyncio
async def test_cancel_action_clears_state():
    callback = FakeCallback(
        "cancel_action"
    )

    state = FakeState(
        {
            "expense_amount": 1250,
        }
    )

    await handlers.cancel_action(
        callback,
        state,
    )

    assert state.clear_calls == 1
    assert state.data == {}

    callback.answer.assert_awaited_once_with(
        "Отменено"
    )

    callback.message.edit_text.assert_awaited_once_with(
        "❌ Действие отменено."
    )

    callback.message.answer.assert_awaited_once()

    text = callback.message.answer.call_args.args[0]

    assert "Главное меню" in text
