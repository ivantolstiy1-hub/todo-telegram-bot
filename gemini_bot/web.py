import os
import json
import time
import logging
import threading
from typing import Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from config import DEFAULT_MODEL

logger = logging.getLogger(__name__)

START_TIME = time.time()

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

class HealthAndDashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Подавляем логи частых health-check запросов для чистоты терминала
        if "/health" in (args[0] if args else ""):
            return
        logger.info("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), format % args))

    def do_GET(self):
        uptime_str = _format_uptime(time.time() - START_TIME)
        
        # 1. Health check эндпоинт для Render / UptimeRobot / Ping-сервисов
        if self.path == "/health" or self.path == "/ping":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            data = {
                "status": "ok",
                "service": "gemini_telegram_bot",
                "uptime": uptime_str,
                "timestamp": int(time.time())
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        # 2. Красивый веб-дашборд на главной странице
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        # Попытка получить статистику из БД
        users_count = "?"
        messages_count = "?"
        active_model = DEFAULT_MODEL
        try:
            from services.database import get_total_users, get_total_messages, get_setting
            users_count = str(get_total_users())
            messages_count = str(get_total_messages())
            active_model = get_setting("default_model", DEFAULT_MODEL)
        except Exception:
            pass

        html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gemini & Antigravity Bot Status</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
            color: #f8fafc;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .card {{
            background: rgba(30, 41, 59, 0.75);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            padding: 36px;
            max-width: 520px;
            width: 100%;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            background: rgba(34, 197, 94, 0.15);
            color: #4ade80;
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 20px;
            border: 1px solid rgba(34, 197, 94, 0.3);
        }}
        .dot {{
            width: 8px;
            height: 8px;
            background-color: #22c55e;
            border-radius: 50%;
            margin-right: 8px;
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }}
            70% {{ transform: scale(1); box-shadow: 0 0 0 8px rgba(34, 197, 94, 0); }}
            100% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }}
        }}
        h1 {{ font-size: 24px; font-weight: 700; margin-bottom: 8px; color: #fff; }}
        p.subtitle {{ color: #94a3b8; font-size: 14px; margin-bottom: 24px; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 14px;
            margin-bottom: 24px;
        }}
        .stat-box {{
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.05);
            padding: 16px;
            border-radius: 12px;
        }}
        .stat-label {{ font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }}
        .stat-value {{ font-size: 20px; font-weight: 700; color: #38bdf8; }}
        .features {{
            list-style: none;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            padding-top: 18px;
            margin-bottom: 24px;
        }}
        .features li {{
            font-size: 13px;
            color: #cbd5e1;
            padding: 4px 0;
            display: flex;
            align-items: center;
        }}
        .features li::before {{
            content: "✓";
            color: #38bdf8;
            margin-right: 8px;
            font-weight: bold;
        }}
        .health-link {{
            display: block;
            text-align: center;
            background: #2563eb;
            color: white;
            padding: 12px;
            border-radius: 10px;
            text-decoration: none;
            font-weight: 600;
            font-size: 14px;
            transition: background 0.2s;
        }}
        .health-link:hover {{ background: #1d4ed8; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="badge"><span class="dot"></span> Online & Active 24/7</div>
        <h1>🤖 Gemini & Antigravity Bot</h1>
        <p class="subtitle">Облачный сервис запущен и готов к обработке запросов</p>

        <div class="stats-grid">
            <div class="stat-box">
                <div class="stat-label">Uptime</div>
                <div class="stat-value">{uptime_str}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Модель</div>
                <div class="stat-value" style="font-size: 14px; word-break: break-all;">{active_model}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Пользователей</div>
                <div class="stat-value">{users_count}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Сообщений</div>
                <div class="stat-value">{messages_count}</div>
            </div>
        </div>

        <ul class="features">
            <li>Автономная самонастройка естественным языком</li>
            <li>Каскад моделей Gemini и авто-балансировка квот</li>
            <li>Распознавание голосовых сообщений и файлов</li>
            <li>Поддержка Antigravity CLI для задач кода</li>
        </ul>

        <a class="health-link" href="/health" target="_blank">Проверить /health JSON</a>
    </div>
</body>
</html>"""
        self.wfile.write(html.encode("utf-8"))

def run_web_server(port: int = 10000):
    server_address = ("0.0.0.0", port)
    try:
        httpd = HTTPServer(server_address, HealthAndDashboardHandler)
        logger.info(f"🌐 Встроенный HTTP health-check сервер запущен на http://0.0.0.0:{port}")
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
