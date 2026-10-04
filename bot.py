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

BOT_TOKEN = "8790966826:AAF8Mc6FWl5uZVsfZCo8uhqT0ejVsv_d_WM"
WEBAPP_URL = "https://todo-telegram-bot-tt80.onrender.com"

BASE_DIR = Path(__file__).resolve().parent
TASKS_FILE = BASE_DIR / "tasks.json"

bot = telebot.TeleBot(BOT_TOKEN)

# --- Встроенный красивый HTML интерфейс с напоминаниями ---
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
      --text: var(--tg-theme-text-color, #111111);
      --btn: var(--tg-theme-button-color, #2481cc);
      --btn-text: var(--tg-theme-button-text-color, #ffffff);
      --hint: var(--tg-theme-hint-color, #8e8e93);
      --card: var(--tg-theme-secondary-bg-color, #f2f2f7);
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 16px;
    }
    h2 { margin: 0 0 16px 0; font-size: 22px; font-weight: 700; }
    .box {
      background: var(--card);
      border-radius: 14px;
      padding: 12px;
      margin-bottom: 20px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    input[type="text"], input[type="datetime-local"] {
      width: 100%;
      box-sizing: border-box;
      padding: 12px;
      border: 1px solid rgba(0,0,0,0.1);
      border-radius: 10px;
      background: var(--bg);
      color: var(--text);
      font-size: 15px;
      outline: none;
    }
    .btn-add {
      background: var(--btn);
      color: var(--btn-text);
      border: none;
      border-radius: 10px;
      padding: 12px;
      font-size: 16px;
      font-weight: 600;
      cursor: pointer;
    }
    .list { display: flex; flex-direction: column; gap: 8px; }
    .item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: var(--card);
      padding: 12px 14px;
      border-radius: 12px;
    }
    .item.done .title { text-decoration: line-through; color: var(--hint); }
    .left { display: flex; align-items: flex-start; gap: 10px; flex: 1; cursor: pointer; }
    .title { font-size: 15px; word-break: break-word; }
    .time-badge { font-size: 12px; color: #e67e22; margin-top: 3px; }
    .del { background: none; border: none; color: #ff3b30; font-size: 18px; cursor: pointer; padding: 4px 8px; }
  </style>
</head>
<body>
  <h2>📝 Задачи и напоминания</h2>

  <div class="box">
    <input type="text" id="taskInput" placeholder="Что нужно сделать?" />
    <label style="font-size: 12px; color: var(--hint);">Время напоминания (Telegram пришлёт пуш):</label>
    <input type="datetime-local" id="remindInput" />
    <button class="btn-add" onclick="addTask()">Добавить задачу</button>
  </div>

  <div id="tasks" class="list"></div>

  <script>
    const tg = window.Telegram.WebApp;
    tg.ready();
    tg.expand();

    const userId = (tg.initDataUnsafe && tg.initDataUnsafe.user) ? tg.initDataUnsafe.user.id : "default";

    async function loadTasks() {
      try {
        const res = await fetch(`/api/tasks?userId=${userId}`);
        const data = await res.json();
        render(data);
      } catch (e) { console.error(e); }
    }

    function render(tasks) {
      const c = document.getElementById("tasks");
      c.innerHTML = "";
      if (!tasks || tasks.length === 0) {
        c.innerHTML = '<div style="text-align:center; color:var(--hint); padding:20px;">Нет активных задач 🎉</div>';
        return;
      }
      tasks.forEach(t => {
        const el = document.createElement("div");
        el.className = "item " + (t.done ? "done" : "");
        let badge = "";
        if (t.remind_at) {
          const d = new Date(t.remind_at);
          badge = `<div class="time-badge">⏰ Напоминание: ${d.toLocaleDateString()} в ${d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}</div>`;
        }
        el.innerHTML = `
          <div class="left" onclick="toggleTask(${t.id})">
            <span>${t.done ? '✅' : '⬜'}</span>
            <div>
              <div class="title">${t.title}</div>
              ${badge}
            </div>
          </div>
          <button class="del" onclick="deleteTask(${t.id})">✕</button>
        `;
        c.appendChild(el);
      });
    }

    async function addTask() {
      const inp = document.getElementById("taskInput");
      const remind = document.getElementById("remindInput").value;
      const title = inp.value.trim();
      if (!title) return;

      await fetch('/api/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ userId, title, remind_at: remind || null })
      });
      inp.value = "";
      document.getElementById("remindInput").value = "";
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

# --- База данных tasks.json ---

def load_all_tasks():
    if not TASKS_FILE.exists():
        return {}
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_all_tasks(data):
    try:
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения: {e}")

def get_user_tasks(uid):
    return load_all_tasks().get(str(uid), [])

def add_user_task(uid, title, remind_at=None):
    data = load_all_tasks()
    u = str(uid)
    tasks = data.get(u, [])
    new_id = max([t.get("id", 0) for t in tasks], default=0) + 1
    tasks.append({
        "id": new_id,
        "title": title.strip(),
        "done": False,
        "remind_at": remind_at
    })
    data[u] = tasks
    save_all_tasks(data)
    return new_id

def toggle_user_task(uid, tid):
    data = load_all_tasks()
    for t in data.get(str(uid), []):
        if t.get("id") == tid:
            t["done"] = not t.get("done", False)
            save_all_tasks(data)
            return True
    return False

def delete_user_task(uid, tid):
    data = load_all_tasks()
    u = str(uid)
    tasks = data.get(u, [])
    filtered = [t for t in tasks if t.get("id") != tid]
    if len(filtered) < len(tasks):
        data[u] = filtered
        save_all_tasks(data)
        return True
    return False

# --- Пуш-напоминания по времени ---

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
                    remind_str = task.get("remind_at")
                    if remind_str and not task.get("done"):
                        try:
                            remind_time = datetime.fromisoformat(remind_str)
                            if now >= remind_time:
                                bot.send_message(
                                    int(uid),
                                    f"⏰ **Напоминание о задаче!**\n\n📌 {task.get('title')}\n\nСделайте её или отметьте выполненной в приложении!",
                                    parse_mode="Markdown"
                                )
                                task["remind_at"] = None
                                modified = True
                        except Exception as e:
                            print(f"Ошибка даты: {e}")
            if modified:
                save_all_tasks(data)
        except Exception as e:
            print(f"Ошибка в воркере: {e}")
        time.sleep(20)

# --- Веб-сервер Mini App ---

class MiniAppServer(BaseHTTPRequestHandler):
    def _send_json(self, d):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(d).encode("utf-8"))

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
        if parsed.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif parsed.path == "/api/tasks":
            qs = parse_qs(parsed.query)
            uid = qs.get("userId", ["default"])[0]
            self._send_json(get_user_tasks(uid))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        payload = json.loads(body.decode("utf-8")) if body else {}
        uid = payload.get("userId", "default")

        if parsed.path == "/api/add":
            nid = add_user_task(uid, payload.get("title", ""), payload.get("remind_at"))
            self._send_json({"success": True, "id": nid})
        elif parsed.path == "/api/toggle":
            res = toggle_user_task(uid, int(payload.get("id")))
            self._send_json({"success": res})
        elif parsed.path == "/api/delete":
            res = delete_user_task(uid, int(payload.get("id")))
            self._send_json({"success": res})
        else:
            self.send_response(404)
            self.end_headers()

def run_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), MiniAppServer)
    server.serve_forever()

# --- Бот ---

@bot.message_handler(commands=['start'])
def welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🚀 Открыть Планировщик", web_app=types.WebAppInfo(WEBAPP_URL)))
    markup.add(types.KeyboardButton("📋 Показать список задач"))
    bot.send_message(
        message.chat.id,
        "Привет! Я твой планировщик задач с напоминаниями.\n\nНажми кнопку **«🚀 Открыть Планировщик»** ниже, чтобы добавить задачи со временем:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: m.text == "📋 Показать список задач")
def send_tasks(message):
    tasks = get_user_tasks(message.from_user.id)
    if not tasks:
        bot.send_message(message.chat.id, "Список задач пуст! 🎉")
        return
    text = "📋 **Твои задачи:**\n\n"
    for t in tasks:
        icon = "✅" if t.get("done") else "⬜"
        remind = f" (⏰ {t['remind_at']})" if t.get("remind_at") else ""
        text += f"{icon} `#{t['id']}` {t['title']}{remind}\n"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    threading.Thread(target=notification_worker, daemon=True).start()
    
    # Защищенный запуск бота
    time.sleep(3)
    try:
        bot.remove_webhook(drop_pending_updates=True)
    except Exception:
        pass

    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=30)
        except Exception as e:
            print(f"Polling reconnect: {e}")
            time.sleep(4)