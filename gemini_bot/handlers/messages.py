import io
import threading
import logging
from telebot import TeleBot, types
from services.gemini_service import gemini_service
from services.hermes_service import hermes_service
from services.antigravity_service import antigravity_service
from services.database import (
    ensure_user,
    get_user_model,
    get_user_engine_mode,
    get_user_antigravity_conv,
    set_user_antigravity_conv,
    add_message,
    get_setting
)
from handlers.admin import is_admin
from services.self_config_service import self_config_service
from utils.helpers import safe_send_message

logger = logging.getLogger(__name__)


def _process_user_prompt(bot: TeleBot, message: types.Message, user_id: int, user_text: str):
    """
    Единая точка входа для обработки запроса пользователя (текстового или расшифрованного из голоса).
    Маршрутизирует запрос либо в Агент Гермес (Мульти-LLM), либо в Antigravity Agent (CLI).
    """
    ensure_user(user_id, username=message.from_user.username, first_name=message.from_user.first_name)

    # Самонастройка бота (Self-Configuration) по запросу администратора
    config_reply = self_config_service.detect_and_execute(user_id, user_text, is_admin=is_admin(user_id))
    if config_reply:
        safe_send_message(bot, message.chat.id, config_reply, reply_to_message_id=message.message_id)
        return

    # Проверка явного вызова Агента Гермес или конкретной LLM (например: "Гермес, спроси у DeepSeek: ...")
    explicit_model, _ = hermes_service.parse_explicit_route(user_text)

    mode = get_user_engine_mode(user_id)
    access_mode = get_setting("agent_access_mode", "admin_only")

    # Проверка прав доступа к Antigravity CLI
    if mode == "agent" and access_mode == "admin_only" and not is_admin(user_id):
        safe_send_message(
            bot,
            message.chat.id,
            "ℹ️ _Режим Antigravity Agent с доступом к терминалу и кодовой базе ограничен Администратором. Запрос перенаправлен в Агент Гермес._"
        )
        mode = "hermes"

    # ---------------------------------------------------------
    # РЕЖИМ: ANTIGRAVITY AGENT (CLI) - только если нет явного вызова Гермеса
    # ---------------------------------------------------------
    if not explicit_model and mode == "agent" and antigravity_service.is_available():
        conv_id = get_user_antigravity_conv(user_id)
        is_new = conv_id is None

        init_status_text = (
            "🤖 *Antigravity Agent:* Инициализирую сессию агента... ⏳\n_(Первый запуск сессии занимает ~30-50 сек)_"
            if is_new else
            "🤖 *Antigravity Agent:* Приступаю к выполнению задачи..."
        )

        status_msg = bot.send_message(
            message.chat.id,
            init_status_text,
            parse_mode="Markdown",
            reply_to_message_id=message.message_id
        )

        stop_typing = threading.Event()
        def keep_typing():
            while not stop_typing.is_set():
                try:
                    bot.send_chat_action(message.chat.id, "typing")
                except Exception:
                    pass
                stop_typing.wait(4.0)

        typing_thread = threading.Thread(target=keep_typing, daemon=True)
        typing_thread.start()

        last_action_text = ""
        def on_progress(action_desc: str):
            nonlocal last_action_text
            if action_desc != last_action_text:
                last_action_text = action_desc
                try:
                    bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                        text=f"🤖 *Antigravity Agent:*\n{action_desc}",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

        try:
            if not conv_id:
                user_tag = message.from_user.username or f"id{user_id}"
                user_model = get_user_model(user_id)
                conv_id, reply = antigravity_service.create_conversation(
                    user_text,
                    model=user_model,
                    title=f"TG_{user_id}_{user_tag}",
                    on_progress=on_progress
                )
                set_user_antigravity_conv(user_id, conv_id)
            else:
                reply = antigravity_service.send_message(conv_id, user_text, on_progress=on_progress)

            try:
                bot.delete_message(message.chat.id, status_msg.message_id)
            except Exception:
                pass

            add_message(user_id, "user", user_text)
            add_message(user_id, "model", reply)
            safe_send_message(bot, message.chat.id, reply, reply_to_message_id=message.message_id)
            return
        except Exception as e:
            logger.exception("Ошибка при работе через Antigravity Agent, переключение на резервный режим:")
            try:
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    text=f"⚠️ _Antigravity Agent переключился на Gemini API ({e}). Подключаю каскад моделей..._",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        finally:
            stop_typing.set()

    # ---------------------------------------------------------
    # РЕЖИМ: АГЕНТ ГЕРМЕС / МУЛЬТИ-LLM (или резервный при ошибке агента)
    # ---------------------------------------------------------
    bot.send_chat_action(message.chat.id, "typing")
    dynamic_status_msg_id = None

    def on_direct_status(text: str):
        nonlocal dynamic_status_msg_id
        try:
            if dynamic_status_msg_id is None:
                msg = bot.send_message(
                    message.chat.id,
                    f"_{text}_",
                    parse_mode="Markdown",
                    reply_to_message_id=message.message_id
                )
                dynamic_status_msg_id = msg.message_id
            else:
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=dynamic_status_msg_id,
                    text=f"_{text}_",
                    parse_mode="Markdown"
                )
        except Exception:
            pass

    try:
        reply = hermes_service.chat(user_id=user_id, user_message=user_text, on_status=on_direct_status)
        if dynamic_status_msg_id:
            try:
                bot.delete_message(message.chat.id, dynamic_status_msg_id)
            except Exception:
                pass

        # Проверка наличия сгенерированного видео для прямой отправки файлом
        from services.video_service import video_service
        video_url = video_service.extract_video_url(reply)
        if video_url:
            try:
                bot.send_chat_action(message.chat.id, "upload_video")
                bot.send_video(
                    message.chat.id,
                    video_url,
                    caption=f"🎬 Сгенерированное AI-видео\n«{user_text[:100]}»",
                    reply_to_message_id=message.message_id
                )
            except Exception as vid_err:
                logger.warning(f"Не удалось отправить видео напрямую: {vid_err}")

        safe_send_message(bot, message.chat.id, reply, reply_to_message_id=message.message_id)
    except Exception as e:
        logger.exception("Ошибка при обработке сообщения:")
        if dynamic_status_msg_id:
            try:
                bot.delete_message(message.chat.id, dynamic_status_msg_id)
            except Exception:
                pass
        safe_send_message(
            bot,
            message.chat.id,
            f"⚠️ Произошла ошибка при обработке запроса:\n_{str(e)}_",
            reply_to_message_id=message.message_id
        )


