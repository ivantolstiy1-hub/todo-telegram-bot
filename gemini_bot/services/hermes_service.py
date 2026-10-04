import json
import logging
import re
import requests
from abc import ABC, abstractmethod
from typing import Optional, Callable, List, Dict, Any, Tuple

from config import (
    GEMINI_API_KEYS,
    OPENROUTER_API_KEY,
    DEEPSEEK_API_KEY,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    DEFAULT_MODEL,
    AVAILABLE_MODELS,
)
from services.database import (
    get_user_model,
    get_history,
    add_message,
    get_temperature,
)
from services.self_config_service import self_config_service

logger = logging.getLogger(__name__)


# =====================================================================
# 1. БАЗОВЫЙ ИНТЕРФЕЙС И КЛАССЫ ПРОВАЙДЕРОВ (BASE AI PROVIDERS)
# =====================================================================

class BaseAIProvider(ABC):
    """Базовый абстрактный класс для всех провайдеров нейросетей."""
    name: str = "base"
    display_name: str = "Base Provider"

    @abstractmethod
    def is_configured(self) -> bool:
        """Проверяет наличие необходимого API-ключа или доступность окружения."""
        pass

    @abstractmethod
    def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float,
        model_id: str,
        on_status: Optional[Callable[[str], None]] = None,
        **kwargs
    ) -> str:
        """Выполняет генерацию ответа от языковой модели или агента."""
        pass


class AntigravityProvider(BaseAIProvider):
    """Провайдер автономного агента Antigravity CLI (выполнение терминальных команд и файлов)."""
    name = "antigravity"
    display_name = "Antigravity Agent (CLI)"

    def is_configured(self) -> bool:
        try:
            from services.antigravity_service import antigravity_service
            return antigravity_service.is_available()
        except Exception:
            return False

    def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float,
        model_id: str,
        on_status: Optional[Callable[[str], None]] = None,
        **kwargs
    ) -> str:
        from services.antigravity_service import antigravity_service
        from services.database import get_user_antigravity_conv, set_user_antigravity_conv

        if not self.is_configured():
            raise RuntimeError("Antigravity CLI недоступен в данной среде (запустите бота на локальном Mac с установленным CLI)")

        user_id = kwargs.get("user_id", 1)
        prompt = messages[-1]["content"] if messages else "Привет"

        conv_id = get_user_antigravity_conv(user_id)
        if not conv_id:
            if on_status:
                on_status("🤖 Antigravity: Инициализация сессии агента... ⏳")
            conv_id, reply = antigravity_service.create_conversation(
                prompt=prompt,
                model="flash",
                title=f"TG_Hermes_{user_id}",
                on_progress=on_status
            )
            set_user_antigravity_conv(user_id, conv_id)
            return reply
        else:
            if on_status:
                on_status("🤖 Antigravity: Выполнение задачи в терминале...")
            reply = antigravity_service.send_message(
                conversation_id=conv_id,
                content=prompt,
                on_progress=on_status
            )
            return reply


class GeminiProvider(BaseAIProvider):
    """Провайдер Google Gemini API (с поддержкой пула ключей и каскада моделей)."""
    name = "gemini"
    display_name = "Google Gemini"

    def is_configured(self) -> bool:
        return bool(GEMINI_API_KEYS)

    def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float,
        model_id: str,
        on_status: Optional[Callable[[str], None]] = None,
        **kwargs
    ) -> str:
        from services.gemini_service import gemini_service
        # Gemini использует свой оптимизированный формат
        contents = []
        for m in messages:
            role = "user" if m.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})

        # Если модель не Gemini (например, auto-hermes), используем gemini-3.5-flash
        actual_model = model_id if model_id.startswith("gemini-") else "gemini-3.5-flash"

        payload = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 8192 if "pro" in actual_model else 4096,
            },
        }
        reply, _ = gemini_service._call_api_with_fallback(actual_model, payload, on_status=on_status)
        return reply


