import re
import json
import logging
from typing import Optional, Tuple, Dict, Any, List
from config import AVAILABLE_MODELS, DEFAULT_MODEL, SYSTEM_PROMPT
from services.database import (
    get_setting,
    set_setting,
    get_custom_rules,
    add_custom_rule,
    remove_custom_rule,
    clear_custom_rules,
    get_temperature,
    set_temperature,
    get_response_style,
    set_response_style,
    get_global_system_prompt,
    set_global_system_prompt,
    get_user_system_prompt,
    set_user_system_prompt,
    reset_all_settings_to_default,
    set_user_model,
)

logger = logging.getLogger(__name__)

STYLE_DESCRIPTIONS = {
    "default": "Стандартный (сбалансированный и точный)",
    "concise": "Краткий (ёмко, тезисно, без лишних вступлений)",
    "detailed": "Развернутый (глубокие пояснения с примерами)",
    "senior": "Senior Engineer (профессиональный код, типизация, архитектура)",
    "friendly": "Дружелюбный (поддерживающий, живой тон общения)"
}

STYLE_PROMPTS = {
    "concise": "Особый стиль ответов: отвечай предельно кратко, ёмко и структурированно, без шаблонных приветствий и лишних вводных фраз.",
    "detailed": "Особый стиль ответов: давай максимально подробные, исчерпывающие и детальные объяснения с наглядными иллюстрациями и шагами.",
    "senior": "Особый стиль ответов: отвечай как опытный Senior Software Architect. Пиши надежный production-ready код с полной типизацией и пояснениями архитектурных решений.",
    "friendly": "Особый стиль ответов: общайся в очень теплой, мотивирующей и дружелюбной манере, помогая во всех деталях."
}