def register_message_handlers(bot: TeleBot):

    @bot.message_handler(content_types=["text"])
    def handle_text(message: types.Message):
        user_id = message.from_user.id
        user_text = message.text.strip()
        if not user_text:
            return
        _process_user_prompt(bot, message, user_id, user_text)

    @bot.message_handler(content_types=["voice"])
    def handle_voice(message: types.Message):
        user_id = message.from_user.id
        ensure_user(user_id, username=message.from_user.username, first_name=message.from_user.first_name)
        caption = message.caption or ""

        bot.send_chat_action(message.chat.id, "typing")

        try:
            file_info = bot.get_file(message.voice.file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            # 1. Быстрая и точная транскрибация речи
            transcribed_text = gemini_service.transcribe_audio(downloaded_file, mime_type="audio/ogg")
            
            if transcribed_text:
                full_prompt = f"{transcribed_text}\n\n{caption}".strip() if caption else transcribed_text
                safe_send_message(
                    bot,
                    message.chat.id,
                    f"🎙 *Распознано голосовое сообщение:*\n«_{full_prompt}_»",
                    reply_to_message_id=message.message_id
                )
                # 2. Направляем команду в Antigravity Agent или Gemini Direct
                _process_user_prompt(bot, message, user_id, full_prompt)
            else:
                # Резервный вызов прямого анализа аудио
                reply = gemini_service.analyze_audio(
                    user_id=user_id,
                    audio_bytes=downloaded_file,
                    mime_type="audio/ogg",
                    caption=caption
                )
                safe_send_message(bot, message.chat.id, reply, reply_to_message_id=message.message_id)

        except Exception as e:
            logger.exception("Ошибка при обработке голосового сообщения:")
            safe_send_message(
                bot,
                message.chat.id,
                f"⚠️ Не удалось обработать голосовое сообщение:\n_{str(e)}_",
                reply_to_message_id=message.message_id
            )

    @bot.message_handler(content_types=["photo"])
    def handle_photo(message: types.Message):
        user_id = message.from_user.id
        ensure_user(user_id, username=message.from_user.username, first_name=message.from_user.first_name)
        caption = message.caption or ""

        bot.send_chat_action(message.chat.id, "typing")

        try:
            photo_info = message.photo[-1]
            file_info = bot.get_file(photo_info.file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            reply = gemini_service.analyze_image(
                user_id=user_id,
                image_bytes=downloaded_file,
                mime_type="image/jpeg",
                caption=caption
            )
            safe_send_message(bot, message.chat.id, reply, reply_to_message_id=message.message_id)
        except Exception as e:
            logger.exception("Ошибка при обработке фотографии:")
            safe_send_message(
                bot,
                message.chat.id,
                f"⚠️ Не удалось обработать фото:\n_{str(e)}_",
                reply_to_message_id=message.message_id
            )

    @bot.message_handler(content_types=["document"])
    def handle_document(message: types.Message):
        user_id = message.from_user.id
        ensure_user(user_id, username=message.from_user.username, first_name=message.from_user.first_name)
        caption = message.caption or ""
        doc = message.document

        bot.send_chat_action(message.chat.id, "typing")

        try:
            file_info = bot.get_file(doc.file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            reply = gemini_service.analyze_document(
                user_id=user_id,
                file_bytes=downloaded_file,
                filename=doc.file_name or "file",
                mime_type=doc.mime_type or "application/octet-stream",
                caption=caption
            )
            safe_send_message(bot, message.chat.id, reply, reply_to_message_id=message.message_id)
        except Exception as e:
            logger.exception("Ошибка при обработке документа:")
            safe_send_message(
                bot,
                message.chat.id,
                f"⚠️ Не удалось обработать документ:\n_{str(e)}_",
                reply_to_message_id=message.message_id
            )
