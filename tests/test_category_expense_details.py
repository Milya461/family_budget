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



def test_cancel_selected_income_removes_its_allocations(monkeypatch):
    operation = {
        "id": 77,
        "operation_type": "income",
        "amount": 50000,
        "category_id": None,
        "debt_id": None,
        "description": "Зарплата",
        "operation_date": "2026-10-10",
    }
    fetch_one = AsyncMock(side_effect=[operation, None])
    fetch_all = AsyncMock(return_value=[])
    execute_many = AsyncMock()
    monkeypatch.setattr(web_api, "ensure_rebalancing_tables", AsyncMock())
    monkeypatch.setattr(web_api, "fetch_one", fetch_one)
    monkeypatch.setattr(web_api, "fetch_all", fetch_all)
    monkeypatch.setattr(web_api, "execute_many", execute_many)

    result = asyncio.run(web_api._cancel_operation(77))

    assert result["success"] is True
    assert result["operation_type"] == "income"
    statements = execute_many.await_args.args[0]
    assert "DELETE FROM monthly_allocations WHERE source = ?" in statements[0][0]
    assert statements[0][1] == ("income:77",)
    assert "DELETE FROM allocation_batches WHERE source_key = ?" in statements[1][0]
    assert "DELETE FROM operations" in statements[-1][0]


def test_cancel_selected_expense_removes_stock_marker_and_operation(monkeypatch):
    operation = {
        "id": 88,
        "operation_type": "expense",
        "amount": 1290,
        "category_id": 1,
        "debt_id": None,
        "description": "Продукты",
        "operation_date": "2026-10-23",
    }
    fetch_one = AsyncMock(side_effect=[operation, None])
    fetch_all = AsyncMock(return_value=[])
    execute_many = AsyncMock()
    monkeypatch.setattr(web_api, "ensure_rebalancing_tables", AsyncMock())
    monkeypatch.setattr(web_api, "fetch_one", fetch_one)
    monkeypatch.setattr(web_api, "fetch_all", fetch_all)
    monkeypatch.setattr(web_api, "execute_many", execute_many)

    result = asyncio.run(web_api._cancel_operation(88))

    assert result["success"] is True
    assert result["operation_type"] == "expense"
    statements = execute_many.await_args.args[0]
    assert "DELETE FROM stock_purchases WHERE operation_id = ?" in statements[0][0]
    assert statements[0][1] == (88,)
    assert "DELETE FROM operations" in statements[1][0]


def test_cancel_selected_mandatory_payment_reopens_payment(monkeypatch):
    operation = {
        "id": 99,
        "operation_type": "expense",
        "amount": 10000,
        "category_id": None,
        "debt_id": None,
        "description": "Коммунальные услуги",
        "operation_date": "2026-10-25",
    }
    candidates = [{"id": 12, "payment_name": "Коммунальные услуги", "actual_amount": 10000, "debt_id": None}]
    fetch_one = AsyncMock(side_effect=[operation, None])
    fetch_all = AsyncMock(return_value=candidates)
    execute_many = AsyncMock()
    monkeypatch.setattr(web_api, "ensure_rebalancing_tables", AsyncMock())
    monkeypatch.setattr(web_api, "fetch_one", fetch_one)
    monkeypatch.setattr(web_api, "fetch_all", fetch_all)
    monkeypatch.setattr(web_api, "execute_many", execute_many)

    result = asyncio.run(web_api._cancel_operation(99))

    assert result["success"] is True
    statements = execute_many.await_args.args[0]
    assert "UPDATE mandatory_payments" in statements[1][0]
    assert statements[1][1] == (12,)
    assert "status = 'pending'" in statements[1][0]
    assert "EXISTS" in statements[2][0]
    assert statements[2][1] == (99, 12)