class DeepSeekProvider(BaseAIProvider):
    """Провайдер DeepSeek API (V3 / R1)."""
    name = "deepseek"
    display_name = "DeepSeek AI"
    BASE_URL = "https://api.deepseek.com/chat/completions"

    def is_configured(self) -> bool:
        return bool(DEEPSEEK_API_KEY)

    def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float,
        model_id: str,
        on_status: Optional[Callable[[str], None]] = None,
        **kwargs
    ) -> str:
        if on_status:
            on_status("🧮 Запрос к DeepSeek API...")

        model_map = {
            "deepseek-reasoner": "deepseek-reasoner",
            "deepseek-chat": "deepseek-chat",
        }
        target_model = model_map.get(model_id, "deepseek-chat")

        formatted_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            role = "assistant" if m.get("role") in ("model", "assistant") else "user"
            formatted_messages.append({"role": role, "content": m.get("content", "")})

        payload = {
            "model": target_model,
            "messages": formatted_messages,
            "temperature": min(temperature, 1.0),
            "stream": False,
        }

        # Для моделей DeepSeek-R1 (reasoner) температура не должна превышать допустимые пределы
        if target_model == "deepseek-reasoner":
            payload["temperature"] = 0.6

        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }

        resp = requests.post(self.BASE_URL, headers=headers, json=payload, timeout=90)
        if resp.status_code != 200:
            raise RuntimeError(f"DeepSeek API Error ({resp.status_code}): {resp.text[:300]}")

        data = resp.json()
        choice = data.get("choices", [{}])[0].get("message", {})
        content = choice.get("content", "")
        # Если модель возвращает рассуждения (reasoning_content у R1)
        reasoning = choice.get("reasoning_content")
        if reasoning and not content:
            content = reasoning
        return content


class OpenAIProvider(BaseAIProvider):
    """Провайдер OpenAI API (GPT-4o, GPT-4o-mini)."""
    name = "openai"
    display_name = "OpenAI"
    BASE_URL = "https://api.openai.com/v1/chat/completions"

    def is_configured(self) -> bool:
        return bool(OPENAI_API_KEY)

    def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float,
        model_id: str,
        on_status: Optional[Callable[[str], None]] = None,
        **kwargs
    ) -> str:
        if on_status:
            on_status("🟢 Запрос к OpenAI API (GPT-4o)...")

        target_model = "gpt-4o" if "4o" in model_id else "gpt-4o-mini"
        formatted_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            role = "assistant" if m.get("role") in ("model", "assistant") else "user"
            formatted_messages.append({"role": role, "content": m.get("content", "")})

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": target_model,
            "messages": formatted_messages,
            "temperature": temperature,
        }

        resp = requests.post(self.BASE_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(f"OpenAI API Error ({resp.status_code}): {resp.text[:300]}")

        data = resp.json()
        return data["choices"][0]["message"]["content"]


class ClaudeProvider(BaseAIProvider):
    """Провайдер Anthropic Claude API (Claude 3.5 Sonnet)."""
    name = "claude"
    display_name = "Anthropic Claude"
    BASE_URL = "https://api.anthropic.com/v1/messages"

    def is_configured(self) -> bool:
        return bool(ANTHROPIC_API_KEY)

    def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float,
        model_id: str,
        on_status: Optional[Callable[[str], None]] = None,
        **kwargs
    ) -> str:
        if on_status:
            on_status("🎭 Запрос к Anthropic Claude API...")

        target_model = "claude-3-5-sonnet-20241022" if "sonnet" in model_id else "claude-3-5-haiku-20241022"

        # Форматирование под строгие требования Anthropic:
        # Сообщения должны чередоваться (user/assistant) и начинаться с user
        claude_msgs = []
        for m in messages:
            role = "assistant" if m.get("role") in ("model", "assistant") else "user"
            content = m.get("content", "").strip()
            if not content:
                continue

            if claude_msgs and claude_msgs[-1]["role"] == role:
                claude_msgs[-1]["content"] += f"\n\n{content}"
            else:
                claude_msgs.append({"role": role, "content": content})

        if not claude_msgs:
            claude_msgs = [{"role": "user", "content": "Привет"}]
        elif claude_msgs[0]["role"] != "user":
            claude_msgs.insert(0, {"role": "user", "content": "Начало контекста"})

        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": target_model,
            "max_tokens": 4096,
            "system": system_prompt,
            "temperature": min(temperature, 1.0),
            "messages": claude_msgs,
        }

        resp = requests.post(self.BASE_URL, headers=headers, json=payload, timeout=75)
        if resp.status_code != 200:
            raise RuntimeError(f"Claude API Error ({resp.status_code}): {resp.text[:300]}")

        data = resp.json()
        parts = data.get("content", [])
        text_parts = [p.get("text", "") for p in parts if p.get("type") == "text"]
        return "".join(text_parts)


