import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
_admin_ids_raw = os.getenv("TELEGRAM_ADMIN_IDS", "").strip()
TELEGRAM_ADMIN_IDS = [int(x) for x in _admin_ids_raw.split(",") if x.strip()] if _admin_ids_raw else []

# CS-Cart API
CSCART_API_URL = os.getenv("CSCART_API_URL")  # Например: https://wabrum.com/api
CSCART_API_EMAIL = os.getenv("CSCART_API_EMAIL")
CSCART_API_KEY = os.getenv("CSCART_API_KEY")

# KlingAI API
KLINGAI_API_URL = "https://api-singapore.klingai.com"
KLINGAI_API_KEY = os.getenv("KLINGAI_API_KEY")

# Anthropic Claude API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Настройки генерации
PRODUCTS_TO_FETCH_DAILY = 20       # Сколько товаров забирать из CS-Cart
PRODUCTS_TO_SELECT_DAILY = 5       # Сколько отбирает AI-стилист
VIDEO_VARIANTS_PER_PRODUCT = 2     # Вариантов видео на товар
KLINGAI_VIDEO_DURATION = "5"       # "5" или "10"
KLINGAI_ASPECT_RATIO = "9:16"
KLINGAI_MODE = "pro"               # "std" или "pro"

# Расписание (UTC+5 Ашхабад, бот работает по UTC)
DAILY_GENERATION_HOUR_UTC = 4      # 9:00 по Ашхабаду = 04:00 UTC
DAILY_GENERATION_MINUTE = 0
KLINGAI_POLLING_INTERVAL = 30      # Секунд между проверками статуса задачи
KLINGAI_TASK_TIMEOUT = 600         # 10 минут максимум на задачу

# БД
DATABASE_PATH = "wabrum_bot.db"
