"""core/ai_grouper.py — group file search results.

The job splits cleanly in two, and the halves want opposite tools.

Which files are copies of one document is a *fact*, written into the filename
by the plant's naming convention. Measured over 40 real results, a model asked
to work it out returned 12 sets one run and 10 the next, and named the same
document two different ways; reading the number off the name finds the same
sets every time, in no measurable time, offline. So that half no longer goes
near a model -- see core/doc_naming.py.

What each document is *about* is not in the name. "Electrical" is; "Cable
Schedule" is not. That half is what a model is genuinely better at, and it is
now all it is asked for -- a shorter prompt, less to drift from, and the token
ceiling that used to cut 100-file groupings short is far less likely to bite.

Because the deterministic half needs no network, grouping no longer fails
outright when no provider answers: it falls back to labelling by discipline and
says so, rather than showing nothing.
"""
from __future__ import annotations

import re

from PySide6.QtCore import QThread, Signal

from core.doc_naming import UNCLASSIFIED, classify, duplicate_sets

_MAX_FILES = 100  # cap to avoid token overflow
# DUPE lines are no longer requested; a model that emits them anyway is simply
# ignored here, since duplicate_sets() has already answered that question.
_LINE_RE = re.compile(
    r"^\s*(?:[-*]|\d+[\.)])?\s*GROUP\s*:\s*(.*?)\s*\|\s*([^|]+?)\s*$",
    re.IGNORECASE,
)
_INDEX_RE = re.compile(r"\d+")


def _short_reason(exc: Exception) -> str:
    """Turn a provider failure into one phrase fit to show a user.

    The raw text is a network library's, written for whoever is reading a
    stack trace: a connection refused arrives as four nested exceptions and a
    WinError number. Shown in a dialog it says nothing useful and buries the
    one fact that matters -- which of the four common things went wrong. The
    full text still goes into the error path when every provider fails.
    """
    text = str(exc)
    lowered = text.lower()
    if "newconnectionerror" in lowered or "max retries exceeded" in lowered:
        return "is not reachable (is it running?)"
    if "timed out" in lowered or "timeout" in lowered:
        return "timed out"
    if "404" in text:
        return "has no such model (404) — check ⚙ LLM Settings"
    if "401" in text or "403" in text:
        return "rejected the API key"
    if "429" in text or "413" in text:
        return "is rate-limited — wait a minute, or group fewer results"
    if "missing api key" in lowered:
        return "has no API key set"
    if "unknown llm provider" in lowered:
        return "is not a valid provider name — check ⚙ LLM Settings"
    return f"failed: {text[:70]}" + ("…" if len(text) > 70 else "")


def _target_group_count(count: int) -> int:
    """How many categories to ask for.

    Left to itself the same model gave 18 categories for 40 files on one run
    and 19 on the next, splitting "Instrument Schedules" into two nearly
    identical headings -- two files per group is a list, not a grouping.
    Naming a target costs one line of prompt and holds the shape steady.
    """
    return max(4, min(12, round(count / 5)))


def _build_prompt(filenames: list[str]) -> str:
    indexed = "\n".join(f"{i}: {n}" for i, n in enumerate(filenames))
    target = _target_group_count(len(filenames))
    return (
        "You are a document librarian for a power plant.\n"
        f"Below are {len(filenames)} files from a search result (0-indexed):\n\n"
        f"{indexed}\n\n"
        "Group them by what each document IS or is ABOUT -- for example "
        "Cable Schedule, P&ID, Commissioning Procedure, O&M Manual, "
        "Instrument List, Training Material, Test Report.\n"
        "Rules:\n"
        f"1. Aim for about {target} categories. Prefer broad, reusable names; "
        "do not create a category for a single file unless nothing else fits.\n"
        "2. Every file must appear in exactly one category.\n"
        "3. Do not report revisions or duplicates — those are handled "
        "separately.\n\n"
        "Reply ONLY with lines in this exact format, nothing else:\n"
        "GROUP: <Category Name> | <comma-separated indices>\n\n"
        "Example:\n"
        "GROUP: Commissioning Procedure | 0,1,5\n"
        "GROUP: O&M Manual | 2,3,4\n"
    )


def _parse_groups(text: str, filenames: list[str]) -> tuple[list[dict], list[int]]:
    """Read the model's reply. Returns (groups, indices it never mentioned)."""
    groups: list[dict] = []
    assigned: set[int] = set()

    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("```"):
            continue
        match = _LINE_RE.match(line)
        if not match:
            continue
        label = match.group(1).strip()
        indices: list[int] = []
        for token in _INDEX_RE.findall(match.group(2)):
            index = int(token)
            # A file claimed by two categories belongs to the first; the second
            # claim is dropped rather than duplicating the row on screen.
            if 0 <= index < len(filenames) and index not in assigned:
                indices.append(index)
                assigned.add(index)
        if not indices or not label:
            continue
        groups.append({"label": label, "files": [(filenames[i], i) for i in indices]})

    unassigned = [i for i in range(len(filenames)) if i not in assigned]
    return groups, unassigned


