import base64
import json
import time
from urllib.parse import urlparse

from app.db import execute, fetch_all, fetch_one
from app.payment_flow import get_moscow_today


# A P-256 VAPID public key. The matching private JWK is stored only as a
# Cloudflare Worker secret named WEB_PUSH_PRIVATE_JWK.
WEB_PUSH_PUBLIC_KEY = "BPa1mEpMD57axdKhOdoftFjD9X-T6LqApof-Jz1taJYZF6iWzeCnkm6uTnQPcMTtEVN_ay5TKQcoh-8yuxuQRPY"
VAPID_SUBJECT = "https://github.com/Milya461/family_budget"


def _b64url_decode(value):
    text = str(value or "").replace("-", "+").replace("_", "/")
    text += "=" * ((4 - len(text) % 4) % 4)
    return base64.b64decode(text)


def _b64url_encode(value):
    return base64.urlsafe_b64encode(bytes(value)).rstrip(b"=").decode("ascii")


def _u8(value):
    from js import Uint8Array
    return Uint8Array.new(list(bytes(value)))


def _js_bytes(value):
    from js import Uint8Array
    return bytes(int(item) for item in Uint8Array.new(value))


def _js_object(value):
    from js import Object
    from pyodide.ffi import to_js
    return to_js(value, dict_converter=Object.fromEntries)


async def _hmac_sha256(key_bytes, data):
    from js import crypto
    key = await crypto.subtle.importKey(
        "raw",
        _u8(key_bytes),
        _js_object({"name": "HMAC", "hash": "SHA-256"}),
        False,
        ["sign"],
    )
    signed = await crypto.subtle.sign("HMAC", key, _u8(data))
    return _js_bytes(signed)


async def _vapid_token(endpoint, private_jwk):
    from js import crypto
    parsed = urlparse(endpoint)
    audience = f"{parsed.scheme}://{parsed.netloc}"
    now = int(time.time())
    header = _b64url_encode(json.dumps(
        {"typ": "JWT", "alg": "ES256"},
        separators=(",", ":"),
    ).encode("utf-8"))
    claims = _b64url_encode(json.dumps(
        {
            "aud": audience,
            "exp": now + 12 * 60 * 60,
            "sub": VAPID_SUBJECT,
        },
        separators=(",", ":"),
    ).encode("utf-8"))
    signing_input = f"{header}.{claims}".encode("ascii")

    private_key = await crypto.subtle.importKey(
        "jwk",
        _js_object(private_jwk),
        _js_object({"name": "ECDSA", "namedCurve": "P-256"}),
        False,
        ["sign"],
    )
    signature = await crypto.subtle.sign(
        _js_object({"name": "ECDSA", "hash": "SHA-256"}),
        private_key,
        _u8(signing_input),
    )
    return f"{header}.{claims}.{_b64url_encode(_js_bytes(signature))}"


async def _encrypt_payload(subscription, payload):
    from js import crypto
    user_public = _b64url_decode(subscription["keys"]["p256dh"])
    auth_secret = _b64url_decode(subscription["keys"]["auth"])

    ephemeral = await crypto.subtle.generateKey(
        _js_object({"name": "ECDH", "namedCurve": "P-256"}),
        True,
        ["deriveBits"],
    )
    sender_public = _js_bytes(
        await crypto.subtle.exportKey("raw", ephemeral.publicKey)
    )
    receiver_public = await crypto.subtle.importKey(
        "raw",
        _u8(user_public),
        _js_object({"name": "ECDH", "namedCurve": "P-256"}),
        False,
        [],
    )
    shared_secret = _js_bytes(await crypto.subtle.deriveBits(
        _js_object({"name": "ECDH", "public": receiver_public}),
        ephemeral.privateKey,
        256,
    ))

    # RFC 8291: combine the ECDH secret with the browser authentication secret.
    prk_key = await _hmac_sha256(auth_secret, shared_secret)
    key_info = b"WebPush: info\x00" + user_public + sender_public
    ikm = await _hmac_sha256(prk_key, key_info + b"\x01")

    salt = _js_bytes(await crypto.getRandomValues(Uint8Array.new(16)))
    prk = await _hmac_sha256(salt, ikm)
    cek = (await _hmac_sha256(
        prk,
        b"Content-Encoding: aes128gcm\x00\x01",
    ))[:16]
    nonce = (await _hmac_sha256(
        prk,
        b"Content-Encoding: nonce\x00\x01",
    ))[:12]

    aes_key = await crypto.subtle.importKey(
        "raw",
        _u8(cek),
        _js_object({"name": "AES-GCM"}),
        False,
        ["encrypt"],
    )
    # 0x02 is the final-record delimiter required by RFC 8188.
    plaintext = payload + b"\x02"
    ciphertext = _js_bytes(await crypto.subtle.encrypt(
        _js_object({
            "name": "AES-GCM",
            "iv": _u8(nonce),
            "tagLength": 128,
        }),
        aes_key,
        _u8(plaintext),
    ))

    # aes128gcm content coding header: salt, record size, key length, key.
    return (
        salt
        + (4096).to_bytes(4, "big")
        + bytes([len(sender_public)])
        + sender_public
        + ciphertext
    )


