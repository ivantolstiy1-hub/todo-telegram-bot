from telebot import TeleBot, types
from config import AVAILABLE_MODELS, DEFAULT_MODEL
from services.database import (
    clear_history,
    count_messages,
    get_user_model,
    set_user_model,
    get_user_engine_mode,
    set_user_engine_mode,
    get_user_antigravity_conv,
)
from services.antigravity_service import antigravity_service
from services.self_config_service import self_config_service, STYLE_DESCRIPTIONS
from handlers.admin import is_admin
from utils.helpers import safe_send_message

def get_models_keyboard(current_model: str) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    for model_id, model_name in AVAILABLE_MODELS.items():
        is_active = (model_id == current_model)
        btn_text = f"✅ {model_name}" if is_active else model_name
        markup.add(types.InlineKeyboardButton(text=btn_text, callback_data=f"setmodel:{model_id}"))
    return markup

def get_modes_keyboard(current_mode: str) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    modes = {
        "agent": "🤖 Antigravity Agent (CLI & Инструменты)",
        "direct": "⚡ Gemini Direct (Быстрый чат)"
    }
    for mode_id, mode_title in modes.items():
        is_active = (mode_id == current_mode)
        btn_text = f"✅ {mode_title}" if is_active else mode_title
        markup.add(types.InlineKeyboardButton(text=btn_text, callback_data=f"setmode:{mode_id}"))
    return markup

