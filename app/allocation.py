from datetime import date, datetime, timedelta, timezone

from app.db import (
    execute,
    execute_many,
    fetch_all,
    fetch_value,
)
from app.rebalancing import ensure_rebalancing_tables


MOSCOW_TIMEZONE = timezone(timedelta(hours=3))


def get_moscow_today():
    return datetime.now(MOSCOW_TIMEZONE).date()


async def get_monthly_category_budgets(
    month: str | None = None,
):
    if month is None:
        month = get_moscow_today().strftime("%Y-%m")

    await ensure_rebalancing_tables()

    rows = await fetch_all(
        """
        SELECT
            c.id,
            c.name,
            COALESCE(
                mb.monthly_limit,
                c.monthly_limit,
                0
            ) AS monthly_limit
        FROM categories c
        LEFT JOIN monthly_category_budgets mb
          ON mb.category_id = c.id
         AND mb.month = ?
        WHERE c.is_active = 1
        ORDER BY c.id
        """,
        month,
    )

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "monthly_limit": float(row["monthly_limit"] or 0),
        }
        for row in rows
    ]


async def _get_category_budgets_for_month(month: str):
    try:
        return await get_monthly_category_budgets(month)
    except TypeError as error:
        message = str(error)

        if (
            "positional argument" not in message
            and "unexpected keyword argument" not in message
        ):
            raise

        return await get_monthly_category_budgets()


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


async def get_monthly_allocation_totals(month: str):
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
        month = get_moscow_today().strftime("%Y-%m")

    categories = await _get_category_budgets_for_month(month)
    allocations = await get_monthly_allocation_totals(month)

    result = []

    for category in categories:
        spent = await get_monthly_category_spent(
            category_id=category["id"],
            month=month,
        )

        already_allocated = allocations["categories"].get(
            category["id"],
            0,
        )

        remaining_to_allocate = max(
            category["monthly_limit"]
            - max(
                float(already_allocated or 0),
                float(spent or 0),
            ),
            0,
        )

        available_to_spend = max(
            already_allocated - spent,
            0,
        )

        result.append(
            {
                "id": category["id"],
                "name": category["name"],
                "monthly_limit": category["monthly_limit"],
                "spent": spent,
                "already_allocated": already_allocated,
                "remaining": remaining_to_allocate,
                "remaining_to_allocate": remaining_to_allocate,
                "available_to_spend": available_to_spend,
            }
        )

    savings_target = await get_savings_target()
    savings_allocated = allocations["savings"]

    return {
        "month": month,
        "categories": result,
        "savings_target": savings_target,
        "savings_allocated": savings_allocated,
        "savings_remaining": max(
            savings_target - savings_allocated,
            0,
        ),
    }


async def get_monthly_budget_summary(
    month: str | None = None,
):
    if month is None:
        month = get_moscow_today().strftime("%Y-%m")

    categories = await _get_category_budgets_for_month(month)
    allocations = await get_monthly_allocation_totals(month)

    life_budget = sum(
        category["monthly_limit"]
        for category in categories
    )

    allocated = sum(allocations["categories"].values())
    spent = 0

    for category in categories:
        spent += await get_monthly_category_spent(
            category_id=category["id"],
            month=month,
        )

    savings_target = await get_savings_target()
    savings_allocated = allocations["savings"]

    return {
        "month": month,
        "life_budget": life_budget,
        "allocated": allocated,
        "spent": spent,
        "remaining_to_spend": max(life_budget - spent, 0),
        "remaining_to_allocate": max(life_budget - allocated, 0),
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

    amount_for_categories = min(amount, category_total)
    result_categories = []

    if amount_for_categories > 0 and category_total > 0:
        distributed = 0

        for index, category in enumerate(available_categories):
            category_remaining = category["remaining"]

            if index == len(available_categories) - 1:
                allocation = amount_for_categories - distributed
            else:
                allocation = round(
                    amount_for_categories
                    * category_remaining
                    / category_total,
                    2,
                )

            allocation = min(allocation, category_remaining)

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
        "unallocated": max(remaining_amount, 0),
    }


async def save_allocation(
    month: str,
    categories: list[dict],
    savings: float,
    source: str,
    allocation_date: date,
    allocation_key: str,
):
    statements = [
        (
            """
            INSERT OR IGNORE INTO allocation_batches (
                source_key,
                status
            )
            VALUES (?, 'pending')
            """,
            (allocation_key,),
        ),
        (
            """
            UPDATE allocation_batches
            SET status = 'processing'
            WHERE source_key = ?
              AND status = 'pending'
            """,
            (allocation_key,),
        ),
    ]

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
                SELECT ?, ?, ?, 0, ?, ?
                WHERE EXISTS (
                    SELECT 1
                    FROM allocation_batches
                    WHERE source_key = ?
                      AND status = 'processing'
                )
                """,
                (
                    month,
                    category["category_id"],
                    category["amount"],
                    source,
                    allocation_date.isoformat(),
                    allocation_key,
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
                SELECT ?, NULL, 0, ?, 'savings', ?
                WHERE EXISTS (
                    SELECT 1
                    FROM allocation_batches
                    WHERE source_key = ?
                      AND status = 'processing'
                )
                """,
                (
                    month,
                    savings,
                    allocation_date.isoformat(),
                    allocation_key,
                ),
            )
        )

        statements.append(
            (
                """
                UPDATE savings
                SET balance = balance + ?
                WHERE id = 1
                  AND EXISTS (
                      SELECT 1
                      FROM allocation_batches
                      WHERE source_key = ?
                        AND status = 'processing'
                  )
                """,
                (
                    savings,
                    allocation_key,
                ),
            )
        )

    statements.append(
        (
            """
            UPDATE allocation_batches
            SET status = 'done',
                completed_at = CURRENT_TIMESTAMP
            WHERE source_key = ?
              AND status = 'processing'
            """,
            (allocation_key,),
        )
    )

    await execute_many(statements)


