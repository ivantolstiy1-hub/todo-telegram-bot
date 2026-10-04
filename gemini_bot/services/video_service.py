"""
Модуль интеграции передовых нейросетей для генерации и монтажа видео.
Поддерживает:
1. Luma Dream Machine (Ray 2) API
2. Fal.ai Hub (Kling AI 1.5, Minimax Hailuo, Luma Ray)
3. Runway Gen-3 Alpha интеграцию
4. Cinematic Prompt Enhancer (превращение простых фраз в голливудские 4K промпты)
5. Video Director & Storyboard Architect (покадровый монтажный план, раскадровка, саунд-дизайн)
6. Zero-Crash Fallback: работа без ключей с созданием готового сценария и промпт-пака.
"""

import os
import re
import json
import time
import logging
import requests
from abc import ABC, abstractmethod
from typing import Optional, Callable, Dict, Any, List, Tuple, Union

from config import (
    FAL_KEY,
    LUMA_API_KEY,
    RUNWAY_API_KEY,
)
from utils.helpers import get_dynamic_api_key

logger = logging.getLogger(__name__)


# =====================================================================
# 1. БАЗОВЫЙ ИНТЕРФЕЙС И КЛИЕНТЫ ВИДЕО-ПРОВАЙДЕРОВ
# =====================================================================

