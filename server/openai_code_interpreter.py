"""Server-only OpenAI Code Interpreter adapter for PORTAL.

No OpenAI credential is accepted from an HTTP request or client build. The API
key is read only from the server environment.
"""
from dataclasses import dataclass, field
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.4-mini"
ALLOWED_MEMORY = {"1g", "4g", "16g", "64g"}
MAX_PROMPT_CHARS = 12000
DEFAULT_TIMEOUT_SECONDS = 180


class CodeInterpreterUnavailable(RuntimeError):
    """The feature is intentionally disabled or not configured."""


class CodeInterpreterRemoteError(RuntimeError):
    """OpenAI could not complete the request; details are intentionally sanitized."""


@dataclass(frozen=True)
class Settings:
    enabled: bool
    model: str
    memory_limit: str
    timeout_seconds: int
    api_key: str = field(repr=False, default="")


def _bool(value, name):
    raw = str(value).strip().lower()
    if raw not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return raw == "true"


def load_settings(env=None):
    env = os.environ if env is None else env
    enabled = _bool(env.get("PORTAL_CODE_INTERPRETER_ENABLED", "false"),
                    "PORTAL_CODE_INTERPRETER_ENABLED")
    model = str(env.get("PORTAL_CODE_INTERPRETER_MODEL", DEFAULT_MODEL)).strip()
    if not model or len(model) > 100 or not re.fullmatch(r"[A-Za-z0-9._:-]+", model):
        raise ValueError("Invalid PORTAL_CODE_INTERPRETER_MODEL")
    memory = str(env.get("PORTAL_CODE_INTERPRETER_MEMORY", "1g")).strip().lower()
    if memory not in ALLOWED_MEMORY:
        raise ValueError("PORTAL_CODE_INTERPRETER_MEMORY must be one of 1g, 4g, 16g, 64g")
    try:
        timeout = int(env.get("PORTAL_CODE_INTERPRETER_TIMEOUT_SECONDS",
                              str(DEFAULT_TIMEOUT_SECONDS)))
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid PORTAL_CODE_INTERPRETER_TIMEOUT_SECONDS") from exc
    if not 30 <= timeout <= 600:
        raise ValueError("PORTAL_CODE_INTERPRETER_TIMEOUT_SECONDS must be 30..600")
    return Settings(
        enabled=enabled,
        model=model,
        memory_limit=memory,
        timeout_seconds=timeout,
        api_key=str(env.get("OPENAI_API_KEY", "")).strip(),
    )


def public_status(env=None):
    settings = load_settings(env)
    return {
        "enabled": settings.enabled,
        "configured": bool(settings.api_key),
        "model": settings.model,
        "memory_limit": settings.memory_limit,
        "network_access": False,
        "store_responses": False,
        "max_prompt_chars": MAX_PROMPT_CHARS,
    }


def _extract_text(payload):
    texts = []
    for item in payload.get("output") or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                texts.append(content["text"])
    return "\n".join(texts).strip()


def _container_id(payload):
    for item in payload.get("output") or []:
        if item.get("type") == "code_interpreter_call":
            value = item.get("container_id") or item.get("container")
            if isinstance(value, str):
                return value
    return None


def _request_payload(prompt, settings):
    return {
        "model": settings.model,
        "store": False,
        "tool_choice": "required",
        "instructions": (
            "Ты внутренний AI-аналитик PORTAL. Отвечай на русском языке. "
            "Для расчётов и анализа используй python tool. Не проси и не раскрывай "
            "пароли, токены, API-ключи или другие секреты. Не делай сетевые запросы. "
            "Работай только с данными, которые пользователь явно передал в этом запросе."
        ),
        "input": prompt,
        "tools": [{
            "type": "code_interpreter",
            "container": {
                "type": "auto",
                "memory_limit": settings.memory_limit,
                "network_policy": {"type": "disabled"},
            },
        }],
    }


def run(prompt, env=None, opener=urlopen):
    settings = load_settings(env)
    if not settings.enabled:
        raise CodeInterpreterUnavailable("Code Interpreter отключён оператором PORTAL")
    if not settings.api_key:
        raise CodeInterpreterUnavailable("OPENAI_API_KEY не настроен на сервере PORTAL")
    if not isinstance(prompt, str):
        raise ValueError("Запрос должен быть текстом")
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("Введите запрос для AI-аналитика")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError(f"Запрос слишком длинный; максимум {MAX_PROMPT_CHARS} символов")

    raw = json.dumps(_request_payload(prompt, settings),
                     ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(
        RESPONSES_URL,
        data=raw,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "PORTAL-CodeInterpreter/1.0",
        },
    )
    try:
        with opener(request, timeout=settings.timeout_seconds) as response:
            body = response.read()
    except HTTPError as exc:
        raise CodeInterpreterRemoteError(
            f"OpenAI API отклонил запрос (HTTP {exc.code})"
        ) from None
    except (URLError, TimeoutError, OSError):
        raise CodeInterpreterRemoteError("OpenAI API временно недоступен") from None

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CodeInterpreterRemoteError("OpenAI API вернул некорректный ответ") from None
    text = _extract_text(payload)
    if not text:
        raise CodeInterpreterRemoteError("OpenAI Code Interpreter не вернул текстовый результат")
    return {
        "text": text,
        "response_id": payload.get("id"),
        "model": payload.get("model") or settings.model,
        "container_id": _container_id(payload),
    }
