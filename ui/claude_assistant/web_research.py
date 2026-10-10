"""ui/claude_assistant/web_research.py — answering from the live web, with sources that can be checked.

The document database answers what *this plant's* drawings say. This module
answers the other half of an engineer's questions: what the standard, the OEM or
the industry says. The difference that matters is provenance. An answer from the
DB can be traced back to a file; an answer from the web is worth nothing to
somebody who has to sign for the decision unless it can be traced back to a page.

So the module is two halves, kept apart on purpose:

* ``build_web_system_prompt`` tells the agent how to research and how to cite.
* ``extract_sources`` / ``tool_urls`` / ``audit`` check the citations against
  what actually happened. The worker reports every tool call with its arguments,
  so the app knows which URLs were really opened with WebFetch. A page the answer
  cites but never opened is shown as such instead of being taken on trust — a
  model will happily credit a figure to a URL it only saw in a search result.
  That audit is the whole point, and the prompt says the audit exists.

No Qt in here: it is text in, text out, so it can be exercised from a plain
script.
"""
from __future__ import annotations

import re
from typing import Iterable, NamedTuple, Sequence

# Twelve is already more than anybody reads; past that the panel is a wall.
MAX_SOURCES = 12


# --------------------------------------------------------------------------- #
#  The system prompt
# --------------------------------------------------------------------------- #

_PROMPT = """WEB RESEARCH

You answer from the live internet for the engineering and operations team of a
thermal power plant. They act on what you say, so the answer is worth exactly as
much as the source behind it.

HOW TO WORK
1. WebSearch first. Several short, specific queries beat one long one. Search in
   English for standards, OEM material and engineering practice even when the
   question is in Vietnamese; add a Vietnamese query when the question is about
   local regulation or local practice.
2. WebFetch the pages that look authoritative and read them. Do not answer from
   search snippets alone — a snippet is a headline, not evidence.
3. Prefer sources in this order: the standard or regulation itself (IEC, IEEE,
   ISO, ASME, NFPA, national regulation), the OEM's own manual or datasheet, an
   industry body or utility publication, a textbook or peer-reviewed paper.
   Vendor blogs and forum threads come last, and when one is all you have, say so.
4. If sources disagree, give both figures and say which source carries more
   weight and why. Never average them into one number.
5. If the web does not settle the question, say that plainly. An honest "the
   pages I could read do not state this" is useful; an invented figure is not.

CITING — this is not optional
- Every sentence stating a fact, figure, limit or requirement ends with a marker:
  [1], [2] … Use [1][3] when two sources back one sentence.
- End the answer with a SOURCES block and nothing after it:

  SOURCES:
  [1] Page or document title - https://full/url
  [2] Page or document title - https://full/url

- Number them in the order the markers first appear. Every number used has a
  line, and every line has a number used somewhere in the text.
- Cite a page only if you opened it with WebFetch. If a point rests on a search
  result you could not open, end that source line with
  "(search result, page not opened)".
- Never write a URL you have not seen in a tool result. The app compares every
  URL in the SOURCES block against the pages you actually fetched and shows the
  user which ones were opened, so a guessed or rebuilt URL is visible as a guess.
- Anything you add from your own knowledge rather than from a page is marked
  [no source] on that sentence, and gets no number.

ANSWERING
- Answer in Vietnamese. Keep standard numbers, equipment names, tag names and
  settled engineering terms in English, the way the plant writes them.
- The direct answer comes first, in one or two sentences. Detail, tables and
  caveats follow.
- Give figures with units, and name the condition they hold under — ambient
  temperature, rated load, altitude, duty class.
- For a set of limits or ratings, a table beats prose.
- Say when a standard has been superseded, and by what."""

_TODAY = """
- Today is {today}. When the answer depends on how current the source is — a
  price, availability, which edition of a standard is in force — say when the
  page was published or last updated."""


def build_web_system_prompt(today: str = "") -> str:
    """The research + citation contract handed to the agent in web mode."""
    prompt = _PROMPT
    if today:
        prompt += _TODAY.format(today=today)
    return prompt


def build_retry_prompt(question: str, answer: str, limit: int = 4000) -> str:
    """Asked once when an answer came back with no SOURCES block at all.

    Carries the question and the attempt back in: each agent run is its own
    session and remembers nothing of the one before it.
    """
    draft = (answer or "").strip()
    if len(draft) > limit:
        draft = draft[:limit] + "\n[…truncated]"
    return (
        "The question was:\n"
        f"{(question or '').strip()}\n\n"
        "An earlier attempt answered it with no sources at all, so none of it "
        "can be checked:\n"
        "---\n"
        f"{draft}\n"
        "---\n\n"
        "Research the question again and answer it properly this time:\n"
        "- open the pages with WebFetch, do not work from search snippets\n"
        "- put a [n] marker on every sentence that states a fact or a figure\n"
        '- end with a line "SOURCES:" and then one line per source, formatted '
        "[n] Title - https://url\n"
        "- list only pages you actually opened\n\n"
        "Keep what the draft got right, drop what you cannot source, and mark a "
        "sentence [no source] rather than giving it a number it has not earned."
    )


