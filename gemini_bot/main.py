import sys
import logging
from telebot import TeleBot, types
from config import TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, DEFAULT_MODEL
from services.database import init_db
from handlers.common import register_common_handlers
from handlers.messages import register_message_handlers
from handlers.admin import register_admin_handlers
from web import start_web_server_thread

logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не задан! Укажите токен в файле .env")
        sys.exit(1)

    if not GEMINI_API_KEY:
        logger.error("❌ GEMINI_API_KEY не задан! Укажите ключ в файле .env")
        sys.exit(1)

    logger.info("Запуск встроенного HTTP health-check сервера для Render...")
    start_web_server_thread()

    logger.info("Инициализация базы данных SQLite...")
    init_db()

    logger.info("Подключение к Telegram Bot API...")
    bot = TeleBot(TELEGRAM_BOT_TOKEN, parse_mode=None)

    # Регистрация меню команд в интерфейсе Telegram
    try:
        bot.set_my_commands([
            types.BotCommand("start", "👋 Запустить бота / Главное меню"),
            types.BotCommand("mode", "🛠 Режим (Antigravity Agent / Chat)"),
            types.BotCommand("config", "⚙️ Настройки и правила бота"),
            types.BotCommand("reset", "🧹 Очистить контекст диалога"),
            types.BotCommand("model", "🧠 Выбрать модель нейросети"),
            types.BotCommand("status", "📊 Статус памяти и модели"),
            types.BotCommand("admin", "👑 Панель Администратора"),
            types.BotCommand("help", "📖 Справка и возможности"),
        ])
    except Exception as e:
        logger.warning(f"Не удалось обновить список команд в меню: {e}")

    # Регистрация обработчиков
    register_admin_handlers(bot)
    register_common_handlers(bot)
    register_message_handlers(bot)

    try:
        bot_info = bot.get_me()
        print("\n" + "=" * 50)
        print(f"🤖 Бот @{bot_info.username} успешно запущен!")
        print(f"🧠 Базовая модель: {DEFAULT_MODEL}")
        print(f"📂 Директория: gemini_bot/")
        print("=" * 50 + "\n")
    except Exception as e:
        logger.warning(f"Не удалось получить информацию о боте (проверьте интернет): {e}")

    logger.info("Бот готов к приёму сообщений (polling запущен)...")
    bot.infinity_polling(timeout=20, long_polling_timeout=20)

if __name__ == "__main__":
    main()
