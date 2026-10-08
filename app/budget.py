from datetime import date, datetime
from zoneinfo import ZoneInfo

import aiosqlite

from app.db import DB_PATH


MOSCOW_TIMEZONE = ZoneInfo("Europe/Moscow")


def get_moscow_today():
    return datetime.now(
        MOSCOW_TIMEZONE
    ).date()


async def get_category_id(db, category_name):
    cursor = await db.execute(
        """
        SELECT id
        FROM categories
        WHERE name = ?
        """,
        (category_name,),
    )
    row = await cursor.fetchone()
    return row[0] if row else None


async def get_debt_id(db, debt_name):
    cursor = await db.execute(
        """
        SELECT id
        FROM debts
        WHERE name = ?
        """,
        (debt_name,),
    )
    row = await cursor.fetchone()
    return row[0] if row else None


async def get_category_limit(db, category_id):
    cursor = await db.execute(
        """
        SELECT monthly_limit
        FROM categories
        WHERE id = ?
        """,
        (category_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def get_category_spent(db, category_id, month):
    cursor = await db.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM operations
        WHERE category_id = ?
          AND operation_type = 'expense'
          AND substr(operation_date, 1, 7) = ?
        """,
        (category_id, month),
    )
    row = await cursor.fetchone()
    return row[0] or 0


async def check_expense(
    telegram_id: int,
    amount: float,
    category_name: str,
):
    current_month = get_moscow_today().strftime(
        "%Y-%m"
    )

    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute(
            """
            SELECT id
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )

        user = await cursor.fetchone()

        if not user:
            return {
                "success": False,
                "error": (
                    "Пользователь не найден. "
                    "Отправьте /start."
                ),
            }

        category_id = await get_category_id(
            db,
            category_name,
        )

        if not category_id:
            return {
                "success": False,
                "error": "Категория не найдена.",
            }

        limit = await get_category_limit(
            db,
            category_id,
        )

        spent = await get_category_spent(
            db,
            category_id,
            current_month,
        )

        remaining_before = limit - spent
        remaining_after = (
            remaining_before - amount
        )

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
    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute(
            """
            SELECT id
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )

        user = await cursor.fetchone()

        if not user:
            return {
                "success": False,
                "error": (
                    "Пользователь не найден. "
                    "Отправьте /start."
                ),
            }

        category_id = await get_category_id(
            db,
            category_name,
        )

        if not category_id:
            return {
                "success": False,
                "error": "Категория не найдена.",
            }

        await db.execute(
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
            (
                user[0],
                amount,
                category_id,
                description,
                get_moscow_today().isoformat(),
            ),
        )

        await db.commit()

        check = await check_expense(
            telegram_id,
            amount,
            category_name,
        )

        return check


async def add_income(
    telegram_id: int,
    amount: float,
    description: str,
):
    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute(
            """
            SELECT id
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )

        user = await cursor.fetchone()

        if not user:
            return {
                "success": False,
                "error": (
                    "Пользователь не найден. "
                    "Отправьте /start."
                ),
            }

        await db.execute(
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
            (
                user[0],
                amount,
                description,
                get_moscow_today().isoformat(),
            ),
        )

        await db.commit()

        return {
            "success": True,
            "amount": amount,
        }


async def get_monthly_report(
    month: str | None = None,
):
    """
    Формирует единый отчёт за месяц.

    В отчёте отдельно учитываются:

    - все доходы;
    - фактически оплаченные обязательные платежи;
    - расходы на жизнь;
    - прочие реальные расходы;
    - виртуальное распределение бюджета;
    - физические накопления;
    - остаток бюджета на жизнь;
    - остаток до цели накоплений;
    - реальные деньги на основном счёте.

    Виртуальное распределение по категориям
    не считается расходом.

    Плановые суммы обязательных платежей
    не считаются фактическими расходами,
    пока платёж реально не записан.
    """

    if month is None:
        month = get_moscow_today().strftime(
            "%Y-%m"
        )

    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute(
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
                ),
                COALESCE(
                    SUM(
                        CASE
                            WHEN operation_type = 'expense'
                            THEN amount
                            ELSE 0
                        END
                    ),
                    0
                )
            FROM operations
            WHERE substr(operation_date, 1, 7) = ?
            """,
            (month,),
        )

        month_operations = await cursor.fetchone()

        cursor = await db.execute(
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
                ),
                COALESCE(
                    SUM(
                        CASE
                            WHEN operation_type = 'expense'
                            THEN amount
                            ELSE 0
                        END
                    ),
                    0
                )
            FROM operations
            """
        )

        all_operations = await cursor.fetchone()

        # Все фактически оплаченные обязательные платежи:
        # кредиты / машина / ипотека определяются
        # по debt_id, коммуналка — по описанию операции.
        cursor = await db.execute(
            """
            SELECT
                COALESCE(SUM(amount), 0)
            FROM operations
            WHERE operation_type = 'expense'
              AND (
                    debt_id IS NOT NULL
                    OR description = 'Коммунальные услуги'
              )
              AND substr(operation_date, 1, 7) = ?
            """,
            (month,),
        )

        mandatory_expenses_row = (
            await cursor.fetchone()
        )

        # Отдельная разбивка обязательных платежей.
        cursor = await db.execute(
            """
            SELECT
                COALESCE(SUM(amount), 0)
            FROM operations
            WHERE operation_type = 'expense'
              AND debt_id IS NOT NULL
              AND substr(operation_date, 1, 7) = ?
            """,
            (month,),
        )

        debt_expenses_row = (
            await cursor.fetchone()
        )

        cursor = await db.execute(
            """
            SELECT
                COALESCE(SUM(amount), 0)
            FROM operations
            WHERE operation_type = 'expense'
              AND description = 'Коммунальные услуги'
              AND substr(operation_date, 1, 7) = ?
            """,
            (month,),
        )

        utilities_expenses_row = (
            await cursor.fetchone()
        )

        # Расходы на жизнь — только расходы,
        # привязанные к месячным категориям.
        cursor = await db.execute(
            """
            SELECT
                COALESCE(SUM(amount), 0)
            FROM operations
            WHERE operation_type = 'expense'
              AND category_id IS NOT NULL
              AND substr(operation_date, 1, 7) = ?
            """,
            (month,),
        )

        life_expenses_row = (
            await cursor.fetchone()
        )

        # Прочие реальные расходы:
        # не категория, не кредит и не коммуналка.
        cursor = await db.execute(
            """
            SELECT
                COALESCE(SUM(amount), 0)
            FROM operations
            WHERE operation_type = 'expense'
              AND category_id IS NULL
              AND debt_id IS NULL
              AND (
                    description IS NULL
                    OR description != 'Коммунальные услуги'
              )
              AND substr(operation_date, 1, 7) = ?
            """,
            (month,),
        )

        other_expenses_row = (
            await cursor.fetchone()
        )

        cursor = await db.execute(
            """
            SELECT
                COALESCE(SUM(amount), 0)
            FROM monthly_allocations
            WHERE month = ?
              AND category_id IS NOT NULL
            """,
            (month,),
        )

        category_allocations_row = (
            await cursor.fetchone()
        )

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

        monthly_savings_row = (
            await cursor.fetchone()
        )

        cursor = await db.execute(
            """
            SELECT
                balance,
                monthly_target
            FROM savings
            WHERE id = 1
            """
        )

        savings_row = await cursor.fetchone()

        cursor = await db.execute(
            """
            SELECT
                COALESCE(
                    SUM(monthly_limit),
                    0
                )
            FROM categories
            WHERE is_active = 1
            """
        )

        life_budget_row = (
            await cursor.fetchone()
        )

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

        category_rows = await cursor.fetchall()

        category_report = []

        for category_id, name, limit in category_rows:
            cursor = await db.execute(
                """
                SELECT
                    COALESCE(SUM(amount), 0)
                FROM operations
                WHERE operation_type = 'expense'
                  AND category_id = ?
                  AND substr(operation_date, 1, 7) = ?
                """,
                (
                    category_id,
                    month,
                ),
            )

            spent_row = await cursor.fetchone()

            cursor = await db.execute(
                """
                SELECT
                    COALESCE(SUM(amount), 0)
                FROM monthly_allocations
                WHERE month = ?
                  AND category_id = ?
                """,
                (
                    month,
                    category_id,
                ),
            )

            allocated_row = await cursor.fetchone()

            spent = (
                spent_row[0]
                if spent_row
                else 0
            )

            allocated = (
                allocated_row[0]
                if allocated_row
                else 0
            )

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
        month_operations[0]
        if month_operations
        else 0
    )

    month_expenses = (
        month_operations[1]
        if month_operations
        else 0
    )

    total_income = (
        all_operations[0]
        if all_operations
        else 0
    )

    total_expenses = (
        all_operations[1]
        if all_operations
        else 0
    )

    mandatory_expenses = (
        mandatory_expenses_row[0]
        if mandatory_expenses_row
        else 0
    )

    debt_expenses = (
        debt_expenses_row[0]
        if debt_expenses_row
        else 0
    )

    utilities_expenses = (
        utilities_expenses_row[0]
        if utilities_expenses_row
        else 0
    )

    life_expenses = (
        life_expenses_row[0]
        if life_expenses_row
        else 0
    )

    other_expenses = (
        other_expenses_row[0]
        if other_expenses_row
        else 0
    )

    category_allocations = (
        category_allocations_row[0]
        if category_allocations_row
        else 0
    )

    monthly_savings = (
        monthly_savings_row[0]
        if monthly_savings_row
        else 0
    )

    savings_balance = (
        savings_row[0]
        if savings_row
        else 0
    )

    savings_target = (
        savings_row[1]
        if savings_row
        else 23000
    )

    life_budget = (
        life_budget_row[0]
        if life_budget_row
        else 60000
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

    # Реальные деньги на основном счёте.
    #
    # Виртуальное распределение по категориям
    # здесь НЕ вычитается.
    #
    # Физические накопления вычитаются,
    # потому что эти деньги уже отправлены
    # в копилку.
    main_account = (
        total_income
        - total_expenses
        - savings_balance
    )

    # Деньги сверх ещё не профинансированных
    # месячных целей.
    #
    # Это информационный показатель:
    # он не является отдельным счётом.
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
        "mandatory_expenses": mandatory_expenses,
        "debt_expenses": debt_expenses,
        "utilities_expenses": utilities_expenses,
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
