import unittest
from pathlib import Path
import sys
from unittest.mock import patch, MagicMock

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from services.hermes_service import (
    hermes_service,
    BaseAIProvider,
    GeminiProvider,
    DeepSeekProvider,
    ClaudeProvider,
    OpenAIProvider,
    OpenRouterProvider,
)
from services.database import init_db, clear_history


class TestHermesOrchestrator(unittest.TestCase):

    def setUp(self):
        init_db()
        clear_history(99999)

    def test_providers_status(self):
        """Проверка возврата статуса всех зарегистрированных провайдеров."""
        status = hermes_service.get_providers_status()
        self.assertIn("gemini", status)
        self.assertIn("deepseek", status)
        self.assertIn("claude", status)
        self.assertIn("openai", status)
        self.assertIn("openrouter", status)
        self.assertIn("name", status["gemini"])
        self.assertIn("configured", status["gemini"])

    def test_explicit_routing_parse(self):
        """Проверка распознавания естественных команд маршрутизации."""
        cases = [
            ("Гермес, спроси у DeepSeek: реши теорему Ферма", "deepseek-reasoner", "реши теорему Ферма"),
            ("гермес спроси у deepseek реши задачу", "deepseek-reasoner", "реши задачу"),
            ("через claude: напиши микросервис на FastAPI", "claude-3-5-sonnet", "напиши микросервис на FastAPI"),
            ("Гермес, спроси у чатгпт: придумай название бренда", "gpt-4o", "придумай название бренда"),
            ("через hermes: сочини фантастический рассказ", "nous-hermes-3", "сочини фантастический рассказ"),
            ("Просто обычный вопрос без упоминания модели", None, "Просто обычный вопрос без упоминания модели"),
        ]
        for prompt, expected_model, expected_clean in cases:
            model, clean = hermes_service.parse_explicit_route(prompt)
            self.assertEqual(model, expected_model, f"Ошибка модели для: {prompt}")
            self.assertEqual(clean, expected_clean, f"Ошибка очистки промпта для: {prompt}")

    def test_intent_classification(self):
        """Проверка интеллектуальной классификации запросов в режиме Auto-Hermes."""
        # 1. Математика / Рассуждения -> DeepSeek
        math_prompt = "Пожалуйста, докажи эту математическую теорему и распиши доказательство шаг за шагом"
        rec_model, reason = hermes_service.classify_intent(math_prompt)
        self.assertEqual(rec_model, "deepseek-reasoner")

        # 2. Программирование / Код -> Claude
        code_prompt = "Напиши функцию на python с рефакторингом и исправь баг в sql запросе"
        rec_model, reason = hermes_service.classify_intent(code_prompt)
        self.assertEqual(rec_model, "claude-3-5-sonnet")

        # 3. Креатив / Литература -> Nous Hermes / GPT
        creative_prompt = "Сочини красивый стих и рассказ про космос"
        rec_model, reason = hermes_service.classify_intent(creative_prompt)
        self.assertEqual(rec_model, "nous-hermes-3")

        # 4. Общий диалог -> Gemini
        general_prompt = "Привет! Как твои дела и какая сегодня погода?"
        rec_model, reason = hermes_service.classify_intent(general_prompt)
        self.assertEqual(rec_model, "gemini-3.5-flash")

    def test_fallback_when_keys_missing(self):
        """Если API-ключ для DeepSeek не указан, запрос плавно переключается на Gemini с пояснением."""
        with patch.object(hermes_service.providers["deepseek"], "is_configured", return_value=False), \
             patch.object(hermes_service.providers["openrouter"], "is_configured", return_value=False):
            prov, actual_model, banner = hermes_service.resolve_provider("deepseek-reasoner")
            self.assertIsInstance(prov, GeminiProvider)
            self.assertEqual(actual_model, "gemini-3.5-flash")
            self.assertIsNotNone(banner)
            self.assertIn("DEEPSEEK_API_KEY", banner)

    def test_openrouter_secondary_provider(self):
        """Если нативный ключ отсутствует, но задан OPENROUTER_API_KEY, модель обслуживается через OpenRouter."""
        with patch.object(hermes_service.providers["deepseek"], "is_configured", return_value=False), \
             patch.object(hermes_service.providers["openrouter"], "is_configured", return_value=True):
            prov, actual_model, banner = hermes_service.resolve_provider("deepseek-reasoner")
            self.assertIsInstance(prov, OpenRouterProvider)
            self.assertEqual(actual_model, "deepseek-reasoner")
            self.assertIsNone(banner)

    def test_chat_execution_with_gemini_fallback(self):
        """Проверка полного цикла чата с защитой от сбоев провайдеров."""
        fake_reply = "Тестовый ответ от Gemini API"
        with patch.object(hermes_service.providers["gemini"], "generate", return_value=fake_reply):
            # Запрос к DeepSeek при отсутствии ключа
            reply = hermes_service.chat(
                user_id=99999,
                user_message="Гермес, спроси у DeepSeek: реши уравнение 2x+5=15"
            )
            self.assertIn("Тестовый ответ от Gemini API", reply)
            self.assertIn("Агент Гермес", reply)

    def test_antigravity_provider_status(self):
        """Проверка наличия Antigravity CLI в списке провайдеров."""
        status = hermes_service.get_providers_status()
        self.assertIn("antigravity", status)
        self.assertIn("Antigravity Agent", status["antigravity"]["name"])

    def test_antigravity_explicit_routing(self):
        """Проверка распознавания прямых команд к Antigravity CLI и терминалу."""
        cases = [
            ("Гермес, через antigravity: запусти git status", "antigravity", "запусти git status"),
            ("через терминал: прочитай README.md", "antigravity", "прочитай README.md"),
            ("Гермес, выполни в терминале: pytest", "antigravity", "pytest"),
        ]
        for prompt, expected_model, expected_clean in cases:
            model, clean = hermes_service.parse_explicit_route(prompt)
            self.assertEqual(model, expected_model, f"Ошибка модели для: {prompt}")
            self.assertEqual(clean, expected_clean, f"Ошибка очистки промпта для: {prompt}")

    def test_antigravity_intent_classification(self):
        """Проверка авто-маршрутизации системных и терминальных задач в Antigravity CLI."""
        term_prompt = "Пожалуйста, выполни команду git status и проверь файлы проекта в терминале"
        rec_model, reason = hermes_service.classify_intent(term_prompt)
        self.assertEqual(rec_model, "antigravity")
        self.assertIn("Antigravity CLI", reason)

    def test_antigravity_fallback_in_cloud(self):
        """Если Antigravity CLI недоступен (например, в облаке Render), задача плавно переключается на Claude/Gemini."""
        with patch.object(hermes_service.providers["antigravity"], "is_configured", return_value=False), \
             patch.object(hermes_service.providers["claude"], "is_configured", return_value=False), \
             patch.object(hermes_service.providers["openrouter"], "is_configured", return_value=False):
            prov, actual_model, banner = hermes_service.resolve_provider("antigravity")
            self.assertIsInstance(prov, GeminiProvider)
            self.assertEqual(actual_model, "gemini-3.5-flash")
            self.assertIsNotNone(banner)
            self.assertIn("Antigravity CLI", banner)

    def test_all_providers_accept_user_id_kwargs(self):
        """Гарантирует, что все провайдеры корректно принимают user_id и **kwargs."""
        import inspect
        for p_name, prov in hermes_service.providers.items():
            sig = inspect.signature(prov.generate)
            has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            self.assertTrue(
                has_kwargs or "user_id" in sig.parameters,
                f"Провайдер {p_name} должен принимать **kwargs или user_id"
            )

if __name__ == "__main__":
    unittest.main()
