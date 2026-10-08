import pytest

from app import allocation


def test_distribute_amount_fills_categories_before_savings():
    budgets = [
        {
            "id": 1,
            "name": "Продукты",
            "remaining": 25000,
        },
        {
            "id": 2,
            "name": "Бензин",
            "remaining": 7000,
        },
        {
            "id": 3,
            "name": "Питомцы",
            "remaining": 6000,
        },
    ]

    result = allocation.distribute_amount(
        amount=10000,
        category_budgets=budgets,
        savings_remaining=23000,
    )

    assert result["savings"] == 0
    assert result["unallocated"] == 0

    total = sum(
        item["amount"]
        for item in result["categories"]
    )

    assert total == 10000


def test_distribute_amount_uses_savings_after_categories():
    budgets = [
        {
            "id": 1,
            "name": "Продукты",
            "remaining": 2000,
        },
    ]

    result = allocation.distribute_amount(
        amount=10000,
        category_budgets=budgets,
        savings_remaining=23000,
    )

    assert result["categories"] == [
        {
            "category_id": 1,
            "category": "Продукты",
            "amount": 2000,
        }
    ]

    assert result["savings"] == 8000
    assert result["unallocated"] == 0


def test_distribute_amount_respects_savings_limit():
    budgets = [
        {
            "id": 1,
            "name": "Продукты",
            "remaining": 0,
        },
    ]

    result = allocation.distribute_amount(
        amount=30000,
        category_budgets=budgets,
        savings_remaining=23000,
    )

    assert result["categories"] == []
    assert result["savings"] == 23000
    assert result["unallocated"] == 7000


def test_distribute_amount_returns_zero_for_non_positive_amount():
    budgets = [
        {
            "id": 1,
            "name": "Продукты",
            "remaining": 25000,
        },
    ]

    result = allocation.distribute_amount(
        amount=0,
        category_budgets=budgets,
        savings_remaining=23000,
    )

    assert result == {
        "categories": [],
        "savings": 0,
        "unallocated": 0,
    }


@pytest.mark.asyncio
async def test_get_monthly_budget_summary(monkeypatch):
    categories = [
        {
            "id": 1,
            "name": "Продукты",
            "monthly_limit": 25000,
        },
        {
            "id": 2,
            "name": "Бензин",
            "monthly_limit": 7000,
        },
    ]

    async def fake_get_categories():
        return categories

    async def fake_get_allocations(month):
        assert month == "2026-10"

        return {
            "categories": {
                1: 10000,
                2: 3000,
            },
            "savings": 5000,
        }

    async def fake_get_spent(category_id, month):
        assert month == "2026-10"

        if category_id == 1:
            return 2000

        if category_id == 2:
            return 1000

        return 0

    async def fake_get_savings_target():
        return 23000

    monkeypatch.setattr(
        allocation,
        "get_monthly_category_budgets",
        fake_get_categories,
    )

    monkeypatch.setattr(
        allocation,
        "get_monthly_allocation_totals",
        fake_get_allocations,
    )

    monkeypatch.setattr(
        allocation,
        "get_monthly_category_spent",
        fake_get_spent,
    )

    monkeypatch.setattr(
        allocation,
        "get_savings_target",
        fake_get_savings_target,
    )

    result = await allocation.get_monthly_budget_summary(
        month="2026-10"
    )

    assert result["month"] == "2026-10"
    assert result["life_budget"] == 32000
    assert result["allocated"] == 13000
    assert result["spent"] == 3000
    assert result["remaining_to_spend"] == 29000
    assert result["remaining_to_allocate"] == 19000
    assert result["savings_target"] == 23000
    assert result["savings_allocated"] == 5000
    assert result["savings_remaining"] == 18000
