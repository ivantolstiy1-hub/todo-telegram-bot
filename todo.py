import sys
import json
from pathlib import Path

TASKS_FILE = Path("tasks.json")
DEFAULT_USER = "default"

def load_all_tasks():
    if not TASKS_FILE.exists():
        return {}
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return {DEFAULT_USER: data}
            return data
    except json.JSONDecodeError:
        return {}

def save_all_tasks(data):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_tasks():
    data = load_all_tasks()
    return data.get(DEFAULT_USER, [])

def print_help():
    print("""Использование:
  python todo.py add "<текст задачи>"        - добавить задачу
  python todo.py list                        - показать задачи
  python todo.py done <id>                   - отметить задачу
  python todo.py edit <id> "<новый текст>"  - изменить задачу
  python todo.py delete <id>                 - удалить задачу
""")

def add_task(title):
    data = load_all_tasks()
    tasks = data.get(DEFAULT_USER, [])
    new_id = max([t["id"] for t in tasks], default=0) + 1
    tasks.append({"id": new_id, "title": title.strip(), "done": False})
    data[DEFAULT_USER] = tasks
    save_all_tasks(data)
    print(f"Задача добавлена: [{new_id}] {title}")

def list_tasks():
    tasks = get_tasks()
    if not tasks:
        print("Список задач пуст.")
        return
    for t in tasks:
        icon = "✅" if t.get("done") else "⬜"
        print(f"{icon} [{t['id']}] {t['title']}")

def done_task(task_id_str):
    if not task_id_str.isdigit():
        print("Ошибка: ID задачи должен быть числом.")
        return
    task_id = int(task_id_str)
    data = load_all_tasks()
    tasks = data.get(DEFAULT_USER, [])
    for t in tasks:
        if t["id"] == task_id:
            t["done"] = True
            save_all_tasks(data)
            print(f"Задача [{task_id}] отмечена выполненной ✅")
            return
    print(f"Ошибка: задача с ID {task_id} не найдена.")

def edit_task(task_id_str, new_title):
    if not task_id_str.isdigit():
        print("Ошибка: ID должен быть числом.")
        return
    task_id = int(task_id_str)
    data = load_all_tasks()
    tasks = data.get(DEFAULT_USER, [])
    for t in tasks:
        if t["id"] == task_id:
            t["title"] = new_title.strip()
            save_all_tasks(data)
            print(f"Задача [{task_id}] изменена на \"{new_title}\"")
            return
    print(f"Ошибка: задача с ID {task_id} не найдена.")

def delete_task(task_id_str):
    if not task_id_str.isdigit():
        print("Ошибка: ID должен быть числом.")
        return
    task_id = int(task_id_str)
    data = load_all_tasks()
    tasks = data.get(DEFAULT_USER, [])
    filtered = [t for t in tasks if t["id"] != task_id]
    if len(filtered) < len(tasks):
        data[DEFAULT_USER] = filtered
        save_all_tasks(data)
        print(f"Задача [{task_id}] удалена 🗑")
    else:
        print(f"Ошибка: задача с ID {task_id} не найдена.")

def main():
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "add" and len(sys.argv) >= 3:
        add_task(sys.argv[2])
    elif cmd == "list":
        list_tasks()
    elif cmd == "done" and len(sys.argv) >= 3:
        done_task(sys.argv[2])
    elif cmd == "edit" and len(sys.argv) >= 4:
        edit_task(sys.argv[2], sys.argv[3])
    elif cmd == "delete" and len(sys.argv) >= 3:
        delete_task(sys.argv[2])
    else:
        print_help()

if __name__ == "__main__":
    main()