async def ensure_web_push_tables():
    await execute("""
        CREATE TABLE IF NOT EXISTS web_push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT NOT NULL UNIQUE,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            user_agent TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await execute("""
        CREATE TABLE IF NOT EXISTS daily_expense_checks (
            check_date TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'reminded',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)


async def save_push_subscription(subscription, user_agent=""):
    endpoint = str(subscription.get("endpoint") or "").strip()
    keys = subscription.get("keys") or {}
    p256dh = str(keys.get("p256dh") or "").strip()
    auth = str(keys.get("auth") or "").strip()

    parsed_endpoint = urlparse(endpoint)
    host = (parsed_endpoint.hostname or "").lower()
    allowed_host = (
        host == "fcm.googleapis.com"
        or host.endswith(".fcm.googleapis.com")
        or host == "web.push.apple.com"
        or host.endswith(".push.apple.com")
        or host == "updates.push.services.mozilla.com"
        or host == "push.services.mozilla.com"
        or host.endswith(".push.services.mozilla.com")
        or host.endswith(".notify.windows.com")
    )
    if (
        parsed_endpoint.scheme != "https"
        or not allowed_host
        or len(endpoint) > 2048
    ):
        raise ValueError("Некорректный адрес push-подписки.")
    if not p256dh or not auth or len(p256dh) > 256 or len(auth) > 128:
        raise ValueError("В подписке отсутствуют ключи браузера.")

    await ensure_web_push_tables()
    await execute("""
        INSERT INTO web_push_subscriptions (
            endpoint, p256dh, auth, user_agent, updated_at
        )
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(endpoint) DO UPDATE SET
            p256dh = excluded.p256dh,
            auth = excluded.auth,
            user_agent = excluded.user_agent,
            updated_at = CURRENT_TIMESTAMP
    """, endpoint, p256dh, auth, str(user_agent or "")[:300])
    return {"success": True}


async def remove_push_subscription(endpoint):
    await ensure_web_push_tables()
    await execute(
        "DELETE FROM web_push_subscriptions WHERE endpoint = ?",
        str(endpoint or ""),
    )
    return {"success": True}


async def get_daily_reminder_status():
    await ensure_web_push_tables()
    today = get_moscow_today().isoformat()
    row = await fetch_one("""
        SELECT check_date, status, updated_at
        FROM daily_expense_checks
        WHERE check_date = ?
        LIMIT 1
    """, today)
    return {
        "date": today,
        "status": (row or {}).get("status", "not_sent"),
        "visible": bool(row and row.get("status") in ("pending", "reminded", "forgot")),
    }


async def set_daily_reminder_status(status):
    if status not in ("acknowledged", "forgot"):
        raise ValueError("Неизвестный статус ежедневной проверки.")
    await ensure_web_push_tables()
    today = get_moscow_today().isoformat()
    await execute("""
        INSERT INTO daily_expense_checks (check_date, status, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(check_date) DO UPDATE SET
            status = excluded.status,
            updated_at = CURRENT_TIMESTAMP
    """, today, status)
    return {"success": True, "date": today, "status": status}


async def _send_one(subscription, payload, private_jwk):
    from js import fetch as js_fetch
    endpoint = subscription["endpoint"]
    push_subscription = {
        "endpoint": endpoint,
        "keys": {
            "p256dh": subscription["p256dh"],
            "auth": subscription["auth"],
        },
    }
    encrypted = await _encrypt_payload(push_subscription, payload)
    token = await _vapid_token(endpoint, private_jwk)
    headers = _js_object({
        "Authorization": (
            f"vapid t={token}, k={WEB_PUSH_PUBLIC_KEY}"
        ),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": "86400",
        "Urgency": "normal",
    })
    response = await js_fetch(
        endpoint,
        _js_object({
            "method": "POST",
            "headers": headers,
            "body": _u8(encrypted),
        }),
    )
    return int(response.status)


async def _save_reminder_state(today, status):
    await execute("""
        INSERT INTO daily_expense_checks (check_date, status, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(check_date) DO UPDATE SET
            status = excluded.status,
            updated_at = CURRENT_TIMESTAMP
    """, today, status)


def _private_key_matches_public(private_jwk):
    try:
        public_bytes = (
            b"\x04"
            + _b64url_decode(private_jwk["x"])
            + _b64url_decode(private_jwk["y"])
        )
        return _b64url_encode(public_bytes) == WEB_PUSH_PUBLIC_KEY
    except Exception:
        return False


async def send_daily_web_push(env):
    await ensure_web_push_tables()
    today = get_moscow_today().isoformat()

    existing = await fetch_one("""
        SELECT check_date, status
        FROM daily_expense_checks
        WHERE check_date = ?
        LIMIT 1
    """, today)
    if existing and existing.get("status") in ("reminded", "acknowledged", "forgot"):
        print("DAILY_WEB_PUSH_SKIPPED: reminder already handled", today,
              existing.get("status"))
        return {"status": existing.get("status"), "delivered": 0}

    subscriptions = await fetch_all("""
        SELECT id, endpoint, p256dh, auth
        FROM web_push_subscriptions
        ORDER BY id
    """)
    if not subscriptions:
        await _save_reminder_state(today, "pending")
        print("DAILY_WEB_PUSH_PENDING: no subscribed devices", today)
        return {"status": "pending", "delivered": 0}

    private_text = getattr(env, "WEB_PUSH_PRIVATE_JWK", None)
    if not private_text:
        await _save_reminder_state(today, "pending")
        print("DAILY_WEB_PUSH_PENDING: WEB_PUSH_PRIVATE_JWK is missing", today)
        return {"status": "pending", "delivered": 0}

    try:
        private_jwk = json.loads(str(private_text))
    except Exception as error:
        await _save_reminder_state(today, "pending")
        print("DAILY_WEB_PUSH_INVALID_PRIVATE_KEY:", repr(error))
        return {"status": "pending", "delivered": 0}

    if not _private_key_matches_public(private_jwk):
        await _save_reminder_state(today, "pending")
        print("DAILY_WEB_PUSH_KEY_MISMATCH: private key does not match public key")
        return {"status": "pending", "delivered": 0}

    payload = json.dumps({
        "title": "Семейный бюджет",
        "body": "Проверь, все ли доходы и расходы за сегодня записаны.",
        "url": f"/?reminder={today}",
        "tag": f"family-budget-reminder-{today}",
    }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    delivered = 0
    for subscription in subscriptions:
        try:
            status = await _send_one(subscription, payload, private_jwk)
            if 200 <= status < 300:
                delivered += 1
                print("DAILY_WEB_PUSH_DELIVERED:", subscription["id"], status)
            elif status in (404, 410):
                await execute(
                    "DELETE FROM web_push_subscriptions WHERE id = ?",
                    subscription["id"],
                )
                print("DAILY_WEB_PUSH_SUBSCRIPTION_REMOVED:", subscription["id"], status)
            else:
                print("DAILY_WEB_PUSH_FAILED:", subscription["id"], status)
        except Exception as error:
            print("DAILY_WEB_PUSH_ERROR:", subscription["id"], repr(error))

    final_status = "reminded" if delivered else "pending"
    await _save_reminder_state(today, final_status)
    print("DAILY_WEB_PUSH_FINISHED:", today, "delivered=", delivered,
          "subscriptions=", len(subscriptions), "status=", final_status)
    return {"status": final_status, "delivered": delivered}
