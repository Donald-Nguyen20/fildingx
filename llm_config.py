# llm_config.py
import json, os, sys
from typing import Dict, Any
from pathlib import Path

DEFAULT_CONFIG = {
    "openrouter_api_key": "",
    "groq_api_key": "",
    "ollama_host": "http://localhost:11434",
    "ollama_model": "llama3.1:8b",
    "openrouter_model": "meta-llama/llama-3.3-70b-instruct:free",
    "groq_model": "llama-3.3-70b-versatile",
}

CONFIG_NAME = "llm_config.json"



def get_config_path() -> str:

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.argv[0]).resolve().parent
        return str(exe_dir / CONFIG_NAME)

    # dev
    base_dir = Path(__file__).resolve().parent
    return str(base_dir / CONFIG_NAME)


def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    # nếu folder không ghi được -> sẽ raise PermissionError
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def load_llm_config() -> Dict[str, Any]:
    path = get_config_path()

    # chưa có -> tạo mới ngay cạnh app
    if not os.path.exists(path):
        try:
            _atomic_write_json(path, dict(DEFAULT_CONFIG))
        except Exception:
            # không tạo được (thường do permission) -> trả default để app vẫn chạy
            return dict(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        # file hỏng JSON / bị lock / encoding lỗi -> trả default (và có thể tự sửa lại)
        return dict(DEFAULT_CONFIG)

    cfg = dict(DEFAULT_CONFIG)
    if isinstance(data, dict):
        cfg.update({k: v for k, v in data.items() if k in cfg})
    return cfg


def save_llm_config(cfg: Dict[str, Any]) -> None:
    path = get_config_path()
    safe = dict(DEFAULT_CONFIG)
    safe.update({k: cfg.get(k, safe[k]) for k in safe.keys()})

    # có -> ghi đè, chưa có -> tạo mới
    _atomic_write_json(path, safe)
