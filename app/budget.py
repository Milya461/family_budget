from datetime import datetime, timedelta, timezone

from app.db import (
    execute,
    fetch_all,
    fetch_one,
    fetch_value,
    to_python,
)

from app.allocation import allocate_income_remainder
from app.rebalancing import ensure_rebalancing_tables
from app.parser import classify_mandatory_payment


MOSCOW_TIMEZONE = timezone(timedelta(hours=3))


def get_moscow_today():
    return datetime.now(MOSCOW_TIMEZONE).date()


async def get_category_id(category_name):
    return await fetch_value(
        """
        SELECT id
        FROM categories
        WHERE name = ?
        """,
        category_name,
    )


async def get_debt_id(debt_name):
    return await fetch_value(
        """
        SELECT id
        FROM debts
        WHERE name = ?
        """,
        debt_name,
    )


async def get_category_limit(category_id, month=None):
    if month is None:
        month = get_moscow_today().strftime("%Y-%m")

    await ensure_rebalancing_tables()

    value = await fetch_value(
        """
        SELECT COALESCE(
            (
                SELECT monthly_limit
                FROM monthly_category_budgets
                WHERE category_id = ?
                  AND month = ?
            ),
            (
                SELECT monthly_limit
                FROM categories
                WHERE id = ?
            ),
            0
        )
        """,
        category_id,
        month,
        category_id,
    )

    return float(value or 0)


async def get_category_spent(category_id, month):
    # category_id is the source of truth: required payments created by
    # the payment flow have no category_id and are counted separately.
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

    return float(value or 0)


async def check_expense(
    telegram_id: int,
    amount: float,
    category_name: str,
):
    current_month = get_moscow_today().strftime("%Y-%m")

    user_id = await fetch_value(
        """
        SELECT id
        FROM users
        WHERE telegram_id = ?
        """,
        telegram_id,
    )

    if user_id is None:
        return {
            "success": False,
            "error": (
                "Пользователь не найден. "
                "Отправьте /start."
            ),
        }

    category_id = await get_category_id(category_name)

    if category_id is None:
        return {
            "success": False,
            "error": "Категория не найдена.",
        }

    limit = await get_category_limit(
        category_id,
        current_month,
    )

    spent = await get_category_spent(
        category_id,
        current_month,
    )

    remaining_before = limit - spent
    remaining_after = remaining_before - amount

    return {
        "success": True,
        "category": category_name,
        "category_id": category_id,
        "amount": amount,
        "limit": limit,
        "spent": spent,
        "remaining": remaining_after,
        "exceeded": remaining_after < 0,
    }


async def save_expense(
    telegram_id: int,
    amount: float,
    category_name: str,
    description: str,
):
    user_id = await fetch_value(
        """
        SELECT id
        FROM users
        WHERE telegram_id = ?
        """,
        telegram_id,
    )

    if user_id is None:
        return {
            "success": False,
            "error": (
                "Пользователь не найден. "
                "Отправьте /start."
            ),
        }

    category_id = await get_category_id(category_name)

    if category_id is None:
        return {
            "success": False,
            "error": "Категория не найдена.",
        }

    operation_date = get_moscow_today().isoformat()

    insert_result = await execute(
        """
        INSERT INTO operations (
            user_id,
            operation_type,
            amount,
            category_id,
            description,
            operation_date
        )
        VALUES (?, 'expense', ?, ?, ?, ?)
        """,
        user_id,
        amount,
        category_id,
        description,
        operation_date,
    )

    insert_result = to_python(insert_result)
    operation_id = None

    if isinstance(insert_result, dict):
        meta = insert_result.get("meta") or {}

        if isinstance(meta, dict):
            operation_id = meta.get("last_row_id")

    current_month = operation_date[:7]

    limit = await get_category_limit(
        category_id,
        current_month,
    )

    spent = await get_category_spent(
        category_id,
        current_month,
    )

    remaining = limit - spent

    return {
        "success": True,
        "operation_id": operation_id,
        "category": category_name,
        "category_id": category_id,
        "amount": amount,
        "limit": limit,
        "spent": spent,
        "remaining": remaining,
        "exceeded": remaining < 0,
    }


