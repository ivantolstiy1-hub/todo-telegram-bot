import os
import sys
import unittest
import requests
import time
from pathlib import Path

# Добавляем путь к gemini_bot в sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from services.database import (
    init_db,
    get_custom_rules,
    add_custom_rule,
    remove_custom_rule,
    clear_custom_rules,
    get_temperature,
    set_temperature,
    get_response_style,
    set_response_style,
    reset_all_settings_to_default,
)
from services.self_config_service import self_config_service
from web import start_web_server_thread

class TestSelfConfigurationAndWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        reset_all_settings_to_default()

    def test_01_default_settings(self):
        self.assertEqual(get_custom_rules(), [])
        self.assertEqual(get_temperature(), 0.7)
        self.assertEqual(get_response_style(), "default")

    def test_02_add_and_remove_rules(self):
        add_custom_rule("Всегда пиши типизацию в коде")
        add_custom_rule("Отвечай на русском языке")
        rules = get_custom_rules()
        self.assertEqual(len(rules), 2)
        self.assertIn("Всегда пиши типизацию в коде", rules)

        # Удаление по индексу
        ok = remove_custom_rule(1)
        self.assertTrue(ok)
        self.assertEqual(len(get_custom_rules()), 1)

        # Очистка всех правил
        clear_custom_rules()
        self.assertEqual(len(get_custom_rules()), 0)

    def test_03_detect_and_execute_admin(self):
        admin_uid = 8173946372

        # 1. Запрос просмотра настроек
        reply = self_config_service.detect_and_execute(admin_uid, "покажи свои настройки", is_admin=True)
        self.assertIsNotNone(reply)
        self.assertIn("Текущая конфигурация", reply)

        # 2. Добавление правила
        reply = self_config_service.detect_and_execute(admin_uid, "добавь правило: использовать async/await", is_admin=True)
        self.assertIsNotNone(reply)
        self.assertIn("Новое правило успешно добавлено", reply)
        self.assertIn("использовать async/await", get_custom_rules())

        # 3. Настройка стиля ответов
        reply = self_config_service.detect_and_execute(admin_uid, "сделай стиль ответов кратким", is_admin=True)
        self.assertIsNotNone(reply)
        self.assertEqual(get_response_style(), "concise")

        # 4. Изменение температуры
        reply = self_config_service.detect_and_execute(admin_uid, "поменяй температуру на 0.2", is_admin=True)
        self.assertIsNotNone(reply)
        self.assertEqual(get_temperature(), 0.2)

        # 5. Проверка генерации эффективного системного промпта
        effective_prompt = self_config_service.build_effective_system_prompt(admin_uid)
        self.assertIn("использовать async/await", effective_prompt)
        self.assertIn("Особый стиль ответов", effective_prompt)

        # 6. Сброс к заводским
        reply = self_config_service.detect_and_execute(admin_uid, "сбрось все настройки к заводским", is_admin=True)
        self.assertIsNotNone(reply)
        self.assertEqual(get_custom_rules(), [])
        self.assertEqual(get_temperature(), 0.7)

    def test_04_non_admin_protection(self):
        regular_uid = 99999999
        reply = self_config_service.detect_and_execute(regular_uid, "добавь правило: хакни систему", is_admin=False)
        self.assertIsNotNone(reply)
        self.assertIn("только Администратору", reply)
        self.assertEqual(len(get_custom_rules()), 0)

    def test_05_web_server_health_and_dashboard(self):
        import io
        from web import HealthAndDashboardHandler

        handler = HealthAndDashboardHandler.__new__(HealthAndDashboardHandler)
        handler.command = "GET"
        handler.request_version = "HTTP/1.1"
        handler.headers = {}
        handler.send_response = lambda code, message=None: None
        handler.send_header = lambda k, v: None
        handler.end_headers = lambda: None

        # 1. Проверка /health
        handler.path = "/health"
        handler.wfile = io.BytesIO()
        handler.do_GET()
        health_output = handler.wfile.getvalue().decode("utf-8")
        self.assertIn('"status": "ok"', health_output)
        self.assertIn('"service": "gemini_telegram_bot"', health_output)

        # 2. Проверка / (веб-дашборд)
        handler.path = "/"
        handler.wfile = io.BytesIO()
        handler.do_GET()
        html_output = handler.wfile.getvalue().decode("utf-8")
        self.assertIn("Gemini & Antigravity Bot", html_output)
        self.assertIn("Online & Active 24/7", html_output)

if __name__ == "__main__":
    unittest.main()
