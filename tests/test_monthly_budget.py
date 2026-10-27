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


def test_distribute_amount_does_not_auto_allocate_savings():
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

    # Накопления теперь пополняются только вручную.
    assert result["savings"] == 0
    assert result["unallocated"] == 8000


def test_distribute_amount_leaves_cash_unallocated_when_categories_are_full():
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
    # Свободные деньги не переводятся в копилку автоматически.
    assert result["savings"] == 0
    assert result["unallocated"] == 30000


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



def test_monthly_spent_includes_ordinary_expenses_without_category_id():
    from app.budget import summarize_month_expenses

    result = summarize_month_expenses([
        {"amount": 2500, "description": "продукты", "category_id": None, "debt_id": None, "debt_name": None},
        {"amount": 1800, "description": "корм котам", "category_id": 3, "debt_id": None, "debt_name": None},
        {"amount": 17300, "description": "Кредитная карта", "category_id": None, "debt_id": 1, "debt_name": "Кредитная карта"},
        {"amount": 9000, "description": "Ипотека", "category_id": None, "debt_id": 3, "debt_name": "Ипотека"},
        {"amount": 10000, "description": "Коммунальные услуги", "category_id": None, "debt_id": None, "debt_name": None},
    ])

    # Regular expenses only: categorized/uncategorized purchases remain,
    # debt-linked and explicitly described mandatory payments are excluded.
    assert result["life_expenses"] == 4300
    assert result["other_expenses"] == 2500


def test_monthly_spent_ignores_only_explicit_required_payments():
    from app.budget import summarize_month_expenses

    result = summarize_month_expenses([
        {"amount": 1000, "description": "покупка воды для котов", "category_id": None, "debt_id": None, "debt_name": None},
        {"amount": 1200, "description": "ремонт квартиры", "category_id": 4, "debt_id": None, "debt_name": None},
    ])

    assert result["life_expenses"] == 2200
    assert result["other_expenses"] == 1000



def test_life_expenses_are_all_monthly_expenses_minus_required_payments():
    from app.budget import calculate_life_expenses

    assert calculate_life_expenses(97519.51, 65496.00) == 32023.51
    assert calculate_life_expenses(0, 0) == 0
    assert calculate_life_expenses(100, 150) == 0



def test_monthly_spent_counts_categorized_ordinary_expense_even_if_debt_link_is_wrong():
    from app.budget import summarize_month_expenses

    result = summarize_month_expenses([
        {"amount": 1200, "description": "продукты", "category_id": 1, "debt_id": 2, "debt_name": "Кредит на машину"},
        {"amount": 800, "description": "бензин", "category_id": 2, "debt_id": 2, "debt_name": "Кредит на машину"},
        {"amount": 17300, "description": "Кредитная карта", "category_id": None, "debt_id": 1, "debt_name": "Кредитная карта"},
        {"amount": 9000, "description": "Ипотека", "category_id": None, "debt_id": None, "debt_name": None},
        {"amount": 10000, "description": "Коммунальные услуги", "category_id": None, "debt_id": None, "debt_name": None},
        {"amount": 450, "description": "такси", "category_id": None, "debt_id": None, "debt_name": None},
    ])

    assert result["life_expenses"] == 2450
    assert result["other_expenses"] == 450
