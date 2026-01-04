"""
Function module: percent_exclude_search.py

Syntax:
- "A%B"  => include keyword A, but EXCLUDE keyword B (both checked on filename).

Upgraded behavior:
- If include/exclude part contains exactly ONE '*', like "A*B",
  then it matches either "A...B" OR "B...A" (unordered 2-keywords),
  same style as your old star-search.

Notes:
- Case-insensitive.
- Supports '*' wildcard in both include and exclude.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PercentQuery:
    include_raw: str
    exclude_raw: str


def _pattern_to_regex(pattern: str) -> re.Pattern:
    """
    Convert a user pattern to regex (case-insensitive).

    Rules:
    - No '*'      : contains match
    - Exactly one '*', and split into 2 non-empty parts:
        "A*B" => matches (A.*B) OR (B.*A)
    - Otherwise (multiple '*' or weird): treat '*' as wildcard sequentially
    """
    pattern = pattern.strip()
    if not pattern:
        return re.compile(r".*", re.IGNORECASE)

    if "*" not in pattern:
        return re.compile(re.escape(pattern), re.IGNORECASE)

    # Has '*'
    parts = [p.strip() for p in pattern.split("*") if p.strip()]

    # Exactly 2 keywords and user typed exactly one '*'
    # Example: "A*B" -> unordered (A.*B | B.*A)
    if pattern.count("*") == 1 and len(parts) == 2:
        a, b = parts[0], parts[1]
        p1 = re.escape(a) + r".*" + re.escape(b)
        p2 = re.escape(b) + r".*" + re.escape(a)
        return re.compile(rf"({p1}|{p2})", re.IGNORECASE)

    # General wildcard: turn every '*' into '.*'
    rx = re.escape(pattern).replace(r"\*", ".*")
    return re.compile(rx, re.IGNORECASE)


def parse_percent_query(user_text: str) -> Optional[PercentQuery]:
    """
    Parse query of form A%B
    - returns None if '%' not present or invalid
    """
    if "%" not in user_text:
        return None

    include_part, exclude_part = user_text.split("%", 1)
    include_part = include_part.strip()
    exclude_part = exclude_part.strip()

    # Require both sides to be non-empty
    if not include_part or not exclude_part:
        return None

    return PercentQuery(include_raw=include_part, exclude_raw=exclude_part)


def match_A_percent_B(filename: str, query: PercentQuery) -> bool:
    """
    True if:
    - filename matches include pattern
    - filename does NOT match exclude pattern
    """
    inc_rx = _pattern_to_regex(query.include_raw)
    exc_rx = _pattern_to_regex(query.exclude_raw)

    if not inc_rx.search(filename):
        return False
    if exc_rx.search(filename):
        return False
    return True
