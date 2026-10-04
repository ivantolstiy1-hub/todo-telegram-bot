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

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "")

BASE_DIR = Path(__file__).resolve().parent
TASKS_FILE = BASE_DIR / "tasks.json"

bot = telebot.TeleBot(BOT_TOKEN)

# --- Хранилище tasks.json ---

def load_all_tasks():
    if not TASKS_FILE.exists():
        return {}
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return {"default": data}
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_all_tasks(data):
    try:
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения tasks.json: {e}")

def get_user_tasks(user_id):
    data = load_all_tasks()
    return data.get(str(user_id), [])

def add_user_task(user_id, title, remind_at=None):
    data = load_all_tasks()
    uid = str(user_id)
    user_tasks = data.get(uid, [])
    new_id = max([t.get("id", 0) for t in user_tasks], default=0) + 1
    user_tasks.append({
        "id": new_id,
        "title": str(title).strip(),
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
        if t.get("id") == task_id:
            t["done"] = not t.get("done", False)
            save_all_tasks(data)
            return True
    return False

def delete_user_task(user_id, task_id):
    data = load_all_tasks()
    uid = str(user_id)
    user_tasks = data.get(uid, [])
    filtered = [t for t in user_tasks if t.get("id") != task_id]
    if len(filtered) < len(user_tasks):
        data[uid] = filtered
        save_all_tasks(data)
        return True
    return False

# --- Фоновый воркер напоминаний ---

def notification_worker():
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
                                bot.send_message(
                                    int(uid),
                                    f"⏰ **Напоминание о задаче!**\n\n📌 {task.get('title')}",
                                    parse_mode="Markdown"
                                )
                                task["remind_at"] = None
                                modified = True
                        except Exception as err:
                            print(f"Ошибка даты: {err}")

            if modified:
                save_all_tasks(data)
        except Exception as e:
            print(f"Ошибка воркера: {e}")

        time.sleep(25)

# --- Веб-сервер Mini App ---

class MiniAppServer(BaseHTTPRequestHandler):
    def _send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_HEAD(self):
        # Ответ для проверок Render Health Check
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            # Пробуем несколько путей до index.html
            candidates = [
                BASE_DIR / "index.html",
                Path("index.html").resolve(),
                Path.cwd() / "index.html"
            ]
            html_file = next((c for c in candidates if c.is_file()), None)

            if html_file:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                with open(html_file, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                # Запасной рендер, если файл не найден в файловой системе Render
                self.wfile.write(b"<h1>Mini App is loading...</h1><script>location.reload();</script>")
        elif path == "/api/tasks":
            qs = parse_qs(parsed.query)
            user_id = qs.get("userId", ["default"])[0]
            self._send_json(get_user_tasks(user_id))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
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

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if WEBAPP_URL:
        markup.add(types.KeyboardButton("🚀 Открыть Планировщик", web_app=types.WebAppInfo(WEBAPP_URL)))
    markup.add(types.KeyboardButton("📋 Список задач"))

    bot.send_message(
        message.chat.id,
        "👋 Планировщик готов к работе!\nНажмите кнопку ниже или используйте кнопку меню для открытия списка задач:",
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
    threading.Thread(target=run_server, daemon=True).start()
    threading.Thread(target=notification_worker, daemon=True).start()
    print("Бот и WebApp запущены...")
    
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)