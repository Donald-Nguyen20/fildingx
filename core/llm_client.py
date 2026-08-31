# llm_client.py
import time
import requests
from typing import List, Tuple
from core.llm_config import (
    load_llm_config,
    DEFAULT_OLLAMA_MODEL, DEFAULT_OPENROUTER_MODEL,
    DEFAULT_GROQ_MODEL, DEFAULT_GEMINI_MODEL,
)

# Generation limits
_OLLAMA_NUM_PREDICT = 700
_OLLAMA_NUM_CTX     = 4096
_MAX_TOKENS_CHAT    = 900
_MAX_TOKENS_GEMINI  = 2048

# Provider keys used internally + labels shown in UI
PROVIDERS: List[Tuple[str, str]] = [
    ("ollama",      "Ollama (Local)"),
    ("openrouter",  "OpenRouter (Cloud)"),
    ("groq",        "Groq (Cloud)"),
    ("gemini",      "Gemini (Google)"),
]

class BaseLLMClient:
    def generate(self, prompt: str) -> str:
        raise NotImplementedError

class LLMClientOllama(BaseLLMClient):
    def __init__(self, model: str, host: str):
        self.model = model
        self.url_generate = f"{host.rstrip('/')}/api/generate"

    def generate(self, prompt: str) -> str:
        r = requests.post(
            self.url_generate,
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": _OLLAMA_NUM_PREDICT,
                    "num_ctx":     _OLLAMA_NUM_CTX,
                },
            },
            timeout=280,
        )
        r.raise_for_status()
        data = r.json()
        return (data.get("response") or "").strip()

class OpenAICompatibleChatClient(BaseLLMClient):
    def __init__(self, api_key: str, base_url: str, model: str, timeout: int = 180):
        if not api_key:
            raise ValueError("Missing API key.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": _MAX_TOKENS_CHAT,
        }
        r = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        msg = choices[0].get("message") or {}
        return (msg.get("content") or "").strip()

class LLMClientOpenRouter(OpenAICompatibleChatClient):
    def __init__(self, api_key: str, model: str):
        super().__init__(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            model=model,
            timeout=220,
        )

class LLMClientGroq(OpenAICompatibleChatClient):
    def __init__(self, api_key: str, model: str):
        super().__init__(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
            model=model,
            timeout=180,
        )

class LLMClientGemini(BaseLLMClient):
    """Google Gemini via REST API (không cần SDK)."""
    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model: str = DEFAULT_GEMINI_MODEL, timeout: int = 180):
        if not api_key:
            raise ValueError("Missing API key.")
        self.api_key = api_key
        self.model   = model
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        # The key goes in a header, not in the URL as "?key=". requests copies the
        # full URL into every HTTPError it raises, and callers show that text to
        # the user as-is -- so with the key in the URL, a plain 404 printed the
        # whole API key on screen. Google accepts either form; only one of them
        # keeps the key out of error messages, logs and proxy records.
        url = f"{self.BASE}/{self.model}:generateContent"
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": _MAX_TOKENS_GEMINI},
        }
        delays = [15, 30, 60]
        for attempt, wait in enumerate(delays + [None]):
            r = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            if r.status_code == 429 and wait is not None:
                time.sleep(wait)
                continue
            r.raise_for_status()
            break
        data = r.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError):
            return ""



def create_llm_client(provider_key: str, model_override: str = "") -> BaseLLMClient:
    cfg = load_llm_config()
    provider_key = (provider_key or "").strip().lower()
    model_override = (model_override or "").strip()

    if provider_key == "ollama":
        model = (model_override or cfg.get("ollama_model") or DEFAULT_OLLAMA_MODEL).strip()
        host = (cfg.get("ollama_host") or "http://localhost:11434").strip()
        return LLMClientOllama(model=model, host=host)

    if provider_key == "openrouter":
        api_key = (cfg.get("openrouter_api_key") or "").strip()
        model = model_override or cfg.get("openrouter_model", DEFAULT_OPENROUTER_MODEL)
        return LLMClientOpenRouter(api_key=api_key, model=model)

    if provider_key == "groq":
        api_key = (cfg.get("groq_api_key") or "").strip()
        model = model_override or cfg.get("groq_model", DEFAULT_GROQ_MODEL)
        return LLMClientGroq(api_key=api_key, model=model)

    if provider_key == "gemini":
        api_key = (cfg.get("gemini_api_key") or "").strip()
        model = model_override or cfg.get("gemini_model", DEFAULT_GEMINI_MODEL)
        return LLMClientGemini(api_key=api_key, model=model)

    # fallback
    model = (cfg.get("ollama_model") or DEFAULT_OLLAMA_MODEL).strip()
    host = (cfg.get("ollama_host") or "http://localhost:11434").strip()
    return LLMClientOllama(model=model, host=host)
