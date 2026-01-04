# llm_config.py
import json, os
from typing import Dict, Any

DEFAULT_CONFIG = {
    "openrouter_api_key": "",
    "groq_api_key": "",
    "gemini_api_key": "",

    "ollama_host": "http://localhost:11434",
    "ollama_model": "llama3.2:3b",

    "openrouter_model": "meta-llama/llama-3.3-70b-instruct:free",
    "groq_model": "llama-3.3-70b-versatile",
    "gemini_model": "gemini-1.5-flash",
}

def get_config_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "llm_config.json")

def load_llm_config() -> Dict[str, Any]:
    path = get_config_path()
    if not os.path.exists(path):
        return dict(DEFAULT_CONFIG)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = dict(DEFAULT_CONFIG)
        cfg.update({k: v for k, v in data.items() if k in cfg})
        return cfg
    except Exception:
        return dict(DEFAULT_CONFIG)

def save_llm_config(cfg: Dict[str, Any]) -> None:
    path = get_config_path()
    safe = dict(DEFAULT_CONFIG)
    safe.update({k: cfg.get(k, safe[k]) for k in safe.keys()})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(safe, f, ensure_ascii=False, indent=2)
