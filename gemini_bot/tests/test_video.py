import unittest
from pathlib import Path
import sys
from unittest.mock import patch, MagicMock

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from services.video_service import (
    video_service,
    CinematicPromptEnhancer,
    VideoDirector,
    LumaVideoProvider,
    FalVideoProvider,
)
from services.hermes_service import (
    hermes_service,
    VideoDirectorProvider,
)
from services.database import init_db, clear_history


class TestVideoAI(unittest.TestCase):

    def setUp(self):
        init_db()
        clear_history(88888)

    def test_cinematic_prompt_enhancer_rule_based(self):
        """Проверка работы расширителя кинематографичных промптов."""
        raw_prompt = "кот летит в космосе"
        enhanced_16_9 = CinematicPromptEnhancer.enhance_rule_based(raw_prompt, aspect_ratio="16:9")
        self.assertIn("кот летит в космосе", enhanced_16_9)
        self.assertIn("cinematic 4K", enhanced_16_9)
        self.assertIn("35mm anamorphic", enhanced_16_9)
        self.assertIn("16:9", enhanced_16_9)

        enhanced_9_16 = CinematicPromptEnhancer.enhance_rule_based(raw_prompt, aspect_ratio="9:16")
        self.assertIn("9:16", enhanced_9_16)

    def test_video_director_storyboard(self):
        """Проверка структуры режиссерского монтажного листа (Director's Cut)."""
        storyboard = VideoDirector.build_storyboard_plan("Неоновый киберпанк город", aspect_ratio="9:16", duration_sec=15)
        self.assertIn("РЕЖИССЕРСКИЙ МОНТАЖНЫЙ ПЛАН", storyboard)
        self.assertIn("Сцена 1", storyboard)
        self.assertIn("Hook", storyboard)
        self.assertIn("Сцена 2", storyboard)
        self.assertIn("Сцена 3", storyboard)
        self.assertIn("Сцена 4", storyboard)
        self.assertIn("САУНД-ДИЗАЙН И МУЗЫКА", storyboard)
        self.assertIn("Kling AI 1.5", storyboard)
        self.assertIn("Luma Dream Machine", storyboard)
        self.assertIn("Runway Gen-3", storyboard)
        self.assertIn("Minimax Hailuo", storyboard)

    def test_extract_video_url(self):
        """Проверка парсинга URL видео из текста ответа."""
        sample_text_mp4 = "Вот ваше сгенерированное видео: https://cdn.example.com/videos/output_123.mp4 приятного просмотра!"
        url = video_service.extract_video_url(sample_text_mp4)
        self.assertEqual(url, "https://cdn.example.com/videos/output_123.mp4")

        sample_fal = "Результат: https://fal.media/files/tiger/gen.mp4"
        self.assertEqual(video_service.extract_video_url(sample_fal), "https://fal.media/files/tiger/gen.mp4")

        no_video = "Здесь нет видеофайла, только обычный текст."
        self.assertIsNone(video_service.extract_video_url(no_video))

    def test_zero_crash_fallback_when_keys_missing(self):
        """Zero-Crash гарантия: при отсутствии ключей FAL_KEY и LUMA_API_KEY бот выдает сценарий и промпт-пак."""
        with patch.object(video_service.luma, "is_configured", return_value=False), \
             patch.object(video_service.fal, "is_configured", return_value=False):
            res = video_service.generate_or_direct("гонки на спортивных машинах", aspect_ratio="16:9")
            self.assertEqual(res["status"], "fallback")
            self.assertIsNone(res["video_url"])
            self.assertIn("РЕЖИССЕРСКИЙ МОНТАЖНЫЙ ПЛАН", res["text"])
            self.assertIn("Kling AI 1.5", res["text"])
            self.assertIn("Luma Dream Machine", res["text"])
            self.assertIn("Как включить прямой рендеринг", res["text"])

    def test_direct_video_generation_mock(self):
        """Проверка успешной генерации видео при доступном провайдере Fal/Kling."""
        fake_url = "https://fal.media/files/kling/sample_video.mp4"
        with patch.object(video_service.fal, "is_configured", return_value=True), \
             patch.object(video_service.fal, "generate_video", return_value={
                 "status": "completed",
                 "video_url": fake_url,
                 "provider": "Fal.ai (Kling AI 1.5)",
                 "details": "Success"
             }):
            res = video_service.generate_or_direct("киберпанк поезд будущего", aspect_ratio="9:16")
            self.assertEqual(res["status"], "completed")
            self.assertEqual(res["video_url"], fake_url)
            self.assertIn("Ваше видео успешно сгенерировано", res["text"])

    def test_hermes_video_intent_classification(self):
        """Проверка авто-маршрутизации видео-запросов в Гермесе."""
        prompts = [
            ("Сгенерируй видеоролик про закат в горах", "video-director"),
            ("смонтируй рилс про тренировки и мотивацию", "video-director"),
            ("сделай клип в стиле аниме", "video-director"),
            ("создай раскадровку и storyboard для тизера", "video-director"),
            ("сделай анимацию падающих листьев", "video-director"),
        ]
        for p, expected_model in prompts:
            model, reason = hermes_service.classify_intent(p)
            self.assertEqual(model, expected_model, f"Ошибка классификации для: {p}")
            self.assertIn("Video AI Director", reason)

    def test_hermes_video_explicit_routing(self):
        """Проверка явных префиксов 'через luma:', 'видео:', 'через kling:'."""
        cases = [
            ("Гермес, через Luma: футуристичный город в 2050 году", "video-director", "футуристичный город в 2050 году"),
            ("через kling: закат на марсианской базе", "video-director", "закат на марсианской базе"),
            ("видео: неоновый самурай под дождем", "video-director", "неоновый самурай под дождем"),
            ("Гермес, смонтируй в видео: реклама кофейни", "video-director", "реклама кофейни"),
        ]
        for text, expected_model, expected_clean in cases:
            model, clean = hermes_service.parse_explicit_route(text)
            self.assertEqual(model, expected_model, f"Ошибка модели для: {text}")
            self.assertEqual(clean, expected_clean, f"Ошибка очистки для: {text}")

    def test_hermes_resolve_video_provider(self):
        """Проверка разрешения провайдера VideoDirectorProvider."""
        prov, model_id, banner = hermes_service.resolve_provider("video-director")
        self.assertIsInstance(prov, VideoDirectorProvider)
        self.assertEqual(model_id, "video-director")
        self.assertIsNone(banner)

    def test_hermes_chat_with_video_request(self):
        """Полный цикл chat() с запросом на видео."""
        reply = hermes_service.chat(
            user_id=88888,
            user_message="Гермес, сгенерируй видео: кот в скафандре исследует Луну",
        )
        self.assertIn("РЕЖИССЕРСКИЙ МОНТАЖНЫЙ ПЛАН", reply)
    def test_luma_provider_mock(self):
        """Проверка работы LumaVideoProvider с моком создания и поллинга статуса."""
        prov = LumaVideoProvider()
        fake_video_url = "https://storage.lumalabs.ai/dream-machine/test_video.mp4"
        with patch.object(prov, "is_configured", return_value=True), \
             patch("requests.post") as mock_post, \
             patch("requests.get") as mock_get, \
             patch("time.sleep"):
            # Мок создания задачи
            mock_post_resp = MagicMock()
            mock_post_resp.status_code = 201
            mock_post_resp.json.return_value = {"id": "luma_12345", "state": "queued"}
            mock_post.return_value = mock_post_resp

            # Мок поллинга статуса
            mock_get_resp = MagicMock()
            mock_get_resp.status_code = 200
            mock_get_resp.json.return_value = {
                "id": "luma_12345",
                "state": "completed",
                "assets": {"video": fake_video_url}
            }
            mock_get.return_value = mock_get_resp

            status_updates = []
            res = prov.generate_video("test prompt", aspect_ratio="16:9", on_status=status_updates.append)
            self.assertEqual(res["status"], "completed")
            self.assertEqual(res["video_url"], fake_video_url)
            self.assertTrue(len(status_updates) > 0)

    def test_fal_provider_mock(self):
        """Проверка работы FalVideoProvider (Kling AI 1.5) с моком очереди."""
        prov = FalVideoProvider()
        fake_url = "https://fal.media/files/kling/sample.mp4"
        with patch.object(prov, "is_configured", return_value=True), \
             patch("requests.post") as mock_post, \
             patch("requests.get") as mock_get, \
             patch("time.sleep"):
            # Постановка в очередь
            mock_post_resp = MagicMock()
            mock_post_resp.status_code = 200
            mock_post_resp.json.return_value = {
                "request_id": "req_999",
                "status_url": "https://queue.fal.run/status/req_999",
                "response_url": "https://queue.fal.run/response/req_999"
            }
            mock_post.return_value = mock_post_resp

            # Опрос статуса и результат
            mock_get_status = MagicMock()
            mock_get_status.status_code = 200
            mock_get_status.json.return_value = {"status": "COMPLETED"}

            mock_get_res = MagicMock()
            mock_get_res.status_code = 200
            mock_get_res.json.return_value = {"video": {"url": fake_url}}

            mock_get.side_effect = [mock_get_status, mock_get_res]

            res = prov.generate_video("prompt", aspect_ratio="9:16")
            self.assertEqual(res["status"], "completed")
            self.assertEqual(res["video_url"], fake_url)

    def test_generation_error_falls_back_to_storyboard(self):
        """Если прямой API видео вернул ошибку, бот бесшовно выдает режиссерский монтажный план."""
        with patch.object(video_service.fal, "is_configured", return_value=True), \
             patch.object(video_service.fal, "generate_video", side_effect=RuntimeError("API Quota Exceeded")):
            res = video_service.generate_or_direct("космический корабль", aspect_ratio="16:9")
            self.assertEqual(res["status"], "fallback")
            self.assertIn("РЕЖИССЕРСКИЙ МОНТАЖНЫЙ ПЛАН", res["text"])


if __name__ == "__main__":
    unittest.main()