class SelfConfigService:
    """
    Движок автономной самонастройки бота по запросам пользователя на естественном языке.
    Управляет правилами, стилями, системными инструкциями и параметрами генерации.
    """

    def build_effective_system_prompt(self, user_id: int) -> str:
        """
        Динамически собирает полный системный промпт:
        [Базовый промпт / Промпт пользователя] + [Инструкция стиля] + [Список кастомных правил].
        """
        # 1. Базовый промпт
        user_prompt = get_user_system_prompt(user_id)
        global_prompt = get_global_system_prompt()
        base = user_prompt if user_prompt != SYSTEM_PROMPT else global_prompt

        parts = [base.strip()]

        # 2. Стиль ответов
        style = get_response_style()
        if style in STYLE_PROMPTS:
            parts.append(f"\n\n{STYLE_PROMPTS[style]}")

        # 3. Активные кастомные правила
        rules = get_custom_rules()
        if rules:
            parts.append("\n\nВАЖНЕЙШИЕ ПРАВИЛА И ОГРАНИЧЕНИЯ (ОБЯЗАТЕЛЬНЫ К ИСПОЛНЕНИЮ):")
            for idx, r in enumerate(rules, 1):
                parts.append(f"{idx}. {r.strip()}")

        return "".join(parts)

    def get_current_config_report(self) -> str:
        """Генерирует наглядный отчет о текущих настройках для пользователя / админа."""
        rules = get_custom_rules()
        temp = get_temperature()
        style = get_response_style()
        style_desc = STYLE_DESCRIPTIONS.get(style, style)
        access_mode = get_setting("agent_access_mode", "admin_only")
        access_label = "🔒 Только Администратор" if access_mode == "admin_only" else "🌐 Все пользователи"
        def_model = get_setting("default_model", DEFAULT_MODEL)

        rules_block = ""
        if rules:
            rules_block = "\n".join([f"  `{i}.` {r}" for i, r in enumerate(rules, 1)])
        else:
            rules_block = "  _Кастомных правил пока нет (бот работает по умолчанию)_"

        report = (
            "⚙️ *Текущая конфигурация бота:*\n\n"
            f"• 🎨 *Стиль ответов:* `{style_desc}`\n"
            f"• 🌡 *Температура (креативность):* `{temp}` _(0.0 — точный, 1.0 — творческий)_\n"
            f"• 🤖 *Базовая модель:* `{def_model}`\n"
            f"• 🛡 *Доступ к Antigravity CLI:* `{access_label}`\n\n"
            f"📋 *Активные правила поведения:*\n{rules_block}\n\n"
            "💡 *Как настраивать меня голосом или текстом:*\n"
            "• _«Настрой себя так, чтобы ты всегда писал код с комментариями»_\n"
            "• _«Добавь правило: отвечать на русском языке и на \'ты\'»_\n"
            "• _«Установи температуру 0.2»_\n"
            "• _«Сделай стиль ответов кратким / senior / дружелюбным»_\n"
            "• _«Удали правило 1»_ или _«Очисти все правила»_\n"
            "• _«Сбрось настройки к начальным»_"
        )
        return report

    def detect_and_execute(self, user_id: int, user_text: str, is_admin: bool) -> Optional[str]:
        """
        Проверяет, является ли сообщение пользователя управляющим запросом на самонастройку.
        Если да — применяет изменения и возвращает текст подтверждения.
        Если нет — возвращает None, и запрос идет в стандартную генерацию.
        """
        text = user_text.strip()
        lower = text.lower()

        # -------------------------------------------------------------
        # 1. Запросы просмотра настроек
        # -------------------------------------------------------------
        is_view_request = (
            ("настройк" in lower and any(w in lower for w in ["покажи", "каки", "текущ", "конфиг", "статус", "как", "свои"])) or
            ("правил" in lower and any(w in lower for w in ["покажи", "каки", "список", "активн"])) or
            any(vt in lower for vt in ["покажи конфиг", "как ты настроен", "твой конфиг", "покажи свои настройки"])
        )
        if is_view_request and len(lower.split()) <= 10 and not any(w in lower for w in ["измени", "сбрось", "установи", "поменяй", "добавь", "удали"]):
            return self.get_current_config_report()

        # -------------------------------------------------------------
        # Все последующие модифицирующие операции требуют прав администратора
        # -------------------------------------------------------------
        config_intent_detected = any([
            lower.startswith("настрой себя"),
            lower.startswith("настрой бота"),
            lower.startswith("измени настройки"),
            lower.startswith("добавь правило"),
            lower.startswith("удали правило"),
            lower.startswith("очисти правила"),
            lower.startswith("сбрось настройки"),
            lower.startswith("поменяй температуру"),
            lower.startswith("установи температуру"),
            lower.startswith("смени стиль"),
            lower.startswith("сделай стиль"),
            "установи модель" in lower,
            "переключи модель по умолчанию" in lower,
            "сбрось все настройки" in lower
        ])

        if not config_intent_detected:
            # Проверка по регулярным выражениям для более гибких фраз
            if not re.search(r'^(настрой|измени|добавь в свои правила|запомни правило|установи)\b', lower):
                return None

        if not is_admin:
            return (
                "ℹ️ _Изменение глобальных настроек, стилей и правил бота доступно только Администратору._\n"
                "Вы можете сменить свою персональную модель через команду /model или сбросить диалог через /reset."
            )

        # -------------------------------------------------------------
        # 2. Сброс настроек к заводским
        # -------------------------------------------------------------
        if any(w in lower for w in ["сбрось настройки", "сбрось все настройки", "заводские настройки", "верни настройки по умолчанию"]):
            reset_all_settings_to_default()
            return (
                "🔄 *Все настройки бота успешно сброшены к заводским значениям!*\n\n"
                "• Кастомные правила очищены\n"
                "• Стиль: `Стандартный`\n"
                "• Температура: `0.7`\n"
                "• Системный промпт: по умолчанию\n\n"
                "Я готов работать в чистом стандартном режиме!"
            )

        # -------------------------------------------------------------
        # 3. Очистка правил
        # -------------------------------------------------------------
        if "очисти все правила" in lower or "удали все правила" in lower or "очисти правила" in lower:
            clear_custom_rules()
            return "🧹 *Все кастомные правила удалены.* Теперь я работаю со стандартными системными инструкциями."

        # -------------------------------------------------------------
        # 4. Удаление правила по номеру
        # -------------------------------------------------------------
        m_del = re.search(r'удали правило\s+(\d+|[^\n]+)', lower)
        if m_del:
            arg = m_del.group(1).strip()
            ok = remove_custom_rule(arg)
            if ok:
                return f"✅ *Правило удалено:* `{arg}`.\n\n" + self.get_current_config_report()
            else:
                return f"⚠️ Правило `{arg}` не найдено. Проверьте список активных правил через «покажи настройки»."

        # -------------------------------------------------------------
        # 5. Изменение температуры
        # -------------------------------------------------------------
        m_temp = re.search(r'(?:температур\w*|temperature)\s*(?:на|=|:)?\s*([0-1](?:[\.,]\d+)?)', lower)
        if m_temp:
            raw_val = m_temp.group(1).replace(",", ".")
            try:
                new_temp = float(raw_val)
                set_temperature(new_temp)
                mode_hint = "максимально строгий и точный" if new_temp <= 0.3 else ("сбалансированный" if new_temp <= 0.7 else "творческий и креативный")
                return (
                    f"🌡 *Температура генерации успешно установлена:* `{new_temp}`\n\n"
                    f"Характер ответов теперь: *{mode_hint}*."
                )
            except ValueError:
                pass

        # -------------------------------------------------------------
        # 6. Изменение стиля ответов
        # -------------------------------------------------------------
        if any(w in lower for w in ["кратк", "коротк", "лаконичн"]):
            set_response_style("concise")
            return "🎯 *Стиль ответов изменен на:* `Краткий`.\nТеперь мои ответы будут максимально емкими, структурированными и без лишней воды."

        if any(w in lower for w in ["развернут", "подробн", "детальн"]):
            set_response_style("detailed")
            return "📚 *Стиль ответов изменен на:* `Развернутый`.\nТеперь я буду давать максимально глубокие и обстоятельные объяснения с примерами."

        if any(w in lower for w in ["senior", "сеньор", "архитектор", "программист"]):
            set_response_style("senior")
            return "💻 *Стиль ответов изменен на:* `Senior Engineer`.\nФокусируюсь на чистом коде, типизации, надежности и архитектурных решениях."

        if any(w in lower for w in ["дружелюб", "тепл"]):
            set_response_style("friendly")
            return "🤝 *Стиль ответов изменен на:* `Дружелюбный`.\nБуду общаться живо, тепло и с максимальной поддержкой!"

        # -------------------------------------------------------------
        # 7. Добавление кастомного правила
        # -------------------------------------------------------------
        m_rule = re.search(r'(?:добавь правило|запомни правило|новое правило)\s*[:\-]?\s*(.+)', text, re.IGNORECASE | re.DOTALL)
        if m_rule:
            rule_text = m_rule.group(1).strip()
            # Отрезаем кавычки, если есть
            if (rule_text.startswith('"') and rule_text.endswith('"')) or (rule_text.startswith('«') and rule_text.endswith('»')):
                rule_text = rule_text[1:-1].strip()

            if rule_text:
                add_custom_rule(rule_text)
                return (
                    f"✅ *Новое правило успешно добавлено в мою память:*\n"
                    f"«_{rule_text}_»\n\n"
                    f"Я буду строго следовать ему во всех последующих ответах. Проверить: /config"
                )

        # -------------------------------------------------------------
        # 8. «Настрой себя так, чтобы...» (динамическое добавление правила/поведения)
        # -------------------------------------------------------------
        m_tune = re.search(r'(?:настрой себя|настрой бота)\s+(?:так,?\s+чтобы|чтобы)\s+(.+)', text, re.IGNORECASE | re.DOTALL)
        if m_tune:
            instruction = m_tune.group(1).strip()
            add_custom_rule(f"Поведение: {instruction}")
            return (
                f"🛠 *Я успешно перенастроил свое поведение:*\n"
                f"«_Всегда {instruction}_»\n\n"
                f"Новая инструкция активирована без перезагрузки и уже действует!"
            )

        # -------------------------------------------------------------
        # 9. Изменение модели по умолчанию
        # -------------------------------------------------------------
        for model_id in AVAILABLE_MODELS.keys():
            if model_id in lower:
                set_setting("default_model", model_id)
                return f"🤖 *Модель по умолчанию успешно изменена на:* `{model_id}`"

        # -------------------------------------------------------------
        # 10. Доступ к режиму агента
        # -------------------------------------------------------------
        if "открой доступ к агенту" in lower or "режим агента для всех" in lower:
            set_setting("agent_access_mode", "all")
            return "🌐 *Доступ к Antigravity CLI открыт для всех пользователей бота.*"

        if "закрой доступ к агенту" in lower or "режим агента только админ" in lower:
            set_setting("agent_access_mode", "admin_only")
            return "🔒 *Доступ к Antigravity CLI теперь ограничен только Администратором.*"

        # Если фраза содержала "настрой себя", но ни под один конкретный шаблон не подошла:
        add_custom_rule(text)
        return (
            f"✅ *Инструкция принята и добавлена в конфигурацию:*\n"
            f"«_{text}_»\n\n"
            f"Я адаптировал свое поведение согласно вашему запросу."
        )

self_config_service = SelfConfigService()
