from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import scheduler


@pytest.mark.asyncio
async def test_activity_reminder_skips_day_with_income_or_expense(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "ensure_reminder_tables",
        AsyncMock(),
    )
    monkeypatch.setattr(
        scheduler,
        "get_moscow_today",
        lambda: date(2026, 10, 27),
    )
    fetch_one = AsyncMock(return_value={"id": 42})
    monkeypatch.setattr(scheduler, "fetch_one", fetch_one)
    bot = SimpleNamespace(send_message=AsyncMock())

    await scheduler.daily_activity_check(bot)

    query = fetch_one.await_args.args[0].upper()
    assert "OPERATION_TYPE IN ('INCOME', 'EXPENSE')" in query
    assert fetch_one.await_args.args[1:] == ("2026-10-27",)
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_activity_reminder_sends_when_no_operations_exist(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "ensure_reminder_tables",
        AsyncMock(),
    )
    monkeypatch.setattr(
        scheduler,
        "get_moscow_today",
        lambda: date(2026, 10, 27),
    )
    fetch_one = AsyncMock(side_effect=[None, None])
    monkeypatch.setattr(scheduler, "fetch_one", fetch_one)
    monkeypatch.setattr(
        scheduler,
        "get_users",
        AsyncMock(return_value=[111, 222]),
    )
    execute = AsyncMock()
    monkeypatch.setattr(scheduler, "execute", execute)
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value={"ok": True}),
    )

    await scheduler.daily_activity_check(bot)

    assert bot.send_message.await_count == 2
    for call in bot.send_message.await_args_list:
        assert "дохода или расхода" in call.args[1]
        assert "зарплата 50000" in call.args[1]
    execute.assert_awaited_once()
    assert "INSERT OR IGNORE INTO DAILY_EXPENSE_CHECKS" in execute.await_args.args[0].upper()
    assert execute.await_args.args[1:] == ("2026-10-27",)


@pytest.mark.asyncio
async def test_activity_reminder_does_not_repeat_on_same_day(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "ensure_reminder_tables",
        AsyncMock(),
    )
    monkeypatch.setattr(
        scheduler,
        "get_moscow_today",
        lambda: date(2026, 10, 27),
    )
    fetch_one = AsyncMock(side_effect=[
        None,
        {"check_date": "2026-10-27"},
    ])
    monkeypatch.setattr(scheduler, "fetch_one", fetch_one)
    bot = SimpleNamespace(send_message=AsyncMock())

    await scheduler.daily_activity_check(bot)

    assert fetch_one.await_count == 2
    bot.send_message.assert_not_awaited()
