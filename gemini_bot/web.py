import os
import json
import time
import logging
import threading
from pathlib import Path
from typing import Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from config import DEFAULT_MODEL

logger = logging.getLogger(__name__)

START_TIME = time.time()
STATIC_DIR = Path(__file__).resolve().parent / "static"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TASKS_FILE = PROJECT_ROOT / "tasks.json"

def _format_uptime(seconds: float) -> str:
    secs = int(seconds)
    days, secs = divmod(secs, 86400)
    hours, secs = divmod(secs, 3600)
    minutes, secs = divmod(secs, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)

def _get_tasks_data() -> list:
    if TASKS_FILE.exists():
        try:
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                tasks = []
                if isinstance(raw, dict):
                    for _, items in raw.items():
                        if isinstance(items, list):
                            tasks.extend(items)
                elif isinstance(raw, list):
                    tasks = raw
                if tasks:
                    return tasks
        except Exception as e:
            logger.warning(f"Ошибка чтения tasks.json: {e}")

    # Задачи по умолчанию, если файл пуст
    return [
        {"id": 1, "title": "Установить PWA на экран смартфона", "done": True},
        {"id": 2, "title": "Протестировать AI Чат в веб-приложении", "done": False},
        {"id": 3, "title": "Проверить экран Самонастройки и правил", "done": False}
    ]

def _save_tasks_data(tasks: list):
    try:
        # Сохраняем в формате словаря для совместимости с ботом
        data = {"8173946372": tasks}
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения tasks.json: {e}")

class PWAAndApiHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Подавляем логи частых health-check запросов для чистоты терминала
        if "/health" in (args[0] if args else "") or "/ping" in (args[0] if args else ""):
            return
        logger.info("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), format % args))

    def _send_json(self, status_code: int, data: dict):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _serve_file(self, file_path: Path, content_type: str, extra_headers: Optional[dict] = None):
        if not file_path.exists():
            self.send_error(404, "File Not Found")
            return
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            if extra_headers:
                for k, v in extra_headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            logger.error(f"Ошибка отдачи файла {file_path}: {e}")
            self.send_error(500, "Internal Server Error")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]

        # 1. Health check эндпоинт для Render
        if path in ("/health", "/ping"):
            uptime_str = _format_uptime(time.time() - START_TIME)
            self._send_json(200, {
                "status": "ok",
                "service": "gemini_telegram_bot",
                "uptime": uptime_str,
                "timestamp": int(time.time())
            })
            return

        # 2. API: Конфигурация бота
        if path == "/api/config":
            try:
                from services.database import get_custom_rules, get_temperature, get_response_style, get_setting
                rules = get_custom_rules()
                temp = get_temperature()
                style = get_response_style()
                def_model = get_setting("default_model", DEFAULT_MODEL)
                self._send_json(200, {
                    "style": style,
                    "temperature": temp,
                    "rules": rules,
                    "default_model": def_model
                })
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        # 3. API: Задачи Todo
        if path == "/api/tasks":
            tasks = _get_tasks_data()
            self._send_json(200, {"tasks": tasks})
            return

        # 4. API: Список моделей и провайдеров Агента Гермес
        if path == "/api/models":
            try:
                from config import AVAILABLE_MODELS
                from services.hermes_service import hermes_service
                from services.database import get_user_model
                pstats = hermes_service.get_providers_status()
                models_list = []
                for mid, mname in AVAILABLE_MODELS.items():
                    configured = True
                    if mid == "antigravity":
                        configured = bool(pstats.get("antigravity", {}).get("configured"))
                    elif mid.startswith("deepseek-"):
                        configured = bool(pstats["deepseek"]["configured"] or pstats["openrouter"]["configured"])
                    elif mid.startswith("claude-"):
                        configured = bool(pstats["claude"]["configured"] or pstats["openrouter"]["configured"])
                    elif mid == "gpt-4o":
                        configured = bool(pstats["openai"]["configured"] or pstats["openrouter"]["configured"])
                    elif mid == "nous-hermes-3":
                        configured = bool(pstats["openrouter"]["configured"])
                    elif mid.startswith("gemini-"):
                        configured = bool(pstats["gemini"]["configured"])
                    models_list.append({
                        "id": mid,
                        "name": mname,
                        "configured": configured
                    })
                self._send_json(200, {
                    "models": models_list,
                    "providers": pstats,
                    "current_model": get_user_model(1)
                })
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        # 4. PWA: Web App Manifest
        if path == "/manifest.json":
            self._serve_file(STATIC_DIR / "manifest.json", "application/manifest+json; charset=utf-8")
            return

        # 5. PWA: Service Worker (критичен заголовок Service-Worker-Allowed: /)
        if path == "/sw.js":
            self._serve_file(STATIC_DIR / "sw.js", "application/javascript; charset=utf-8", {
                "Service-Worker-Allowed": "/",
                "Cache-Control": "no-cache"
            })
            return

        # 6. PWA: Статические файлы (CSS, JS, Favicon, Иконки)
        if path == "/styles.css":
            self._serve_file(STATIC_DIR / "styles.css", "text/css; charset=utf-8")
            return

        if path == "/app.js":
            self._serve_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
            return

        if path == "/favicon.svg":
            self._serve_file(STATIC_DIR / "favicon.svg", "image/svg+xml")
            return

        if path.startswith("/icons/"):
            icon_name = path.replace("/icons/", "")
            self._serve_file(STATIC_DIR / "icons" / icon_name, "image/png")
            return

        # 7. Главная страница PWA
        if path in ("/", "/index.html", "/app"):
            self._serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return

        self.send_error(404, "Page Not Found")

    def do_POST(self):
        path = self.path.split("?")[0]
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        
        try:
            req_data = json.loads(body)
        except Exception:
            req_data = {}

        # 1. API: Чат с Агентом Гермес / Multi-LLM
        if path == "/api/chat":
            user_message = req_data.get("message", "").strip()
            user_id = int(req_data.get("user_id", 1))
            target_model = req_data.get("model")

            if not user_message:
                self._send_json(400, {"error": "Message is empty"})
                return

            try:
                from services.hermes_service import hermes_service
                reply = hermes_service.chat(user_id=user_id, user_message=user_message, target_model=target_model)
                self._send_json(200, {"reply": reply})
            except Exception as e:
                logger.exception("Ошибка обработки веб-сообщения:")
                self._send_json(500, {"reply": f"⚠️ Ошибка генерации: {str(e)}"})
            return

        # 2. API: Управление самонастройкой
        if path == "/api/config":
            action = req_data.get("action")
            try:
                from services.database import (
                    set_response_style,
                    set_temperature,
                    add_custom_rule,
                    remove_custom_rule,
                    reset_all_settings_to_default,
                    get_custom_rules,
                    get_temperature,
                    get_response_style,
                    get_setting,
                    set_setting,
                    set_user_model,
                )
                from config import AVAILABLE_MODELS

                if action == "set_style":
                    set_response_style(req_data.get("style", "default"))
                elif action == "set_temp":
                    set_temperature(float(req_data.get("temperature", 0.7)))
                elif action == "set_model":
                    new_m = req_data.get("model")
                    if new_m in AVAILABLE_MODELS:
                        set_user_model(1, new_m)
                        set_setting("default_model", new_m)
                elif action == "add_rule":
                    rule = req_data.get("rule", "").strip()
                    if rule:
                        add_custom_rule(rule)
                elif action == "delete_rule":
                    remove_custom_rule(req_data.get("query"))
                elif action == "reset_all":
                    reset_all_settings_to_default()

                self._send_json(200, {
                    "style": get_response_style(),
                    "temperature": get_temperature(),
                    "rules": get_custom_rules(),
                    "default_model": get_setting("default_model", DEFAULT_MODEL)
                })
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        # 3. API: Управление задачами Todo
        if path == "/api/tasks":
            action = req_data.get("action")
            tasks = _get_tasks_data()

            if action == "add":
                title = req_data.get("title", "").strip()
                if title:
                    new_id = int(time.time() * 1000) % 1000000
                    tasks.append({"id": new_id, "title": title, "done": False})
                    _save_tasks_data(tasks)
            elif action == "toggle":
                target_id = req_data.get("id")
                for t in tasks:
                    if t.get("id") == target_id:
                        t["done"] = not t.get("done", False)
                        break
                _save_tasks_data(tasks)

            self._send_json(200, {"tasks": tasks})
            return

        self.send_error(404, "API Not Found")

# Алиас для обратной совместимости с тестами и старым кодом
HealthAndDashboardHandler = PWAAndApiHandler

def run_web_server(port: int = 10000):
    server_address = ("0.0.0.0", port)
    try:
        httpd = HTTPServer(server_address, PWAAndApiHandler)
        logger.info(f"🌐 PWA & Health-check сервер запущен на http://0.0.0.0:{port}")
        httpd.serve_forever()
    except Exception as e:
        logger.error(f"Ошибка запуска HTTP-сервера на порту {port}: {e}")

def start_web_server_thread(port: Optional[int] = None) -> threading.Thread:
    """Запускает HTTP-сервер в отдельном daemon-потоке."""
    if port is None:
        port = int(os.getenv("PORT", "10000"))
    
    server_thread = threading.Thread(target=run_web_server, args=(port,), daemon=True)
    server_thread.start()
    return server_thread