class BaseVideoProvider(ABC):
    """Базовый абстрактный класс для видеогенераторов."""
    name: str = "base_video"
    display_name: str = "Base Video Provider"

    @abstractmethod
    def is_configured(self) -> bool:
        """Проверяет наличие API-ключа."""
        pass

    @abstractmethod
    def generate_video(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        duration_sec: int = 5,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Генерирует видео по промпту.
        Возвращает dict с полями:
        - status: 'completed' | 'failed' | 'fallback'
        - video_url: Optional[str]
        - provider: str
        - details: str
        """
        pass


class LumaVideoProvider(BaseVideoProvider):
    """
    Провайдер официального API Luma Dream Machine (Ray 2).
    Docs: https://api.lumalabs.ai/dream-machine/v1/generations
    """
    name = "luma"
    display_name = "Luma Dream Machine (Ray 2)"
    CREATE_URL = "https://api.lumalabs.ai/dream-machine/v1/generations"

    @property
    def api_key(self) -> str:
        return get_dynamic_api_key("LUMA_API_KEY", LUMA_API_KEY)

    def is_configured(self) -> bool:
        k = self.api_key
        return bool(k and len(k) > 10)

    def generate_video(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        duration_sec: int = 5,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("LUMA_API_KEY не настроен")
        key = self.api_key or "mock_luma_key"

        if on_status:
            on_status("🎬 Luma Dream Machine: Отправка задания на генерацию...")

        # Соотношение сторон для Luma: 16:9, 9:16, 1:1, 4:3, 21:9
        ratio = "9:16" if "9:16" in aspect_ratio else "16:9"

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "prompt": prompt,
            "aspect_ratio": ratio,
        }

        resp = requests.post(self.CREATE_URL, headers=headers, json=payload, timeout=30)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Luma API error ({resp.status_code}): {resp.text[:300]}")

        data = resp.json()
        gen_id = data.get("id")
        if not gen_id:
            raise RuntimeError(f"Luma API не вернул generation id: {data}")

        # Поллинг статуса генерации
        poll_url = f"{self.CREATE_URL}/{gen_id}"
        max_attempts = 45  # До ~3.5 минут
        for attempt in range(max_attempts):
            time.sleep(5)
            if on_status:
                on_status(f"🎬 Luma Dream Machine: Рендеринг видео... ({attempt * 5} сек) ⏳")

            poll_resp = requests.get(poll_url, headers=headers, timeout=20)
            if poll_resp.status_code != 200:
                continue

            poll_data = poll_resp.json()
            state = poll_data.get("state")

            if state == "completed":
                assets = poll_data.get("assets", {})
                video_url = assets.get("video")
                if video_url:
                    return {
                        "status": "completed",
                        "video_url": video_url,
                        "provider": self.display_name,
                        "details": f"Luma Ray 2 generation completed (ID: {gen_id})",
                    }
            elif state == "failed":
                failure_reason = poll_data.get("failure_reason", "Неизвестная ошибка рендеринга")
                raise RuntimeError(f"Luma generation failed: {failure_reason}")

        raise TimeoutError("Время ожидания генерации видео в Luma истекло (> 3 минут)")


class FalVideoProvider(BaseVideoProvider):
    """
    Провайдер единого хаба Fal.ai.
    Позволяет через один FAL_KEY вызывать Kling 1.5, Minimax Hailuo и Luma Ray.
    """
    name = "fal"
    display_name = "Fal.ai (Kling AI 1.5 / Minimax Hailuo)"
    QUEUE_BASE = "https://queue.fal.run"

    @property
    def api_key(self) -> str:
        return get_dynamic_api_key("FAL_KEY", FAL_KEY)

    def is_configured(self) -> bool:
        k = self.api_key
        return bool(k and len(k) > 10)

    def generate_video(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        duration_sec: int = 5,
        on_status: Optional[Callable[[str], None]] = None,
        model_name: str = "fal-ai/kling-video/v1/standard/text-to-video",
    ) -> Dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("FAL_KEY не настроен")
        key = self.api_key or "mock_fal_key"

        if on_status:
            on_status("⚡ Fal.ai: Постановка задачи в очередь Kling AI 1.5...")

        ratio = "9:16" if "9:16" in aspect_ratio else "16:9"
        duration_str = "5" if duration_sec <= 5 else "10"

        headers = {
            "Authorization": f"Key {key}",
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": prompt,
            "aspect_ratio": ratio,
            "duration": duration_str,
        }

        submit_url = f"{self.QUEUE_BASE}/{model_name}"
        resp = requests.post(submit_url, headers=headers, json=payload, timeout=30)
        if resp.status_code not in (200, 201):
            if resp.status_code == 403 and ("Exhausted" in resp.text or "locked" in resp.text.lower()):
                raise RuntimeError(
                    "На аккаунте fal.ai исчерпан баланс (Exhausted balance). "
                    "Пожалуйста, пополните баланс на https://fal.ai/dashboard/billing для генерации видео."
                )
            raise RuntimeError(f"Fal.ai API error ({resp.status_code}): {resp.text[:300]}")

        data = resp.json()
        status_url = data.get("status_url")
        response_url = data.get("response_url")

        if not status_url or not response_url:
            raise RuntimeError(f"Fal.ai не вернул URL для отслеживания: {data}")

        # Опрос статуса
        max_attempts = 45
        for attempt in range(max_attempts):
            time.sleep(5)
            if on_status:
                on_status(f"⚡ Fal.ai (Kling AI): Генерация видеокадров... ({attempt * 5} сек) ⏳")

            poll_resp = requests.get(status_url, headers=headers, timeout=20)
            if poll_resp.status_code != 200:
                continue

            poll_data = poll_resp.json()
            status = poll_data.get("status")

            if status == "COMPLETED":
                # Получаем готовый результат
                res_resp = requests.get(response_url, headers=headers, timeout=20)
                if res_resp.status_code == 200:
                    res_data = res_resp.json()
                    video_info = res_data.get("video", {})
                    video_url = video_info.get("url")
                    if video_url:
                        return {
                            "status": "completed",
                            "video_url": video_url,
                            "provider": self.display_name,
                            "details": f"Kling 1.5 video rendered successfully via Fal.ai",
                        }
            elif status in ("FAILED", "CANCELLED"):
                error_msg = poll_data.get("error", "Генерация отменена или завершилась с ошибкой")
                raise RuntimeError(f"Fal.ai generation failed: {error_msg}")

        raise TimeoutError("Время ожидания генерации видео в Fal.ai истекло (> 3 минут)")

    def upload_media_if_needed(self, media_data: Union[str, bytes], content_type: str = "video/mp4") -> str:
        """
        Загружает локальные байты или файл в Fal CDN и возвращает публичный URL.
        Если уже передан HTTP(S) URL, возвращает его без изменений.
        """
        if isinstance(media_data, str) and (media_data.startswith("http://") or media_data.startswith("https://")):
            return media_data

        try:
            import fal_client
            key = self.api_key or "mock_fal_key"
            os.environ["FAL_KEY"] = key
            if isinstance(media_data, bytes):
                return fal_client.upload(media_data, content_type=content_type)
            elif isinstance(media_data, str) and os.path.exists(media_data):
                return fal_client.upload_file(media_data)
        except Exception as e:
            logger.warning(f"Ошибка загрузки в Fal CDN: {e}")
            raise
        return str(media_data)

    def generate_video_to_video(
        self,
        video_input: Union[str, bytes],
        prompt: str,
        negative_prompt: str = "ugly, deformed, low quality, distortion, blurry, low resolution, face distortion, changing background, changing lighting",
        strength: float = 0.6,
        duration_sec: int = 5,
        on_status: Optional[Callable[[str], None]] = None,
        model_name: str = "fal-ai/kling/v1.5/video-to-video",
    ) -> Dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("FAL_KEY не настроен")
        key = self.api_key or "mock_fal_key"
        os.environ["FAL_KEY"] = key

        if on_status:
            on_status("📤 Подготовка и загрузка исходного видео в Kling AI 1.5...")

        video_url = self.upload_media_if_needed(video_input, content_type="video/mp4")

        if on_status:
            on_status("🎬 Kling AI 1.5: Запуск Video-to-Video трансформации... ⏳")

        duration_str = "5" if duration_sec <= 5 else "10"
        arguments = {
            "video_url": video_url,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "strength": strength,
            "duration": duration_str,
        }

        try:
            import fal_client
            handler = fal_client.submit(model_name, arguments=arguments)
            result = handler.get()
            out_url = result.get("video", {}).get("url")
            if out_url:
                return {
                    "status": "completed",
                    "video_url": out_url,
                    "provider": "Fal.ai (Kling AI 1.5 Video-to-Video)",
                    "details": "Video-to-Video transformation completed via Kling 1.5",
                }
        except Exception as e:
            err_str = str(e)
            if "Exhausted" in err_str or "locked" in err_str.lower() or "403" in err_str:
                raise RuntimeError(
                    "На аккаунте fal.ai исчерпан баланс (Exhausted balance). "
                    "Пожалуйста, пополните баланс на https://fal.ai/dashboard/billing для генерации видео."
                )
            raise RuntimeError(f"Kling Video-to-Video error: {err_str}")

        raise RuntimeError("Не удалось получить видео из ответа Kling AI 1.5")

    def generate_image_to_video(
        self,
        image_input: Union[str, bytes],
        prompt: str,
        negative_prompt: str = "ugly, deformed, noise, blurry, low resolution, motion blur, bad anatomy",
        duration_sec: int = 5,
        mode: str = "pro",
        on_status: Optional[Callable[[str], None]] = None,
        model_name: str = "fal-ai/kling/v1.5/image-to-video",
    ) -> Dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("FAL_KEY не настроен")
        key = self.api_key or "mock_fal_key"
        os.environ["FAL_KEY"] = key

        if on_status:
            on_status("📤 Подготовка исходного фото в Kling AI 1.5...")

        image_url = self.upload_media_if_needed(image_input, content_type="image/jpeg")

        if on_status:
            on_status("🎬 Kling AI 1.5: Запуск Image-to-Video анимации... ⏳")

        duration_str = "5" if duration_sec <= 5 else "10"
        arguments = {
            "image_url": image_url,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "duration": duration_str,
            "mode": mode,
        }

        try:
            import fal_client
            handler = fal_client.submit(model_name, arguments=arguments)
            result = handler.get()
            out_url = result.get("video", {}).get("url")
            if out_url:
                return {
                    "status": "completed",
                    "video_url": out_url,
                    "provider": "Fal.ai (Kling AI 1.5 Image-to-Video)",
                    "details": "Image-to-Video animation completed via Kling 1.5",
                }
        except Exception as e:
            err_str = str(e)
            if "Exhausted" in err_str or "locked" in err_str.lower() or "403" in err_str:
                raise RuntimeError(
                    "На аккаунте fal.ai исчерпан баланс (Exhausted balance). "
                    "Пожалуйста, пополните баланс на https://fal.ai/dashboard/billing для генерации видео."
                )
            raise RuntimeError(f"Kling Image-to-Video error: {err_str}")

        raise RuntimeError("Не удалось получить видео из ответа Kling AI 1.5")


# =====================================================================
# 2. CINEMATIC PROMPT ENHANCER & DIRECTOR ARCHITECT
# =====================================================================

class CinematicPromptEnhancer:
    """
    Интеллектуальный улучшитель промптов для видео.
    Превращает простое описание в детальный голливудский кинематографичный промпт:
    добавляет тип оптики (35mm/anamorphic), динамику света, движение камеры,
    детализацию текстур и цветовую гамму.
    """

    CINEMATIC_MODIFIERS = [
        "cinematic 4K resolution, photorealistic masterpiece",
        "shot on 35mm anamorphic lens, shallow depth of field",
        "volumetric cinematic lighting, atmospheric rim light",
        "smooth dynamic camera pan, high framerate motion blur, 24fps film grain",
        "hyper-detailed textures, unreal engine 5 render aesthetics, color graded",
    ]

    @classmethod
    def enhance_rule_based(cls, user_prompt: str, aspect_ratio: str = "16:9") -> str:
        """Надежный оффлайн/правильный генератор кинематографичного промпта."""
        cleaned = user_prompt.strip().rstrip(".,")
        aspect_tag = "vertical 9:16 aspect ratio" if "9:16" in aspect_ratio else "widescreen 16:9 cinematic ratio"
        modifiers = ", ".join(cls.CINEMATIC_MODIFIERS)
        return f"{cleaned}, {modifiers}, {aspect_tag}, hyper-realistic, award-winning cinematography"

    @classmethod
    def enhance(cls, user_prompt: str, aspect_ratio: str = "16:9") -> str:
        """
        Улучшает промпт с помощью Gemini API (если доступен) или резервного движка.
        """
        import sys
        if "unittest" in sys.modules or os.getenv("TESTING", "").lower() in ("true", "1"):
            return cls.enhance_rule_based(user_prompt, aspect_ratio)

        try:
            from services.gemini_service import gemini_service
            if gemini_service.key_pool.keys:
                sys_prompt = (
                    "You are a Hollywood Cinematographer and Senior AI Video Director for Kling AI 1.5, Luma Ray 2, and Runway Gen-3. "
                    "Your task is to take the user's idea and convert it into a SINGLE highly effective, descriptive English video prompt. "
                    "Include: visual subject details, camera movement (e.g. slow crane up, fast tracking, orbital pan), "
                    "lens type (35mm anamorphic, bokeh), volumetric lighting (golden hour, neon cyber, studio glow), "
                    "and cinematic color grading. Return ONLY the English prompt, without quotes or explanations."
                )
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": f"Enhance this video idea into a cinematic prompt: {user_prompt}"}]}],
                    "systemInstruction": {"parts": [{"text": sys_prompt}]},
                    "generationConfig": {"temperature": 0.7, "maxOutputTokens": 300},
                }
                reply, _ = gemini_service._call_api_with_fallback("gemini-3.5-flash-lite", payload)
                reply = reply.strip().strip('"').strip("'")
                if len(reply) > 20:
                    return reply
        except Exception as e:
            logger.warning(f"Не удалось использовать Gemini для расширения промпта ({e}), используем встроенный энхансер.")

        return cls.enhance_rule_based(user_prompt, aspect_ratio)


class VideoDirector:
    """
    Режиссер и архитектор монтажа видеоконтента.
    Генерирует профессиональную раскадровку (Storyboard), поминутный план сцен,
    технические параметры камеры, звуковое оформление и готовые промпты для ТОП нейросетей.
    """

    @classmethod
    def build_meme_transformation_plan(
        cls,
        user_idea: str,
        aspect_ratio: str = "9:16",
        duration_sec: int = 12,
    ) -> str:
        """
        Специализированный режиссерский монтажный план для вирусных мем-трансформаций
        (например: перекрашивание в клоуна, морфинг лица, сохранение идентичности и фона).
        """
        format_label = "📱 Вертикальный (9:16 Shorts / Reels / TikTok)" if "9:16" in aspect_ratio else "🖥 Горизонтальный (16:9)"

        storyboard = f"""🎬 *РЕЖИССЕРСКИЙ МОНТАЖНЫЙ ПЛАН: МЕМ-ТРАНСФОРМАЦИЯ ЛИЦА*
━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 *Задача:* {user_idea}
🎭 *Жанр:* Вирусный тренд «Клоунский грим / Clown Makeup Meme Morph»
📐 *Формат:* `{format_label}`
⏱ *Хронометраж:* `{duration_sec} сек.`
🔒 *Ключевое условие:* Сохранение идентичности лица (Face-Lock) и фона комнаты на 100%!

━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 *ПОСЕКУНДНАЯ РАСКАДРОВКА (STORYBOARD)*

⏱ *Сцена 1: [00:00 — 00:03] — Исходный вид (Base Shot)*
• *Визуал:* Крупный план лица девушки с белой базой под макияж (ровно как в прикрепленном видео). Прямой, нейтрально-серьезный взгляд в камеру.
• *Фон и свет:* Интерьер комнаты, мягкий фронтальный свет, сохранение геометрии.
• *Действие:* Девушка делает секундную паузу, слегка приподнимает бровь.
• *Звук:* Начало вирусного трека (*Entry of the Gladiators Trap Remix*).

⏱ *Сцена 2: [00:03 — 00:05] — Мемный триггер / Переход (Transition)*
• *Визуал:* Быстрый жест (взмах кистью перед объективом, щелчок пальцами или резкий кивок).
• *Монтажный эффект:* Whip-pan (хлыстовой зум) + Motion Glitch (эффект помех).
• *Звуковой эффект (SFX):* Резкий свистящий *Whoosh* переход + мемный *Vine Boom Impact*.

⏱ *Сцена 3: [00:05 — 00:09] — AI-Морфинг в клоунский грим (Clown Morph)*
• *Визуал:* Мгновенная трансформация поверх белой основы:
  - Появление яркого круглого красного клоунского носа.
  - Контрастная гиперболизированная алая улыбка с приподнятыми уголками.
  - Поп-арт синие стрелки/слезы под глазами.
• *Ключевой AI-параметр:* Точное сохранение черт лица, формы глаз, мимики и фона комнаты!
• *Музыка:* Мощный цирковой трэп-бит дроп (Circus Theme Trap Drop).

⏱ *Сцена 4: [00:09 — 00:12] — Финальный панчлайн (Deadpan Reaction)*
• *Визуал:* Неподвижный, слегка самоироничный взгляд в камеру (Deadpan / Poker Face) с клоунским гримом.
• *Текст на экране:* Мемная подпись (например: *«Я, когда снова поверила обещаниям:»*).
• *Звуковой эффект (SFX):* Мемный двойной клаксон (*Honk-Honk!* 🤡) + затихающий бит.

━━━━━━━━━━━━━━━━━━━━━━━━━━
🎵 *САУНД-ДИЗАЙН И МУЗЫКА*
• *Главный трек:* `Julius Fučík - Entry of the Gladiators (Circus Trap Remix / Phonk)`
• *SFX пакет:*
  1. `whoosh_fast.mp3` — на переходе (00:03).
  2. `clown_horn_honk.mp3` — звук клаксона на появлении грима (00:05).
  3. `sad_trombone.mp3` или `vine_boom.mp3` — на панчлайне (00:10).

━━━━━━━━━━━━━━━━━━━━━━━━━━
🎥 *ГОТОВЫЕ ПРОМПТЫ ДЛЯ ТОП НЕЙРОСЕТЕЙ (VIDEO-TO-VIDEO):*

1️⃣ *Для Kling AI 1.5 (Video-to-Video & Image-to-Video):*
`video-to-video style transition, young woman with white face base makeup seamlessly transforms into a funny clown meme makeup, bright round red clown nose, exaggerated artistic red clown smile, blue tear accents on cheeks, maintaining exact same face identity, identical facial structure, identical room background and ambient lighting, high temporal consistency, photorealistic 4k, stable motion, no distortion`

2️⃣ *Для Luma Dream Machine Ray 2 (Keyframe Transition):*
`Start frame: young woman with white foundation makeup looking at camera in room. End frame: exact same woman with vibrant meme clown face paint, round red clown nose, theatrical smile, locked facial landmarks and identical indoor room, smooth seamless morphing transition, 35mm lens, photorealistic`

3️⃣ *Для Runway Gen-3 Alpha (Video-to-Video Style Transfer):*
`Video-to-video motion transfer, meme clown makeup transition, preserve exact female facial geometry and room background, clean vibrant clown paint, red nose, expressive clown smile, stable lighting, photorealistic 24fps film grain`

4️⃣ *Для Minimax Hailuo AI:*
`Consistent face identity, video to video clown makeup transition, natural facial movement, preserve indoor background, smooth realistic transition`

━━━━━━━━━━━━━━━━━━━━━━━━━━
✂️ *ИНСТРУКЦИЯ ПО МОНТАЖУ В CAPCUT ЗА 2 МИНУТЫ:*
1. Импортируйте ваше видео в CapCut.
2. Сделайте разрез на 3-й секунде.
3. Ко второй части примените эффект перехода: **«Размытие при движении» (Motion Blur)** или **«Глитч»**.
4. Добавьте стикер/эффект клоунского носа и улыбки из вкладки *«Эффекты тела» -> «Макияж»*.
5. Наложите звуковой эффект *Clown Horn (Клаксон)* ровно в момент перехода!
"""
        return storyboard

    @classmethod
    def build_storyboard_plan(
        cls,
        user_idea: str,
        aspect_ratio: str = "9:16",
        duration_sec: int = 15,
    ) -> str:
        """
        Формирует подробный режиссерский монтажный лист для Shorts / Reels / YouTube / TikTok.
        """
        user_idea_lower = user_idea.lower()
        if any(k in user_idea_lower for k in ["клон", "клоун", "грим", "переход", "мем", "морф", "clown", "makeup", "макияж", "превращени"]):
            return cls.build_meme_transformation_plan(user_idea, aspect_ratio=aspect_ratio, duration_sec=12)

        enhanced_prompt = CinematicPromptEnhancer.enhance(user_idea, aspect_ratio)
        format_label = "📱 Вертикальный (9:16 Shorts / Reels / TikTok)" if "9:16" in aspect_ratio else "🖥 Горизонтальный (16:9 YouTube / Кино)"

        storyboard = f"""🎬 *РЕЖИССЕРСКИЙ МОНТАЖНЫЙ ПЛАН (DIRECTOR'S CUT)*
━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 *Концепция:* {user_idea}
📐 *Формат:* `{format_label}`
⏱ *Хронометраж:* `{duration_sec} сек.`
🎞 *Стиль:* Cinematic 4K, 24 fps, цветокоррекция Teal & Orange / Cyberpunk

━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 *ПОКАДРОВАЯ РАСКАДРОВКА (STORYBOARD)*

⏱ *Сцена 1: [00:00 — 00:03] — Визуальный хук (Hook)*
• *Кадр:* Крупный план (Close-up), резкий фокус.
• *Движение камеры:* Быстрый наезд (Dolly-in) с легким покачиванием ручной камеры.
• *Свет и атмосфера:* Контрастный свет, объемные лучи (God rays / Neon flare).
• *Озвучка / Текст:* Динамичная фраза, захватывающая внимание в первые 2 секунды.
• *Звуковой эффект (SFX):* Глубокий Sub-Bass Impact + легкий Whoosh.

⏱ *Сцена 2: [00:03 — 00:08] — Развитие и динамика (Action)*
• *Кадр:* Средний / Общий план (Medium tracking shot).
• *Движение камеры:* Плавное орбитальное движение вокруг объекта (Orbit / Tracking).
• *Свет:* Мягкий рассеянный контровой свет (Rim lighting), кинематографичный боке.
• *Озвучка:* Основной тезис или смысловое действие сцены.
• *Музыка:* Разгон бита (Drum build-up / Synthesizer riser).

⏱ *Сцена 3: [00:08 — 00:12] — Кульминация (Climax)*
• *Кадр:* Эпический угол снизу (Low-angle hero shot).
• *Движение камеры:* Медленное замедление (Slow-motion 60->24fps) с панорамированием вверх.
• *Спецэффекты:* Частицы пыли, дым, атмосферные искры, motion blur.
• *Звук:* Мощный звуковой дроп (Beat drop) + атмосферный реверб.

⏱ *Сцена 4: [00:12 — 00:15] — Финал и призыв к действию (Outro / CTA)*
• *Кадр:* Отъезд камеры назад (Pull-back reveal), появление логотипа или плашки.
• *Текст на экране:* Главный призыв (Call to action): подписаться, перейти, попробовать.
• *Звук:* Мягкое затухание (Fade out) с финальным звонким аккордом.

━━━━━━━━━━━━━━━━━━━━━━━━━━
🎵 *САУНД-ДИЗАЙН И МУЗЫКА*
• *Жанр трека:* Cinematic Electronic / Dark Synthwave / Modern Trap Beat
• *Темп:* 120-128 BPM
• *Спецэффекты:* 2x Whoosh переходов, 1x Sub-Drop, 1x Riser перед кульминацией.

━━━━━━━━━━━━━━━━━━━━━━━━━━
🎥 *ГОТОВЫЕ ПРОМПТЫ ДЛЯ ТОП НЕЙРОСЕТЕЙ:*

1️⃣ *Для Kling AI 1.5 & Fal.ai:*
`{enhanced_prompt}, kling video standard quality, realistic fluid physics, high temporal consistency`

2️⃣ *Для Luma Dream Machine (Ray 2):*
`{enhanced_prompt}, dream machine ray 2, hyper-realistic camera trajectory, natural motion, 35mm film stock`

3️⃣ *Для Runway Gen-3 Alpha:*
`{enhanced_prompt}, cinematic photorealism, subtle natural lighting, high dynamic range, no artifacts`

4️⃣ *Для Minimax Hailuo AI:*
`{enhanced_prompt}, ultra-smooth character motion, cinematic color grading, award-winning cinematography`
"""
        return storyboard


# =====================================================================
# 3. ОСНОВНОЙ СЕРВИС VIDEO SERVICE
# =====================================================================

class VideoService:
    """
    Центральный фасад для управления видеогенерацией и режиссурой.
    """

    def __init__(self):
        self.luma = LumaVideoProvider()
        self.fal = FalVideoProvider()

    def get_providers_status(self) -> Dict[str, bool]:
        """Возвращает статус доступности API-ключей для видео."""
        return {
            "luma": self.luma.is_configured(),
            "fal": self.fal.is_configured(),
            "runway": bool(RUNWAY_API_KEY),
        }

    def has_any_active_provider(self) -> bool:
        """Проверяет, подключен ли хотя бы один реальный API-провайдер видео."""
        return self.luma.is_configured() or self.fal.is_configured()

    def extract_video_url(self, text: str) -> Optional[str]:
        """Извлекает прямую ссылку на видео (.mp4 / cdn) из ответа, если она есть."""
        patterns = [
            r"(https?://[^\s\)\"\'\<\>]+(?:\.mp4|\.mov))",
            r"(https?://fal\.media/files/[^\s\)\"\'\<\>]+)",
            r"(https?://storage\.lumalabs\.ai/[^\s\)\"\'\<\>]+)",
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1)
        return None

    def generate_or_direct(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        duration_sec: int = 5,
        on_status: Optional[Callable[[str], None]] = None,
        force_storyboard_only: bool = False,
        source_media: Optional[Union[str, bytes]] = None,
        media_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Главный метод:
        1. Если передано исходное видео (Video-to-Video) или фото (Image-to-Video) и настроен FAL_KEY:
           - Запускает трансформацию через Kling AI 1.5 Video-to-Video или Image-to-Video.
        2. Если текстовый запрос и ключи настроены:
           - Пробует сгенерировать видео через Fal.ai (Kling) или Luma.
        3. Если ключи не заданы или исчерпан баланс (Zero-Crash Mode):
           - Создает детальный Режиссерский монтажный план (Director's Cut Storyboard)
           - Генерирует готовые промпты под все популярные нейросети
        """
        # Проверяем наличие соотношения сторон в промпте
        if "9:16" in prompt or "вертикальн" in prompt.lower() or "shorts" in prompt.lower() or "рилс" in prompt.lower() or "reels" in prompt.lower():
            aspect_ratio = "9:16"
        elif "16:9" in prompt or "горизонтал" in prompt.lower() or "youtube" in prompt.lower() or "широкоформатн" in prompt.lower():
            aspect_ratio = "16:9"

        # Очищаем сервисный префикс в начале промпта
        clean_idea = re.sub(
            r"^(?:видео|video|сгенерируй|создай|смонтируй|сделай)?\s*(?:видео|ролик|клип|рилс|shorts|анимацию)?\s*(?:через\s*(?:luma|kling|fal|runway))?[:,\s]*",
            "",
            prompt.strip(),
            flags=re.IGNORECASE
        ).strip()
        if not clean_idea or len(clean_idea) < 3:
            clean_idea = prompt.strip()

        last_error = ""
        # Попытка прямой генерации видео при наличии API ключей
        if not force_storyboard_only and self.has_any_active_provider():
            enhanced_eng = CinematicPromptEnhancer.enhance(clean_idea, aspect_ratio)

            # Выбираем провайдер: Luma или Fal
            provider = self.fal if self.fal.is_configured() else self.luma
            try:
                if source_media and media_type == "video" and self.fal.is_configured():
                    result = self.fal.generate_video_to_video(
                        video_input=source_media,
                        prompt=enhanced_eng,
                        duration_sec=duration_sec,
                        on_status=on_status,
                    )
                elif source_media and media_type == "photo" and self.fal.is_configured():
                    result = self.fal.generate_image_to_video(
                        image_input=source_media,
                        prompt=enhanced_eng,
                        duration_sec=duration_sec,
                        on_status=on_status,
                    )
                else:
                    if on_status:
                        on_status(f"🎬 Генерация видео через {provider.display_name}... ⏳")

                    result = provider.generate_video(
                        prompt=enhanced_eng,
                        aspect_ratio=aspect_ratio,
                        duration_sec=duration_sec,
                        on_status=on_status,
                    )
                video_url = result.get("video_url")
                if video_url:
                    text_reply = (
                        f"🎬 *Ваше видео успешно сгенерировано!* ✨\n\n"
                        f"🎥 *Нейросеть:* `{result.get('provider')}`\n"
                        f"📐 *Формат:* `{aspect_ratio}`\n"
                        f"💡 *Кинематографичный промпт:*\n`{enhanced_eng}`\n\n"
                        f"🔗 *Ссылка на видео:* {video_url}\n\n"
                        f"*(Видео отправляется в чат файлом...)*"
                    )
                    return {
                        "status": "completed",
                        "video_url": video_url,
                        "text": text_reply,
                        "prompt": enhanced_eng,
                    }
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Ошибка при прямой генерации видео через {provider.display_name}: {e}. Включаем режиссерский сценарий...")
                if on_status:
                    on_status("⚠️ Прямой рендеринг вернул ошибку. Формирую подробный режиссерский монтажный план...")

        # Режим режиссерского сценария и раскадровки (Zero-Crash Fallback)
        if on_status:
            on_status("🎬 Создание режиссерского монтажного плана и промпт-пака...")

        storyboard_text = VideoDirector.build_storyboard_plan(clean_idea, aspect_ratio=aspect_ratio, duration_sec=15)

        # Добавляем баннер о статусе ключей и инструкции подключения
        status_banner = ""
        p_status = self.get_providers_status()
        if "исчерпан баланс" in last_error or "Exhausted" in last_error:
            status_banner = (
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ *Статус API ключа Fal.ai:*\n"
                "Ключ проверен и валиден, но на аккаунте Fal.ai закончились кредиты (`Exhausted balance`).\n"
                "👉 Чтобы бот генерировал видео напрямую, пополните баланс на [fal.ai/dashboard/billing](https://fal.ai/dashboard/billing).\n"
                "А пока вы можете скопировать готовые промпты выше в веб-версию Kling AI или Luma Dream Machine!\n"
            )
        elif not any(p_status.values()):
            status_banner = (
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "💡 *Как включить прямой рендеринг видео в боте:*\n"
                "1. Получите ключ на [fal.ai](https://fal.ai) (даёт доступ к Kling AI 1.5, Minimax Hailuo) "
                "или [lumalabs.ai](https://lumalabs.ai) (Luma Ray 2).\n"
                "2. В настройках сервиса на Render добавьте переменную окружения:\n"
                "   `FAL_KEY` = `ваш_ключ` или `LUMA_API_KEY` = `ваш_ключ`.\n"
                "   Либо администратор может отправить боту команду:\n"
                "   `/set_key FAL_KEY ваш_ключ`\n"
                "3. Бот начнет мгновенно рендерить и присылать готовые `.mp4` файлы прямо сюда в Telegram!\n"
            )
        elif last_error:
            status_banner = (
                f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ *Заметка:* Рендеринг временно вернул ошибку: `{last_error[:120]}`.\n"
                f"Используйте режиссерский сценарий и готовые промпты выше для бесплатного запуска в веб-интерфейсе."
            )

        full_reply = f"{storyboard_text}{status_banner}"

        return {
            "status": "fallback",
            "video_url": None,
            "text": full_reply,
            "prompt": clean_idea,
        }


video_service = VideoService()
