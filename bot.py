import os
import json
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types

# Токен берем из переменных окружения Render
BOT_TOKEN = os.getenv("BOT_TOKEN", "8790966826:AAHwuqig_8SJFJ4TdXkEzpWrcuBmPUWILUg")

BASE_DIR = Path(__file__).resolve().parent
TASKS_FILE = BASE_DIR / "tasks.json"

bot = telebot.TeleBot(BOT_TOKEN)

# --- Легковесный сервер для Render Health Check ---
class SimpleHealthServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHealthServer)
    server.serve_forever()

# --- Работа с tasks.json ---
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

def add_user_task(user_id, title):
    data = load_all_tasks()
    uid = str(user_id)
    user_tasks = data.get(uid, [])
    new_id = max([t["id"] for t in user_tasks], default=0) + 1
    user_tasks.append({"id": new_id, "title": title.strip(), "done": False})
    data[uid] = user_tasks
    save_all_tasks(data)
    return new_id

def done_user_task(user_id, task_id):
    data = load_all_tasks()
    uid = str(user_id)
    user_tasks = data.get(uid, [])
    for t in user_tasks:
        if t["id"] == task_id:
            t["done"] = True
            save_all_tasks(data)
            return True
    return False

def edit_user_task(user_id, task_id, new_title):
    data = load_all_tasks()
    uid = str(user_id)
    user_tasks = data.get(uid, [])
    for t in user_tasks:
        if t["id"] == task_id:
            t["title"] = new_title.strip()
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

# --- Меню и кнопки ---
def main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        types.KeyboardButton("📋 Список задач"),
        types.KeyboardButton("➕ Добавить задачу"),
        types.KeyboardButton("✅ Выполнить"),
        types.KeyboardButton("✏️ Изменить"),
        types.KeyboardButton("🗑 Удалить")
    )
    return keyboard

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        f"👋 Привет, {message.from_user.first_name}!\n"
        f"Твой личный список синхронизирован на сервере Render.",
        reply_markup=main_keyboard()
    )

@bot.message_handler(func=lambda msg: msg.text == "📋 Список задач")
def show_tasks(message):
    tasks = get_user_tasks(message.from_user.id)
    if not tasks:
        bot.send_message(message.chat.id, "Список пуст 📭", reply_markup=main_keyboard())
        return
    text = "📋 **Ваши задачи:**\n\n"
    for t in tasks:
        icon = "✅" if t.get("done") else "⬜"
        text += f"{icon} `#{t['id']}` {t['title']}\n"
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=main_keyboard())

@bot.message_handler(func=lambda msg: msg.text == "➕ Добавить задачу")
def ask_add(message):
    msg = bot.send_message(message.chat.id, "Введите текст задачи:")
    bot.register_next_step_handler(msg, process_add)

def process_add(message):
    title = message.text.strip() if message.text else ""
    if title:
        new_id = add_user_task(message.from_user.id, title)
        bot.send_message(message.chat.id, f"✅ Задача `#{new_id}` сохранена!", parse_mode="Markdown", reply_markup=main_keyboard())

@bot.message_handler(func=lambda msg: msg.text == "✅ Выполнить")
def ask_done(message):
    tasks = [t for t in get_user_tasks(message.from_user.id) if not t.get("done")]
    if not tasks:
        bot.send_message(message.chat.id, "Нет невыполненных задач 🎉", reply_markup=main_keyboard())
        return
    markup = types.InlineKeyboardMarkup()
    for t in tasks:
        markup.add(types.InlineKeyboardButton(f"⬜ #{t['id']} {t['title']}", callback_data=f"done_{t['id']}"))
    bot.send_message(message.chat.id, "Выберите выполненную задачу:", reply_markup=markup)

@bot.message_handler(func=lambda msg: msg.text == "🗑 Удалить")
def ask_delete(message):
    tasks = get_user_tasks(message.from_user.id)
    if not tasks:
        bot.send_message(message.chat.id, "Список пуст 📭", reply_markup=main_keyboard())
        return
    markup = types.InlineKeyboardMarkup()
    for t in tasks:
        markup.add(types.InlineKeyboardButton(f"🗑 #{t['id']} {t['title']}", callback_data=f"del_{t['id']}"))
    bot.send_message(message.chat.id, "Выберите задачу для удаления:", reply_markup=markup)

@bot.message_handler(func=lambda msg: msg.text == "✏️ Изменить")
def ask_edit(message):
    tasks = get_user_tasks(message.from_user.id)
    if not tasks:
        bot.send_message(message.chat.id, "Список пуст 📭", reply_markup=main_keyboard())
        return
    markup = types.InlineKeyboardMarkup()
    for t in tasks:
        markup.add(types.InlineKeyboardButton(f"✏️ #{t['id']} {t['title']}", callback_data=f"edit_{t['id']}"))
    bot.send_message(message.chat.id, "Какую задачу изменить?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith(("done_", "del_", "edit_")))
def handle_callbacks(call):
    action, task_id_str = call.data.split("_")
    task_id = int(task_id_str)
    uid = call.from_user.id

    if action == "done":
        if done_user_task(uid, task_id):
            bot.edit_message_text(f"Задача `#{task_id}` выполнена ✅", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    elif action == "del":
        if delete_user_task(uid, task_id):
            bot.edit_message_text(f"Задача `#{task_id}` удалена 🗑", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    elif action == "edit":
        msg = bot.edit_message_text(f"Введите новое название для задачи `#{task_id}`:", call.message.chat.id, call.message.message_id)
        bot.register_next_step_handler(msg, process_edit_text, task_id)
    bot.answer_callback_query(call.id)

def process_edit_text(message, task_id):
    new_text = message.text.strip() if message.text else ""
    if new_text and edit_user_task(message.from_user.id, task_id, new_text):
        bot.send_message(message.chat.id, f"✅ Задача `#{task_id}` обновлена!", parse_mode="Markdown", reply_markup=main_keyboard())

if __name__ == "__main__":
    # Фоновый сервер для Render
    threading.Thread(target=run_health_server, daemon=True).start()
    print("Бот запущен...")
    bot.infinity_polling()