class OpenRouterProvider(BaseAIProvider):
    """
    Провайдер OpenRouter API.
    Позволяет через единый ключ использовать Nous Hermes 3, Claude 3.5, DeepSeek R1, GPT-4o и др.
    """
    name = "openrouter"
    display_name = "OpenRouter (Nous Hermes)"
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def is_configured(self) -> bool:
        return bool(OPENROUTER_API_KEY)

    def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float,
        model_id: str,
        on_status: Optional[Callable[[str], None]] = None,
        **kwargs
    ) -> str:
        if on_status:
            on_status(f"🦙 Запрос к OpenRouter ({model_id})...")

        # Карта соответствия моделей для OpenRouter
        model_map = {
            "nous-hermes-3": "nousresearch/hermes-3-llama-3.1-70b",
            "deepseek-reasoner": "deepseek/deepseek-r1",
            "deepseek-chat": "deepseek/deepseek-chat",
            "claude-3-5-sonnet": "anthropic/claude-3.5-sonnet",
            "gpt-4o": "openai/gpt-4o",
        }
        target_model = model_map.get(model_id, model_id)

        formatted_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            role = "assistant" if m.get("role") in ("model", "assistant") else "user"
            formatted_messages.append({"role": role, "content": m.get("content", "")})

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://todo-telegram-bot.onrender.com",
            "X-Title": "Telegram Bot Hermes Orchestrator",
        }
        payload = {
            "model": target_model,
            "messages": formatted_messages,
            "temperature": temperature,
        }

        resp = requests.post(self.BASE_URL, headers=headers, json=payload, timeout=90)
        if resp.status_code != 200:
            raise RuntimeError(f"OpenRouter API Error ({resp.status_code}): {resp.text[:300]}")

        data = resp.json()
        return data["choices"][0]["message"]["content"]


class VideoDirectorProvider(BaseAIProvider):
    """
    Провайдер генерации и режиссуры видеоконтента.
    Объединяет прямое создание видео (Luma Ray 2, Kling 1.5, Minimax Hailuo)
    и профессиональный монтажный стол (Director's Cut Storyboard + Саунд-дизайн).
    """
    name = "video"
    display_name = "Video AI & Монтаж (Luma, Kling, Minimax)"

    def is_configured(self) -> bool:
        from services.video_service import video_service
        return video_service.has_any_active_provider()

    def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float,
        model_id: str,
        on_status: Optional[Callable[[str], None]] = None,
        **kwargs
    ) -> str:
        from services.video_service import video_service
        prompt = messages[-1]["content"] if messages else "Создай видеоролик"
        aspect_ratio = kwargs.get("aspect_ratio", "16:9")
        duration = kwargs.get("duration", 5)

        source_media = kwargs.get("source_media")
        media_type = kwargs.get("media_type")

        result = video_service.generate_or_direct(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            duration_sec=duration,
            on_status=on_status,
            source_media=source_media,
            media_type=media_type,
        )
        return result["text"]


# =====================================================================
# 2. ОРКЕСТРАТОР АГЕНТ ГЕРМЕС (HERMES ORCHESTRATOR)
# =====================================================================

