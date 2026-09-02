# llm_client.py
import time
import requests
from typing import List, Tuple
from core.llm_config import (
    load_llm_config,
    DEFAULT_OLLAMA_MODEL, DEFAULT_OPENROUTER_MODEL,
    DEFAULT_GROQ_MODEL, DEFAULT_GEMINI_MODEL,
)

# Generation limits.
#
# These budgets cover the model's *whole* output, and on a reasoning model the
# private thinking is spent out of the same pot before a single visible
# character is written. The replacements for the withdrawn models -- gpt-oss
# and Gemini 3.x -- both reason by default, and the old budgets left them
# nothing to answer with: on the AI grouping prompt gpt-oss burned all 900
# tokens thinking and returned an empty string, while Gemini spent 1962 of its
# 2048 and got cut off mid-line. Grouping looked like it had gotten worse; in
# fact it was never seeing a complete reply. Measured need on that prompt is
# ~1600-3400 tokens for gpt-oss and ~2900 total for Gemini.
#
# The chat ceiling cannot simply be set generously, though: Groq's free tier
# allows 8000 tokens a minute and reserves prompt + max_tokens against that
# budget up front, so an over-large ceiling is refused outright with HTTP 413
# on exactly the big result sets that need it most. 4000 covers a 40-file
# grouping prompt with room to spare. A full 100-file one it does not: that
# prompt alone is ~2000 tokens, and gpt-oss wants more thinking than the
# remaining ~6000 the tier would allow -- 100-file grouping is simply past
# what this model and tier can do together, and it now says so and hands the
# job to Gemini instead of returning half a grouping. Gemini is not metered
# this way and finishes the same prompt inside its own ceiling.
_OLLAMA_NUM_PREDICT = 700
_OLLAMA_NUM_CTX     = 4096
_MAX_TOKENS_CHAT    = 4000
_MAX_TOKENS_GEMINI  = 6000

# Gemini 3.x grows its thinking to fill whatever budget it is given, so raising
# the ceiling alone does not help it -- the level has to be asked for directly.
# Older Gemini models do not know this field, hence the one-shot retry below.
_GEMINI_THINKING_LEVEL = "low"

# Provider keys used internally + labels shown in UI
PROVIDERS: List[Tuple[str, str]] = [
    ("ollama",      "Ollama (Local)"),
    ("openrouter",  "OpenRouter (Cloud)"),
    ("groq",        "Groq (Cloud)"),
    ("gemini",      "Gemini (Google)"),
]

class BaseLLMClient:
    # Set by generate() when the model stopped because it hit the token
    # ceiling rather than because it had finished speaking. A cut-off reply is
    # still a non-empty string, so callers that only test for emptiness accept
    # half an answer as a whole one -- this is the only way to tell them apart.
    last_truncated = False

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
        self.last_truncated = data.get("done_reason") == "length"
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
        self.last_truncated = choices[0].get("finish_reason") == "length"
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
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": _MAX_TOKENS_GEMINI,
                "thinkingConfig": {"thinkingLevel": _GEMINI_THINKING_LEVEL},
            },
        }
        delays = [15, 30, 60]
        for attempt, wait in enumerate(delays + [None]):
            r = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            # thinkingConfig only exists from Gemini 3 on. If the configured
            # model predates it the request is rejected outright, so drop the
            # field and repeat this same attempt -- a tuning hint the model has
            # never heard of should not cost a call or a rate-limit retry.
            if r.status_code == 400 and "thinkingConfig" in payload["generationConfig"]:
                payload["generationConfig"].pop("thinkingConfig")
                r = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            if r.status_code == 429 and wait is not None:
                time.sleep(wait)
                continue
            r.raise_for_status()
            break
        data = r.json()
        try:
            candidate = data["candidates"][0]
        except (KeyError, IndexError):
            return ""
        self.last_truncated = candidate.get("finishReason") == "MAX_TOKENS"
        try:
            parts = candidate["content"]["parts"]
        except KeyError:
            return ""
        # A reasoning model may return its thinking as parts of the same reply,
        # flagged with "thought", and may split the answer itself across
        # several parts. Reading parts[0] alone could hand back a fragment --
        # or the thinking instead of the answer.
        answer = "".join(
            p.get("text", "") for p in parts if not p.get("thought")
        )
        return answer.strip()



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

    # An unrecognised provider used to fall through to Ollama. That turned a
    # typo in the config into a connection error against localhost, which
    # names the wrong problem entirely -- nothing is wrong with Ollama, the
    # provider key is simply not one of the four. Say which key was given and
    # what the valid ones are; every caller already reports the exception.
    valid = ", ".join(key for key, _label in PROVIDERS)
    raise ValueError(
        f"Unknown LLM provider {provider_key!r}. Choose one of: {valid} "
        "-- set it in ⚙ LLM Settings."
    )
