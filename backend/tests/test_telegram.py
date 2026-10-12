"""Тесты Telegram-привязки."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.routers.telegram import _unlink_user, LINK_TTL_MINUTES, UPLOAD_SOURCE


class UnlinkTests(unittest.TestCase):
    def test_unlink_clears_fields(self):
        user = MagicMock()
        user.telegram_chat_id = "123"
        user.telegram_notify = True
        user.telegram_link_code = "ABC"
        user.telegram_link_expires = datetime.utcnow() + timedelta(minutes=5)
        _unlink_user(user)
        self.assertIsNone(user.telegram_chat_id)
        self.assertFalse(user.telegram_notify)
        self.assertIsNone(user.telegram_link_code)
        self.assertIsNone(user.telegram_link_expires)

    def test_constants(self):
        self.assertEqual(LINK_TTL_MINUTES, 15)
        self.assertEqual(UPLOAD_SOURCE, "UPLOAD_TELEGRAM")


if __name__ == "__main__":
    unittest.main()
