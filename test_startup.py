import os
import unittest
from unittest.mock import patch

import bot


class StartupTests(unittest.TestCase):
    def test_missing_telegram_token(self):
        with patch.object(bot, "TELEGRAM_TOKEN", None), patch.object(
            bot, "ANTHROPIC_API_KEY", None
        ), patch.object(bot, "Anthropic") as client:
            with self.assertRaisesRegex(RuntimeError, "TELEGRAM_BOT_TOKEN"):
                bot.main()
            client.assert_not_called()

    def test_missing_anthropic_key(self):
        with patch.object(bot, "TELEGRAM_TOKEN", "123456:test-placeholder"), patch.object(
            bot, "ANTHROPIC_API_KEY", None
        ), patch.object(bot, "Anthropic") as client:
            with self.assertRaisesRegex(RuntimeError, "ANTHROPIC_API_KEY"):
                bot.main()
            client.assert_not_called()

    @patch.dict(os.environ, {key: value for key, value in os.environ.items()
                             if not key.lower().endswith("_proxy")}, clear=True)
    def test_worker_start_without_network(self):
        with patch.object(bot, "TELEGRAM_TOKEN", "123456:test-placeholder"), patch.object(
            bot, "ANTHROPIC_API_KEY", "test-placeholder"
        ), patch("telegram.ext.Application.run_polling") as polling:
            try:
                bot.main()
                polling.assert_called_once_with()
                # Build the real Telegram application, including reminder support.
                app = bot.Application.builder().token(bot.TELEGRAM_TOKEN).build()
                self.assertIsNotNone(app.job_queue)
            finally:
                if bot.client is not None:
                    bot.client.close()
                    bot.client = None


if __name__ == "__main__":
    unittest.main()
