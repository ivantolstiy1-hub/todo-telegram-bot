import base64
import json
import logging
import requests
import threading
import time
from typing import Optional, Callable, List, Tuple
from config import (
    GEMINI_API_KEYS,
    GEMINI_API_KEY,
    DEFAULT_MODEL,
    SYSTEM_PROMPT,
    MODEL_CASCADES,
    DEFAULT_CASCADE,
    MAX_CONTEXT_CHARS,
)
from services.database import (
    get_user_model,
    add_message,
    get_history,
    get_temperature,
)
from services.self_config_service import self_config_service

logger = logging.getLogger(__name__)

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class ApiKeyPool:
    """
    Потокобезопасный пул API-ключей Gemini с поддержкой:
    - Round-Robin распределения запросов между ключами.
    - Автоматической паузы (cooldown) на 60-65 сек при ошибке 429 (Resource Exhausted).
    - Мониторинга активных ключей и времени ожидания.
    """
    def __init__(self, keys: List[str]):
        self.keys = [k.strip() for k in keys if k and k.strip()]
        self._cooldowns: dict[Tuple[str, str], float] = {}  # (key, model) -> timestamp окончания кулдауна
        self._index = 0
        self._lock = threading.Lock()

    def get_candidate_keys(self, model: str = "") -> List[str]:
        """
        Возвращает упорядоченный список доступных ключей для конкретной модели.
        Квоты Google разделены по моделям!
        """
        with self._lock:
            if not self.keys:
                return []
            now = time.time()
            # Очистка истекших кулдаунов
            for k in list(self._cooldowns.keys()):
                if self._cooldowns[k] <= now:
                    del self._cooldowns[k]

            active = [k for k in self.keys if (k, model) not in self._cooldowns]
            cooling = sorted(
                [k for k in self.keys if (k, model) in self._cooldowns],
                key=lambda k: self._cooldowns.get((k, model), 0)
            )

            if active:
                start = self._index % len(active)
                rotated = active[start:] + active[:start]
                self._index = (self._index + 1) % len(active)
                return rotated + cooling

            return cooling

    def mark_rate_limited(self, key: str, model: str = "", cooldown_seconds: float = 65.0):
        """Помещает ключ на временный карантин для конкретной модели при ошибке 429."""
        with self._lock:
            self._cooldowns[(key, model)] = time.time() + cooldown_seconds
            masked = (key[:6] + "..." + key[-4:]) if len(key) > 10 else "KEY"
            now = time.time()
            active_count = sum(1 for k in self.keys if (k, model) not in self._cooldowns or self._cooldowns.get((k, model), 0) <= now)
            logger.warning(
                f"⚠️ Ключ {masked} исчерпал лимит для модели {model} (429). Пауза {int(cooldown_seconds)}с. "
                f"Свободных ключей для {model}: {active_count}/{len(self.keys)}"
            )

    def get_active_count(self, model: str = "") -> int:
        with self._lock:
            now = time.time()
            return sum(1 for k in self.keys if (k, model) not in self._cooldowns or self._cooldowns[(k, model)] <= now)

    def get_min_wait_time(self, model: str = "") -> float:
        """Возвращает время в секундах до разблокировки ключа для указанной модели."""
        with self._lock:
            now = time.time()
            if not self.keys:
                return 0.0
            if any((k, model) not in self._cooldowns or self._cooldowns[(k, model)] <= now for k in self.keys):
                return 0.0
            cooling_vals = [self._cooldowns[(k, model)] for k in self.keys if (k, model) in self._cooldowns]
            if not cooling_vals:
                return 0.0
            earliest = min(cooling_vals)
            return max(1.0, earliest - now)

    def get_stats(self) -> dict:
        """Возвращает подробную сводку для панели администратора."""
        with self._lock:
            now = time.time()
            key_details = []
            for k in self.keys:
                active_models = [m for (ck, m), cd in self._cooldowns.items() if ck == k and cd > now]
                is_ready = len(active_models) == 0
                masked = (k[:6] + "..." + k[-4:]) if len(k) > 10 else "***"
                key_details.append({
                    "masked": masked,
                    "active": is_ready,
                    "cooldown_left": 0 if is_ready else 60
                })
            active_total = sum(1 for kd in key_details if kd["active"])
            return {
                "total": len(self.keys),
                "active": active_total,
                "cooldown": len(self.keys) - active_total,
                "keys": key_details
            }

    def reload_keys(self, raw_keys: str):
        """Динамически обновляет список ключей Gemini без перезагрузки бота."""
        with self._lock:
            new_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
            if new_keys:
                self.keys = new_keys
                self._cooldowns.clear()
                logger.info(f"🔑 Gemini ApiKeyPool обновлен: {len(self.keys)} ключей загружено.")