def register_common_handlers(bot: TeleBot):

    @bot.message_handler(commands=["start"])
    def cmd_start(message: types.Message):
        user_name = message.from_user.first_name or "друг"
        user_id = message.from_user.id
        mode = get_user_engine_mode(user_id)
        mode_label = "🤖 Antigravity Agent" if mode == "agent" else "⚡ Gemini Direct"

        text = (
            f"👋 *Привет, {user_name}!* Я персональный AI-ассистент на базе *Google Antigravity CLI* и *Gemini*.\n\n"
            f"⚙️ *Текущий режим:* `{mode_label}`\n\n"
            "✨ *Что я умею:*\n"
            "• 🤖 *Автономный агент (Antigravity CLI)* — могу работать с вашим проектом, читать файлы, писать код и запускать команды прямо из Telegram.\n"
            "• 🧠 *Полноценная память* — удерживаю контекст диалога и детали задач.\n"
            "• 📸 *Фото и скриншоты* — анализирую графики, код с экрана и решаю задачи.\n"
            "• 🎙 *Голосовые сообщения* — понимаю речь и отвечаю текстом.\n"
            "• 📄 *Документы* — разбираю `.py`, `.txt`, `.pdf` файлы.\n\n"
            "⚡ *Команды управления:*\n"
            "/mode — Переключить режим (Antigravity Agent / Gemini Direct)\n"
            "/reset или /new — Очистить память диалога и начать с чистого листа\n"
            "/model — Выбрать модель нейросети\n"
            "/status — Текущий статус памяти, режима и сессии\n"
            "/help — Справка и примеры\n\n"
            "Отправь мне задачу или вопрос прямо сейчас! 👇"
        )
        if is_admin(user_id):
            text += "\n\n👑 *Вы Администратор бота!* Панель управления: /admin"
        safe_send_message(bot, message.chat.id, text)

    @bot.message_handler(commands=["mode"])
    def cmd_mode(message: types.Message):
        user_id = message.from_user.id
        current_mode = get_user_engine_mode(user_id)
        kb = get_modes_keyboard(current_mode)
        text = (
            "🛠 *Выберите режим работы ассистента:*\n\n"
            "• 🤖 *Antigravity Agent (CLI)* — полноценный агент с доступом к коду, инструментам терминала, многошаговому рассуждению и решению сложных задач.\n"
            "• ⚡ *Gemini Direct* — сверхбыстрый прямой чат через Google Gemini API для простых вопросов и генерации текстов."
        )
        safe_send_message(bot, message.chat.id, text, reply_markup=kb)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("setmode:"))
    def callback_set_mode(call: types.CallbackQuery):
        user_id = call.from_user.id
        new_mode = call.data.split(":", 1)[1]
        
        if new_mode in ("agent", "direct"):
            set_user_engine_mode(user_id, new_mode)
            kb = get_modes_keyboard(new_mode)
            mode_name = "🤖 Antigravity Agent (CLI)" if new_mode == "agent" else "⚡ Gemini Direct (API)"
            
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"✅ *Режим успешно изменен на:*\n`{mode_name}`",
                    parse_mode="Markdown",
                    reply_markup=kb
                )
            except Exception:
                pass
            
            bot.answer_callback_query(call.id, f"Режим изменен на {new_mode}")

    @bot.message_handler(commands=["reset", "new", "clear"])
    def cmd_reset(message: types.Message):
        user_id = message.from_user.id
        clear_history(user_id)
        text = (
            "🧹 *Память диалога очищена!*\n\n"
            "Я сбросил предыдущий контекст диалога и сессию агента. Готов к новой задаче!"
        )
        safe_send_message(bot, message.chat.id, text)

    @bot.message_handler(commands=["model"])
    def cmd_model(message: types.Message):
        user_id = message.from_user.id
        current_model = get_user_model(user_id)
        kb = get_models_keyboard(current_model)
        text = (
            "⚙️ *Выбор модели:* \n\n"
            f"Текущая модель: `{current_model}`\n\n"
            "Выберите подходящую модель для решения ваших задач:"
        )
        safe_send_message(bot, message.chat.id, text, reply_markup=kb)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("setmodel:"))
    def callback_set_model(call: types.CallbackQuery):
        user_id = call.from_user.id
        new_model = call.data.split(":", 1)[1]
        
        if new_model in AVAILABLE_MODELS:
            set_user_model(user_id, new_model)
            set_user_antigravity_conv(user_id, None)
            kb = get_models_keyboard(new_model)
            model_title = AVAILABLE_MODELS[new_model]
            
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"✅ *Модель успешно переключена на:*\n`{model_title}`",
                    parse_mode="Markdown",
                    reply_markup=kb
                )
            except Exception:
                pass
            
            bot.answer_callback_query(call.id, f"Модель переключена на {new_model}")

    @bot.message_handler(commands=["status", "info"])
    def cmd_status(message: types.Message):
        user_id = message.from_user.id
        current_model = get_user_model(user_id)
        mode = get_user_engine_mode(user_id)
        conv_id = get_user_antigravity_conv(user_id)
        msg_count = count_messages(user_id)
        
        mode_label = "🤖 Antigravity Agent (CLI)" if mode == "agent" else "⚡ Gemini Direct"
        agent_status = f"`{conv_id[:12]}...`" if conv_id else "_Не активна (будет создана при первом запросе)_"

        role_label = "👑 Администратор" if is_admin(user_id) else "👤 Пользователь"
        
        from services.gemini_service import gemini_service
        kstats = gemini_service.key_pool.get_stats()
        keys_label = f"`{kstats['active']}/{kstats['total']} активны`"

        text = (
            "📊 *Текущий статус ассистента:*\n\n"
            f"• 🔑 *Ваш статус:* `{role_label}`\n"
            f"• 🛠 *Режим работы:* `{mode_label}`\n"
            f"• 🤖 *Активная модель:* `{current_model}`\n"
            f"• 🧠 *Сообщений в памяти:* `{msg_count}`\n"
            f"• 🔑 *Пул API-ключей:* {keys_label}\n"
            f"• 🆔 *Сессия Antigravity:* {agent_status}\n\n"
            "Используйте /mode для смены режима или /reset для сброса контекста."
        )
        safe_send_message(bot, message.chat.id, text)

    @bot.message_handler(commands=["help"])
    def cmd_help(message: types.Message):
        text = (
            "📖 *Справочник по боту Antigravity & Gemini:*\n\n"
            "1. *Режим Antigravity Agent:* идеален для программирования, работы с проектом, исследования файлов и выполнения сложных задач через CLI.\n"
            "2. *Режим Gemini Direct:* быстрые ответы на вопросы без вызова инструментов.\n"
            "3. *Автономная самонастройка:* говорите боту «Настрой себя так, чтобы...», «Добавь правило: ...», «Поменяй температуру на 0.2» или используйте /config.\n"
            "4. *Безлимитный режим запросов:* бот автоматически балансирует нагрузку между пулом ключей и каскадом моделей, предотвращая ошибку 429.\n"
            "5. *Команда /mode:* переключение между режимами агента и прямого чата.\n"
            "6. *Команда /reset:* очищает память и начинает новую сессию с чистого листа.\n"
            "7. *Медиа (фото, голос, файлы):* отправляйте голосовые сообщения, фото задач или файлы кода прямо в чат — бот обработает их автоматически."
        )
        safe_send_message(bot, message.chat.id, text)

    # -------------------------------------------------------------
    # Команда и интерактивное меню /config
    # -------------------------------------------------------------
    def _build_config_keyboard():
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_style = types.InlineKeyboardButton("🎨 Стиль ответов", callback_data="cfg:menu_style")
        btn_temp = types.InlineKeyboardButton("🌡 Температура", callback_data="cfg:menu_temp")
        btn_clear_rules = types.InlineKeyboardButton("🧹 Очистить правила", callback_data="cfg:clearrules")
        btn_reset = types.InlineKeyboardButton("🔄 Сброс к заводским", callback_data="cfg:resetall")
        btn_refresh = types.InlineKeyboardButton("🔄 Обновить", callback_data="cfg:refresh")
        markup.add(btn_style, btn_temp)
        markup.add(btn_clear_rules, btn_reset)
        markup.add(btn_refresh)
        return markup

    @bot.message_handler(commands=["config", "settings"])
    def cmd_config(message: types.Message):
        report = self_config_service.get_current_config_report()
        safe_send_message(bot, message.chat.id, report, reply_markup=_build_config_keyboard())

    @bot.callback_query_handler(func=lambda call: call.data.startswith("cfg:"))
    def callback_config(call: types.CallbackQuery):
        user_id = call.from_user.id
        action = call.data.split(":", 1)[1]

        if not is_admin(user_id) and action not in ("refresh",):
            bot.answer_callback_query(call.id, "⛔ Изменение настроек доступно только Администратору.", show_alert=True)
            return

        if action == "refresh":
            report = self_config_service.get_current_config_report()
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=report,
                    parse_mode="Markdown",
                    reply_markup=_build_config_keyboard()
                )
            except Exception:
                pass
            bot.answer_callback_query(call.id, "Обновлено")

        elif action == "clearrules":
            from services.database import clear_custom_rules
            clear_custom_rules()
            bot.answer_callback_query(call.id, "Все правила очищены", show_alert=True)
            report = self_config_service.get_current_config_report()
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=report,
                    parse_mode="Markdown",
                    reply_markup=_build_config_keyboard()
                )
            except Exception:
                pass

        elif action == "resetall":
            from services.database import reset_all_settings_to_default
            reset_all_settings_to_default()
            bot.answer_callback_query(call.id, "Настройки сброшены к заводским!", show_alert=True)
            report = self_config_service.get_current_config_report()
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=report,
                    parse_mode="Markdown",
                    reply_markup=_build_config_keyboard()
                )
            except Exception:
                pass

        elif action == "menu_style":
            markup = types.InlineKeyboardMarkup(row_width=1)
            from services.database import get_response_style
            curr_style = get_response_style()
            for s_id, s_name in STYLE_DESCRIPTIONS.items():
                label = f"✅ {s_name}" if s_id == curr_style else s_name
                markup.add(types.InlineKeyboardButton(label, callback_data=f"cfg:setstyle:{s_id}"))
            markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="cfg:refresh"))
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="🎨 *Выберите предпочитаемый стиль общения:*",
                    parse_mode="Markdown",
                    reply_markup=markup
                )
            except Exception:
                pass
            bot.answer_callback_query(call.id)

        elif action.startswith("setstyle:"):
            new_style = action.split(":", 1)[1]
            from services.database import set_response_style
            set_response_style(new_style)
            bot.answer_callback_query(call.id, f"Стиль изменен на {new_style}", show_alert=True)
            report = self_config_service.get_current_config_report()
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=report,
                    parse_mode="Markdown",
                    reply_markup=_build_config_keyboard()
                )
            except Exception:
                pass

        elif action == "menu_temp":
            markup = types.InlineKeyboardMarkup(row_width=2)
            temps = [
                ("0.1 (Строгий)", "0.1"),
                ("0.3 (Точный)", "0.3"),
                ("0.7 (Базовый)", "0.7"),
                ("1.0 (Творческий)", "1.0"),
            ]
            for label, tval in temps:
                markup.add(types.InlineKeyboardButton(label, callback_data=f"cfg:settemp:{tval}"))
            markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="cfg:refresh"))
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="🌡 *Выберите температуру генерации (0.0 — точный код, 1.0 — фантазия):*",
                    parse_mode="Markdown",
                    reply_markup=markup
                )
            except Exception:
                pass
            bot.answer_callback_query(call.id)

        elif action.startswith("settemp:"):
            new_t = float(action.split(":", 1)[1])
            from services.database import set_temperature
            set_temperature(new_t)
            bot.answer_callback_query(call.id, f"Температура: {new_t}", show_alert=True)
            report = self_config_service.get_current_config_report()
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=report,
                    parse_mode="Markdown",
                    reply_markup=_build_config_keyboard()
                )
            except Exception:
                pass