def _offline_groups(filenames: list[str], indices: list[int]) -> list[dict]:
    """Label files from their names alone -- the fallback that always works."""
    buckets: dict[str, list[tuple[str, int]]] = {}
    for index in indices:
        buckets.setdefault(classify(filenames[index]), []).append(
            (filenames[index], index)
        )
    # Biggest first, with the give-up bucket last wherever it lands.
    ordered = sorted(
        buckets.items(), key=lambda kv: (kv[0] == UNCLASSIFIED, -len(kv[1]), kv[0])
    )
    return [{"label": label, "files": files} for label, files in ordered]


def _merge_groups(groups: list[dict], extra: list[dict]) -> list[dict]:
    """Fold offline labels into the model's, so one name means one heading."""
    merged = [dict(group) for group in groups]
    by_label = {group["label"].strip().lower(): group for group in merged}
    for group in extra:
        existing = by_label.get(group["label"].strip().lower())
        if existing:
            existing["files"] = existing["files"] + group["files"]
        else:
            merged.append(dict(group))
            by_label[group["label"].strip().lower()] = merged[-1]
    return merged


class GroupWorker(QThread):
    done  = Signal(dict)
    error = Signal(str)

    def __init__(self, file_pairs: list[tuple[str, str]], provider: str):
        super().__init__()
        self._pairs    = file_pairs[:_MAX_FILES]
        self._dropped  = max(0, len(file_pairs) - _MAX_FILES)
        self._provider = provider
        self._selected = (provider or "gemini").strip().lower()

    def run(self):
        try:
            filenames = [name for name, _path in self._pairs]
            # Facts first, and without a network: whatever the model does or
            # fails to do afterwards, this part of the answer is already right.
            revisions, copies = duplicate_sets(filenames)
            outcome = self._ask_model(filenames)
            groups = outcome["groups"]
            if outcome["unassigned"]:
                groups = _merge_groups(
                    groups, _offline_groups(filenames, outcome["unassigned"])
                )
            note, alert = self._build_note(outcome)
            self.done.emit({
                "groups":  groups,
                "dupes":   revisions,
                "copies":  copies,
                "pairs":   self._pairs,
                "offline": not outcome["used"],
                "note":    note,
                "alert":   alert,
            })
        except Exception as exc:
            self.error.emit(str(exc))

    def _ask_model(self, filenames: list[str]) -> dict:
        """Ask a model for subject labels.

        Never raises. A provider failing is an outcome, not an error: the
        deterministic half of the grouping stands either way, so the caller
        shows what it has and reports what was missing.
        """
        from core.llm_client import create_llm_client

        prompt = _build_prompt(filenames)
        reasons: dict[str, str] = {}
        for provider in self._provider_order():
            try:
                client = create_llm_client(provider)
                response = client.generate(prompt)
                if not response.strip():
                    reasons[provider] = "returned nothing (token limit reached)"
                    continue
                groups, unassigned = _parse_groups(response, filenames)
                if not groups:
                    reasons[provider] = "replied in an unusable format"
                    continue
                return {
                    "groups":     groups,
                    "unassigned": unassigned,
                    "used":       provider,
                    "truncated":  client.last_truncated,
                    "reasons":    reasons,
                }
            except Exception as exc:
                reasons[provider] = _short_reason(exc)
        return {
            "groups":     [],
            "unassigned": list(range(len(filenames))),
            "used":       "",
            "truncated":  False,
            "reasons":    reasons,
        }

    def _build_note(self, outcome: dict) -> tuple[str, bool]:
        """Say so when the result is not the one the user asked for.

        Three things used to happen silently. Results past the hundredth were
        dropped, the chosen provider could fail and another answer in its
        place, and a reply could be cut off at the token ceiling yet still
        parse into a plausible-looking set of groups. In every case the user
        was shown a result with no hint that it was partial.

        Returns the text and whether it deserves interrupting for. Anything
        that changes which files are on screen, or answers with a model the
        user did not choose, is worth a dialog; a handful of files the model
        skipped is worth a line in the status bar and nothing more. Making
        every note modal would train the habit of dismissing all of them.
        """
        used = outcome["used"]
        notes: list[str] = []
        alert = False

        if self._dropped:
            alert = True
            notes.append(
                f"⚠ Only the first {len(self._pairs)} results were grouped; "
                f"{self._dropped} more were left out. Narrow the search to "
                "include them."
            )
        if not used:
            alert = True
            why = "; ".join(f"{name} {reason}" for name, reason in outcome["reasons"].items())
            notes.append(
                "⚠ No AI provider answered"
                + (f" ({why})" if why else "")
                + " — grouped offline from file names only, so categories are "
                "by discipline rather than by subject. Duplicates and revisions "
                "are unaffected."
            )
        elif used != self._selected:
            alert = True
            reason = outcome["reasons"].get(self._selected, "was unavailable")
            notes.append(f"⚠ {self._selected} {reason} — grouped with {used} instead.")

        if outcome["truncated"]:
            alert = True
            notes.append(
                f"⚠ {used or 'model'} hit its token limit — the reply was cut off, "
                "so some files fell back to offline labels. Try fewer results, or "
                "a larger token budget."
            )
        skipped = len(outcome["unassigned"]) if used else 0
        if skipped:
            notes.append(
                f"{skipped} file(s) the model did not place were labelled from "
                "their file names."
            )
        return " ".join(notes), alert

    def _provider_order(self) -> list[str]:
        from core.llm_config import load_llm_config

        cfg = load_llm_config()
        order = [self._selected, "gemini", "groq", "openrouter", "ollama"]
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
        return available or [self._selected]