async def get_available_cash_for_allocation(
    month: str,
    allocation_date: date | None = None,
):
    """
    Считает свободные деньги:
    остаток основного счёта минус суммы, уже выделенные
    категориям, и неоплаченные обязательства только на текущую
    дату распределения — 10-е или 25-е число.

    Не создаёт события доходов или обязательных платежей.
    Будущие обязательства не резервируются.
    """
    if allocation_date is None:
        allocation_date = get_moscow_today()

    totals = await fetch_all(
        """
        SELECT
            COALESCE(
                SUM(
                    CASE
                        WHEN operation_type = 'income'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            ) AS income,
            COALESCE(
                SUM(
                    CASE
                        WHEN operation_type = 'expense'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            ) AS expenses
        FROM operations
        """
    )

    if totals:
        main_account = (
            float(totals[0]["income"] or 0)
            - float(totals[0]["expenses"] or 0)
            - float(await get_savings_balance() or 0)
        )
    else:
        main_account = 0.0

    pending_payments = 0

    if allocation_date.day in (10, 25):
        pending_payments = await fetch_value(
            """
            SELECT COALESCE(SUM(mp.planned_amount), 0)
            FROM mandatory_payments AS mp
            JOIN salary_events AS se
              ON se.id = mp.salary_event_id
            WHERE mp.status != 'paid'
              AND substr(se.event_date, 1, 7) = ?
              AND se.planned_day = ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM operations AS o
                  WHERE o.operation_type = 'expense'
                    AND o.description = mp.payment_name
                    AND substr(o.operation_date, 1, 7) = ?
                    AND CAST(
                        substr(o.operation_date, 9, 2)
                        AS INTEGER
                    ) = se.planned_day
              )
            """,
            month,
            allocation_date.day,
            month,
        ) or 0

    allocations = await get_monthly_allocation_totals(month)
    reserved_categories = 0.0

    for category_id, allocated in allocations["categories"].items():
        spent = await get_monthly_category_spent(
            category_id,
            month,
        )

        reserved_categories += max(
            float(allocated or 0) - float(spent or 0),
            0,
        )

    return max(
        main_account
        - float(pending_payments or 0)
        - reserved_categories,
        0,
    )


async def allocate_income_remainder(
    amount: float,
    allocation_date: date | None = None,
    allocation_key: str | None = None,
):
    if amount <= 0:
        return {
            "success": True,
            "amount": 0,
            "categories": [],
            "savings": 0,
            "unallocated": 0,
            "already_allocated": False,
        }

    if allocation_date is None:
        allocation_date = get_moscow_today()

    month = allocation_date.strftime("%Y-%m")

    if allocation_key is None:
        allocation_key = (
            f"manual:{allocation_date.isoformat()}:"
            f"{amount:.2f}"
        )

    await execute(
        """
        CREATE TABLE IF NOT EXISTS allocation_batches (
            source_key TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        )
        """
    )

    existing = await fetch_value(
        """
        SELECT status
        FROM allocation_batches
        WHERE source_key = ?
        """,
        allocation_key,
    )

    if existing == "done":
        return {
            "success": True,
            "amount": amount,
            "month": month,
            "categories": [],
            "savings": 0,
            "unallocated": 0,
            "already_allocated": True,
        }

    budgets = await calculate_remaining_monthly_budgets(month)

    available_cash = await get_available_cash_for_allocation(
        month,
        allocation_date,
    )
    amount_to_allocate = min(float(amount), available_cash)

    distribution = distribute_amount(
        amount=amount_to_allocate,
        category_budgets=budgets["categories"],
        savings_remaining=budgets["savings_remaining"],
    )

    await save_allocation(
        month=month,
        categories=distribution["categories"],
        savings=distribution["savings"],
        source=allocation_key,
        allocation_date=allocation_date,
        allocation_key=allocation_key,
    )

    completed = await fetch_value(
        """
        SELECT status
        FROM allocation_batches
        WHERE source_key = ?
        """,
        allocation_key,
    )

    if completed != "done":
        return {
            "success": False,
            "error": "Не удалось завершить распределение дохода.",
            "amount": amount,
            "already_allocated": False,
        }

    return {
        "success": True,
        "amount": amount,
        "allocated_amount": amount_to_allocate,
        "available_cash": available_cash,
        "month": month,
        "categories": distribution["categories"],
        "savings": distribution["savings"],
        "unallocated": distribution["unallocated"],
        "already_allocated": False,
    }
