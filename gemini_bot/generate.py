#!/usr/bin/env python3
"""
Скрипт для прямого запуска генерации Kling AI 1.5 через fal-client.
Поддерживает два режима:
1. Video-to-Video: стилизация и трансформация готового видеоролика.
2. Image-to-Video: оживление фотографии или арта.

Использование:
  python generate.py                          # Запуск демонстрационной генерации
  python generate.py --mode v2v --video URL   # Video-to-Video
  python generate.py --mode i2v --image URL   # Image-to-Video
"""

import os
import sys
import argparse
from pathlib import Path

# Загрузка переменных окружения из .env если доступно
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

# Проверяем или устанавливаем API-ключ Fal.ai
FAL_KEY = os.getenv("FAL_KEY", "").strip() or "fal_sk_4a14ebfc3ce5415c99a55448dec50345:d65e69466f230d9c4998cdbdf9a8b36b"
os.environ["FAL_KEY"] = FAL_KEY

try:
    import fal_client
except ImportError:
    print("❌ Библиотека fal-client не найдена.")
    print("Установите её командой: pip install fal-client")
    sys.exit(1)


CLOWN_MEME_PROMPT = (
    "video-to-video style transition, young woman with white face base makeup seamlessly "
    "transforms into a funny clown meme makeup, bright round red clown nose, exaggerated "
    "artistic red clown smile, blue tear accents on cheeks, maintaining exact same face identity, "
    "identical facial structure, identical room background and ambient lighting, "
    "high temporal consistency, photorealistic 4k, stable motion, no distortion"
)

NEGATIVE_PROMPT = (
    "ugly, deformed, low quality, distortion, blurry, low resolution, face distortion, "
    "changing background, changing lighting, bad anatomy"
)


def run_video_to_video(
    video_url: str,
    prompt: str = CLOWN_MEME_PROMPT,
    strength: float = 0.6,
    duration: str = "5"
) -> str:
    """Запускает Kling AI 1.5 Video-to-Video трансформацию."""
    print("🚀 [Kling 1.5] Запуск Video-to-Video трансформации...")
    print(f"📹 Входное видео: {video_url}")
    print(f"💡 Промпт: {prompt[:100]}...")
    print(f"⚙️ Сила эффекта (strength): {strength}, длительность: {duration} сек.")

    try:
        handler = fal_client.submit(
            "fal-ai/kling/v1.5/video-to-video",
            arguments={
                "video_url": video_url,
                "prompt": prompt,
                "negative_prompt": NEGATIVE_PROMPT,
                "strength": strength,
                "duration": duration,
            }
        )
        print("⏳ Ожидание завершения генерации на сервере fal.ai...")
        result = handler.get()
        out_url = result.get("video", {}).get("url")
        if not out_url:
            raise RuntimeError(f"Видео не найдено в ответе: {result}")
        print("\n🎉 Генерация успешно завершена!")
        print(f"🔗 Ссылка на готовое видео: {out_url}")
        return out_url
    except Exception as e:
        _handle_error(e)
        raise


def run_image_to_video(
    image_url: str,
    prompt: str = CLOWN_MEME_PROMPT,
    duration: str = "5",
    mode: str = "pro"
) -> str:
    """Запускает Kling AI 1.5 Image-to-Video анимацию."""
    print("🚀 [Kling 1.5] Запуск Image-to-Video анимации...")
    print(f"🖼 Исходное фото: {image_url}")
    print(f"💡 Промпт: {prompt[:100]}...")
    print(f"⚙️ Режим: {mode}, длительность: {duration} сек.")

    try:
        handler = fal_client.submit(
            "fal-ai/kling/v1.5/image-to-video",
            arguments={
                "image_url": image_url,
                "prompt": prompt,
                "negative_prompt": NEGATIVE_PROMPT,
                "duration": duration,
                "mode": mode,
            }
        )
        print("⏳ Ожидание завершения генерации на сервере fal.ai...")
        result = handler.get()
        out_url = result.get("video", {}).get("url")
        if not out_url:
            raise RuntimeError(f"Видео не найдено в ответе: {result}")
        print("\n🎉 Видео успешно сгенерировано!")
        print(f"🔗 Ссылка на результат: {out_url}")
        return out_url
    except Exception as e:
        _handle_error(e)
        raise


def _handle_error(e: Exception):
    err = str(e)
    print("\n" + "═" * 60)
    if "Exhausted" in err or "locked" in err.lower() or "403" in err:
        print("⚠️ ОШИБКА: На аккаунте fal.ai исчерпан баланс (Exhausted balance).")
        print("Ключ верен, но баланс $0.")
        print("👉 Пополните баланс на https://fal.ai/dashboard/billing для генерации видео.")
    else:
        print(f"⚠️ Ошибка вызова Fal.ai: {e}")
    print("═" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Kling AI 1.5 Generator via fal-client")
    parser.add_argument("--mode", choices=["v2v", "i2v"], default="v2v", help="Режим: v2v (Video-to-Video) или i2v (Image-to-Video)")
    parser.add_argument("--video", type=str, default="", help="URL исходного видео для Video-to-Video")
    parser.add_argument("--image", type=str, default="", help="URL исходного изображения для Image-to-Video")
    parser.add_argument("--prompt", type=str, default=CLOWN_MEME_PROMPT, help="Кинематографичный промпт")
    parser.add_argument("--strength", type=float, default=0.6, help="Сила изменения для Video-to-Video (0.1 - 1.0)")
    parser.add_argument("--duration", choices=["5", "10"], default="5", help="Длительность (5 или 10 сек)")

    args = parser.parse_args()

    if args.mode == "v2v":
        video_url = args.video.strip() or "https://storage.googleapis.com/falserverless/gallery/kling-video/source_girl.mp4"
        run_video_to_video(video_url=video_url, prompt=args.prompt, strength=args.strength, duration=args.duration)
    else:
        image_url = args.image.strip() or "https://storage.googleapis.com/falserverless/gallery/kling-video/source_portrait.jpg"
        run_image_to_video(image_url=image_url, prompt=args.prompt, duration=args.duration)


if __name__ == "__main__":
    main()
