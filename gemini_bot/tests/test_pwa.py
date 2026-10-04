import io
import json
import unittest
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from web import PWAAndApiHandler
from services.database import init_db, reset_all_settings_to_default

class TestPWAAndApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        reset_all_settings_to_default()

    def _simulate_get(self, path: str):
        handler = PWAAndApiHandler.__new__(PWAAndApiHandler)
        handler.command = "GET"
        handler.path = path
        handler.request_version = "HTTP/1.1"
        handler.headers = {}
        handler.wfile = io.BytesIO()
        handler.response_code = None
        handler.response_headers = {}

        def send_response(code, msg=None):
            handler.response_code = code

        def send_header(k, v):
            handler.response_headers[k.lower()] = v

        def end_headers():
            pass

        handler.send_response = send_response
        handler.send_header = send_header
        handler.end_headers = end_headers
        handler.do_GET()

        return handler.response_code, handler.response_headers, handler.wfile.getvalue()

    def _simulate_post(self, path: str, body_dict: dict):
        handler = PWAAndApiHandler.__new__(PWAAndApiHandler)
        handler.command = "POST"
        handler.path = path
        handler.request_version = "HTTP/1.1"
        
        body_bytes = json.dumps(body_dict).encode("utf-8")
        handler.headers = {"Content-Length": str(len(body_bytes))}
        handler.rfile = io.BytesIO(body_bytes)
        handler.wfile = io.BytesIO()
        handler.response_code = None
        handler.response_headers = {}

        def send_response(code, msg=None):
            handler.response_code = code

        def send_header(k, v):
            handler.response_headers[k.lower()] = v

        def end_headers():
            pass

        handler.send_response = send_response
        handler.send_header = send_header
        handler.end_headers = end_headers
        handler.do_POST()

        return handler.response_code, handler.response_headers, handler.wfile.getvalue()

    def test_01_manifest_json(self):
        code, headers, body = self._simulate_get("/manifest.json")
        self.assertEqual(code, 200)
        self.assertIn("application/manifest+json", headers.get("content-type", ""))
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("display"), "standalone")
        self.assertEqual(data.get("short_name"), "Gemini AI")
        self.assertTrue(len(data.get("icons", [])) >= 2)

    def test_02_service_worker(self):
        code, headers, body = self._simulate_get("/sw.js")
        self.assertEqual(code, 200)
        self.assertIn("javascript", headers.get("content-type", ""))
        self.assertEqual(headers.get("service-worker-allowed"), "/")
        self.assertIn(b"CACHE_NAME", body)

    def test_03_index_html_pwa_tags(self):
        code, headers, body = self._simulate_get("/")
        self.assertEqual(code, 200)
        self.assertIn("text/html", headers.get("content-type", ""))
        html = body.decode("utf-8")
        self.assertIn('rel="manifest"', html)
        self.assertIn('apple-mobile-web-app-capable', html)
        self.assertIn('theme-color', html)

    def test_04_api_config(self):
        # 1. GET config
        code, _, body = self._simulate_get("/api/config")
        self.assertEqual(code, 200)
        cfg = json.loads(body.decode("utf-8"))
        self.assertIn("temperature", cfg)

        # 2. POST update temperature
        code, _, body = self._simulate_post("/api/config", {"action": "set_temp", "temperature": 0.3})
        self.assertEqual(code, 200)
        updated = json.loads(body.decode("utf-8"))
        self.assertEqual(updated.get("temperature"), 0.3)

    def test_05_api_tasks(self):
        # 1. GET tasks
        code, _, body = self._simulate_get("/api/tasks")
        self.assertEqual(code, 200)
        tasks_data = json.loads(body.decode("utf-8"))
        self.assertIn("tasks", tasks_data)

        # 2. POST add task
        code, _, body = self._simulate_post("/api/tasks", {"action": "add", "title": "PWA Тест Задачи"})
        self.assertEqual(code, 200)
        updated_tasks = json.loads(body.decode("utf-8"))
        titles = [t["title"] for t in updated_tasks.get("tasks", [])]
        self.assertIn("PWA Тест Задачи", titles)

    def test_06_health_check(self):
        code, _, body = self._simulate_get("/health")
        self.assertEqual(code, 200)
        health_data = json.loads(body.decode("utf-8"))
        self.assertEqual(health_data.get("status"), "ok")

if __name__ == "__main__":
    unittest.main()