class GeminiService:
    def __init__(self, keys: Optional[List[str]] = None):
        key_list = keys if keys is not None else GEMINI_API_KEYS
        self.key_pool = ApiKeyPool(key_list)

    def _extract_text(self, data: dict) -> str:
        """Извлекает текст ответа модели из структуры ответа Google."""
        candidates = data.get("candidates", [])
        if not candidates:
            prompt_feedback = data.get("promptFeedback", {})
            block_reason = prompt_feedback.get("blockReason")
            if block_reason:
                raise RuntimeError(f"⚠️ Запрос отклонен политикой безопасности Google: {block_reason}")
            raise RuntimeError("❌ Пустой ответ от модели.")

        first_cand = candidates[0]
        content = first_cand.get("content", {})
        parts = content.get("parts", [])
        
        text_pieces = []
        for p in parts:
            if "text" in p:
                text_pieces.append(p["text"])
        
        result_text = "".join(text_pieces).strip()
        if not result_text:
            finish_reason = first_cand.get("finishReason", "UNKNOWN")
            return f"⚠️ Модель завершила ответ без текста (причина: {finish_reason})."

        return result_text

    def _call_api_with_fallback(
        self,
        preferred_model: str,
        payload: dict,
        on_status: Optional[Callable[[str], None]] = None
    ) -> Tuple[str, str]:
        """
        Интеллектуальный вызов Gemini API:
        1. Использует пул ключей с авто-ротацией при 429.
        2. При исчерпании лимитов на текущей модели мгновенно переключается на каскадную модель
           (у каждой модели отдельный лимит RPM в Google).
        3. Выполняет адаптивный Exponential Backoff вместо падения с ошибкой.
        Возвращает кортеж: (ответ_модели, использованная_модель).
        """
        # Формируем цепочку моделей
        cascade = MODEL_CASCADES.get(preferred_model, DEFAULT_CASCADE).copy()
        if preferred_model in cascade:
            cascade.remove(preferred_model)
        cascade.insert(0, preferred_model)

        max_passes = 2
        last_error_msg = ""

        for pass_num in range(max_passes):
            for model_idx, model in enumerate(cascade):
                candidate_keys = self.key_pool.get_candidate_keys(model=model)
                if not candidate_keys:
                    raise RuntimeError("❌ Пул API-ключей Gemini пуст. Добавьте GEMINI_API_KEY в .env")

                for key_idx, key in enumerate(candidate_keys):
                    # Проверяем, нужно ли кратковременно подождать
                    wait_s = self.key_pool.get_min_wait_time(model=model)
                    if wait_s > 0 and wait_s <= 8.0:
                        if on_status:
                            on_status(f"⏳ Ожидание квоты API ({int(wait_s)} сек)...")
                        time.sleep(wait_s)

                    url = f"{GEMINI_API_BASE_URL}/{model}:generateContent?key={key}"
                    headers = {"Content-Type": "application/json"}

                    try:
                        response = requests.post(url, headers=headers, json=payload, timeout=50)
                    except requests.exceptions.Timeout:
                        logger.warning(f"Таймаут запроса к {model} (ключ ...{key[-4:]})")
                        last_error_msg = "Превышено время ожидания ответа от Google (таймаут)"
                        time.sleep(1.5)
                        continue
                    except requests.exceptions.RequestException as e:
                        logger.warning(f"Сетевая ошибка при запросе к {model}: {e}")
                        last_error_msg = f"Сетевая ошибка подключения: {e}"
                        time.sleep(1.5)
                        continue

                    # УСПЕХ: 200 OK
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            return self._extract_text(data), model
                        except Exception as e:
                            logger.error(f"Ошибка парсинга ответа от {model}: {e}")
                            raise RuntimeError(f"❌ Ошибка обработки ответа модели: {e}")

                    # ОШИБКА 429: Лимит запросов в минуту (RPM) или токенов (TPM)
                    if response.status_code == 429:
                        self.key_pool.mark_rate_limited(key, model=model, cooldown_seconds=65.0)
                        last_error_msg = "429 Too Many Requests (превышен минутный лимит Google)"

                        # Если есть еще свободные ключи для этой модели, сразу пробуем следующий
                        remaining_active = self.key_pool.get_active_count(model=model)
                        if remaining_active > 0:
                            if on_status:
                                on_status(f"🔄 Смена API-ключа (осталось активных: {remaining_active})...")
                            time.sleep(0.5)
                            continue
                        else:
                            # Все ключи для данной модели исчерпали квоту -> каскадируем на СЛЕДУЮЩУЮ модель!
                            next_model_idx = model_idx + 1
                            if next_model_idx < len(cascade):
                                next_model = cascade[next_model_idx]
                                if on_status:
                                    on_status(f"⚡ Лимит модели исчерпан, переключаюсь на резервную модель {next_model}...")
                                logger.info(f"Каскадный переход: {model} -> {next_model}")
                                time.sleep(0.5)
                                break  # переходим к следующей модели в цикле cascade
                            continue

                    # ОШИБКА 503: Временная перегрузка серверов Google
                    if response.status_code == 503:
                        logger.warning(f"Сервер Google 503 перегружен на {model}")
                        if on_status:
                            on_status("⚠️ Модель временно перегружена Google, пробую резервный путь...")
                        time.sleep(2.0)
                        continue

                    # ОШИБКА 400: Неверный ключ или аргумент
                    if response.status_code == 400:
                        try:
                            err_data = response.json()
                            err_msg = err_data.get("error", {}).get("message", response.text)
                        except Exception:
                            err_msg = response.text

                        if "API key not valid" in err_msg or "API_KEY_INVALID" in err_msg:
                            logger.error(f"Невалидный API ключ ...{key[-4:]}: {err_msg}")
                            self.key_pool.mark_rate_limited(key, cooldown_seconds=86400.0)
                            continue

                        # Неизвестная ошибка 400 (например, контент)
                        raise RuntimeError(f"❌ Ошибка запроса ({response.status_code}): {err_msg}")

                    # Другие ошибки
                    logger.warning(f"Google API вернул код {response.status_code}: {response.text[:200]}")
                    last_error_msg = f"Код {response.status_code}: {response.text[:150]}"

            # Если после полного прохода по всем моделям и ключам все еще лимиты, делаем паузу
            wait_time = self.key_pool.get_min_wait_time()
            if pass_num < max_passes - 1 and wait_time <= 25.0:
                if on_status:
                    on_status(f"⏳ Все лимиты исчерпаны. Авто-повтор через {int(wait_time)}с...")
                time.sleep(wait_time)

        raise RuntimeError(
            f"⚠️ Все доступные модели и ключи временно исчерпали квоту запросов ({last_error_msg}). "
            "Пожалуйста, подождите 30 секунд или добавьте дополнительный бесплатный ключ в .env."
        )

    def _optimize_context(self, history: list, current_user_content: dict, model: str = "") -> list:
        """
        Ограничивает суммарный размер контекста (Sliding Window).
        Для Pro-моделей лимит существенно расширен (до 150 000 символов),
        для Flash-моделей используется компактный экономный бюджет.
        """
        max_chars = 150000 if "pro" in (model or "").lower() else MAX_CONTEXT_CHARS
        curr_len = sum(len(p.get("text", "")) for p in current_user_content.get("parts", []))
        budget = max(0, max_chars - curr_len)

        selected_reversed = []
        acc_len = 0
        for item in reversed(history):
            item_len = sum(len(p.get("text", "")) for p in item.get("parts", []))
            if acc_len + item_len > budget:
                break
            selected_reversed.append(item)
            acc_len += item_len

        selected_reversed.reverse()
        return selected_reversed + [current_user_content]

    def chat(self, user_id: int, user_message: str, on_status: Optional[Callable[[str], None]] = None) -> str:
        """
        Отправляет текстовое сообщение в контексте диалога с пользователем.
        Сохраняет вопрос и ответ в базе данных.
        """
        model = get_user_model(user_id)
        sys_prompt = self_config_service.build_effective_system_prompt(user_id)
        is_pro = "pro" in (model or "").lower()
        configured_temp = get_temperature()
        effective_temp = min(configured_temp, 0.5) if is_pro else configured_temp

        history = get_history(user_id)
        current_user_content = {
            "role": "user",
            "parts": [{"text": user_message}]
        }
        contents = self._optimize_context(history, current_user_content, model=model)

        payload = {
            "contents": contents,
            "systemInstruction": {
                "parts": [{"text": sys_prompt}]
            },
            "generationConfig": {
                "temperature": effective_temp,
                "maxOutputTokens": 8192 if is_pro else 4096,
            }
        }

        reply, used_model = self._call_api_with_fallback(model, payload, on_status=on_status)

        add_message(user_id, "user", user_message)
        add_message(user_id, "model", reply)
        return reply

    def analyze_image(
        self,
        user_id: int,
        image_bytes: bytes,
        mime_type: str,
        caption: str = "",
        on_status: Optional[Callable[[str], None]] = None
    ) -> str:
        """Анализирует изображение с опциональным вопросом."""
        model = get_user_model(user_id)
        sys_prompt = self_config_service.build_effective_system_prompt(user_id)
        b64_data = base64.b64encode(image_bytes).decode("utf-8")

        prompt = caption.strip() if caption else "Подробно опиши, что изображено на картинке, и ответь на любые явные или подразумеваемые вопросы."
        parts = [
            {"text": prompt},
            {"inlineData": {"mimeType": mime_type, "data": b64_data}}
        ]

        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "systemInstruction": {"parts": [{"text": sys_prompt}]},
            "generationConfig": {"temperature": 0.5, "maxOutputTokens": 8192 if "pro" in (model or "").lower() else 4096}
        }

        reply, _ = self._call_api_with_fallback(model, payload, on_status=on_status)
        add_message(user_id, "user", f"[Отправлено изображение]: {prompt}")
        add_message(user_id, "model", reply)
        return reply

    def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
        """
        Сверхбыстрая и точная транскрибация голосового сообщения в текст.
        Использует gemini-3.5-flash (высокая скорость и точность понимания русской речи).
        """
        b64_data = base64.b64encode(audio_bytes).decode("utf-8")
        parts = [
            {"text": "Точно транскрибируй аудиозапись в текст на исходном языке. Выведи ТОЛЬКО расшифрованный текст пользователя без вступительных фраз, кавычек и комментариев."},
            {"inlineData": {"mimeType": mime_type, "data": b64_data}}
        ]
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 2048}
        }
        text, _ = self._call_api_with_fallback("gemini-3.5-flash", payload)
        return text.strip()

    def analyze_audio(
        self,
        user_id: int,
        audio_bytes: bytes,
        mime_type: str,
        caption: str = "",
        on_status: Optional[Callable[[str], None]] = None
    ) -> str:
        """Обрабатывает аудио/голосовое сообщение с помощью Gemini."""
        model = get_user_model(user_id)
        sys_prompt = self_config_service.build_effective_system_prompt(user_id)
        b64_data = base64.b64encode(audio_bytes).decode("utf-8")

        prompt = caption.strip() if caption else "Прослушай это голосовое сообщение, транскрибируй его смысл и дай подробный, полезный ответ."
        parts = [
            {"text": prompt},
            {"inlineData": {"mimeType": mime_type, "data": b64_data}}
        ]

        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "systemInstruction": {"parts": [{"text": sys_prompt}]},
            "generationConfig": {"temperature": 0.5, "maxOutputTokens": 8192 if "pro" in (model or "").lower() else 4096}
        }

        reply, _ = self._call_api_with_fallback(model, payload, on_status=on_status)
        add_message(user_id, "user", f"[Голосовое сообщение]: {prompt}")
        add_message(user_id, "model", reply)
        return reply

    def analyze_document(
        self,
        user_id: int,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
        caption: str = "",
        on_status: Optional[Callable[[str], None]] = None
    ) -> str:
        """Обрабатывает текстовый документ или PDF."""
        model = get_user_model(user_id)
        sys_prompt = self_config_service.build_effective_system_prompt(user_id)
        prompt = caption.strip() if caption else f"Изучи прикрепленный файл '{filename}' и кратко резюмируй его содержание или ключевые выводы."

        if mime_type.startswith("text/") or filename.endswith((".py", ".txt", ".md", ".json", ".csv", ".html", ".js", ".css")):
            try:
                text_content = file_bytes.decode("utf-8", errors="replace")
                full_prompt = f"{prompt}\n\nФайл: {filename}\n```\n{text_content[:20000]}\n```"
                parts = [{"text": full_prompt}]
            except Exception:
                b64_data = base64.b64encode(file_bytes).decode("utf-8")
                parts = [{"text": prompt}, {"inlineData": {"mimeType": mime_type or "application/octet-stream", "data": b64_data}}]
        else:
            b64_data = base64.b64encode(file_bytes).decode("utf-8")
            parts = [
                {"text": prompt},
                {"inlineData": {"mimeType": mime_type or "application/pdf", "data": b64_data}}
            ]

        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "systemInstruction": {"parts": [{"text": sys_prompt}]},
            "generationConfig": {"temperature": 0.5, "maxOutputTokens": 8192 if "pro" in (model or "").lower() else 4096}
        }

        reply, _ = self._call_api_with_fallback(model, payload, on_status=on_status)
        add_message(user_id, "user", f"[Документ {filename}]: {prompt}")
        add_message(user_id, "model", reply)
        return reply


gemini_service = GeminiService()
