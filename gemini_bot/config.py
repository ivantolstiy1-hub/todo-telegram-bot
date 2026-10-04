import os
import warnings
from pathlib import Path
from dotenv import load_dotenv

# Подавление предупреждений LibreSSL на macOS для чистоты логов
warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")
warnings.filterwarnings("ignore", category=UserWarning)

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

try:
    from dotenv import load_dotenv
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE)
    else:
        load_dotenv()
except ImportError:
    pass

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# Загрузка пула API ключей Gemini (поддержка одного или нескольких ключей через запятую/точку с запятой)
raw_keys = os.getenv("GEMINI_API_KEYS", "") or os.getenv("GEMINI_API_KEY", "")
GEMINI_API_KEYS = []
for k in raw_keys.replace(";", ",").replace("\n", ",").split(","):
    cleaned = k.strip()
    if cleaned and cleaned not in GEMINI_API_KEYS:
        GEMINI_API_KEYS.append(cleaned)

# Основной ключ для совместимости
GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-3.8-flash").strip()
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "8173946372,8562721499")
ADMIN_IDS = set()
for item in ADMIN_IDS_RAW.split(","):
    item = item.strip()
    if item.isdigit():
        ADMIN_IDS.add(int(item))
ADMIN_ID = int(os.getenv("ADMIN_ID", "8173946372"))
ADMIN_IDS.add(ADMIN_ID)
DEFAULT_AGENT_ACCESS = os.getenv("AGENT_ACCESS_MODE", "admin_only").strip()  # "admin_only" или "all"
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "Ты — умный, эрудированный и дружелюбный персональный AI-ассистент в Telegram на базе Google Gemini. "
    "Твоя задача — оперативно, точно и понятно помогать пользователю в решении любых задач: в коде, учебе, работе, "
    "анализе текстов и генерации идей. Отвечай на языке собеседника, сохраняй нить диалога и используй красивое форматирование."
).strip()

DB_PATH = BASE_DIR / "bot_memory.db"
# Оптимальная длина истории (16 сообщений = 8 пар вопрос-ответ), чтобы не превышать TPM (токены в минуту)
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "16"))
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "35000"))

AVAILABLE_MODELS = {
    "gemini-3.5-flash": "⚡ Gemini 3.5 Flash (Стабильная, высокая квота)",
    "gemini-3.5-flash-lite": "🚀 Gemini 3.5 Flash-Lite (Сверхбыстрая)",
    "gemini-3.1-flash-lite": "💡 Gemini 3.1 Flash-Lite (Экономная)",
    "gemini-3.1-pro-preview": "🧠 Gemini 3.1 Pro (Флагман Pro)",
    "gemini-3.8-flash": "🔥 Gemini 3.8 Flash (Превью модель)",
}

# Каскад фолбэков для моделей: у каждой модели Google отдельный лимит запросов в минуту (RPM).
# Если у одной модели исчерпан дневной или минутный лимит, запрос мгновенно переключается на рабочую модель!
MODEL_CASCADES = {
    "gemini-3.5-flash": ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
    "gemini-3.5-flash-lite": ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.1-flash-lite"],
    "gemini-3.1-flash-lite": ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.5-flash-lite"],
    "gemini-3.1-pro-preview": ["gemini-3.1-pro-preview", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
    "gemini-pro-latest": ["gemini-pro-latest", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
    "gemini-3.8-flash": ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
    "gemini-flash-latest": ["gemini-flash-latest", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
}
DEFAULT_CASCADE = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]



