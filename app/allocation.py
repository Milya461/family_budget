from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.db import (
    execute_many,
    fetch_all,
    fetch_value,
)


MOSCOW_TIMEZONE = ZoneInfo("Europe/Moscow")


def get_moscow_today():
    return datetime.now(
        MOSCOW_TIMEZONE
    ).date()


async def get_monthly_category_budgets():
    rows = await fetch_all(
        """
        SELECT
            id,
            name,
            monthly_limit
        FROM categories
        WHERE is_active = 1
        ORDER BY id
        """
    )

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "monthly_limit": row["monthly_limit"],
        }
        for row in rows
    ]


async def get_monthly_category_spent(
    category_id: int,
    month: str,
):
    value = await fetch_value(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM operations
        WHERE category_id = ?
          AND operation_type = 'expense'
          AND substr(operation_date, 1, 7) = ?
        """,
        category_id,
        month,
    )

    return value or 0


async def get_savings_target():
    value = await fetch_value(
        """
        SELECT monthly_target
        FROM savings
        WHERE id = 1
        """
    )

    return value if value is not None else 23000


async def get_savings_balance():
    value = await fetch_value(
        """
        SELECT balance
        FROM savings
        WHERE id = 1
        """
    )

    return value if value is not None else 0


async def get_monthly_allocation_totals(
    month: str,
):
    category_rows = await fetch_all(
        """
        SELECT
            category_id,
            COALESCE(SUM(amount), 0) AS amount
        FROM monthly_allocations
        WHERE month = ?
          AND category_id IS NOT NULL
        GROUP BY category_id
        """,
        month,
    )

    savings_value = await fetch_value(
        """
        SELECT COALESCE(SUM(savings_amount), 0)
        FROM monthly_allocations
        WHERE month = ?
          AND savings_amount > 0
        """,
        month,
    )

    return {
        "categories": {
            row["category_id"]: row["amount"]
            for row in category_rows
        },
        "savings": savings_value or 0,
    }


async def calculate_remaining_monthly_budgets(
    month: str | None = None,
):
    if month is None:
        month = get_moscow_today().strftime(
            "%Y-%m"
        )

    categories = await get_monthly_category_budgets()

    allocations = await get_monthly_allocation_totals(
        month
    )

    result = []

    for category in categories:
        spent = await get_monthly_category_spent(
            category_id=category["id"],
            month=month,
        )

        already_allocated = allocations[
            "categories"
        ].get(
            category["id"],
            0,
        )

        remaining_to_allocate = max(
            category["monthly_limit"]
            - already_allocated,
            0,
        )

        available_to_spend = max(
            already_allocated
            - spent,
            0,
        )

        result.append(
            {
                "id": category["id"],
                "name": category["name"],
                "monthly_limit": category[
                    "monthly_limit"
                ],
                "spent": spent,
                "already_allocated": (
                    already_allocated
                ),
                "remaining": (
                    remaining_to_allocate
                ),
                "remaining_to_allocate": (
                    remaining_to_allocate
                ),
                "available_to_spend": (
                    available_to_spend
                ),
            }
        )

    savings_target = await get_savings_target()

    savings_allocated = allocations[
        "savings"
    ]

    savings_remaining = max(
        savings_target
        - savings_allocated,
        0,
    )

    return {
        "month": month,
        "categories": result,
        "savings_target": savings_target,
        "savings_allocated": savings_allocated,
        "savings_remaining": savings_remaining,
    }


async def get_monthly_budget_summary(
    month: str | None = None,
):
    if month is None:
        month = get_moscow_today().strftime(
            "%Y-%m"
        )

    categories = await get_monthly_category_budgets()

    allocations = await get_monthly_allocation_totals(
        month
    )

    life_budget = sum(
        category["monthly_limit"]
        for category in categories
    )

    allocated = sum(
        allocations["categories"].values()
    )

    spent = 0

    for category in categories:
        spent += await get_monthly_category_spent(
            category_id=category["id"],
            month=month,
        )

    savings_target = await get_savings_target()

    savings_allocated = allocations[
        "savings"
    ]

    return {
        "month": month,
        "life_budget": life_budget,
        "allocated": allocated,
        "spent": spent,
        "remaining_to_spend": max(
            life_budget - spent,
            0,
        ),
        "remaining_to_allocate": max(
            life_budget - allocated,
            0,
        ),
        "savings_target": savings_target,
        "savings_allocated": savings_allocated,
        "savings_remaining": max(
            savings_target - savings_allocated,
            0,
        ),
    }


def distribute_amount(
    amount: float,
    category_budgets: list[dict],
    savings_remaining: float,
):
    if amount <= 0:
        return {
            "categories": [],
            "savings": 0,
            "unallocated": 0,
        }

    available_categories = [
        category
        for category in category_budgets
        if category["remaining"] > 0
    ]

    category_total = sum(
        category["remaining"]
        for category in available_categories
    )

    amount_for_categories = min(
        amount,
        category_total,
    )

    result_categories = []

    if (
        amount_for_categories > 0
        and category_total > 0
    ):
        distributed = 0

        for index, category in enumerate(
            available_categories
        ):
            category_remaining = category[
                "remaining"
            ]

            if index == len(
                available_categories
            ) - 1:
                allocation = (
                    amount_for_categories
                    - distributed
                )
            else:
                allocation = round(
                    amount_for_categories
                    * category_remaining
                    / category_total,
                    2,
                )

            allocation = min(
                allocation,
                category_remaining,
            )

            if allocation <= 0:
                continue

            result_categories.append(
                {
                    "category_id": category["id"],
                    "category": category["name"],
                    "amount": allocation,
                }
            )

            distributed += allocation

    allocated_to_categories = sum(
        category["amount"]
        for category in result_categories
    )

    remaining_amount = max(
        amount - allocated_to_categories,
        0,
    )

    savings_allocation = min(
        savings_remaining,
        remaining_amount,
    )

    remaining_amount -= savings_allocation

    return {
        "categories": result_categories,
        "savings": savings_allocation,
        "unallocated": max(
            remaining_amount,
            0,
        ),
    }


async def save_allocation(
    month: str,
    categories: list[dict],
    savings: float,
    source: str,
    allocation_date: date,
):
    statements = []

    for category in categories:
        if category["amount"] <= 0:
            continue

        statements.append(
            (
                """
                INSERT INTO monthly_allocations (
                    month,
                    category_id,
                    amount,
                    savings_amount,
                    source,
                    allocation_date
                )
                VALUES (?, ?, ?, 0, ?, ?)
                """,
                (
                    month,
                    category["category_id"],
                    category["amount"],
                    source,
                    allocation_date.isoformat(),
                ),
            )
        )

    if savings > 0:
        statements.append(
            (
                """
                INSERT INTO monthly_allocations (
                    month,
                    category_id,
                    amount,
                    savings_amount,
                    source,
                    allocation_date
                )
                VALUES (?, NULL, 0, ?, 'savings', ?)
                """,
                (
                    month,
                    savings,
                    allocation_date.isoformat(),
                ),
            )
        )

        statements.append(
            (
                """
                UPDATE savings
                SET balance = balance + ?
                WHERE id = 1
                """,
                (savings,),
            )
        )

    if statements:
        await execute_many(statements)


async def allocate_income_remainder(
    amount: float,
    allocation_date: date | None = None,
):
    if amount <= 0:
        return {
            "success": True,
            "amount": 0,
            "categories": [],
            "savings": 0,
            "unallocated": 0,
        }

    if allocation_date is None:
        allocation_date = get_moscow_today()

    month = allocation_date.strftime(
        "%Y-%m"
    )

    budgets = await calculate_remaining_monthly_budgets(
        month
    )

    distribution = distribute_amount(
        amount=amount,
        category_budgets=budgets["categories"],
        savings_remaining=budgets[
            "savings_remaining"
        ],
    )

    await save_allocation(
        month=month,
        categories=distribution["categories"],
        savings=distribution["savings"],
        source=(
            f"income_{allocation_date.isoformat()}"
        ),
        allocation_date=allocation_date,
    )

    return {
        "success": True,
        "amount": amount,
        "month": month,
        "categories": distribution["categories"],
        "savings": distribution["savings"],
        "unallocated": distribution["unallocated"],
    }
