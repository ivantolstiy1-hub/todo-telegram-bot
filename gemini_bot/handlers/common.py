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
from services.hermes_service import hermes_service
from services.self_config_service import self_config_service, STYLE_DESCRIPTIONS
from handlers.admin import is_admin
from utils.helpers import safe_send_message

def get_models_keyboard(current_model: str) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    pstats = hermes_service.get_providers_status()
    
    for model_id, model_name in AVAILABLE_MODELS.items():
        is_active = (model_id == current_model)
        
        # Индикатор готовности провайдера
        if model_id == "auto-hermes":
            indicator = "✨"
        elif model_id == "video-director":
            from services.video_service import video_service
            indicator = "🟢" if video_service.has_any_active_provider() else "🎬"
        elif model_id == "antigravity":
            indicator = "🟢" if pstats.get("antigravity", {}).get("configured") else "💻"
        elif model_id.startswith("gemini-"):
            indicator = "🟢" if pstats["gemini"]["configured"] else "🔴"
        elif model_id.startswith("deepseek-"):
            indicator = "🟢" if (pstats["deepseek"]["configured"] or pstats["openrouter"]["configured"]) else "🔑"
        elif model_id.startswith("claude-"):
            indicator = "🟢" if (pstats["claude"]["configured"] or pstats["openrouter"]["configured"]) else "🔑"
        elif model_id == "gpt-4o":
            indicator = "🟢" if (pstats["openai"]["configured"] or pstats["openrouter"]["configured"]) else "🔑"
        elif model_id == "nous-hermes-3":
            indicator = "🟢" if pstats["openrouter"]["configured"] else "🔑"
        else:
            indicator = "🟢"

        label = f"{indicator} {model_name}"
        btn_text = f"✅ {label}" if is_active else label
        markup.add(types.InlineKeyboardButton(text=btn_text, callback_data=f"setmodel:{model_id}"))
    return markup

