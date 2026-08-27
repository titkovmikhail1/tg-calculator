"""Конфигурация Telegram-бота через переменные окружения."""

import os


BOT_TOKEN = os.environ.get("BOT_TOKEN", "8752674653:AAGL8vBb1eW3dE558fn_HOfU9Sj7wbe5OIs")
WEBAPP_URL = os.environ.get(
	"WEBAPP_URL",
	"https://titkovmikhail1.github.io/tg-calculator/webapp/",
)
