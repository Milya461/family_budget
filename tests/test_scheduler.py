from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import web_push


@pytest.mark.asyncio
async def test_daily_web_reminder_is_saved_without_subscribed_devices(monkeypatch):
    monkeypatch.setattr(
        web_push,
        "ensure_web_push_tables",
        AsyncMock(),
    )
    monkeypatch.setattr(
        web_push,
        "get_moscow_today",
        lambda: date(2026, 11, 19),
    )
    monkeypatch.setattr(
        web_push,
        "fetch_one",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        web_push,
        "fetch_all",
        AsyncMock(return_value=[]),
    )
    execute = AsyncMock()
    monkeypatch.setattr(web_push, "execute", execute)

    await web_push.send_daily_web_push(SimpleNamespace())

    execute.assert_awaited_once()
    assert "INSERT INTO DAILY_EXPENSE_CHECKS" in (
        execute.await_args.args[0].upper()
    )
    assert execute.await_args.args[1:] == ("2026-11-19", "pending")


@pytest.mark.asyncio
async def test_daily_web_reminder_does_not_repeat_for_same_date(monkeypatch):
    monkeypatch.setattr(
        web_push,
        "ensure_web_push_tables",
        AsyncMock(),
    )
    monkeypatch.setattr(
        web_push,
        "get_moscow_today",
        lambda: date(2026, 11, 19),
    )
    monkeypatch.setattr(
        web_push,
        "fetch_one",
        AsyncMock(return_value={
            "check_date": "2026-11-19",
            "status": "reminded",
        }),
    )
    fetch_all = AsyncMock()
    monkeypatch.setattr(web_push, "fetch_all", fetch_all)
    execute = AsyncMock()
    monkeypatch.setattr(web_push, "execute", execute)

    await web_push.send_daily_web_push(SimpleNamespace())

    fetch_all.assert_not_awaited()
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_daily_reminder_can_be_acknowledged_in_web_app(monkeypatch):
    monkeypatch.setattr(
        web_push,
        "ensure_web_push_tables",
        AsyncMock(),
    )
    monkeypatch.setattr(
        web_push,
        "get_moscow_today",
        lambda: date(2026, 11, 19),
    )
    execute = AsyncMock()
    monkeypatch.setattr(web_push, "execute", execute)

    result = await web_push.set_daily_reminder_status("acknowledged")

    assert result == {
        "success": True,
        "date": "2026-11-19",
        "status": "acknowledged",
    }
    execute.assert_awaited_once()
    assert "ON CONFLICT(CHECK_DATE) DO UPDATE" in (
        execute.await_args.args[0].upper()
    )
    assert execute.await_args.args[1:] == (
        "2026-11-19",
        "acknowledged",
    )


def test_private_vapid_key_matches_configured_public_key():
    private_jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": "9rWYSkwPntrF0qE52h-0WMP1f5PouoCmh_4nPW1olhk",
        "y": "F6iWzeCnkm6uTnQPcMTtEVN_ay5TKQcoh-8yuxuQRPY",
        "d": "MVC1tpxRZQewXDssxINwPK5qNrqPSjBxL5QzoOvOMww",
    }
    assert web_push._private_key_matches_public(private_jwk)


def test_mismatched_private_vapid_key_is_rejected():
    private_jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "y": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "d": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    }
    assert not web_push._private_key_matches_public(private_jwk)