def test_cancel_selected_expense_refuses_ambiguous_payment(monkeypatch):
    operation = {
        "id": 100,
        "operation_type": "expense",
        "amount": 15000,
        "category_id": None,
        "debt_id": 2,
        "description": "Кредит на машину",
        "operation_date": "2026-10-25",
    }
    candidates = [
        {"id": 12, "payment_name": "Кредит на машину", "actual_amount": 15000, "debt_id": 2},
        {"id": 13, "payment_name": "Кредит на машину", "actual_amount": 15000, "debt_id": 2},
    ]
    fetch_one = AsyncMock(return_value=operation)
    fetch_all = AsyncMock(return_value=candidates)
    execute_many = AsyncMock()
    monkeypatch.setattr(web_api, "ensure_rebalancing_tables", AsyncMock())
    monkeypatch.setattr(web_api, "fetch_one", fetch_one)
    monkeypatch.setattr(web_api, "fetch_all", fetch_all)
    monkeypatch.setattr(web_api, "execute_many", execute_many)

    try:
        asyncio.run(web_api._cancel_operation(100))
    except ValueError as error:
        assert "несколько" in str(error)
    else:
        raise AssertionError("Expected an ambiguous payment to be rejected")

    execute_many.assert_not_awaited()



def test_cancel_selected_expense_without_matched_payment_still_cancels(monkeypatch):
    operation = {
        "id": 101,
        "operation_type": "expense",
        "amount": 18000,
        "category_id": None,
        "debt_id": None,
        "description": "Кредитная карта",
        "operation_date": "2026-10-10",
    }
    fetch_one = AsyncMock(side_effect=[operation, None])
    fetch_all = AsyncMock(return_value=[])
    execute_many = AsyncMock()
    monkeypatch.setattr(web_api, "ensure_rebalancing_tables", AsyncMock())
    monkeypatch.setattr(web_api, "fetch_one", fetch_one)
    monkeypatch.setattr(web_api, "fetch_all", fetch_all)
    monkeypatch.setattr(web_api, "execute_many", execute_many)

    result = asyncio.run(web_api._cancel_operation(101))

    assert result["success"] is True
    statements = execute_many.await_args.args[0]
    assert any("DELETE FROM operations" in sql for sql, _ in statements)
    assert not any("UPDATE mandatory_payments" in sql for sql, _ in statements)


def test_duplicate_utility_cleanup_keeps_top_and_removes_older_once(monkeypatch):
    candidates = [
        {"id": 202, "amount": 18195.60, "operation_date": "2026-10-25"},
        {"id": 199, "amount": 18195.00, "operation_date": "2026-10-24"},
    ]
    fetch_value = AsyncMock(return_value=None)
    fetch_all = AsyncMock(return_value=candidates)
    execute = AsyncMock()
    execute_many = AsyncMock()
    monkeypatch.setattr(web_api, "fetch_value", fetch_value)
    monkeypatch.setattr(web_api, "fetch_all", fetch_all)
    monkeypatch.setattr(web_api, "execute", execute)
    monkeypatch.setattr(web_api, "execute_many", execute_many)

    asyncio.run(web_api._remove_known_duplicate_utility_expense())

    statements = execute_many.await_args.args[0]
    assert statements[0][1] == (199,)
    assert "DELETE FROM operations" in statements[0][0]
    assert statements[1][1] == ("cleanup_duplicate_utility_expense_2026_10_v3",)
    query = fetch_all.await_args.args[0]
    assert "LOWER(" not in query
    assert "ORDER BY operation_date DESC, id DESC" in query


def test_duplicate_utility_cleanup_leaves_single_row_and_can_retry(monkeypatch):
    fetch_value = AsyncMock(return_value=None)
    fetch_all = AsyncMock(return_value=[
        {"id": 202, "amount": 18195.60, "operation_date": "2026-10-25"}
    ])
    execute = AsyncMock()
    execute_many = AsyncMock()
    monkeypatch.setattr(web_api, "fetch_value", fetch_value)
    monkeypatch.setattr(web_api, "fetch_all", fetch_all)
    monkeypatch.setattr(web_api, "execute", execute)
    monkeypatch.setattr(web_api, "execute_many", execute_many)

    asyncio.run(web_api._remove_known_duplicate_utility_expense())

    execute_many.assert_not_awaited()
