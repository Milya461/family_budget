import asyncio
import sys
import types
from unittest.mock import AsyncMock

# Importing Cloudflare's workers package outside Pyodide requires the JS runtime.
# The helper tested here only needs the Response symbol at import time.
workers_stub = types.ModuleType("workers")
workers_stub.Response = type("Response", (), {})
sys.modules["workers"] = workers_stub

from app import web_api


def test_category_expense_details_uses_complete_month_history(monkeypatch):
    operations = [
        {"id": 31, "amount": 1000, "description": "заправка", "operation_date": "2026-10-23"},
        {"id": 28, "amount": 3500, "description": "бензин", "operation_date": "2026-10-18"},
        {"id": 27, "amount": 2000, "description": "бензин", "operation_date": "2026-10-17"},
        {"id": 9, "amount": 5607.25, "description": "ранние заправки", "operation_date": "2026-10-03"},
    ]
    fetch_value = AsyncMock(side_effect=[2, 12107.25])
    fetch_all = AsyncMock(return_value=operations)
    monkeypatch.setattr(web_api, "fetch_value", fetch_value)
    monkeypatch.setattr(web_api, "fetch_all", fetch_all)

    result = asyncio.run(web_api._category_expense_details("Бензин", "2026-10"))

    assert result["category"] == "Бензин"
    assert result["month"] == "2026-10"
    assert result["total"] == 12107.25
    assert sum(item["amount"] for item in result["operations"]) == result["total"]
    assert len(result["operations"]) == 4

    query = fetch_all.await_args.args[0].upper()
    assert "LIMIT" not in query
    assert "OPERATION_TYPE = 'EXPENSE'" in query
    assert fetch_all.await_args.args[1:] == (2, "2026-10")
