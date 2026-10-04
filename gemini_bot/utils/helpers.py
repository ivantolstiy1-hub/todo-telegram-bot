import re
import logging
from telebot import TeleBot

logger = logging.getLogger(__name__)

def split_message(text: str, max_length: int = 4000) -> list[str]:
    """Разбивает длинный текст на части, сохраняя целостность абзацев и строк."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""
    lines = text.split("\n")

    for line in lines:
        # Если добавление строки превышает лимит
        if len(current_chunk) + len(line) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            
            # Если сама строка больше лимита, режем её по словам/символам
            while len(line) > max_length:
                split_pos = line.rfind(" ", 0, max_length)
                if split_pos == -1:
                    split_pos = max_length
                chunks.append(line[:split_pos].strip())
                line = line[split_pos:].lstrip()

            current_chunk = line
        else:
            if current_chunk:
                current_chunk += "\n" + line
            else:
                current_chunk = line

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks

def safe_send_message(bot: TeleBot, chat_id: int, text: str, reply_markup=None, reply_to_message_id=None):
    """
    Отправляет сообщение в Telegram.
    Сначала пытается отправить с Markdown. Если Telegram отклоняет из-за спецсимволов,
    отправляет как обычный текст без сбоев.
    """
    chunks = split_message(text)
    sent_messages = []

    for i, chunk in enumerate(chunks):
        # Прикрепляем клавиатуру только к последнему сообщению пачки
        markup = reply_markup if i == len(chunks) - 1 else None
        reply_id = reply_to_message_id if i == 0 else None

        try:
            msg = bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode="Markdown",
                reply_markup=markup,
                reply_to_message_id=reply_id,
                disable_web_page_preview=True
            )
            sent_messages.append(msg)
        except Exception as e:
            logger.warning(f"Ошибка отправки с Markdown: {e}. Повтор в обычном текстовом режиме.")
            try:
                msg = bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode=None,
                    reply_markup=markup,
                    reply_to_message_id=reply_id,
                    disable_web_page_preview=True
                )
                sent_messages.append(msg)
            except Exception as final_e:
                logger.error(f"Не удалось отправить сообщение: {final_e}")
                raise final_e

    return sent_messages
