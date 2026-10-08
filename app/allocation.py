from datetime import date, datetime
from zoneinfo import ZoneInfo

import aiosqlite

from app.db import DB_PATH


MOSCOW_TIMEZONE = ZoneInfo("Europe/Moscow")


def get_moscow_today():
    return datetime.now(
        MOSCOW_TIMEZONE
    ).date()


async def get_monthly_category_budgets():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
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

        rows = await cursor.fetchall()

    return [
        {
            "id": row[0],
            "name": row[1],
            "monthly_limit": row[2],
        }
        for row in rows
    ]


async def get_monthly_category_spent(
    category_id: int,
    month: str,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM operations
            WHERE category_id = ?
              AND operation_type = 'expense'
              AND substr(operation_date, 1, 7) = ?
            """,
            (
                category_id,
                month,
            ),
        )

        row = await cursor.fetchone()

    return row[0] or 0


async def get_savings_target():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT monthly_target
            FROM savings
            WHERE id = 1
            """
        )

        row = await cursor.fetchone()

    return row[0] if row else 23000


async def get_savings_balance():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT balance
            FROM savings
            WHERE id = 1
            """
        )

        row = await cursor.fetchone()

    return row[0] if row else 0


async def get_monthly_allocation_totals(
    month: str,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                category_id,
                COALESCE(SUM(amount), 0)
            FROM monthly_allocations
            WHERE month = ?
              AND category_id IS NOT NULL
            GROUP BY category_id
            """,
            (month,),
        )

        category_rows = await cursor.fetchall()

        cursor = await db.execute(
            """
            SELECT
                COALESCE(SUM(amount), 0)
            FROM monthly_allocations
            WHERE month = ?
              AND category_id IS NULL
              AND debt_id IS NULL
              AND source = 'savings'
            """,
            (month,),
        )

        savings_row = await cursor.fetchone()

    return {
        "categories": {
            row[0]: row[1]
            for row in category_rows
        },
        "savings": (
            savings_row[0]
            if savings_row
            else 0
        ),
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

        remaining = max(
            category["monthly_limit"]
            - spent
            - already_allocated,
            0,
        )

        result.append(
            {
                "id": category["id"],
                "name": category["name"],
                "monthly_limit": category["monthly_limit"],
                "spent": spent,
                "already_allocated": already_allocated,
                "remaining": remaining,
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


def distribute_amount(
    amount: float,
    category_budgets: list[dict],
    savings_remaining: float,
):
    """
    Распределяет остаток после обязательных платежей.

    Порядок:
    1. Заполняются оставшиеся месячные бюджеты категорий.
    2. После категорий остаток отправляется в копилку.
    3. Сверх месячных целей деньги не распределяются.

    Важно:
    функция ничего не записывает в БД.
    Она только рассчитывает распределение.
    """

    if amount <= 0:
        return {
            "categories": [],
            "savings": 0,
            "unallocated": 0,
        }

    category_total = sum(
        category["remaining"]
        for category in category_budgets
    )

    total_available = (
        category_total
        + savings_remaining
    )

    amount_to_distribute = min(
        amount,
        total_available,
    )

    result_categories = []

    remaining_amount = amount_to_distribute

    for category in category_budgets:
        if remaining_amount <= 0:
            break

        category_remaining = category[
            "remaining"
        ]

        if category_remaining <= 0:
            continue

        allocation = min(
            category_remaining,
            remaining_amount,
        )

        result_categories.append(
            {
                "category_id": category["id"],
                "category": category["name"],
                "amount": allocation,
            }
        )

        remaining_amount -= allocation

    savings_allocation = min(
        savings_remaining,
        remaining_amount,
    )

    remaining_amount -= savings_allocation

    return {
        "categories": result_categories,
        "savings": savings_allocation,
        "unallocated": remaining_amount,
    }


async def save_allocation(
    month: str,
    categories: list[dict],
    savings: float,
    source: str,
):
    async with aiosqlite.connect(DB_PATH) as db:
        for category in categories:
            if category["amount"] <= 0:
                continue

            await db.execute(
                """
                INSERT INTO monthly_allocations (
                    month,
                    category_id,
                    debt_id,
                    amount,
                    source
                )
                VALUES (?, ?, NULL, ?, ?)
                """,
                (
                    month,
                    category["category_id"],
                    category["amount"],
                    source,
                ),
            )

        if savings > 0:
            await db.execute(
                """
                INSERT INTO monthly_allocations (
                    month,
                    category_id,
                    debt_id,
                    amount,
                    source
                )
                VALUES (?, NULL, NULL, ?, 'savings')
                """,
                (
                    month,
                    savings,
                ),
            )

            await db.execute(
                """
                UPDATE savings
                SET balance = balance + ?
                WHERE id = 1
                """,
                (
                    savings,
                ),
            )

        await db.commit()


async def allocate_income_remainder(
    amount: float,
    allocation_date: date | None = None,
):
    """
    Распределяет остаток после обязательных платежей.

    Например:

    Доход: 50 000 ₽
    Платежи: 17 642 + 14 983 ₽
    Остаток: 17 375 ₽

    Остаток распределяется между месячными
    категориями и копилкой.
    """

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
        source=f"income_{allocation_date.isoformat()}",
    )

    return {
        "success": True,
        "amount": amount,
        "month": month,
        "categories": distribution["categories"],
        "savings": distribution["savings"],
        "unallocated": distribution["unallocated"],
    }
