"""Валидация Telegram Mini App initData (подпись HMAC-SHA256).

Telegram подписывает initData секретным ключом, производным от bot_token.
Проверяем подпись на сервере, чтобы доверять user.id, а не полю в URL.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.parse


def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """Проверяет подпись initData и возвращает распарсенные поля (или None)."""
    if not init_data or not bot_token:
        return None
    parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    # data_check_string = отсортированные по ключу пары через \n (кроме hash)
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

    # secret_key = HMAC_SHA256(bot_token, "WebAppData")
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calc_hash, received_hash):
        return None
    return parsed


def extract_user_id(init_data: str, bot_token: str) -> int | None:
    """Возвращает Telegram user id из валидного initData (или None)."""
    data = validate_init_data(init_data, bot_token)
    if not data or "user" not in data:
        return None
    try:
        return int(json.loads(data["user"]).get("id"))
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
