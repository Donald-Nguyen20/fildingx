"""core/ai_grouper.py — AI-powered grouping of file search results."""
from __future__ import annotations

import re

from PySide6.QtCore import QThread, Signal

_MAX_FILES = 100  # cap to avoid token overflow
_LINE_RE = re.compile(
    r"^\s*(?:[-*]|\d+[\.)])?\s*(GROUP|DUPE)\s*:\s*(.*?)\s*\|\s*([^|]+?)\s*$",
    re.IGNORECASE,
)
_INDEX_RE = re.compile(r"\d+")


def _build_prompt(filenames: list[str]) -> str:
    indexed = "\n".join(f"{i}: {n}" for i, n in enumerate(filenames))
    return (
        "You are a document librarian for a power plant.\n"
        f"Below are {len(filenames)} files from a search result (0-indexed):\n\n"
        f"{indexed}\n\n"
        "Instructions:\n"
        "1. Group files into logical categories based on document type or subject "
        "(e.g. Training Material, O&M Manual, P&ID, Procedure, Drawing, Specification, "
        "Commissioning, Calculation, etc.).\n"
        "2. Identify sets that appear to be multiple revisions of the same document "
        "(same document number, different revision codes like rev.A / rev.01 / Rev.AB0).\n\n"
        "Reply ONLY using these exact line formats -- no explanation, no numbering:\n"
        "GROUP: <Category Name> | <comma-separated indices>\n"
        "DUPE: <Base Document Name> | <comma-separated indices>\n\n"
        "Example:\n"
        "GROUP: Training Material | 0,1,5\n"
        "GROUP: O&M Manual | 2,3,4\n"
        "DUPE: VP1-C-L1-P-SG-30110 | 6,7,8\n"
    )


def _parse_response(text: str, filenames: list[str]) -> dict:
    groups: list[dict] = []
    dupes: list[dict] = []
    assigned: set[int] = set()

    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("```"):
            continue
        match = _LINE_RE.match(line)
        if not match:
            continue
        kind = match.group(1).upper()
        label = match.group(2).strip()
        indices = []
        for tok in _INDEX_RE.findall(match.group(3)):
            idx = int(tok)
            if 0 <= idx < len(filenames) and idx not in indices:
                indices.append(idx)
        if not indices:
            continue
        files = [(filenames[i], i) for i in indices]
        if kind == "GROUP":
            groups.append({"label": label, "files": files})
            assigned.update(indices)
        elif kind == "DUPE" and len(files) > 1:
            dupes.append({"base": label, "files": files})

    ungrouped = [(filenames[i], i) for i in range(len(filenames)) if i not in assigned]
    if ungrouped:
        groups.append({"label": "Other / Unclassified", "files": ungrouped})

    return {"groups": groups, "dupes": dupes}


class GroupWorker(QThread):
    done  = Signal(dict)
    error = Signal(str)

    def __init__(self, file_pairs: list[tuple[str, str]], provider: str):
        super().__init__()
        self._pairs    = file_pairs[:_MAX_FILES]
        self._provider = provider

    def run(self):
        try:
            from core.llm_client import create_llm_client
            filenames = [n for n, _ in self._pairs]
            prompt = _build_prompt(filenames)
            errors: list[str] = []
            response = ""
            for provider in self._provider_order():
                try:
                    client = create_llm_client(provider)
                    response = client.generate(prompt)
                    if response.strip():
                        break
                    errors.append(f"{provider}: empty response")
                except Exception as exc:
                    errors.append(f"{provider}: {exc}")
            else:
                raise RuntimeError("; ".join(errors) or "No LLM provider returned a response.")
            result    = _parse_response(response, filenames)
            result["pairs"] = self._pairs
            self.done.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))

    def _provider_order(self) -> list[str]:
        from core.llm_config import load_llm_config

        cfg = load_llm_config()
        selected = (self._provider or "gemini").strip().lower()
        order = [selected, "gemini", "groq", "openrouter", "ollama"]
        seen: set[str] = set()
        available: list[str] = []
        for provider in order:
            if provider in seen:
                continue
            seen.add(provider)
            if provider == "gemini" and not (cfg.get("gemini_api_key") or "").strip():
                continue
            if provider == "groq" and not (cfg.get("groq_api_key") or "").strip():
                continue
            if provider == "openrouter" and not (cfg.get("openrouter_api_key") or "").strip():
                continue
            available.append(provider)
        return available or [selected]