# --------------------------------------------------------------------------- #
#  Reading the citations back out
# --------------------------------------------------------------------------- #

class WebSource(NamedTuple):
    """One line of the SOURCES block, after the audit."""
    n: int
    title: str
    url: str
    opened: bool = False
    note: str = ""          # the model's own caveat on that line, if any

    @property
    def domain(self) -> str:
        m = re.match(r"^[a-z]+://([^/]+)", self.url, re.I)
        host = m.group(1).lower() if m else ""
        return host[4:] if host.startswith("www.") else host


_HEADINGS = (
    "tài liệu tham khảo", "tai lieu tham khao", "nguồn tham khảo",
    "nguon tham khao", "references", "reference", "sources", "source",
    "nguồn", "nguon",
)
_HEAD_RE = re.compile(
    r"(?im)^[ \t]*(?:#{1,6}[ \t]*)?[*_]{0,2}[ \t]*(?:"
    + "|".join(re.escape(h) for h in sorted(_HEADINGS, key=len, reverse=True))
    + r")[ \t]*[*_]{0,2}[ \t]*(?::|$)"
)

# Models number their sources every way there is: "[1] ", "1. ", "(1) ", "1) ",
# sometimes behind a bullet. They are all one entry.
_NUM_LINE = re.compile(
    r"^[ \t]*[-*•]?[ \t]*[\[(]?(\d{1,2})(?:[\])]|\.(?=\s)|:)[ \t]*(.+)$")
_MARKER = re.compile(r"\[(\d{1,2})\]")
_MD_LINK = re.compile(r"\[([^\]\n]{1,200})\]\((https?://[^)\s]+)\)")
_URL = re.compile(r"https?://[^\s<>\"'`]+")
_TRIM = " \t*_-–—·|:,.;\"')]“”’"
_NOTE_HINTS = ("not opened", "search result", "snippet", "không mở", "khong mo")


def has_sources(answer: str) -> bool:
    """True when the answer ends with something that looks like a SOURCES block."""
    return bool(extract_sources(answer))


def _clean_url(url: str) -> str:
    return url.strip().rstrip(".,;:)]}>\"'“”’")


def normalize_url(url: str) -> str:
    """Scheme, host and path only, lowercased — enough to compare two spellings."""
    u = _clean_url(url)
    u = u.split("#", 1)[0]
    m = re.match(r"^([a-z]+)://([^/?]+)(.*)$", u, re.I)
    if not m:
        return u.lower()
    host = m.group(2).lower()
    if host.startswith("www."):
        host = host[4:]
    rest = m.group(3)
    query = ""
    if "?" in rest:
        rest, query = rest.split("?", 1)
        keep = [p for p in query.split("&")
                if p and not p.lower().startswith(("utm_", "fbclid", "gclid"))]
        query = ("?" + "&".join(keep)) if keep else ""
    rest = rest.rstrip("/")
    # Lowercased whole: the only use is comparing two spellings of one address
    # for equality, and a retyped path differing in case must not read as a
    # different page. The untouched URL is what the card links to.
    return f"{m.group(1)}://{host}{rest}{query}".lower()


def _host_path(url: str) -> str:
    """The same, without the scheme — http/https alone must not split a match."""
    return normalize_url(url).split("://", 1)[-1]


def _entry_lines(block: str) -> list[str]:
    """The numbered entries of a SOURCES block, each joined back onto one line."""
    out: list[str] = []
    for raw in block.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if _NUM_LINE.match(line):
            out.append(line.strip())
        elif out and not _HEAD_RE.match(line):
            # A wrapped entry: "[3] A very long title\n    https://…"
            out[-1] += " " + line.strip()
    return out


def _split_entry(text: str) -> tuple[str, str, str]:
    """(title, url, trailing remark) out of one entry body.

    Whatever the model wrote after the URL is kept apart instead of being glued
    onto the title. On a wrapped entry that tail is usually its own remark about
    what the page gives — "states the 105 K rise limit in table 8" — which the
    source card has a line for and the title has no room for.
    """
    md = _MD_LINK.search(text)
    if md:
        title = md.group(1).strip()
        url = _clean_url(md.group(2))
        before = text[:md.start()].strip(_TRIM)
        tail = text[md.end():].strip(_TRIM)
        if title or before:
            return (title or before), url, tail
        return tail, url, ""
    m = _URL.search(text)
    if not m:
        return text.strip(_TRIM), "", ""
    url = _clean_url(m.group(0))
    head = text[:m.start()].strip(_TRIM)
    tail = text[m.end():].strip(_TRIM)
    if head:
        return head, url, tail
    # "https://… - Page title": nothing before the URL, so the tail is the title.
    return tail, url, ""