async def add_income(
    telegram_id: int,
    amount: float,
    description: str,
):
    try:
        user_id = await fetch_value(
            """
            SELECT id
            FROM users
            WHERE telegram_id = ?
            """,
            telegram_id,
        )

        if user_id is None:
            return {
                "success": False,
                "error": (
                    "Пользователь не найден. "
                    "Отправьте /start."
                ),
            }

        operation_date = get_moscow_today().isoformat()

        insert_result = await execute(
            """
            INSERT INTO operations (
                user_id,
                operation_type,
                amount,
                description,
                operation_date
            )
            VALUES (?, 'income', ?, ?, ?)
            """,
            user_id,
            amount,
            description,
            operation_date,
        )

        insert_result = to_python(insert_result)
        operation_id = None

        if isinstance(insert_result, dict):
            meta = insert_result.get("meta") or {}

            if isinstance(meta, dict):
                operation_id = meta.get("last_row_id")

        result = {
            "success": True,
            "amount": amount,
        }

        if operation_id is None:
            result["allocation_warning"] = (
                "Доход записан, но не удалось получить "
                "идентификатор операции для распределения. "
                "Повторно вносить доход не нужно."
            )
            return result

        try:
            allocation = await allocate_income_remainder(
                amount=amount,
                allocation_date=datetime.fromisoformat(
                    operation_date
                ).date(),
                allocation_key=f"income:{operation_id}",
            )

            result["allocation"] = allocation

            if not allocation.get("success"):
                result["allocation_warning"] = allocation.get(
                    "error",
                    "Не удалось распределить доход.",
                )

        except Exception as allocation_error:
            result["allocation_warning"] = (
                "Доход записан, но распределение не завершено: "
                f"{type(allocation_error).__name__}: "
                f"{allocation_error}. "
                "Повторно вносить доход не нужно."
            )

        return result

    except Exception as error:
        return {
            "success": False,
            "error": (
                f"Диагностика add_income: "
                f"{type(error).__name__}: {error}"
            ),
        }


def calculate_life_expenses(month_expenses, mandatory_expenses):
    """Ordinary spending = all monthly expenses minus required payments."""
    return round(
        max(
            float(month_expenses or 0) - float(mandatory_expenses or 0),
            0.0,
        ),
        2,
    )


def summarize_month_expenses(rows):
    """Separate ordinary spending from explicitly identified required payments."""
    mandatory_totals = {
        "Кредитная карта": 0.0,
        "Кредит на машину": 0.0,
        "Ипотека": 0.0,
        "Коммунальные услуги": 0.0,
    }
    life_expenses = 0.0
    other_expenses = 0.0

    for row in rows:
        amount = float(row.get("amount") or 0)
        payment_kind = classify_mandatory_payment(
            row.get("description") or "",
            row.get("debt_name"),
        )

        if payment_kind in mandatory_totals:
            mandatory_totals[payment_kind] += amount
            continue

        if row.get("debt_id") is not None:
            continue

        life_expenses += amount
        if row.get("category_id") is None:
            other_expenses += amount

    credit_expenses = mandatory_totals["Кредитная карта"] + mandatory_totals["Кредит на машину"]
    mortgage_expenses = mandatory_totals["Ипотека"]
    utilities_expenses = mandatory_totals["Коммунальные услуги"]
    mandatory_expenses = credit_expenses + mortgage_expenses + utilities_expenses

    return {
        "life_expenses": life_expenses,
        "other_expenses": other_expenses,
        "credit_expenses": credit_expenses,
        "mortgage_expenses": mortgage_expenses,
        "utilities_expenses": utilities_expenses,
        "mandatory_expenses": mandatory_expenses,
    }


