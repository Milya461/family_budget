import hashlib
import hmac
import json
import re
import time
import traceback
from datetime import date
from urllib.parse import parse_qs, urlparse

from workers import Response

from app.allocation import allocate_income_remainder, get_monthly_budget_summary
from app.budget import get_monthly_report
from app.db import execute, execute_many, fetch_all, fetch_one, fetch_value, to_python
from app.payment_flow import get_current_balance, get_moscow_today, record_actual_payment
from app.rebalancing import ensure_rebalancing_tables, mark_stock_purchase


SESSION_COOKIE = "family_budget_session"
SESSION_SECONDS = 60 * 60 * 24 * 7
VALID_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,80}$")


def _json(data, status=200, headers=None):
    response_headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if headers:
        response_headers.update(headers)
    return Response(
        json.dumps(data, ensure_ascii=False, default=str),
        status=status,
        headers=response_headers,
    )


def _get_password(env):
    value = getattr(env, "WEB_APP_PASSWORD", None)
    if value is None or type(value).__name__ == "JsUndefined":
        return None
    value = str(value)
    return value if len(value) >= 12 else None


async def _get_database_user_id():
    user_id = await fetch_value(
        "SELECT id FROM users ORDER BY id LIMIT 1"
    )
    if user_id is None:
        raise ValueError(
            "В общей базе пока нет пользователя. Один раз запусти старого бота командой /start."
        )
    return int(user_id)


def _operation_id_from_result(result):
    result = to_python(result)
    if isinstance(result, dict):
        meta = result.get("meta") or {}
        if isinstance(meta, dict):
            return meta.get("last_row_id")
    return None


def _session_signature(password, expires):
    key = hashlib.sha256(("family-budget-web:" + password).encode("utf-8")).digest()
    return hmac.new(key, str(expires).encode("ascii"), hashlib.sha256).hexdigest()


def _cookie_value(request):
    header = request.headers.get("Cookie") or request.headers.get("cookie") or ""
    for part in header.split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == SESSION_COOKIE:
            return value
    return ""


def _is_authorized(request, password):
    if not password:
        return False
    token = _cookie_value(request)
    expires_text, separator, signature = token.partition(".")
    if not separator or not expires_text.isdigit():
        return False
    expires = int(expires_text)
    if expires < int(time.time()):
        return False
    expected = _session_signature(password, expires)
    return hmac.compare_digest(signature, expected)


def _session_cookie(password):
    expires = int(time.time()) + SESSION_SECONDS
    signature = _session_signature(password, expires)
    value = f"{expires}.{signature}"
    return (
        f"{SESSION_COOKIE}={value}; Path=/; Max-Age={SESSION_SECONDS}; "
        "HttpOnly; Secure; SameSite=Strict"
    )


def _clear_cookie():
    return (
        f"{SESSION_COOKIE}=; Path=/; Max-Age=0; "
        "HttpOnly; Secure; SameSite=Strict"
    )


