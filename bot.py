import os
import json
import time
import threading
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types

BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_ТОКЕН")
WEBAPP_URL = os.getenv("WEBAPP_URL", "")

BASE_DIR = Path(__file__).resolve().parent
TASKS_FILE = BASE_DIR / "tasks.json"

bot = telebot.TeleBot(BOT_TOKEN)

# --- Работа со структурой tasks.json ---

def load_all_tasks():
    if not TASKS_FILE.exists():
        return {}
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return {"default": data}
            return data
    except json.JSONDecodeError:
        return {}

def save_all_tasks(data):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_tasks(user_id):
    data = load_all_tasks()
    return data.get(str(user_id), [])

def add_user_task(user_id, title, remind_at=None):
    data = load_all_tasks()
    uid = str(user_id)
    user_tasks = data.get(uid, [])
    new_id = max([t["id"] for t in user_tasks], default=0) + 1
    user_tasks.append({
        "id": new_id,
        "title": title.strip(),
        "done": False,
        "remind_at": remind_at if remind_at else None
    })
    data[uid] = user_tasks
    save_all_tasks(data)
    return new_id

def toggle_user_task(user_id, task_id):
    data = load_all_tasks()
    uid = str(user_id)
    user_tasks = data.get(uid, [])
    for t in user_tasks:
        if t["id"] == task_id:
            t["done"] = not t["done"]
            save_all_tasks(data)
            return True
    return False

def delete_user_task(user_id, task_id):
    data = load_all_tasks()
    uid = str(user_id)
    user_tasks = data.get(uid, [])
    filtered = [t for t in user_tasks if t["id"] != task_id]
    if len(filtered) < len(user_tasks):
        data[uid] = filtered
        save_all_tasks(data)
        return True
    return False

# --- Фоновый планировщик push-напоминаний ---

def notification_worker():
    """Каждые 30 секунд проверяет tasks.json на наступившие напоминания."""
    while True:
        try:
            data = load_all_tasks()
            now = datetime.now()
            modified = False

            for uid, tasks in data.items():
                if uid == "default":
                    continue
                for task in tasks:
                    remind_at_str = task.get("remind_at")
                    if remind_at_str and not task.get("done"):
                        try:
                            remind_time = datetime.fromisoformat(remind_at_str)
                            if now >= remind_time:
                                # Отправляем уведомление пользователю в чат
                                bot.send_message(
                                    int(uid),
                                    f"⏰ **Напоминание о задаче!**\n\n📌 {task['title']}",
                                    parse_mode="Markdown"
                                )
                                # Очищаем remind_at, чтобы не спамить повторно
                                task["remind_at"] = None
                                modified = True
                        except Exception as e:
                            print(f"Ошибка обработки даты: {e}")

            if modified:
                save_all_tasks(data)
        except Exception as e:
            print(f"Ошибка воркера напоминаний: {e}")

        time.sleep(30)

# --- Web Server & API для Telegram Mini App ---

class MiniAppServer(BaseHTTPRequestHandler):
    def _send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            html_path = BASE_DIR / "index.html"
            if html_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                with open(html_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
        elif parsed.path == "/api/tasks":
            qs = parse_qs(parsed.query)
            user_id = qs.get("userId", ["default"])[0]
            self._send_json(get_user_tasks(user_id))
        else:
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        payload = json.loads(body.decode("utf-8")) if body else {}

        user_id = payload.get("userId", "default")

        if parsed.path == "/api/add":
            new_id = add_user_task(user_id, payload.get("title", ""), payload.get("remind_at"))
            self._send_json({"success": True, "id": new_id})
        elif parsed.path == "/api/toggle":
            success = toggle_user_task(user_id, int(payload.get("id")))
            self._send_json({"success": success})
        elif parsed.path == "/api/delete":
            success = delete_user_task(user_id, int(payload.get("id")))
            self._send_json({"success": success})
        else:
            self.send_response(404)
            self.end_headers()

def run_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), MiniAppServer)
    server.serve_forever()

# --- Telegram Bot Handler ---

@bot.message_handler(commands=['start', 'app'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if WEBAPP_URL:
        markup.add(types.KeyboardButton("🚀 Открыть Планировщик", web_app=types.WebAppInfo(WEBAPP_URL)))
    markup.add(types.KeyboardButton("📋 Список задач"))

    bot.send_message(
        message.chat.id,
        "👋 Планировщик с push-напоминаниями готов!\n"
        "Открой приложение, чтобы ставить задачи и указывать время для напоминаний:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda msg: msg.text == "📋 Список задач")
def show_tasks(message):
    tasks = get_user_tasks(message.from_user.id)
    if not tasks:
        bot.send_message(message.chat.id, "Список пуст 📭")
        return
    text = "📋 **Ваши задачи:**\n\n"
    for t in tasks:
        icon = "✅" if t.get("done") else "⬜"
        remind = f" (🔔 {t['remind_at']})" if t.get("remind_at") else ""
        text += f"{icon} `#{t['id']}` {t['title']}{remind}\n"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

if __name__ == "__main__":
    # 1. Запуск веб-сервера Mini App
    threading.Thread(target=run_server, daemon=True).start()
    # 2. Запуск фоновой проверки напоминаний
    threading.Thread(target=notification_worker, daemon=True).start()
    print("Бот, WebApp и система напоминаний запущены...")
    bot.infinity_polling()