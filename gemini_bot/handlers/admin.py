import logging
import datetime
from telebot import TeleBot, types
from config import ADMIN_ID, ADMIN_IDS, DEFAULT_MODEL
from services.database import (
    get_total_users,
    get_total_messages,
    get_active_antigravity_sessions_count,
    get_all_users_list,
    get_all_user_ids,
    get_setting,
    set_setting,
)
from utils.helpers import safe_send_message, split_message

logger = logging.getLogger(__name__)

from services.gemini_service import gemini_service

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS or user_id == ADMIN_ID

def get_admin_main_keyboard() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_stats = types.InlineKeyboardButton("📊 Статистика", callback_data="admin:stats")
    btn_keys = types.InlineKeyboardButton("🔑 Пул API ключей", callback_data="admin:keys")
    btn_users = types.InlineKeyboardButton("👥 Пользователи", callback_data="admin:users")
    btn_access = types.InlineKeyboardButton("🛡 Доступ к Агенту", callback_data="admin:access")
    btn_config = types.InlineKeyboardButton("⚙️ Самонастройка", callback_data="admin:config")
    btn_refresh = types.InlineKeyboardButton("🔄 Обновить", callback_data="admin:main")
    markup.add(btn_stats, btn_keys)
    markup.add(btn_users, btn_access)
    markup.add(btn_config, btn_refresh)
    return markup

def build_dashboard_text() -> str:
    total_users = get_total_users()
    total_msgs = get_total_messages()
    active_sessions = get_active_antigravity_sessions_count()
    access_mode = get_setting("agent_access_mode", "admin_only")
    access_label = "🔒 Только Администратор" if access_mode == "admin_only" else "🌐 Все пользователи"
    
    key_stats = gemini_service.key_pool.get_stats()
    keys_active = key_stats["active"]
    keys_total = key_stats["total"]

    text = (
        "👑 *Панель Администратора Antigravity Bot*\n\n"
        f"• 👤 *Пользователей в базе:* `{total_users}`\n"
        f"• 💬 *Всего сообщений:* `{total_msgs}`\n"
        f"• 🤖 *Активных сессий Antigravity:* `{active_sessions}`\n"
        f"• 🛡 *Доступ к режиму Агента:* `{access_label}`\n"
        f"• 🔑 *Пул API-ключей Gemini:* `{keys_active}/{keys_total} активны`\n\n"
        "📢 *Для массовой рассылки используйте команду:*\n"
        "`/broadcast <текст вашего сообщения>`\n\n"
        "Выберите раздел в меню ниже:"
    )
    return text