def _note_of(text: str) -> str:
    """The model's own caveat on an entry, kept so the UI can repeat it."""
    low = text.lower()
    for hint in _NOTE_HINTS:
        if hint in low:
            m = re.search(r"\(([^)]*" + re.escape(hint) + r"[^)]*)\)", text, re.I)
            return (m.group(1) if m else hint).strip()
    return ""


def extract_sources(answer: str, limit: int = MAX_SOURCES) -> list[WebSource]:
    """Parse the SOURCES block. Falls back to any links found in the body."""
    if not answer:
        return []

    block = ""
    for m in _HEAD_RE.finditer(answer):   # the last heading wins
        block = answer[m.end():]

    found: list[WebSource] = []
    seen: set[str] = set()

    def add(n: int, title: str, url: str, note: str = "") -> None:
        key = normalize_url(url) if url else f"#{title.lower()}"
        if not key or key in seen or len(found) >= limit:
            return
        seen.add(key)
        found.append(WebSource(n=n, title=title[:300], url=url,
                               note=note[:240]))

    for entry in _entry_lines(block):
        m = _NUM_LINE.match(entry)
        if not m:
            continue
        title, url, tail = _split_entry(m.group(2))
        add(int(m.group(1)), title, url, _note_of(m.group(2)) or tail)

    if not found:
        # No block, or a block with no numbers: take whatever links the answer
        # does carry rather than reporting nothing at all.
        for md in _MD_LINK.finditer(answer):
            add(len(found) + 1, md.group(1).strip(), _clean_url(md.group(2)))
        for m in _URL.finditer(answer):
            add(len(found) + 1, "", _clean_url(m.group(0)))
    return found


def markers_used(answer: str) -> set[int]:
    """The [n] markers that appear in the body, above the SOURCES block."""
    body = answer
    for m in _HEAD_RE.finditer(answer):
        body = answer[:m.start()]
    return {int(x) for x in _MARKER.findall(body)}


# --------------------------------------------------------------------------- #
#  What actually happened
# --------------------------------------------------------------------------- #

def _tool_kind(name: str) -> str:
    """'fetch', 'search' or '' — tolerant of the MCP spellings (web_fetch_exa)."""
    flat = re.sub(r"[^a-z]", "", (name or "").lower())
    if "webfetch" in flat or flat == "fetch":
        return "fetch"
    if "websearch" in flat or flat == "search":
        return "search"
    return ""


def tool_urls(calls: Sequence[tuple]) -> tuple[list[str], list[str]]:
    """(pages fetched, queries searched) from a list of (tool_name, input) pairs."""
    fetched: list[str] = []
    queries: list[str] = []
    for call in calls or ():
        try:
            name, args = call[0], call[1]
        except (IndexError, TypeError):
            continue
        if not isinstance(args, dict):
            args = {}
        kind = _tool_kind(name)
        if kind == "fetch":
            url = args.get("url") or args.get("uri") or ""
            if isinstance(url, str) and url.strip():
                fetched.append(url.strip())
        elif kind == "search":
            query = args.get("query") or args.get("q") or ""
            if isinstance(query, str) and query.strip():
                queries.append(query.strip())
    return fetched, queries


def audit(sources: Iterable[WebSource],
          fetched: Iterable[str]) -> list[WebSource]:
    """Mark each cited source according to whether that page was really opened."""
    exact = {normalize_url(u) for u in fetched if u}
    loose = {_host_path(u) for u in fetched if u}
    out = []
    for src in sources:
        opened = bool(src.url) and (
            normalize_url(src.url) in exact or _host_path(src.url) in loose)
        out.append(src._replace(opened=opened))
    return out


def verdict(sources: Sequence[WebSource],
            queries: Sequence[str],
            fetched: Sequence[str]) -> tuple[str, str]:
    """One line for under the answer, plus a level: 'ok', 'warn' or 'none'."""
    pages = len({normalize_url(u) for u in fetched if u})
    searches = len(queries)
    if not sources:
        return ("No source was cited — treat this answer as unverified.", "none")

    opened = sum(1 for s in sources if s.opened)
    bits = [f"{len(sources)} source{'s' if len(sources) != 1 else ''} cited",
            f"{opened} of them opened"]
    if pages:
        bits.append(f"{pages} page{'s' if pages != 1 else ''} read")
    if searches:
        bits.append(f"{searches} search{'es' if searches != 1 else ''}")
    line = " · ".join(bits)

    gap = len(sources) - opened
    if gap:
        return (line + f" — {gap} cited page"
                + ("s were" if gap != 1 else " was")
                + " never opened, so check "
                + ("those" if gap != 1 else "that one") + " yourself.", "warn")
    return (line + ".", "ok")