async def get_monthly_report(
    month: str | None = None,
):
    if month is None:
        month = get_moscow_today().strftime("%Y-%m")

    await execute(
        """
        CREATE TABLE IF NOT EXISTS balance_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delta REAL NOT NULL,
            previous_balance REAL NOT NULL,
            target_balance REAL NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await ensure_rebalancing_tables()

    month_operations = await fetch_one(
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
        WHERE substr(operation_date, 1, 7) = ?
        """,
        month,
    )

    all_operations = await fetch_one(
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

    monthly_expense_rows = await fetch_all(
        """
        SELECT
            o.amount,
            o.category_id,
            o.debt_id,
            o.description,
            d.name AS debt_name
        FROM operations o
        LEFT JOIN debts d ON d.id = o.debt_id
        WHERE o.operation_type = 'expense'
          AND substr(o.operation_date, 1, 7) = ?
        """,
        month,
    )

    # The mandatory_payments table is the authoritative source for required
    # payments. This is important because a payment can be recorded in the
    # salary/payment flow without its operations.description being a phrase
    # that the text classifier can recognize. Ordinary spending is therefore
    # always the monthly operations total minus the actual required payments.
    mandatory_payment_rows = await fetch_all(
        """
        SELECT
            mp.payment_name,
            COALESCE(mp.actual_amount, 0) AS actual_amount
        FROM mandatory_payments mp
        JOIN salary_events se ON se.id = mp.salary_event_id
        WHERE substr(se.event_date, 1, 7) = ?
          AND mp.actual_amount IS NOT NULL
          AND mp.status = 'paid'
        """,
        month,
    )

    mandatory_totals = {
        "Кредитная карта": 0.0,
        "Кредит на машину": 0.0,
        "Ипотека": 0.0,
        "Коммунальные услуги": 0.0,
    }

    for row in mandatory_payment_rows:
        payment_name = str(row.get("payment_name") or "")
        amount = float(row.get("actual_amount") or 0)
        if payment_name in mandatory_totals:
            mandatory_totals[payment_name] += amount

    credit_expenses = round(
        mandatory_totals["Кредитная карта"]
        + mandatory_totals["Кредит на машину"],
        2,
    )
    mortgage_expenses = round(mandatory_totals["Ипотека"], 2)
    utilities_expenses = round(mandatory_totals["Коммунальные услуги"], 2)
    mandatory_expenses = round(
        credit_expenses + mortgage_expenses + utilities_expenses,
        2,
    )

    expense_summary = summarize_month_expenses(monthly_expense_rows)

    category_allocations = await fetch_value(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM monthly_allocations
        WHERE month = ?
          AND category_id IS NOT NULL
        """,
        month,
    ) or 0

    monthly_savings = await fetch_value(
        """
        SELECT COALESCE(SUM(savings_amount), 0)
        FROM monthly_allocations
        WHERE month = ?
          AND savings_amount > 0
        """,
        month,
    ) or 0

    savings_row = await fetch_one(
        """
        SELECT
            balance,
            monthly_target
        FROM savings
        WHERE id = 1
        """
    )

    savings_balance = 0
    savings_target = 23000

    if savings_row:
        savings_balance = savings_row.get("balance") or 0
        savings_target = (
            savings_row.get("monthly_target") or 23000
        )

    life_budget = await fetch_value(
        """
        SELECT value
        FROM bot_settings
        WHERE key = 'monthly_life_budget'
        """
    )

    if life_budget is None:
        life_budget = 60000
    else:
        life_budget = float(life_budget)

    category_rows = await fetch_all(
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

    category_report = []

    for row in category_rows:
        category_id = row["id"]
        name = row["name"]
        limit = float(row["monthly_limit"] or 0)

        spent = await get_category_spent(
            category_id,
            month,
        )

        allocated = await fetch_value(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM monthly_allocations
            WHERE month = ?
              AND category_id = ?
            """,
            month,
            category_id,
        ) or 0

        category_report.append(
            {
                "id": category_id,
                "name": name,
                "limit": limit,
                "allocated": allocated,
                "spent": spent,
                "remaining": max(limit - spent, 0),
                "remaining_to_allocate": max(
                    limit - allocated,
                    0,
                ),
            }
        )

    month_income = (
        month_operations.get("income", 0)
        if month_operations
        else 0
    )

    month_expenses = (
        month_operations.get("expenses", 0)
        if month_operations
        else 0
    )

    # Only ordinary expense operations count toward the life budget.
    # Debt-linked rows and explicitly named required payments are excluded
    # inside summarize_month_expenses; do not subtract them a second time.
    life_expenses = round(
        float(expense_summary["life_expenses"] or 0),
        2,
    )

    total_income = (
        all_operations.get("income", 0)
        if all_operations
        else 0
    )

    total_expenses = (
        all_operations.get("expenses", 0)
        if all_operations
        else 0
    )

    life_remaining = max(
        life_budget - life_expenses,
        0,
    )

    life_remaining_to_allocate = max(
        life_budget - category_allocations,
        0,
    )

    savings_remaining = max(
        savings_target - monthly_savings,
        0,
    )

    balance_adjustments_total = await fetch_value(
        """
        SELECT COALESCE(SUM(delta), 0)
        FROM balance_adjustments
        """
    ) or 0

    main_account = (
        total_income
        - total_expenses
        - savings_balance
        + float(balance_adjustments_total or 0)
    )

    free_after_targets = (
        main_account
        - life_remaining_to_allocate
        - savings_remaining
    )

    return {
        "month": month,
        "month_income": month_income,
        "month_expenses": month_expenses,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "credit_expenses": credit_expenses,
        "mortgage_expenses": mortgage_expenses,
        "utilities_expenses": utilities_expenses,
        "mandatory_expenses": mandatory_expenses,
        "debt_expenses": (
            credit_expenses
            + mortgage_expenses
        ),
        "life_expenses": life_expenses,
        "other_expenses": expense_summary["other_expenses"],
        "category_allocations": category_allocations,
        "life_budget": life_budget,
        "life_remaining": life_remaining,
        "life_remaining_to_allocate": (
            life_remaining_to_allocate
        ),
        "monthly_savings": monthly_savings,
        "savings_balance": savings_balance,
        "savings_target": savings_target,
        "savings_remaining": savings_remaining,
        "main_account": main_account,
        "free_after_targets": free_after_targets,
        "categories": category_report,
    }