def register_admin_handlers(bot: TeleBot):

    @bot.message_handler(commands=["admin"])
    def cmd_admin(message: types.Message):
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ У вас нет прав администратора.")
            return

        text = build_dashboard_text()
        bot.send_message(
            message.chat.id,
            text,
            parse_mode="Markdown",
            reply_markup=get_admin_main_keyboard()
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin:"))
    def callback_admin(call: types.CallbackQuery):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Доступ запрещен.", show_alert=True)
            return

        action = call.data.split(":", 1)[1]

        if action == "main":
            text = build_dashboard_text()
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=get_admin_main_keyboard()
                )
            except Exception:
                pass
            bot.answer_callback_query(call.id)

        elif action == "stats":
            total_users = get_total_users()
            total_msgs = get_total_messages()
            active_sessions = get_active_antigravity_sessions_count()
            access_mode = get_setting("agent_access_mode", "admin_only")

            stats_text = (
                "📊 *Детальная статистика системы:*\n\n"
                f"• 👥 Зарегистрировано пользователей: `{total_users}`\n"
                f"• ✉️ Обработано запросов/сообщений: `{total_msgs}`\n"
                f"• ⚡ Выделенных сессий Antigravity CLI: `{active_sessions}`\n"
                f"• 🛡 Политика безопасности: `{access_mode}`\n"
                f"• 🧠 Модель по умолчанию: `{DEFAULT_MODEL}`\n"
                f"• 🕒 Время сервера: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin:main"))
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=stats_text,
                    parse_mode="Markdown",
                    reply_markup=markup
                )
            except Exception:
                pass
            bot.answer_callback_query(call.id)

        elif action == "access":
            current_mode = get_setting("agent_access_mode", "admin_only")
            new_mode = "all" if current_mode == "admin_only" else "admin_only"
            set_setting("agent_access_mode", new_mode)
            
            mode_name = "🌐 Для всех пользователей" if new_mode == "all" else "🔒 Только Администратор"
            bot.answer_callback_query(call.id, f"Доступ к агенту изменен: {mode_name}", show_alert=True)
            
            # Возвращаемся в главное меню с обновленным статусом
            text = build_dashboard_text()
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=get_admin_main_keyboard()
                )
            except Exception:
                pass

        elif action == "config":
            from services.self_config_service import self_config_service
            report = self_config_service.get_current_config_report()
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("⬅️ В меню админа", callback_data="admin:main"))
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=report,
                    parse_mode="Markdown",
                    reply_markup=markup
                )
            except Exception:
                pass
            bot.answer_callback_query(call.id)

        elif action == "users":
            users = get_all_users_list(limit=25)
            lines = ["👥 *Список последних пользователей:*\n"]
            for u in users:
                uname = f"@{u['username']}" if u['username'] else (u['first_name'] or "Без имени")
                session_icon = "🟢" if u['has_agent_session'] else "⚪"
                mode_icon = "🤖" if u['mode'] == 'agent' else "⚡"
                lines.append(f"{session_icon} {mode_icon} *{uname}* (ID: `{u['user_id']}`) — `{u['msg_count']}` сообщ.")

            users_text = "\n".join(lines)
            if not users:
                users_text = "👥 Список пользователей пуст."

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin:main"))
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=users_text,
                    parse_mode="Markdown",
                    reply_markup=markup
                )
            except Exception:
                pass
            bot.answer_callback_query(call.id)

        elif action == "keys":
            from utils.helpers import get_dynamic_api_key
            key_stats = gemini_service.key_pool.get_stats()
            lines = [
                "🔑 *Пул API-ключей Gemini и лимиты:*\n",
                f"• Всего Gemini ключей: `{key_stats['total']}`",
                f"• Активных: `{key_stats['active']}`",
                f"• На паузе (кулдаун): `{key_stats['cooldown']}`\n",
                "*Зарегистрированные ключи Gemini:*"
            ]
            for idx, kinfo in enumerate(key_stats["keys"], 1):
                status_icon = "🟢 Готов" if kinfo["active"] else f"⏳ Пауза ({kinfo['cooldown_left']}с)"
                lines.append(f"{idx}. `{kinfo['masked']}` — {status_icon}")

            # Статус Video AI и Multi-LLM ключей
            fal_k = get_dynamic_api_key("FAL_KEY")
            luma_k = get_dynamic_api_key("LUMA_API_KEY")
            openrouter_k = get_dynamic_api_key("OPENROUTER_API_KEY")
            deepseek_k = get_dynamic_api_key("DEEPSEEK_API_KEY")
            openai_k = get_dynamic_api_key("OPENAI_API_KEY")

            def mask_k(k: str) -> str:
                if not k or len(k) < 8:
                    return "⚪ Не настроен"
                return f"🟢 `{k[:6]}...{k[-4:]}`"

            lines.append("\n🎬 *Video AI & Генерация:*")
            lines.append(f"• `FAL_KEY` (Kling 1.5, Minimax): {mask_k(fal_k)}")
            lines.append(f"• `LUMA_API_KEY` (Ray 2): {mask_k(luma_k)}")

            lines.append("\n🧠 *Multi-LLM (Агент Гермес):*")
            lines.append(f"• `OPENROUTER_API_KEY`: {mask_k(openrouter_k)}")
            lines.append(f"• `DEEPSEEK_API_KEY`: {mask_k(deepseek_k)}")
            lines.append(f"• `OPENAI_API_KEY`: {mask_k(openai_k)}")

            lines.append("\n💡 *Команда быстрой смены ключей прямо в чате:*")
            lines.append("`/set_key FAL_KEY ваш_ключ`")
            lines.append("`/set_key GEMINI_API_KEYS ключ1,ключ2`")

            keys_text = "\n".join(lines)
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔄 Обновить статус", callback_data="admin:keys"))
            markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin:main"))
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=keys_text,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                    reply_markup=markup
                )
            except Exception:
                pass
            bot.answer_callback_query(call.id)

    @bot.message_handler(commands=["set_key"])
    def cmd_set_key(message: types.Message):
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ У вас нет прав администратора.")
            return

        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            bot.reply_to(
                message,
                "⚠️ *Формат команды:*\n"
                "`/set_key KEY_NAME VALUE`\n\n"
                "*Примеры:*\n"
                "• `/set_key FAL_KEY fal_sk_...`\n"
                "• `/set_key LUMA_API_KEY luma_...`\n"
                "• `/set_key OPENROUTER_API_KEY sk-or-...`\n"
                "• `/set_key GEMINI_API_KEYS AIzaSy...`",
                parse_mode="Markdown"
            )
            return

        key_name = parts[1].strip().upper()
        key_val = parts[2].strip()

        ALLOWED_KEYS = {
            "FAL_KEY",
            "LUMA_API_KEY",
            "RUNWAY_API_KEY",
            "OPENROUTER_API_KEY",
            "DEEPSEEK_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GEMINI_API_KEY",
            "GEMINI_API_KEYS",
        }

        if key_name not in ALLOWED_KEYS:
            bot.reply_to(
                message,
                f"⚠️ Неизвестный ключ `{key_name}`. Допустимые ключи:\n" +
                ", ".join(f"`{k}`" for k in sorted(ALLOWED_KEYS)),
                parse_mode="Markdown"
            )
            return

        # Сохраняем в SQLite и os.environ
        set_setting(key_name, key_val)
        import os
        os.environ[key_name] = key_val

        # Если обновлен GEMINI_API_KEYS, обновляем пул
        if key_name in ("GEMINI_API_KEY", "GEMINI_API_KEYS"):
            gemini_service.key_pool.reload_keys(key_val)

        masked = key_val[:8] + "..." + key_val[-4:] if len(key_val) > 12 else "***"
        extra_note = ""

        # Для FAL_KEY проводим быструю онлайн-проверку аккаунта
        if key_name == "FAL_KEY":
            try:
                import requests
                resp = requests.get(
                    "https://rest.alpha.fal.ai/users/current",
                    headers={"Authorization": f"Key {key_val}"},
                    timeout=5
                )
                if resp.status_code == 200:
                    info = resp.json()
                    user_login = info.get("user_id") or info.get("display_name", "")
                    is_locked = info.get("is_locked", False)
                    lock_reason = info.get("lock_reason", "")
                    if is_locked:
                        extra_note = (
                            f"\n\n⚠️ *Статус Fal.ai:* Аккаунт `{user_login}` подтвержден, "
                            f"но заблокирован: `{lock_reason}`.\n"
                            f"👉 Пополните баланс на https://fal.ai/dashboard/billing"
                        )
                    else:
                        extra_note = f"\n\n✨ *Fal.ai:* Аккаунт `{user_login}` активен, баланс доступен!"
                else:
                    extra_note = f"\n\n⚠️ Fal.ai API код ответа: {resp.status_code} ({resp.text[:100]})"
            except Exception as e:
                extra_note = f"\n\nℹ️ Не удалось проверить статус Fal.ai онлайн: {e}"

        bot.reply_to(
            message,
            f"✅ *Ключ `{key_name}` успешно сохранен и активирован!*\n"
            f"🔑 Значение: `{masked}`{extra_note}",
            parse_mode="Markdown"
        )

    @bot.message_handler(commands=["broadcast"])
    def cmd_broadcast(message: types.Message):
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ У вас нет прав администратора.")
            return

        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) < 2:
            bot.reply_to(
                message,
                "⚠️ *Формат команды:*\n`/broadcast Ваше сообщение для всех пользователей`",
                parse_mode="Markdown"
            )
            return

        broadcast_text = command_parts[1].strip()
        user_ids = get_all_user_ids()

        status_msg = bot.reply_to(
            message,
            f"📢 *Запуск рассылки...*\nПолучателей: `{len(user_ids)}`",
            parse_mode="Markdown"
        )

        sent_count = 0
        error_count = 0

        formatted_broadcast = f"📢 *Оповещение от Администратора:*\n\n{broadcast_text}"

        for uid in user_ids:
            try:
                safe_send_message(bot, uid, formatted_broadcast)
                sent_count += 1
            except Exception as e:
                logger.warning(f"Не удалось доставить рассылку пользователю {uid}: {e}")
                error_count += 1

        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            text=(
                "✅ *Рассылка завершена!*\n\n"
                f"• 👥 Всего пользователей: `{len(user_ids)}`\n"
                f"• ✉️ Успешно доставлено: `{sent_count}`\n"
                f"• ⚠️ Ошибок отправки: `{error_count}`"
            ),
            parse_mode="Markdown"
        )