def _number(value, field_name="Сумма"):
    try:
        number = float(str(value).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError(f"{field_name}: введи число.")
    if number < 0 or number > 1_000_000_000:
        raise ValueError(f"{field_name}: значение вне допустимого диапазона.")
    return round(number, 2)


async def _dashboard(month):
    await ensure_rebalancing_tables()
    report = await get_monthly_report(month)
    budget = await get_monthly_budget_summary(month)

    operations = await fetch_all(
        """
        SELECT
            o.id,
            o.operation_type,
            o.amount,
            o.description,
            o.operation_date,
            c.name AS category_name,
            d.name AS debt_name
        FROM operations o
        LEFT JOIN categories c ON c.id = o.category_id
        LEFT JOIN debts d ON d.id = o.debt_id
        ORDER BY o.operation_date DESC, o.id DESC
        LIMIT 40
        """
    )

    payments = await fetch_all(
        """
        SELECT
            mp.id,
            mp.payment_name,
            mp.planned_amount,
            mp.actual_amount,
            mp.status,
            se.event_date,
            se.planned_day
        FROM mandatory_payments mp
        JOIN salary_events se ON se.id = mp.salary_event_id
        WHERE substr(se.event_date, 1, 7) = ?
        ORDER BY se.planned_day, mp.id
        """,
        month,
    )

    adjustments = await fetch_all(
        """
        SELECT id, delta, previous_balance, target_balance, note, created_at
        FROM balance_adjustments
        ORDER BY id DESC
        LIMIT 5
        """
    )

    return {
        "month": month,
        "report": report,
        "budget": budget,
        "operations": operations,
        "payments": payments,
        "adjustments": adjustments,
    }


async def _add_manual_savings(body):
    amount = _number(body.get("amount"), "Сумма пополнения")
    if amount <= 0:
        raise ValueError("Сумма пополнения должна быть больше нуля.")

    request_id = str(body.get("request_id") or "")
    if not VALID_REQUEST_ID.fullmatch(request_id):
        raise ValueError("Не удалось подтвердить запрос. Обнови страницу и попробуй ещё раз.")

    existing = await fetch_one(
        "SELECT status, amount FROM manual_savings_moves WHERE request_id = ?",
        request_id,
    )
    if existing and existing.get("status") == "done":
        return {
            "success": True,
            "already_processed": True,
            "amount": float(existing.get("amount") or amount),
            "balance": await get_current_balance(),
        }

    current_balance = float(await get_current_balance() or 0)
    if amount > current_balance:
        raise ValueError(
            "На основном счёте недостаточно реальных денег для такого пополнения. "
            f"Сейчас доступно {current_balance:.2f} ₽."
        )

    today = get_moscow_today().isoformat()
    month = today[:7]
    source = "manual-savings:" + request_id

    await execute_many([
        (
            """
            INSERT OR IGNORE INTO manual_savings_moves
                (request_id, amount, operation_date, status)
            VALUES (?, ?, ?, 'pending')
            """,
            (request_id, amount, today),
        ),
        (
            """
            UPDATE savings
            SET balance = balance + ?
            WHERE id = 1
              AND EXISTS (
                  SELECT 1 FROM manual_savings_moves
                  WHERE request_id = ? AND status = 'pending'
              )
            """,
            (amount, request_id),
        ),
        (
            """
            INSERT INTO monthly_allocations
                (month, category_id, amount, savings_amount, source, allocation_date)
            SELECT ?, NULL, 0, ?, ?, ?
            WHERE EXISTS (
                SELECT 1 FROM manual_savings_moves
                WHERE request_id = ? AND status = 'pending'
            )
            """,
            (month, amount, source, today, request_id),
        ),
        (
            """
            UPDATE manual_savings_moves
            SET status = 'done'
            WHERE request_id = ? AND status = 'pending'
            """,
            (request_id,),
        ),
    ])

    saved = await fetch_one(
        "SELECT status, amount FROM manual_savings_moves WHERE request_id = ?",
        request_id,
    )
    if not saved or saved.get("status") != "done":
        raise RuntimeError("Не удалось подтвердить перевод в копилку.")

    return {
        "success": True,
        "already_processed": False,
        "amount": float(saved.get("amount") or amount),
        "balance": await get_current_balance(),
    }


async def _set_real_balance(body):
    target = _number(body.get("amount"), "Реальный остаток")
    current = round(float(await get_current_balance() or 0), 2)
    delta = round(target - current, 2)
    note = str(body.get("note") or "Ручная корректировка реального остатка").strip()[:200]

    if abs(delta) < 0.005:
        return {
            "success": True,
            "changed": False,
            "previous_balance": current,
            "target_balance": target,
            "delta": 0,
        }

    await execute(
        """
        INSERT INTO balance_adjustments
            (delta, previous_balance, target_balance, note)
        VALUES (?, ?, ?, ?)
        """,
        delta,
        current,
        target,
        note,
    )

    actual = round(float(await get_current_balance() or 0), 2)
    return {
        "success": True,
        "changed": True,
        "previous_balance": current,
        "target_balance": target,
        "delta": delta,
        "balance": actual,
    }


async def handle_web_api(path, request, env):
    method = (request.method or "GET").upper()

    if path == "/api/login":
        if method != "POST":
            return _json({"error": "Метод не поддерживается."}, 405)
        password = _get_password(env)
        if not password:
            return _json({
                "error": (
                    "В Cloudflare не задан секрет WEB_APP_PASSWORD. "
                    "Создай его в настройках Worker, затем перезапусти приложение."
                ),
                "password_configured": False,
            }, 503)
        try:
            body = await request.json()
        except Exception:
            body = {}
        supplied = str((body or {}).get("password") or "")
        if not hmac.compare_digest(supplied, password):
            return _json({"error": "Неверный пароль."}, 401)
        return _json(
            {"success": True},
            headers={"Set-Cookie": _session_cookie(password)},
        )

    if path == "/api/logout":
        return _json(
            {"success": True},
            headers={"Set-Cookie": _clear_cookie()},
        )

    password = _get_password(env)
    if not password:
        return _json({
            "error": (
                "Не задан секрет WEB_APP_PASSWORD в настройках Cloudflare Worker."
            ),
            "password_configured": False,
        }, 503)

    if not _is_authorized(request, password):
        return _json({"error": "Нужен вход по паролю.", "unauthorized": True}, 401)

    try:
        if path == "/api/dashboard" and method == "GET":
            parsed = urlparse(request.url)
            params = parse_qs(parsed.query)
            month = (params.get("month") or [get_moscow_today().strftime("%Y-%m")])[0]
            if not VALID_MONTH.fullmatch(month):
                return _json({"error": "Некорректный месяц."}, 400)
            return _json(await _dashboard(month))

        if path == "/api/expense" and method == "POST":
            body = await request.json()
            amount = _number(body.get("amount"))
            category = str(body.get("category") or "").strip()
            description = str(body.get("description") or "").strip()[:200]
            if amount <= 0:
                raise ValueError("Сумма расхода должна быть больше нуля.")
            if not category:
                raise ValueError("Выбери категорию расхода.")

            user_id = await _get_database_user_id()
            category_id = await fetch_value(
                "SELECT id FROM categories WHERE name = ? AND is_active = 1",
                category,
            )
            if category_id is None:
                raise ValueError("Категория не найдена.")
            operation_date = get_moscow_today().isoformat()
            insert_result = await execute(
                """
                INSERT INTO operations (
                    user_id, operation_type, amount, category_id,
                    description, operation_date
                )
                VALUES (?, 'expense', ?, ?, ?, ?)
                """,
                user_id, amount, category_id, description, operation_date,
            )
            operation_id = _operation_id_from_result(insert_result)
            return _json({
                "success": True,
                "result": {
                    "operation_id": operation_id,
                    "operation_type": "expense",
                    "amount": amount,
                    "category": category,
                    "description": description,
                },
                "balance": await get_current_balance(),
            })

        if path == "/api/income" and method == "POST":
            body = await request.json()
            amount = _number(body.get("amount"))
            description = str(body.get("description") or "Доход").strip()[:100] or "Доход"
            if amount <= 0:
                raise ValueError("Сумма дохода должна быть больше нуля.")

            user_id = await _get_database_user_id()
            operation_date = get_moscow_today().isoformat()
            insert_result = await execute(
                """
                INSERT INTO operations (
                    user_id, operation_type, amount, description, operation_date
                )
                VALUES (?, 'income', ?, ?, ?)
                """,
                user_id, amount, description, operation_date,
            )
            operation_id = _operation_id_from_result(insert_result)
            if operation_id is None:
                return _json({
                    "success": True,
                    "result": {"amount": amount, "description": description},
                    "allocation_warning": (
                        "Доход записан, но не удалось получить его ID для распределения. "
                        "Не записывай этот доход повторно."
                    ),
                    "balance": await get_current_balance(),
                })

            result = {"success": True, "amount": amount}
            try:
                allocation = await allocate_income_remainder(
                    amount=amount,
                    allocation_date=date.fromisoformat(operation_date),
                    allocation_key=f"income:{operation_id}",
                )
                result["allocation"] = allocation
                if not allocation.get("success"):
                    result["allocation_warning"] = allocation.get(
                        "error", "Не удалось распределить доход."
                    )
            except Exception as allocation_error:
                result["allocation_warning"] = (
                    "Доход записан, но распределение не завершено: "
                    f"{type(allocation_error).__name__}: {allocation_error}. "
                    "Не записывай этот доход повторно."
                )
            return _json({
                "success": True,
                "result": result,
                "balance": await get_current_balance(),
            })

        if path == "/api/savings" and method == "POST":
            body = await request.json()
            result = await _add_manual_savings(body)
            return _json(result)

        if path == "/api/balance" and method == "POST":
            body = await request.json()
            return _json(await _set_real_balance(body))

        if path == "/api/payment" and method == "POST":
            body = await request.json()
            try:
                payment_id = int(body.get("payment_id"))
            except (TypeError, ValueError):
                return _json({"error": "Не удалось определить платёж."}, 400)
            amount = _number(body.get("amount"), "Сумма платежа")
            if amount <= 0:
                raise ValueError("Сумма платежа должна быть больше нуля.")
            result = await record_actual_payment(payment_id=payment_id, actual_amount=amount)
            if not result or not result.get("success"):
                return _json({"error": (result or {}).get("error", "Не удалось записать платёж.")}, 400)
            return _json({"success": True, "result": result, "balance": await get_current_balance()})

        if path == "/api/stock" and method == "POST":
            body = await request.json()
            try:
                operation_id = int(body.get("operation_id"))
                months = int(body.get("months"))
            except (TypeError, ValueError):
                return _json({"error": "Проверь покупку и срок запаса."}, 400)
            result = await mark_stock_purchase(operation_id=operation_id, months=months)
            if not result.get("success"):
                return _json({"error": result.get("error", "Не удалось отметить запас.")}, 400)
            return _json(result)

        return _json({"error": "Неизвестный API-маршрут."}, 404)

    except ValueError as error:
        return _json({"error": str(error)}, 400)
    except Exception as error:
        print(
            "FAMILY_BUDGET_WEB_API_ERROR:",
            path,
            repr(error),
            traceback.format_exc(),
        )
        return _json({
            "error": (
                "Не удалось выполнить действие. Проверь соединение. "
                "Не отправляй операцию повторно, пока не обновишь баланс."
            )
        }, 500)
