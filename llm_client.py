# llm_client.py
import requests
from typing import List, Tuple
from llm_config import load_llm_config

# Provider keys used internally + labels shown in UI
PROVIDERS: List[Tuple[str, str]] = [
    ("ollama", "Ollama (Local)"),
    ("openrouter", "OpenRouter (Cloud)"),
    ("groq", "Groq (Cloud)"),
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
                    "num_predict": 700,
                    "num_ctx": 4096,
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
            "max_tokens": 900,
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



def create_llm_client(provider_key: str, model_override: str = "") -> BaseLLMClient:
    cfg = load_llm_config()
    provider_key = (provider_key or "").strip().lower()
    model_override = (model_override or "").strip()

    if provider_key == "ollama":
        model = (model_override or cfg.get("ollama_model") or "llama3.1:8b").strip()
        host = (cfg.get("ollama_host") or "http://localhost:11434").strip()
        return LLMClientOllama(model=model, host=host)

    if provider_key == "openrouter":
        api_key = (cfg.get("openrouter_api_key") or "").strip()
        model = model_override or cfg["openrouter_model"]
        return LLMClientOpenRouter(api_key=api_key, model=model)

    if provider_key == "groq":
        api_key = (cfg.get("groq_api_key") or "").strip()
        model = model_override or cfg["groq_model"]
        return LLMClientGroq(api_key=api_key, model=model)


    # fallback
    model = (cfg.get("ollama_model") or "llama3.1:8b").strip()
    host = (cfg.get("ollama_host") or "http://localhost:11434").strip()
    return LLMClientOllama(model=model, host=host)