def get_modes_keyboard(current_mode: str) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    modes = {
        "hermes": "🏛 Агент Гермес (Мульти-LLM маршрутизатор)",
        "agent": "🤖 Antigravity Agent (CLI & Инструменты)",
        "direct": "⚡ Gemini Direct (Прямой чат Google)"
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
        mode_labels = {
            "hermes": "🏛 Агент Гермес (Мульти-LLM)",
            "agent": "🤖 Antigravity Agent (CLI)",
            "direct": "⚡ Gemini Direct (API)"
        }
        mode_label = mode_labels.get(mode, "🏛 Агент Гермес")

        text = (
            f"👋 *Привет, {user_name}!* Я персональный AI-ассистент на базе *Агента Гермес*, *Google Gemini* и *Antigravity CLI*.\n\n"
            f"⚙️ *Текущий режим:* `{mode_label}`\n\n"
            "✨ *Что я умею:*\n"
            "• 🏛 *Агент Гермес (Мульти-LLM)* — умный диспетчер нейросетей! Автоматически направляет математику в DeepSeek R1, сложный код в Claude 3.5, творчество в Nous Hermes / ChatGPT, а быстрые ответы — в Gemini 3.5 Flash.\n"
            "• 🎬 *Video AI & Монтаж* — генерация кинематографичных видео (Luma Dream Machine, Kling AI, Minimax) и режиссерская раскадровка сцен.\n"
            "• 🤖 *Antigravity Agent (CLI)* — работа с проектом, чтение файлов, запуск команд прямо из Telegram.\n"
            "• 🧠 *Единая память диалога* — контекст сохраняется при переключении между любыми нейросетями.\n"
            "• 📸 *Фото и скриншоты* — анализ графиков, диаграмм, кода с экрана.\n"
            "• 🎙 *Голосовые сообщения* — понимаю речь и выполняю голосовые поручения.\n"
            "• 📄 *Документы* — разбираю `.py`, `.txt`, `.pdf` файлы.\n\n"
            "⚡ *Команды управления:*\n"
            "/video — Генератор видео и режиссерский монтажный стол\n"
            "/mode — Режим работы (Гермес / Antigravity CLI / Gemini Direct)\n"
            "/model — Выбрать модель (Auto-Hermes, Video AI, DeepSeek, Claude, ChatGPT, Gemini)\n"
            "/status — Текущий статус памяти, ключей и провайдеров\n"
            "/reset или /new — Очистить память и начать заново\n"
            "/config — Интерактивная самонастройка стиля и температуры\n"
            "/help — Справка и примеры\n\n"
            "💡 *Быстрые фразы Гермеса:* можно написать прямо в чат:\n"
            "_«Гермес, сгенерируй видео: кот в скафандре летит к Марсу»_\n"
            "_«видео 9:16: неоновый спорткар на ночной трассе»_\n"
            "_«Гермес, спроси у DeepSeek: реши задачу...»_\n"
            "_«через Claude: напиши скрипт...»_\n\n"
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
            "• 🏛 *Агент Гермес (Мульти-LLM)* — интеллектуальный маршрутизатор: автоматически выбирает лучшую модель (DeepSeek, Claude, ChatGPT, Gemini) под сложность вопроса или слушает команды «Гермес, спроси у...».\n"
            "• 🤖 *Antigravity Agent (CLI)* — автономный агент с терминалом и доступом к файловой системе для задач кодинга.\n"
            "• ⚡ *Gemini Direct* — сверхбыстрый прямой чат через Google Gemini API."
        )
        safe_send_message(bot, message.chat.id, text, reply_markup=kb)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("setmode:"))
    def callback_set_mode(call: types.CallbackQuery):
        user_id = call.from_user.id
        new_mode = call.data.split(":", 1)[1]
        
        mode_names = {
            "hermes": "🏛 Агент Гермес (Мульти-LLM)",
            "agent": "🤖 Antigravity Agent (CLI)",
            "direct": "⚡ Gemini Direct (API)"
        }
        if new_mode in mode_names:
            set_user_engine_mode(user_id, new_mode)
            kb = get_modes_keyboard(new_mode)
            mode_name = mode_names[new_mode]
            
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
            "⚙️ *Выбор модели нейросети:*\n\n"
            f"Текущая модель: `{current_model}`\n\n"
            "📌 *Обозначения:*\n"
            "✨ — Умный Агент Гермес (сам подберет лучшую LLM под ваш вопрос)\n"
            "🟢 — Провайдер подключен и готов к работе\n"
            "🔑 — Требуется API-ключ (при выборе включится каскадный резерв на Gemini)\n\n"
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
        
        mode_labels = {
            "hermes": "🏛 Агент Гермес (Мульти-LLM)",
            "agent": "🤖 Antigravity Agent (CLI)",
            "direct": "⚡ Gemini Direct"
        }
        mode_label = mode_labels.get(mode, mode)
        agent_status = f"`{conv_id[:12]}...`" if conv_id else "_Не активна (создается при запросе к агенту)_"

        role_label = "👑 Администратор" if is_admin(user_id) else "👤 Пользователь"
        
        from services.gemini_service import gemini_service
        kstats = gemini_service.key_pool.get_stats()
        keys_label = f"`{kstats['active']}/{kstats['total']} активны`"

        pstats = hermes_service.get_providers_status()
        prov_items = []
        for p_key, p_data in pstats.items():
            icon = "🟢" if p_data["configured"] else "⚪"
            prov_items.append(f"{icon} {p_data['name']}")
        providers_status_str = " | ".join(prov_items)

        text = (
            "📊 *Текущий статус ассистента:*\n\n"
            f"• 🔑 *Ваш статус:* `{role_label}`\n"
            f"• 🛠 *Режим работы:* `{mode_label}`\n"
            f"• 🤖 *Активная модель:* `{current_model}`\n"
            f"• 🧠 *Сообщений в памяти:* `{msg_count}`\n"
            f"• ⚡ *Ключи Gemini:* {keys_label}\n"
            f"• 🏛 *Провайдеры LLM:* {providers_status_str}\n"
            f"• 🆔 *Сессия Antigravity:* {agent_status}\n\n"
            "Используйте /mode для смены режима или /reset для сброса контекста."
        )
        safe_send_message(bot, message.chat.id, text)

    @bot.message_handler(commands=["help"])
    def cmd_help(message: types.Message):
        text = (
            "📖 *Справочник по боту Antigravity & Агент Гермес:*\n\n"
            "1. 🏛 *Агент Гермес (Мульти-LLM):* умная маршрутизация между DeepSeek, Claude, ChatGPT, Gemini и Nous Hermes. Говорите естественными фразами:\n"
            "   • _«Гермес, спроси у DeepSeek: реши теорему...»_\n"
            "   • _«через Claude: найди баг в коде...»_\n"
            "   • _«через ChatGPT: придумай слоган...»_\n"
            "   • _«Гермес, ...»_ — автовыбор лучшей модели.\n"
            "2. 🎬 *Video AI & Монтаж (/video):* генерация видео через ТОП нейросети (Luma Ray 2, Kling AI 1.5, Minimax Hailuo) и создание режиссерских раскадровок с саунд-дизайном.\n"
            "   • _«/video 9:16 неоновый спорткар в ночном городе»_\n"
            "   • _«Гермес, смонтируй рилс про фитнес»_\n"
            "3. 🤖 *Режим Antigravity Agent:* решение задач в терминале, работа с репозиторием и файлами.\n"
            "4. ⚡ *Режим Gemini Direct:* сверхбыстрый чат через прямой API Google.\n"
            "5. 🛠 *Автономная самонастройка:* бот меняет температуру, стиль и правила по фразам «Настрой себя так...» или через /config.\n"
            "6. 🔄 *Авто-каскад и отказоустойчивость:* при отсутствии ключей сторонних LLM Гермес автоматически перенаправляет запрос на Gemini без ошибок для пользователя.\n"
            "7. 🎙 *Медиа (видео, фото, голос, файлы):* отправляйте голосовые сообщения, фото или код — бот поймет и ответит."
        )
        safe_send_message(bot, message.chat.id, text)

    @bot.message_handler(commands=["video", "kling", "luma"])
    def cmd_video(message: types.Message):
        user_id = message.from_user.id
        raw_text = message.text or message.caption or ""
        parts = raw_text.split(maxsplit=1)
        if len(parts) > 1 and parts[1].strip():
            # Запрос с описанием видео прямо в команде
            prompt = parts[1].strip()
            from handlers.messages import _process_user_prompt
            _process_user_prompt(bot, message, user_id, f"видео: {prompt}")
            return

        # Если команда без аргументов, показываем интерактивное меню выбора формата и статуса
        from services.video_service import video_service
        v_status = video_service.get_providers_status()
        luma_icon = "🟢 Готов" if v_status["luma"] else "⚪ (нужен ключ)"
        fal_icon = "🟢 Готов" if v_status["fal"] else "⚪ (нужен ключ)"
        runway_icon = "🟢 Готов" if v_status["runway"] else "⚪ (нужен ключ)"

        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_shorts = types.InlineKeyboardButton("📱 9:16 Shorts / Reels", callback_data="vid_ratio:9:16")
        btn_yt = types.InlineKeyboardButton("🖥 16:9 YouTube / Кино", callback_data="vid_ratio:16:9")
        btn_model_set = types.InlineKeyboardButton("🎬 Включить режим Video AI", callback_data="setmodel:video-director")
        markup.add(btn_shorts, btn_yt)
        markup.add(btn_model_set)

        text = (
            "🎬 *Video AI Режиссер и Генератор Видео*\n\n"
            "Я умею создавать кинематографичные видео и профессиональные монтажные планы:\n"
            "• 🌟 *Kling AI 1.5 & Fal.ai* — реалистичная физика, текучесть и динамика\n"
            "• 🚀 *Luma Dream Machine (Ray 2)* — плавные движения камеры и 35mm эстетика\n"
            "• 🎞 *Minimax Hailuo & Runway Gen-3* — кинематографичные персонажи и свет\n"
            "• 📋 *Director's Cut Storyboard* — раскадровка сцен, хронометраж и саунд-дизайн\n\n"
            "📊 *Статус ключей прямого рендеринга:*\n"
            f"• Luma Dream Machine: {luma_icon}\n"
            f"• Fal.ai (Kling 1.5): {fal_icon}\n"
            f"• Runway Gen-3: {runway_icon}\n\n"
            "💡 *Как запустить генерацию:*\n"
            "1. Отправьте команду с описанием:\n"
            "`/video 9:16 Неоновый спорткар на ночной дождливой трассе`\n"
            "2. Или напишите прямо в чат:\n"
            "_«Гермес, сгенерируй видео: кот в скафандре летит к Марсу»_\n\n"
            "Выберите формат ролика:"
        )
        safe_send_message(bot, message.chat.id, text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("vid_ratio:"))
    def callback_vid_ratio(call: types.CallbackQuery):
        ratio = call.data.split(":", 1)[1]
        label = "📱 9:16 (Shorts / Reels / TikTok)" if ratio == "9:16" else "🖥 16:9 (YouTube / Кино)"
        bot.answer_callback_query(call.id, f"Выбран формат {ratio}")
        text = (
            f"🎬 *Выбран формат:* `{label}`\n\n"
            f"Теперь отправьте в чат команду с описанием сцены, например:\n"
            f"`/video {ratio} Неоновый кот-детектив под дождем в Токио`\n\n"
            f"Либо напишите сообщением:\n"
            f"_«видео {ratio}: закат над океаном, стая дельфинов, кинематографичный свет»_"
        )
        safe_send_message(bot, call.message.chat.id, text)

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

