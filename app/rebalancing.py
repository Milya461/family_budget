from datetime import date, datetime, timedelta, timezone

from app.db import (
    execute,
    execute_many,
    fetch_all,
    fetch_value,
)


MOSCOW_TIMEZONE = timezone(timedelta(hours=3))


async def ensure_rebalancing_tables():
    await execute(
        """
        CREATE TABLE IF NOT EXISTS stock_purchases (
            operation_id INTEGER PRIMARY KEY,
            months INTEGER NOT NULL
                CHECK (months >= 1 AND months <= 24),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    await execute(
        """
        CREATE TABLE IF NOT EXISTS monthly_budget_rebalances (
            source_month TEXT PRIMARY KEY,
            target_month TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        )
        """
    )


def get_moscow_today():
    return datetime.now(MOSCOW_TIMEZONE).date()


def get_next_month(month):
    year, number = map(int, month.split("-"))

    if number == 12:
        return f"{year + 1:04d}-01"

    return f"{year:04d}-{number + 1:02d}"


def get_previous_month(month):
    year, number = map(int, month.split("-"))

    if number == 1:
        return f"{year - 1:04d}-12"

    return f"{year:04d}-{number - 1:02d}"


async def mark_stock_purchase(
    operation_id: int,
    months: int,
):
    if not isinstance(months, int) or not 1 <= months <= 24:
        return {
            "success": False,
            "error": "Срок запаса должен быть от 1 до 24 месяцев.",
        }

    await ensure_rebalancing_tables()

    await execute(
        """
        INSERT INTO stock_purchases (
            operation_id,
            months
        )
        VALUES (?, ?)
        ON CONFLICT(operation_id)
        DO UPDATE SET months = excluded.months
        """,
        operation_id,
        months,
    )

    return {
        "success": True,
        "operation_id": operation_id,
        "months": months,
    }


async def get_monthly_budget_total():
    value = await fetch_value(
        """
        SELECT value
        FROM bot_settings
        WHERE key = 'monthly_life_budget'
        """
    )

    if value is None:
        return 60000

    return float(value)


async def get_category_spending_for_rebalance(
    category_id: int,
    month: str,
):
    regular_spending = await fetch_value(
        """
        SELECT COALESCE(SUM(o.amount), 0)
        FROM operations o
        WHERE o.category_id = ?
          AND o.operation_type = 'expense'
          AND substr(o.operation_date, 1, 7) = ?
          AND NOT EXISTS (
              SELECT 1
              FROM stock_purchases sp
              WHERE sp.operation_id = o.id
          )
        """,
        category_id,
        month,
    ) or 0

    stock_spending = await fetch_value(
        """
        SELECT COALESCE(
            SUM(o.amount * 1.0 / sp.months),
            0
        )
        FROM operations o
        JOIN stock_purchases sp
          ON sp.operation_id = o.id
        WHERE o.category_id = ?
          AND o.operation_type = 'expense'
          AND substr(o.operation_date, 1, 7) <= ?
          AND (
              (
                  CAST(substr(?, 1, 4) AS INTEGER)
                  - CAST(substr(o.operation_date, 1, 4) AS INTEGER)
              ) * 12
              +
              (
                  CAST(substr(?, 6, 2) AS INTEGER)
                  - CAST(substr(o.operation_date, 6, 2) AS INTEGER)
              )
          ) < sp.months
        """,
        category_id,
        month,
        month,
        month,
    ) or 0

    return float(regular_spending) + float(stock_spending)


async def rebalance_next_month(
    source_month: str | None = None,
):
    await ensure_rebalancing_tables()

    if source_month is None:
        today = get_moscow_today()
        source_month = (
            today.replace(day=1) - timedelta(days=1)
        ).strftime("%Y-%m")

    target_month = get_next_month(source_month)

    existing = await fetch_value(
        """
        SELECT status
        FROM monthly_budget_rebalances
        WHERE source_month = ?
        """,
        source_month,
    )

    if existing == "done":
        return {
            "success": True,
            "already_rebalanced": True,
            "source_month": source_month,
            "target_month": target_month,
        }

    categories = await fetch_all(
        """
        SELECT id, name, monthly_limit
        FROM categories
        WHERE is_active = 1
        ORDER BY id
        """
    )

    if not categories:
        return {
            "success": False,
            "error": "Не найдены активные категории бюджета.",
        }

    total_budget = await get_monthly_budget_total()

    if total_budget <= 0:
        return {
            "success": False,
            "error": "Общий бюджет должен быть больше нуля.",
        }

    measured = []

    for category in categories:
        spending = await get_category_spending_for_rebalance(
            category_id=category["id"],
            month=source_month,
        )

        old_limit = float(category["monthly_limit"] or 0)

        # Половина веса — прежний лимит,
        # половина — расходы с учётом запасов.
        demand = max(
            old_limit * 0.5 + spending * 0.5,
            0,
        )

        measured.append(
            {
                "id": category["id"],
                "name": category["name"],
                "old_limit": old_limit,
                "spending": spending,
                "demand": demand,
            }
        )

    demand_total = sum(item["demand"] for item in measured)

    if demand_total <= 0:
        return {
            "success": False,
            "error": (
                "Не удалось рассчитать новые лимиты: "
                "нет данных о расходах и прежних лимитах."
            ),
        }

    # Распределяем общий бюджет пропорционально потребности.
    # Последней категории отдаём остаток, чтобы сумма
    # новых лимитов точно совпала с общим бюджетом.
    updates = []
    distributed = 0.0

    for index, item in enumerate(measured):
        if index == len(measured) - 1:
            new_limit = round(total_budget - distributed, 2)
        else:
            new_limit = round(
                total_budget * item["demand"] / demand_total,
                2,
            )
            distributed += new_limit

        updates.append(
            {
                **item,
                "new_limit": new_limit,
            }
        )

    await execute(
        """
        INSERT OR IGNORE INTO monthly_budget_rebalances (
            source_month,
            target_month,
            status
        )
        VALUES (?, ?, 'pending')
        """,
        source_month,
        target_month,
    )

    await execute(
        """
        UPDATE monthly_budget_rebalances
        SET status = 'processing',
            target_month = ?
        WHERE source_month = ?
          AND status = 'pending'
        """,
        target_month,
        source_month,
    )

    status = await fetch_value(
        """
        SELECT status
        FROM monthly_budget_rebalances
        WHERE source_month = ?
        """,
        source_month,
    )

    if status == "done":
        return {
            "success": True,
            "already_rebalanced": True,
            "source_month": source_month,
            "target_month": target_month,
        }

    if status != "processing":
        return {
            "success": False,
            "error": (
                "Перерасчёт уже выполняется "
                "или требует проверки."
            ),
        }

    statements = []

    for item in updates:
        statements.append(
            (
                """
                UPDATE categories
                SET monthly_limit = ?
                WHERE id = ?
                  AND is_active = 1
                  AND EXISTS (
                      SELECT 1
                      FROM monthly_budget_rebalances
                      WHERE source_month = ?
                        AND status = 'processing'
                  )
                """,
                (
                    item["new_limit"],
                    item["id"],
                    source_month,
                ),
            )
        )

    statements.append(
        (
            """
            UPDATE monthly_budget_rebalances
            SET status = 'done',
                completed_at = CURRENT_TIMESTAMP
            WHERE source_month = ?
              AND status = 'processing'
            """,
            (source_month,),
        )
    )

    await execute_many(statements)

    final_status = await fetch_value(
        """
        SELECT status
        FROM monthly_budget_rebalances
        WHERE source_month = ?
        """,
        source_month,
    )

    if final_status != "done":
        return {
            "success": False,
            "error": "Не удалось завершить перерасчёт бюджета.",
        }

    return {
        "success": True,
        "already_rebalanced": False,
        "source_month": source_month,
        "target_month": target_month,
        "total_budget": total_budget,
        "categories": updates,
    }
