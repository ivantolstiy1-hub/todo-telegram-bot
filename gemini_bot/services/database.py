import sqlite3
import datetime
import json
from pathlib import Path
from typing import Optional, List, Dict, Union
from config import DB_PATH, DEFAULT_MODEL, SYSTEM_PROMPT, MAX_HISTORY_MESSAGES, DEFAULT_AGENT_ACCESS

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT NULL,
                first_name TEXT DEFAULT NULL,
                model TEXT DEFAULT NULL,
                system_prompt TEXT DEFAULT NULL,
                mode TEXT DEFAULT 'agent',
                antigravity_conv_id TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)")
        
        # Миграция колонок users
        cursor.execute("PRAGMA table_info(users)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "username" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN username TEXT DEFAULT NULL")
        if "first_name" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN first_name TEXT DEFAULT NULL")
        if "mode" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN mode TEXT DEFAULT 'agent'")
        if "antigravity_conv_id" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN antigravity_conv_id TEXT DEFAULT NULL")
            
        # Инициализация настроек по умолчанию
        defaults = {
            "agent_access_mode": DEFAULT_AGENT_ACCESS,
            "custom_rules": "[]",
            "temperature": "0.7",
            "response_style": "default",
            "global_system_prompt": SYSTEM_PROMPT,
            "default_model": DEFAULT_MODEL,
            "max_history_messages": str(MAX_HISTORY_MESSAGES)
        }
        for k, v in defaults.items():
            cursor.execute("SELECT value FROM bot_settings WHERE key = ?", (k,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO bot_settings (key, value) VALUES (?, ?)", (k, v))

        conn.commit()

def ensure_user(user_id: int, username: Optional[str] = None, first_name: Optional[str] = None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, first_name FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            cursor.execute(
                """INSERT INTO users 
                   (user_id, username, first_name, model, system_prompt, mode) 
                   VALUES (?, ?, ?, ?, ?, 'agent')""",
                (user_id, username, first_name, DEFAULT_MODEL, SYSTEM_PROMPT)
            )
        else:
            cursor.execute(
                """UPDATE users SET 
                   last_active = CURRENT_TIMESTAMP,
                   username = COALESCE(?, username),
                   first_name = COALESCE(?, first_name)
                   WHERE user_id = ?""",
                (username, first_name, user_id)
            )
        conn.commit()

def get_user_model(user_id: int) -> str:
    ensure_user(user_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT model FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row["model"]:
            return row["model"]
    return DEFAULT_MODEL

def set_user_model(user_id: int, model: str):
    ensure_user(user_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET model = ? WHERE user_id = ?", (model, user_id))
        conn.commit()

def get_user_engine_mode(user_id: int) -> str:
    ensure_user(user_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT mode FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row["mode"]:
            return row["mode"]
    return "agent"

def set_user_engine_mode(user_id: int, mode: str):
    ensure_user(user_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET mode = ? WHERE user_id = ?", (mode, user_id))
        conn.commit()

def get_user_antigravity_conv(user_id: int) -> Optional[str]:
    ensure_user(user_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT antigravity_conv_id FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row["antigravity_conv_id"]:
            return row["antigravity_conv_id"]
    return None

def set_user_antigravity_conv(user_id: int, conv_id: Optional[str]):
    ensure_user(user_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET antigravity_conv_id = ? WHERE user_id = ?", (conv_id, user_id))
        conn.commit()

def get_user_system_prompt(user_id: int) -> str:
    ensure_user(user_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT system_prompt FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row["system_prompt"]:
            return row["system_prompt"]
    return SYSTEM_PROMPT

def set_user_system_prompt(user_id: int, prompt: str):
    ensure_user(user_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET system_prompt = ? WHERE user_id = ?", (prompt, user_id))
        conn.commit()

def add_message(user_id: int, role: str, content: str):
    ensure_user(user_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content)
        )
        conn.commit()

def get_history(user_id: int, limit: int = MAX_HISTORY_MESSAGES):
    ensure_user(user_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT role, content FROM (
                SELECT id, role, content FROM messages
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
            ) ORDER BY id ASC
        """, (user_id, limit))
        rows = cursor.fetchall()
        
        history = []
        for row in rows:
            history.append({
                "role": row["role"],
                "parts": [{"text": row["content"]}]
            })
        return history

def clear_history(user_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        cursor.execute("UPDATE users SET antigravity_conv_id = NULL WHERE user_id = ?", (user_id,))
        conn.commit()

def count_messages(user_id: int) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM messages WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row["cnt"] if row else 0

# -------------------------------------------------------------
# Методы для Администратора и безопасности
# -------------------------------------------------------------

def get_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default

def set_setting(key: str, value: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO bot_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value)
        )
        conn.commit()

def get_total_users() -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM users")
        row = cursor.fetchone()
        return row["cnt"] if row else 0

def get_total_messages() -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM messages")
        row = cursor.fetchone()
        return row["cnt"] if row else 0

def get_active_antigravity_sessions_count() -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE antigravity_conv_id IS NOT NULL")
        row = cursor.fetchone()
        return row["cnt"] if row else 0

def get_all_user_ids() -> List[int]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        return [row["user_id"] for row in cursor.fetchall()]

def get_all_users_list(limit: int = 50) -> List[Dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.user_id, u.username, u.first_name, u.mode, u.model, u.last_active,
                   COUNT(m.id) as msg_count,
                   (u.antigravity_conv_id IS NOT NULL) as has_agent_session
            FROM users u
            LEFT JOIN messages m ON u.user_id = m.user_id
            GROUP BY u.user_id
            ORDER BY u.last_active DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

# -------------------------------------------------------------
# Методы динамической самонастройки (Self-Configuration)
# -------------------------------------------------------------

def get_custom_rules() -> List[str]:
    """Возвращает список пользовательских правил поведения бота."""
    raw = get_setting("custom_rules", "[]")
    try:
        rules = json.loads(raw)
        return rules if isinstance(rules, list) else []
    except Exception:
        return []

def set_custom_rules(rules: List[str]):
    """Сохраняет список правил."""
    set_setting("custom_rules", json.dumps(rules, ensure_ascii=False))

def add_custom_rule(rule: str) -> List[str]:
    """Добавляет новое правило в активный список."""
    rules = get_custom_rules()
    clean_rule = rule.strip()
    if clean_rule and clean_rule not in rules:
        rules.append(clean_rule)
        set_custom_rules(rules)
    return rules

def remove_custom_rule(rule_query: Union[str, int]) -> bool:
    """Удаляет правило по индексу (1-based) или по подстроке."""
    rules = get_custom_rules()
    if not rules:
        return False

    # Попытка удалить по индексу (1-based)
    if isinstance(rule_query, int) or (isinstance(rule_query, str) and rule_query.strip().isdigit()):
        idx = int(rule_query) - 1
        if 0 <= idx < len(rules):
            rules.pop(idx)
            set_custom_rules(rules)
            return True
        return False

    # Попытка удалить по тексту/подстроке
    target_text = str(rule_query).strip().lower()
    for i, r in enumerate(rules):
        if target_text in r.lower() or r.lower() in target_text:
            rules.pop(i)
            set_custom_rules(rules)
            return True

    return False

def clear_custom_rules():
    """Очищает все кастомные правила."""
    set_custom_rules([])

def get_temperature() -> float:
    """Возвращает текущую температуру генерации."""
    raw = get_setting("temperature", "0.7")
    try:
        return float(raw)
    except Exception:
        return 0.7

def set_temperature(temp: float):
    """Устанавливает температуру генерации (0.0 - 1.0)."""
    val = max(0.0, min(1.0, float(temp)))
    set_setting("temperature", str(round(val, 2)))

def get_response_style() -> str:
    """Возвращает текущий стиль ответов."""
    return get_setting("response_style", "default")

def set_response_style(style: str):
    """Устанавливает стиль ответов (concise, detailed, code_focused, default)."""
    set_setting("response_style", style.strip().lower())

def get_global_system_prompt() -> str:
    """Возвращает глобальный системный промпт."""
    return get_setting("global_system_prompt", SYSTEM_PROMPT)

def set_global_system_prompt(prompt: str):
    """Устанавливает глобальный системный промпт."""
    set_setting("global_system_prompt", prompt.strip())

def reset_all_settings_to_default():
    """Сбрасывает все динамические настройки бота к заводским значениям."""
    set_setting("custom_rules", "[]")
    set_setting("temperature", "0.7")
    set_setting("response_style", "default")
    set_setting("global_system_prompt", SYSTEM_PROMPT)
    set_setting("default_model", DEFAULT_MODEL)
    set_setting("agent_access_mode", DEFAULT_AGENT_ACCESS)
    set_setting("max_history_messages", str(MAX_HISTORY_MESSAGES))

