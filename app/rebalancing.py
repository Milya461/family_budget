from datetime import datetime, timedelta, timezone
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
    await execute(
        """
        CREATE TABLE IF NOT EXISTS monthly_category_budgets (
            month TEXT NOT NULL,
            category_id INTEGER NOT NULL,
            monthly_limit REAL NOT NULL,
            source TEXT NOT NULL DEFAULT 'initial',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (month, category_id)
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
async def mark_stock_purchase(
    operation_id: int,
    months: int,
):
    if (
        not isinstance(months, int)
        or isinstance(months, bool)
        or not 1 <= months <= 24
    ):
        return {
            "success": False,
            "error": "Срок запаса должен быть от 1 до 24 месяцев.",
        }
    await ensure_rebalancing_tables()
    operation = await fetch_value(
        """
        SELECT id
        FROM operations
        WHERE id = ?
          AND operation_type = 'expense'
          AND category_id IS NOT NULL
        """,
        operation_id,
    )
    if operation is None:
        return {
            "success": False,
            "error": "Расход не найден или не относится к категории.",
        }
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
        return 60000.0
    return float(value)
async def get_category_limits_for_month(month: str):
    await ensure_rebalancing_tables()
    categories = await fetch_all(
        """
        SELECT id, name, monthly_limit
        FROM categories
        WHERE is_active = 1
        ORDER BY id
        """
    )
    if not categories:
        return []
    saved_limits = await fetch_all(
        """
        SELECT category_id, monthly_limit
        FROM monthly_category_budgets
        WHERE month = ?
        """,
        month,
    )
    saved_by_id = {
        row["category_id"]: float(row["monthly_limit"])
        for row in saved_limits
    }
    result = []
    for category in categories:
        category_id = category["id"]
        if category_id in saved_by_id:
            limit = saved_by_id[category_id]
        else:
            limit = float(category["monthly_limit"] or 0)
        result.append(
            {
                "id": category_id,
                "name": category["name"],
                "monthly_limit": limit,
            }
        )
    return result
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
          ) >= 0
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
    try:
        year, number = map(int, source_month.split("-"))
        if not 1 <= number <= 12 or year < 2000:
            raise ValueError
    except (TypeError, ValueError):
        return {
            "success": False,
            "error": "Месяц должен быть в формате ГГГГ-ММ.",
        }
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
        saved = await fetch_all(
            """
            SELECT
                c.id,
                c.name,
                b.monthly_limit
            FROM monthly_category_budgets b
            JOIN categories c
              ON c.id = b.category_id
            WHERE b.month = ?
            ORDER BY c.id
            """,
            target_month,
        )
        return {
            "success": True,
            "already_rebalanced": True,
            "source_month": source_month,
            "target_month": target_month,
            "categories": saved,
        }
    categories = await get_category_limits_for_month(source_month)
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
        # Учитываем как прежний план, так и фактические расходы.
        # Разовые большие покупки можно пометить как запас,
        # чтобы учитывать их стоимость постепенно.
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
    # Сначала резервируем перерасчёт для исходного месяца.
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
        SET status = 'processing'
        WHERE source_month = ?
          AND status = 'pending'
        """,
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
    # Записываем новые лимиты только для целевого месяца.
    # Старые месяцы и текущие значения категорий не меняем.
    for item in updates:
        statements.append(
            (
                """
                INSERT INTO monthly_category_budgets (
                    month,
                    category_id,
                    monthly_limit,
                    source
                )
                SELECT ?, ?, ?, 'rebalance'
                WHERE EXISTS (
                    SELECT 1
                    FROM monthly_budget_rebalances
                    WHERE source_month = ?
                      AND status = 'processing'
                )
                ON CONFLICT(month, category_id)
                DO UPDATE SET
                    monthly_limit = excluded.monthly_limit,
                    source = excluded.source
                """,
                (
                    target_month,
                    item["id"],
                    item["new_limit"],
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
