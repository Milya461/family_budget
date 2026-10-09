from datetime import datetime, timedelta, timezone

from app.db import (
    execute,
    fetch_all,
    fetch_one,
    fetch_value,
    to_python,
)

from app.allocation import allocate_income_remainder


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


async def get_category_limit(category_id):
    value = await fetch_value(
        """
        SELECT monthly_limit
        FROM categories
        WHERE id = ?
        """,
        category_id,
    )

    return value or 0


async def get_category_spent(category_id, month):
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

    limit = await get_category_limit(category_id)

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

    await execute(
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

    current_month = operation_date[:7]

    limit = await get_category_limit(category_id)

    spent = await get_category_spent(
        category_id,
        current_month,
    )

    remaining = limit - spent

    return {
        "success": True,
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


async def get_monthly_report(
    month: str | None = None,
):
    if month is None:
        month = get_moscow_today().strftime("%Y-%m")

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

    credit_expenses = await fetch_value(
        """
        SELECT COALESCE(SUM(o.amount), 0)
        FROM operations o
        JOIN debts d
          ON d.id = o.debt_id
        WHERE o.operation_type = 'expense'
          AND d.name IN (
              'Кредитная карта',
              'Кредит на машину'
          )
          AND substr(o.operation_date, 1, 7) = ?
        """,
        month,
    ) or 0

    mortgage_expenses = await fetch_value(
        """
        SELECT COALESCE(SUM(o.amount), 0)
        FROM operations o
        JOIN debts d
          ON d.id = o.debt_id
        WHERE o.operation_type = 'expense'
          AND d.name = 'Ипотека'
          AND substr(o.operation_date, 1, 7) = ?
        """,
        month,
    ) or 0

    utilities_expenses = await fetch_value(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM operations
        WHERE operation_type = 'expense'
          AND description = 'Коммунальные услуги'
          AND substr(operation_date, 1, 7) = ?
        """,
        month,
    ) or 0

    mandatory_expenses = await fetch_value(
        """
        SELECT COALESCE(SUM(o.amount), 0)
        FROM operations o
        LEFT JOIN debts d
          ON d.id = o.debt_id
        WHERE o.operation_type = 'expense'
          AND (
              d.id IS NOT NULL
              OR o.description = 'Коммунальные услуги'
          )
          AND substr(o.operation_date, 1, 7) = ?
        """,
        month,
    ) or 0

    life_expenses = await fetch_value(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM operations
        WHERE operation_type = 'expense'
          AND category_id IS NOT NULL
          AND substr(operation_date, 1, 7) = ?
        """,
        month,
    ) or 0

    other_expenses = await fetch_value(
        """
        SELECT COALESCE(SUM(o.amount), 0)
        FROM operations o
        LEFT JOIN debts d
          ON d.id = o.debt_id
        WHERE o.operation_type = 'expense'
          AND o.category_id IS NULL
          AND d.id IS NULL
          AND (
              o.description IS NULL
              OR o.description != 'Коммунальные услуги'
          )
          AND substr(o.operation_date, 1, 7) = ?
        """,
        month,
    ) or 0

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
        savings_balance = (
            savings_row.get("balance") or 0
        )
        savings_target = (
            savings_row.get("monthly_target")
            or 23000
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
            id,
            name,
            monthly_limit
        FROM categories
        WHERE is_active = 1
        ORDER BY id
        """
    )

    category_report = []

    for row in category_rows:
        category_id = row["id"]
        name = row["name"]
        limit = row["monthly_limit"] or 0

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
                "remaining": max(
                    limit - spent,
                    0,
                ),
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

    main_account = (
        total_income
        - total_expenses
        - savings_balance
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
        "other_expenses": other_expenses,
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