class HermesOrchestrator:
    """
    Интеллектуальный мульти-агентный диспетчер (Агент Гермес).
    - Определяет намерения пользователя и тип запроса.
    - Автоматически направляет запрос в специализированную нейросеть:
      * Генерация и режиссура видео -> Video AI Director (Luma, Kling, Minimax)
      * Рассуждения и математика -> DeepSeek R1
      * Программирование и архитектура -> Claude 3.5 Sonnet
      * Творчество и текст -> ChatGPT / Nous Hermes 3
      * Быстрые ответы и мультимодальность -> Google Gemini 3.5 Flash
    - Поддерживает естественные команды: "Гермес, спроси у DeepSeek: ...", "через Claude: ..."
    - Реализует бесшовный резервный каскад (Fallback) на Gemini при отсутствии ключей сторонних LLM.
    """

    def __init__(self):
        self.providers: Dict[str, BaseAIProvider] = {
            "video": VideoDirectorProvider(),
            "antigravity": AntigravityProvider(),
            "gemini": GeminiProvider(),
            "deepseek": DeepSeekProvider(),
            "openai": OpenAIProvider(),
            "claude": ClaudeProvider(),
            "openrouter": OpenRouterProvider(),
        }

    def get_providers_status(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает информацию о доступности и ключах всех провайдеров."""
        status = {}
        for key, p in self.providers.items():
            status[key] = {
                "name": p.display_name,
                "configured": p.is_configured(),
            }
        return status

    def parse_explicit_route(self, text: str) -> Tuple[Optional[str], str]:
        """
        Проверяет наличие явного указания модели в тексте запроса.
        Примеры:
          "Гермес, спроси у deepseek: реши задачу..."
          "через claude: напиши скрипт..."
          "Гермес, через antigravity: запусти команду git status"
        """
        # Паттерн 1: "Гермес, [через/спроси у/реши через/передай/используй/запусти/выполни/сгенерируй/смонтируй/сделай] <модель>[:|, ] <текст>"
        pattern1 = re.compile(
            r"^(?:гермес|hermes)[,\s]+(?:через|спроси\s+у|реши\s+через|передай|используй|запусти(?:\s+в)?|выполни(?:\s+в)?|сгенерируй(?:\s+в|\s+мне)?|смонтируй(?:\s+в|\s+мне|\s+через)?|сделай(?:\s+мне)?|нарисуй)?\s*"
            r"(deepseek|дипсик|claude|клод|chatgpt|openai|чатгпт|hermes|гермес|gemini|джемини|antigravity|антигравити|терминале|терминал|agy|luma|лума|kling|клинг|runway|ранвей|minimax|минимакс|hailuo|видео|video)[,\s:]*(.*)$",
            re.IGNORECASE | re.DOTALL,
        )
        # Паттерн 2: "через <модель>[:|, ] <текст>" или "спроси у <модель>[:|, ] <текст>"
        pattern2 = re.compile(
            r"^(?:через|спроси\s+у|выполни\s+в|запусти\s+в|сгенерируй(?:\s+в|\s+мне)?|смонтируй(?:\s+в|\s+через)?|сделай(?:\s+мне)?)\s+"
            r"(deepseek|дипсик|claude|клод|chatgpt|openai|чатгпт|hermes|гермес|gemini|джемини|antigravity|антигравити|терминале|терминал|agy|luma|лума|kling|клинг|runway|ранвей|minimax|минимакс|hailuo|видео|video)[,\s:]*(.*)$",
            re.IGNORECASE | re.DOTALL,
        )
        # Паттерн 3: прямое обращение "видео[:\s] <текст>" или "видео 9:16[:\s] <текст>" или "video[:\s] <текст>"
        pattern3 = re.compile(
            r"^(?:видео|video)(?:\s+(?:9:16|16:9))?[,\s:]+(.*)$",
            re.IGNORECASE | re.DOTALL,
        )

        match3 = pattern3.match(text)
        if match3:
            rem = match3.group(1).strip()
            return "video-director", rem if rem else text

        match = pattern1.match(text) or pattern2.match(text)
        if match:
            target_raw = match.group(1).lower()
            remaining_prompt = match.group(2).strip()
            
            # Если после префикса остался пустой текст, не обрезаем
            prompt_to_use = remaining_prompt if remaining_prompt else text

            if target_raw in ("antigravity", "антигравити", "терминал", "терминале", "agy"):
                return "antigravity", prompt_to_use
            elif target_raw in ("luma", "лума", "kling", "клинг", "runway", "ранвей", "minimax", "минимакс", "hailuo", "видео", "video"):
                return "video-director", prompt_to_use
            elif target_raw in ("deepseek", "дипсик"):
                return "deepseek-reasoner", prompt_to_use
            elif target_raw in ("claude", "клод"):
                return "claude-3-5-sonnet", prompt_to_use
            elif target_raw in ("chatgpt", "openai", "чатгпт"):
                return "gpt-4o", prompt_to_use
            elif target_raw in ("hermes", "гермес"):
                return "nous-hermes-3", prompt_to_use
            elif target_raw in ("gemini", "джемини"):
                return "gemini-3.5-flash", prompt_to_use

        return None, text

    def classify_intent(self, text: str) -> Tuple[str, str]:
        """
        Интеллектуальная классификация запроса для режима Auto-Hermes.
        Возвращает кортеж: (рекомендуемая_модель, причина_маршрутизации).
        """
        t = text.lower()

        # -1. Генерация и монтаж видео, рилсы, анимация, раскадровка -> Video AI Director
        video_patterns = [
            r"видео", r"ролик", r"клип", r"рилс", r"reels", r"shorts", r"тизер",
            r"трейлер", r"смонтируй", r"монтаж", r"анимаци", r"раскадровк",
            r"storyboard", r"сценарий видео", r"kling", r"luma", r"runway",
            r"hailuo", r"minimax", r"сгенерируй.*видео", r"создай.*видео"
        ]
        if any(re.search(p, t) for p in video_patterns):
            return "video-director", "🎬 Анализ: генерация видео и режиссура монтажа -> маршрут в Video AI Director"

        # 0. Терминальные команды, запуск скриптов, работа с файловой системой -> Antigravity CLI
        terminal_patterns = [
            r"в терминале", r"через терминал", r"командной строке", r"запусти команду",
            r"выполни команду", r"терминальн.*команд", r"прочитай файл", r"создай файл",
            r"открой файл", r"запиши в файл", r"удали файл", r"структур.*пап",
            r"файлы проекта", r"git status", r"git commit", r"git push", r"git log",
            r"npm run", r"npm test", r"pip install", r"pytest", r"запусти тест"
        ]
        if any(re.search(p, t) for p in terminal_patterns):
            return "antigravity", "🛠 Анализ: терминальная команда или работа с файлами -> маршрут в Antigravity CLI"

        # 1. Математика, формальная логика, цепочки рассуждений -> DeepSeek R1
        reasoning_patterns = [
            r"докажи", r"теорем", r"рассуди", r"доказательств", r"посчитай",
            r"вычисли", r"интеграл", r"уравнени", r"математик", r"вероятност",
            r"логик", r"головоломк", r"шаг за шагом", r"step-by-step", r"algorithm",
            r"олимпиад", r"сумма ряда", r"предел"
        ]
        if any(re.search(p, t) for p in reasoning_patterns):
            return "deepseek-reasoner", "🧮 Анализ: глубокие математические и логические рассуждения -> маршрут в DeepSeek R1"

        # 2. Архитектура, программирование, анализ кода, баги -> Claude 3.5 Sonnet
        code_patterns = [
            r"напиши код", r"напиши функцию", r"исправь баг", r"ошибк",
            r"рефакторинг", r"архитектур", r"скрипт", r"python", r"javascript",
            r"typescript", r"react", r"html", r"css", r"sql", r"api", r"docker",
            r"def\s+", r"return\s+", r"import\s+", r"class\s+", r"function\s+",
            r"traceback", r"syntaxerror"
        ]
        if any(re.search(p, t) for p in code_patterns):
            return "claude-3-5-sonnet", "🎭 Анализ: разработка кода и техническая архитектура -> маршрут в Claude 3.5 Sonnet"

        # 3. Творчество, литературные тексты, сценарии -> Nous Hermes 3 / GPT-4o
        creative_patterns = [
            r"сочини", r"стих", r"рассказ", r"эссе", r"сценарий", r"придумай историю",
            r"креатив", r"шутк", r"анекдот", r"диалог персонажей"
        ]
        if any(re.search(p, t) for p in creative_patterns):
            return "nous-hermes-3", "🦙 Анализ: креативный контент и литература -> маршрут в Nous Hermes 3"

        # 4. По умолчанию: высокая скорость и общение -> Gemini 3.5 Flash
        return "gemini-3.5-flash", "⚡ Анализ: универсальный диалог -> маршрут в Gemini 3.5 Flash"

    def resolve_provider(self, target_model: str) -> Tuple[BaseAIProvider, str, Optional[str]]:
        """
        Подбирает рабочий провайдер для запрошенной модели.
        Если ключ целевого провайдера отсутствует, реализует плавный fallback:
        - DeepSeek / Claude / GPT / Hermes могут работать через OpenRouter (если задан OPENROUTER_API_KEY).
        - Antigravity CLI в облачной среде Render плавно переключается на Claude/Gemini.
        
        Возвращает: (provider_instance, actual_model_id, notification_banner)
        """
        # -1. Запрос к Video AI & Монтаж (Luma, Kling, Minimax, Video Director)
        if target_model in ("video-director", "video", "luma", "kling", "runway", "minimax", "hailuo"):
            return self.providers["video"], "video-director", None

        # 0. Запрос к Antigravity CLI
        if target_model in ("antigravity", "agent"):
            if self.providers["antigravity"].is_configured():
                return self.providers["antigravity"], "antigravity", None
            # Fallback для облачного сервера Render
            banner = (
                "🏛 *[Агент Гермес: среда Antigravity CLI активна на локальном компьютере с установленным агентом]*\n"
                "💡 _На облачном сервере Render терминал изолирован, поэтому задача решена аналитически через Claude / Gemini._\n\n"
            )
            if self.providers["claude"].is_configured():
                return self.providers["claude"], "claude-3-5-sonnet", banner
            elif self.providers["openrouter"].is_configured():
                return self.providers["openrouter"], "claude-3-5-sonnet", banner
            else:
                return self.providers["gemini"], "gemini-3.5-flash", banner

        # 1. Запрос к Gemini
        if target_model.startswith("gemini-"):
            return self.providers["gemini"], target_model, None

        # 2. Запрос к DeepSeek
        if target_model.startswith("deepseek-"):
            if self.providers["deepseek"].is_configured():
                return self.providers["deepseek"], target_model, None
            if self.providers["openrouter"].is_configured():
                return self.providers["openrouter"], target_model, None
            # Fallback на Gemini
            banner = (
                "🏛 *[Агент Гермес: маршрут направлен в Gemini 3.5 Flash]*\n"
                "💡 _Для прямого доступа к DeepSeek R1 добавьте переменную DEEPSEEK_API_KEY (или OPENROUTER_API_KEY) в Render._\n\n"
            )
            return self.providers["gemini"], "gemini-3.5-flash", banner

        # 3. Запрос к Claude
        if target_model.startswith("claude-"):
            if self.providers["claude"].is_configured():
                return self.providers["claude"], target_model, None
            if self.providers["openrouter"].is_configured():
                return self.providers["openrouter"], target_model, None
            # Fallback на Gemini
            banner = (
                "🏛 *[Агент Гермес: маршрут направлен в Gemini 3.5 Flash]*\n"
                "💡 _Для прямого доступа к Claude 3.5 Sonnet добавьте переменную ANTHROPIC_API_KEY (или OPENROUTER_API_KEY) в Render._\n\n"
            )
            return self.providers["gemini"], "gemini-3.5-flash", banner

        # 4. Запрос к ChatGPT (OpenAI)
        if target_model == "gpt-4o":
            if self.providers["openai"].is_configured():
                return self.providers["openai"], target_model, None
            if self.providers["openrouter"].is_configured():
                return self.providers["openrouter"], target_model, None
            # Fallback на Gemini
            banner = (
                "🏛 *[Агент Гермес: маршрут направлен в Gemini 3.5 Flash]*\n"
                "💡 _Для прямого доступа к ChatGPT (GPT-4o) добавьте переменную OPENAI_API_KEY (или OPENROUTER_API_KEY) в Render._\n\n"
            )
            return self.providers["gemini"], "gemini-3.5-flash", banner

        # 5. Запрос к Nous Hermes 3
        if target_model == "nous-hermes-3":
            if self.providers["openrouter"].is_configured():
                return self.providers["openrouter"], target_model, None
            # Fallback на Gemini
            banner = (
                "🏛 *[Агент Гермес: маршрут направлен в Gemini 3.5 Flash]*\n"
                "💡 _Для использования модели Nous Hermes 3 добавьте переменную OPENROUTER_API_KEY в Render._\n\n"
            )
            return self.providers["gemini"], "gemini-3.5-flash", banner

        # По умолчанию
        return self.providers["gemini"], "gemini-3.5-flash", None

    def chat(
        self,
        user_id: int,
        user_message: str,
        target_model: Optional[str] = None,
        on_status: Optional[Callable[[str], None]] = None,
        **kwargs
    ) -> str:
        """
        Главная точка входа для общения с Агентом Гермес:
        1. Проверяет естественные команды маршрутизации.
        2. Определяет целевую модель (или использует выбранную пользователем / Auto-Hermes).
        3. Получает системный промпт и единую историю диалога из БД.
        4. Вызывает провайдера с перехватом ошибок и каскадным резервом на Gemini.
        5. Сохраняет историю в SQLite.
        """
        # 1. Проверяем явное обращение в сообщении (например: "Гермес, спроси у deepseek: ...")
        explicit_model, prompt_clean = self.parse_explicit_route(user_message)
        effective_prompt = prompt_clean or user_message

        # 2. Определяем модель
        selected_user_model = target_model or get_user_model(user_id)
        route_notice = None

        if explicit_model:
            model_to_use = explicit_model
            if on_status:
                on_status(f"🏛 Агент Гермес: обнаружен прямой вызов {explicit_model}...")
        elif selected_user_model in ("auto-hermes", "hermes", "auto"):
            model_to_use, reason = self.classify_intent(effective_prompt)
            route_notice = f"🏛 *[Агент Гермес: {reason}]*\n\n"
            if on_status:
                on_status(f"🏛 Агент Гермес: {reason}")
        else:
            model_to_use = selected_user_model

        # 3. Подбираем провайдер и проверяем доступность ключей
        provider, actual_model_id, fallback_banner = self.resolve_provider(model_to_use)

        # 4. Формируем контекст и параметры генерации
        sys_prompt = self_config_service.build_effective_system_prompt(user_id)
        temp = get_temperature()
        db_history = get_history(user_id)

        # Подготавливаем сообщения в едином формате [{role: user/assistant, content: text}]
        messages: List[Dict[str, str]] = []
        for m in db_history:
            role = m.get("role", "user")
            content = ""
            if "content" in m:
                content = m["content"]
            elif "parts" in m and isinstance(m["parts"], list) and m["parts"]:
                content = m["parts"][0].get("text", "")
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": effective_prompt})

        # 5. Выполняем запрос с защитой от сбоев
        try:
            raw_reply = provider.generate(
                messages=messages,
                system_prompt=sys_prompt,
                temperature=temp,
                model_id=actual_model_id,
                on_status=on_status,
                user_id=user_id,
                **kwargs
            )
        except Exception as e:
            logger.warning(f"Ошибка провайдера {provider.name} ({actual_model_id}): {e}. Переключаюсь на каскад Gemini...")
            if on_status:
                on_status("⚠️ Ошибка внешнего провайдера. Мгновенный резервный переход на Gemini...")
            
            # Резервный вызов Gemini
            gemini_prov = self.providers["gemini"]
            raw_reply = gemini_prov.generate(
                messages=messages,
                system_prompt=sys_prompt,
                temperature=temp,
                model_id="gemini-3.5-flash",
                on_status=on_status,
                user_id=user_id,
            )
            fallback_banner = (
                f"🏛 *[Агент Гермес: сбой обращения к {actual_model_id} ({e.__class__.__name__}). Ответ получен через Gemini 3.5 Flash]*\n\n"
            )

        # 6. Собираем итоговый ответ
        final_reply = ""
        if fallback_banner:
            final_reply += fallback_banner
        elif route_notice and selected_user_model in ("auto-hermes", "hermes", "auto"):
            final_reply += route_notice

        final_reply += raw_reply

        # 7. Сохраняем в единую память SQLite
        add_message(user_id, "user", user_message)
        add_message(user_id, "model", final_reply)

        return final_reply


hermes_service = HermesOrchestrator()
