"""Тесты валидации Telegram Mini App initData (HMAC-подпись)."""

import hashlib
import hmac
import json
import unittest
import urllib.parse

from app.telegram_auth import extract_user_id, validate_init_data

TOKEN = "test_token_123"


def make_init_data(user_id: int, token: str = TOKEN, hash_ok: bool = True) -> str:
    user = json.dumps({"id": user_id, "first_name": "X"})
    fields = {"user": user, "auth_date": "1700000000", "query_id": "AA"}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    if not hash_ok:
        h = "0" * 64
    fields["hash"] = h
    return urllib.parse.urlencode(fields)


class TelegramAuthTest(unittest.TestCase):
    def test_valid_signature(self):
        self.assertEqual(extract_user_id(make_init_data(12345), TOKEN), 12345)

    def test_bad_hash_rejected(self):
        self.assertIsNone(extract_user_id(make_init_data(12345, hash_ok=False), TOKEN))

    def test_wrong_token_rejected(self):
        self.assertIsNone(extract_user_id(make_init_data(12345), "other_token"))

    def test_empty_rejected(self):
        self.assertIsNone(extract_user_id("", TOKEN))
        self.assertIsNone(validate_init_data("", TOKEN))

    def test_missing_user(self):
        fields = {"auth_date": "1700000000"}
        dcs = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
        secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
        fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        self.assertIsNone(extract_user_id(urllib.parse.urlencode(fields), TOKEN))


if __name__ == "__main__":
    unittest.main()
