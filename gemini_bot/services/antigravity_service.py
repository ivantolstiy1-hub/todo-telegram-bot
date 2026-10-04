import os
import json
import time
import subprocess
import logging
import re
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

AGENTAPI_PATH = Path("/Users/alenaserduk/.gemini/antigravity/bin/agentapi")
BRAIN_DIR = Path("/Users/alenaserduk/.gemini/antigravity/brain")

def normalize_agent_model(model_name: str) -> str:
    """Нормализует имя модели к поддерживаемым agentapi tier: flash_lite, flash, pro"""
    m = (model_name or "flash").lower()
    if "pro" in m:
        return "pro"
    if "lite" in m:
        return "flash_lite"
    return "flash"

class AntigravityAgentService:
    def __init__(self, agentapi_bin: Path = AGENTAPI_PATH, brain_dir: Path = BRAIN_DIR):
        self.agentapi_bin = agentapi_bin
        self.brain_dir = brain_dir
        self._ls_addr: Optional[str] = None
        self._csrf_token: Optional[str] = None

    def _discover_ls_env(self) -> dict:
        env = os.environ.copy()
        
        # 1. Проверяем окружение
        if env.get("ANTIGRAVITY_LS_ADDRESS") and env.get("ANTIGRAVITY_CSRF_TOKEN"):
            env["ANTIGRAVITYLSADDRESS"] = env["ANTIGRAVITY_LS_ADDRESS"]
            return env

        # 2. Проверяем кэш
        if self._ls_addr and self._csrf_token:
            env["ANTIGRAVITY_LS_ADDRESS"] = self._ls_addr
            env["ANTIGRAVITYLSADDRESS"] = self._ls_addr
            env["ANTIGRAVITY_CSRF_TOKEN"] = self._csrf_token
            return env

        # 3. Авто-обнаружение процесса language_server
        try:
            res = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
            pid = None
            csrf_token = None
            for line in res.stdout.splitlines():
                if "language_server" in line and "--csrf_token" in line:
                    parts = line.split()
                    pid = parts[1]
                    m = re.search(r'--csrf_token\s+([^\s]+)', line) or re.search(r'--csrf_token=([^\s]+)', line)
                    if m:
                        csrf_token = m.group(1)
                    break

            if pid and csrf_token:
                lsof_res = subprocess.run(["lsof", "-nP", "-p", pid], capture_output=True, text=True, timeout=5)
                ports = []
                for line in lsof_res.stdout.splitlines():
                    if "LISTEN" in line and "127.0.0.1:" in line:
                        m = re.search(r'127\.0\.0\.1:(\d+)', line)
                        if m:
                            ports.append(int(m.group(1)))
                if ports:
                    ls_addr = f"localhost:{max(ports)}"
                    self._ls_addr = ls_addr
                    self._csrf_token = csrf_token
                    env["ANTIGRAVITY_LS_ADDRESS"] = ls_addr
                    env["ANTIGRAVITYLSADDRESS"] = ls_addr
                    env["ANTIGRAVITY_CSRF_TOKEN"] = csrf_token
                    logger.info(f"Авто-обнаружен Antigravity Language Server: {ls_addr}")
                    return env
        except Exception as e:
            logger.warning(f"Не удалось обнаружить Antigravity Language Server: {e}")

        return env

    def is_available(self) -> bool:
        """Проверяет, доступен ли бинарник agentapi в системе."""
        return self.agentapi_bin.exists() and os.access(self.agentapi_bin, os.X_OK)

    def _get_transcript_path(self, conversation_id: str) -> Path:
        return self.brain_dir / conversation_id / ".system_generated" / "logs" / "transcript.jsonl"

    def _read_transcript_lines(self, conversation_id: str) -> list[dict]:
        path = self._get_transcript_path(conversation_id)
        if not path.exists():
            return []
        lines = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            lines.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.warning(f"Ошибка чтения transcript {conversation_id}: {e}")
        return lines

    def _extract_error(self, res: subprocess.CompletedProcess) -> str:
        """Извлекает текст ошибки из stderr или stdout (JSON) agentapi."""
        err_msg = res.stderr.strip() if res.stderr else ""
        if not err_msg and res.stdout:
            try:
                err_data = json.loads(res.stdout)
                err_msg = err_data.get("error", res.stdout.strip())
            except Exception:
                err_msg = res.stdout.strip()
        return err_msg or "неизвестная ошибка"

    def create_conversation(
        self,
        initial_prompt: str,
        model: str = "flash",
        title: Optional[str] = None,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> tuple[str, str]:
        """
        Создает новую сессию агента Antigravity через agentapi new-conversation.
        Возвращает (conversation_id, initial_agent_reply).
        """
        tier = normalize_agent_model(model)
        model_flag = f"--model={tier}"
        cmd = [str(self.agentapi_bin), "new-conversation", model_flag]
        if title:
            cmd.append(f"--title={title}")
        cmd.append(initial_prompt)
        
        max_retries = 2
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                res = subprocess.run(cmd, env=self._discover_ls_env(), capture_output=True, text=True, timeout=180)
                if res.returncode != 0:
                    err_text = self._extract_error(res)
                    if ("quota" in err_text.lower() or "exhausted" in err_text.lower() or "rate" in err_text.lower()) and attempt < max_retries:
                        if on_progress:
                            on_progress("⏳ Квота агента временно исчерпана, повторная попытка через 5 сек...")
                        time.sleep(5)
                        continue
                    raise RuntimeError(f"agentapi error: {err_text}")
                
                data = json.loads(res.stdout)
                conv_id = data["response"]["newConversation"]["conversationId"]
                break
            except subprocess.TimeoutExpired:
                logger.error("Таймаут при создании разговора через agentapi (180 сек)")
                raise RuntimeError("⏳ Превышено время инициализации агента Antigravity (таймаут 180 сек). Повторите запрос.")
            except Exception as e:
                last_error = e
                if attempt < max_retries and ("quota" in str(e).lower() or "exhausted" in str(e).lower()):
                    time.sleep(5)
                    continue
                logger.error(f"Не удалось создать разговор через agentapi: {e}")
                raise RuntimeError(f"Ошибка запуска Antigravity Agent: {e}")

        # Ожидаем первый ответ агента
        reply = self._wait_for_response(conv_id, start_step_index=0, on_progress=on_progress, timeout=180)
        return conv_id, reply

    def send_message(
        self,
        conversation_id: str,
        content: str,
        on_progress: Optional[Callable[[str], None]] = None,
        timeout: int = 120
    ) -> str:
        """
        Отправляет задачу в существующий диалог Antigravity и дожидается ответа.
        """
        # Считаем текущее количество шагов в transcript перед отправкой
        existing_lines = self._read_transcript_lines(conversation_id)
        last_step_index = len(existing_lines) - 1 if existing_lines else -1

        cmd = [str(self.agentapi_bin), "send-message", conversation_id, content]
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                res = subprocess.run(cmd, env=self._discover_ls_env(), capture_output=True, text=True, timeout=180)
                if res.returncode != 0:
                    err_text = self._extract_error(res)
                    if ("quota" in err_text.lower() or "exhausted" in err_text.lower() or "rate" in err_text.lower()) and attempt < max_retries:
                        if on_progress:
                            on_progress("⏳ Квота запросов агента исчерпана, ожидаю 5с...")
                        time.sleep(5)
                        continue
                    raise RuntimeError(f"agentapi send-message error: {err_text}")
                break
            except Exception as e:
                if attempt < max_retries and ("quota" in str(e).lower() or "exhausted" in str(e).lower()):
                    time.sleep(5)
                    continue
                logger.error(f"Ошибка отправки сообщения через agentapi: {e}")
                raise RuntimeError(f"Ошибка обращения к Antigravity: {e}")

        # Ожидаем ответ агента
        return self._wait_for_response(
            conversation_id,
            start_step_index=last_step_index,
            on_progress=on_progress,
            timeout=timeout
        )

    def _wait_for_response(
        self,
        conversation_id: str,
        start_step_index: int = -1,
        on_progress: Optional[Callable[[str], None]] = None,
        timeout: int = 120
    ) -> str:
        """
        Отслеживает transcript.jsonl и ждет финальный ответ модели.
        """
        start_time = time.time()
        final_answer = ""
        last_notified_action = ""

        while time.time() - start_time < timeout:
            lines = self._read_transcript_lines(conversation_id)
            
            # Просматриваем новые шаги после start_step_index
            for entry in lines:
                step_idx = entry.get("step_index", 0)
                if step_idx <= start_step_index:
                    continue

                source = entry.get("source")
                step_type = entry.get("type")
                
                # Если модель вызывает инструмент
                if source == "MODEL" and step_type == "PLANNER_RESPONSE":
                    tool_calls = entry.get("tool_calls", [])
                    if tool_calls and on_progress:
                        for tc in tool_calls:
                            action = tc.get("args", {}).get("toolAction") or tc.get("args", {}).get("toolSummary") or tc.get("name")
                            if action and action != last_notified_action:
                                last_notified_action = action
                                clean_action = str(action).replace('"', '')
                                on_progress(f"🛠 *Выполняю:* {clean_action}")

                    # Проверяем, есть ли готовый текстовый ответ для пользователя
                    content = entry.get("content", "").strip()
                    if content and not tool_calls:
                        final_answer = content

            if final_answer:
                return final_answer

            time.sleep(1.0)

        if final_answer:
            return final_answer
        raise TimeoutError("⏳ Время ожидания ответа агента Antigravity истекло (таймаут).")

antigravity_service = AntigravityAgentService()
