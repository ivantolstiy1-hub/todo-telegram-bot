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

# ⚠️ Вставь сюда свой рабочий токен от @BotFather:
BOT_TOKEN = os.getenv("8790966826:AAF8Mc6FWl5uZVsfZCo8uhqT0ejVsv_d_WM", "8790966826:AAF8Mc6FWl5uZVsfZCo8uhqT0ejVsv_d_WM")
WEBAPP_URL = "https://todo-telegram-bot-tt80.onrender.com"

BASE_DIR = Path(__file__).resolve().parent
TASKS_FILE = BASE_DIR / "tasks.json"

bot = telebot.TeleBot(BOT_TOKEN)

# --- Встроенный HTML-интерфейс Mini App ---
HTML_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
  <title>Мой Планировщик</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    :root {
      --bg: var(--tg-theme-bg-color, #ffffff);
      --text: var(--tg-theme-text-color, #222222);
      --btn-bg: var(--tg-theme-button-color, #2481cc);
      --btn-text: var(--tg-theme-button-text-color, #ffffff);
      --hint: var(--tg-theme-hint-color, #999999);
      --card-bg: var(--tg-theme-secondary-bg-color, #f4f4f5);
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 16px;
    }
    h2 { margin-top: 0; font-size: 20px; }
    .input-group {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-bottom: 20px;
    }
    .input-row {
      display: flex;
      gap: 8px;
    }
    input[type="text"], input[type="datetime-local"] {
      flex: 1;
      padding: 12px 14px;
      border: 1px solid var(--hint);
      border-radius: 12px;
      background: var(--bg);
      color: var(--text);
      font-size: 14px;
      outline: none;
    }
    button.add-btn {
      padding: 12px 18px;
      background-color: var(--btn-bg);
      color: var(--btn-text);
      border: none;
      border-radius: 12px;
      font-size: 15px;
      font-weight: 600;
      cursor: pointer;
    }
    .task-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .task-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background-color: var(--card-bg);
      padding: 12px 16px;
      border-radius: 12px;
    }
    .task-item.done span.title {
      text-decoration: line-through;
      color: var(--hint);
    }
    .task-left {
      display: flex;
      align-items: flex-start;
      gap: 12px;
      cursor: pointer;
      flex: 1;
    }
    .task-content {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .remind-tag {
      font-size: 11px;
      color: var(--hint);
    }
    .del-btn {
      background: none;
      border: none;
      color: #ff3b30;
      font-size: 18px;
      cursor: pointer;
      padding: 4px;
    }
  </style>
</head>
<body>
  <h2>Мои задачи</h2>

  <div class="input-group">
    <input type="text" id="taskInput" placeholder="Новая задача..." />
    <div class="input-row">
      <input type="datetime-local" id="remindInput" />
      <button class="add-btn" onclick="addTask()">Добавить</button>
    </div>
  </div>

  <div id="tasks" class="task-list"></div>

  <script>
    const tg = window.Telegram.WebApp;
    tg.ready();
    tg.expand();

    const userId = (tg.initDataUnsafe && tg.initDataUnsafe.user) ? tg.initDataUnsafe.user.id : "default";

    async function loadTasks() {
      try {
        const res = await fetch(`/api/tasks?userId=${userId}`);
        const tasks = await res.json();
        renderTasks(tasks);
      } catch (e) {
        console.error(e);
      }
    }

    function renderTasks(tasks) {
      const container = document.getElementById("tasks");
      container.innerHTML = "";
      if (!tasks || tasks.length === 0) {
        container.innerHTML = '<div style="color: var(--hint); text-align: center; margin-top: 20px;">Нет задач 🎉</div>';
        return;
      }
      tasks.forEach(task => {
        const el = document.createElement("div");
        el.className = `task-item ${task.done ? 'done' : ''}`;
        
        let remindInfo = "";
        if (task.remind_at) {
          const d = new Date(task.remind_at);
          remindInfo = `<span class="remind-tag">🔔 ${d.toLocaleDateString()} ${d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>`;
        }

        el.innerHTML = `
          <div class="task-left" onclick="toggleTask(${task.id})">
            <span>${task.done ? '✅' : '⬜'}</span>
            <div class="task-content">
              <span class="title">${task.title}</span>
              ${remindInfo}
            </div>
          </div>
          <button class="del-btn" onclick="deleteTask(${task.id})">✕</button>
        `;
        container.appendChild(el);
      });
    }

    async function addTask() {
      const inp = document.getElementById("taskInput");
      const remindInp = document.getElementById("remindInput");
      const title = inp.value.trim();
      const remind_at = remindInp.value;
      if (!title) return;

      await fetch('/api/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ userId, title, remind_at })
      });
      inp.value = "";
      remindInp.value = "";
      loadTasks();
    }

    async function toggleTask(id) {
      await fetch('/api/toggle', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ userId, id })
      });
      loadTasks();
    }

    async function deleteTask(id) {
      await fetch('/api/delete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ userId, id })
      });
      loadTasks();
    }

    loadTasks();
  </script>
</body>
</html>
"""

# --- Работа с tasks.json ---

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
        print(f"Ошибка сохранения: {e}")

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

# --- HTTP Сервер Mini App ---

class MiniAppServer(BaseHTTPRequestHandler):
    def _send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_HEAD(self):
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
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
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
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), MiniAppServer)
    server.serve_forever()

# --- Telegram Bot Handler ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🚀 Открыть Планировщик", web_app=types.WebAppInfo(WEBAPP_URL)))
    markup.add(types.KeyboardButton("📋 Список задач"))

    bot.send_message(
        message.chat.id,
        "👋 Планировщик готов к работе!\nНажмите кнопку ниже, чтобы открыть список задач:",
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
    
    try:
        bot.remove_webhook(drop_pending_updates=True)
        time.sleep(1)
    except Exception as e:
        print(f"Ошибка Webhook: {e}")

    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=30)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)