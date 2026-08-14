"""ui/claude_assistant/chat_render.py — the answer's markdown, as Qt rich text.

Claude replies in markdown: headings, GitHub tables, bullet lists, bold, block
quotes. The chat pane used to print that source verbatim, so a table arrived as
a wall of pipes and every ``##`` was read as two hash characters. This module is
what turns it back into a document.

Written by hand rather than handed to ``QTextDocument.setMarkdown``. Two reasons:
Qt's reader drops block quotes entirely -- and citing the source document is the
one thing this app's answers must never lose -- and its output carries Qt's own
margins and sizes, which cannot be restyled without walking the document
afterwards. A small converter over the subset Claude actually emits costs less
than fighting that, and it lets document codes become clickable in the same pass.

Qt's rich text is a subset of HTML 4: no flexbox, no border-radius, no
box-shadow. Anything that looks like a padded, tinted block here is a one-row
table with a coloured cell for the left rule -- that is the only way Qt draws it.
"""
from __future__ import annotations

import html
import re

# Body text and the greys around it. Kept next to the palette the chat pane is
# styled with (#f8fafc ground, #1e293b text) so the two cannot drift apart.
_TEXT = "#1e293b"
_STRONG = "#0f172a"
_QUOTE_BG = "#eef4fb"
_QUOTE_RULE = "#7c9fc4"
_QUOTE_TEXT = "#334155"
_TABLE_BORDER = "#dbe4ee"
_TABLE_HEAD_BG = "#eef4fb"
_TABLE_ROW_BG = "#ffffff"
_TABLE_ALT_BG = "#f8fafc"
_CODE_BG = "#eef2f7"
_CODE_TEXT = "#9d174d"
_USER_BG = "#eef2ff"
_USER_RULE = "#6366f1"
_USER_TEXT = "#3730a3"
_TOOL_BG = "#f4f1ea"
_TOOL_TEXT = "#8a6d3b"
# Same orange the orb paints cited neurons and the sources panel titles cards
# with: a code in the text and a marker on the orb are one fact, shown twice.
_DOC_LINK = "#ff7e2e"

# Heading level → (size, colour). Levels past 4 fall back to the smallest.
_HEADINGS = {
    1: ("18px", _STRONG),
    2: ("16px", _STRONG),
    3: ("14px", "#1e3a5f"),
    4: ("13px", "#334155"),
}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_ORDERED_RE = re.compile(r"^(\s*)\d+[.)]\s+(.*)$")
_RULE_RE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_FENCE_RE = re.compile(r"^\s*```")
# A separator row under a table header: only dashes, colons and spaces.
_SEP_CELL_RE = re.compile(r"^:?-{2,}:?$")

# Link target for a document code. Read back by the widget, which resolves the
# code to a file and opens it.
DOC_LINK_SCHEME = "doc:"


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _inline(text: str, doc_codes: frozenset[str] = frozenset()) -> str:
    """Escape one line, then apply the inline marks.

    Order matters: escaping first means a ``<`` in the answer can never open a
    tag, and every mark added after it is ours. Code spans are pulled out before
    the emphasis passes so that ``**`` inside backticks stays literal.
    """
    spans: list[str] = []

    def _stash(match: re.Match) -> str:
        spans.append(match.group(1))
        return f"\x00{len(spans) - 1}\x00"

    out = re.sub(r"`([^`]+)`", _stash, text)
    out = _esc(out)
    out = re.sub(r"\*\*(.+?)\*\*", rf'<b style="color:{_STRONG}">\1</b>', out)
    out = re.sub(r"__(.+?)__", rf'<b style="color:{_STRONG}">\1</b>', out)
    # Single ``*`` only when it is not part of a ``**`` pair and not mid-word,
    # so ``a*b`` and a stray asterisk are left alone.
    out = re.sub(r"(?<![\*\w])\*([^*\n]+?)\*(?!\*)", r"<i>\1</i>", out)

    if doc_codes:
        out = _link_doc_codes(out, doc_codes)

    for i, code in enumerate(spans):
        # The code spans get their own link pass. Answers write a document code
        # as ``VP1-C-L1-M-HFC-50016`` far more often than bare, so a linker that
        # only saw the text outside backticks left almost every citation dead.
        body = _esc(code)
        if doc_codes:
            body = _link_doc_codes(body, doc_codes)
        out = out.replace(
            f"\x00{i}\x00",
            f'<span style="background:{_CODE_BG};color:{_CODE_TEXT}">'
            f"&nbsp;{body}&nbsp;</span>",
        )
    return out


def _link_doc_codes(text: str, doc_codes: frozenset[str]) -> str:
    """Turn the codes this DB actually holds into links, and only those.

    The caller passes the codes it already resolved to a real file, so a code
    that leads nowhere -- an external standard, a typo, a part number that looks
    like one -- is left as plain text rather than offered as a dead link.
    """
    pattern = re.compile(
        r"(?<![\w-])(" + "|".join(re.escape(c) for c in sorted(doc_codes, key=len, reverse=True)) + r")(?![\w-])"
    )

    def _repl(match: re.Match) -> str:
        code = match.group(1)
        return (
            f'<a href="{DOC_LINK_SCHEME}{code}" '
            f'style="color:{_DOC_LINK};text-decoration:none">{code}</a>'
        )

    return pattern.sub(_repl, text)


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(_SEP_CELL_RE.match(c) for c in cells)


def _render_table(rows: list[str], doc_codes: frozenset[str]) -> str:
    """A pipe table as a real bordered table.

    The header row is whatever precedes the ``|---|`` separator; a table without
    one is rendered as all body, which is what a reader would take it for.
    """
    parsed = [_split_row(r) for r in rows]
    head: list[str] = []
    if len(parsed) >= 2 and _is_separator(parsed[1]):
        head, body = parsed[0], parsed[2:]
    else:
        body = [r for r in parsed if not _is_separator(r)]
    if not head and not body:
        return ""

    out = [
        f'<table width="100%" cellspacing="0" cellpadding="7" '
        f'style="border:1px solid {_TABLE_BORDER}">'
    ]
    # Every cell states its colour. Qt inherits the character format from
    # whatever precedes the insertion point, so a cell that leaves colour unset
    # comes out tinted by the block above it.
    if head:
        out.append(f'<tr bgcolor="{_TABLE_HEAD_BG}">')
        out += [
            f'<td style="border-bottom:1px solid {_TABLE_BORDER};color:{_STRONG}">'
            f"<b>{_inline(c, doc_codes)}</b></td>"
            for c in head
        ]
        out.append("</tr>")
    for i, row in enumerate(body):
        out.append(f'<tr bgcolor="{_TABLE_ALT_BG if i % 2 else _TABLE_ROW_BG}">')
        out += [
            f'<td style="border-bottom:1px solid {_TABLE_BORDER};color:{_TEXT}">'
            f"{_inline(c, doc_codes)}</td>"
            for c in row
        ]
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def _render_quote(lines: list[str], doc_codes: frozenset[str]) -> str:
    """A block quote as a tinted panel with a coloured left rule.

    Answers use quotes to name the document they rest on, so this is the most
    load-bearing block on the page after the tables.
    """
    body = "<br>".join(_inline(ln, doc_codes) for ln in lines)
    return (
        f'<table width="100%" cellspacing="0" cellpadding="8" '
        f'bgcolor="{_QUOTE_BG}"><tr>'
        f'<td width="3" bgcolor="{_QUOTE_RULE}"></td>'
        f'<td style="color:{_QUOTE_TEXT};font-size:12px">{body}</td>'
        f"</tr></table>"
    )


def _rule_html() -> str:
    """A thematic break, drawn as an actual hairline.

    Qt gives a table row at least one line of text height, so ``height="1"`` on
    the cell paints a 16px band, and ``<hr>`` reserves 28px. A one-pixel font
    inside the cell is what collapses the row to the rule itself.
    """
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0">'
        f'<tr><td bgcolor="{_TABLE_BORDER}">'
        f'<span style="font-size:1px">&nbsp;</span></td></tr></table>'
    )


def _render_code_block(lines: list[str],
                       doc_codes: frozenset[str] = frozenset()) -> str:
    """A fenced block, with its document codes still clickable.

    The fenced blocks in these answers are the SQL that produced them, and the
    code in a ``WHERE doc_number = ...`` names a file like any other citation
    does. Linking runs after the spaces become ``&nbsp;`` -- the other way round
    would substitute inside the anchor's own attributes and break the tag.
    """
    body = "<br>".join(_esc(ln).replace(" ", "&nbsp;") for ln in lines)
    if doc_codes:
        body = _link_doc_codes(body, doc_codes)
    return (
        f'<table width="100%" cellspacing="0" cellpadding="8" '
        f'bgcolor="{_CODE_BG}"><tr><td>'
        f'<span style="font-family:Consolas,monospace;font-size:11px;'
        f'color:{_CODE_TEXT}">{body}</span></td></tr></table>'
    )


def _render_list(items: list[tuple[int, str]], ordered: bool,
                 doc_codes: frozenset[str]) -> str:
    """A list, nested by the indent each item was written with.

    Qt renders ``<ul>``/``<ol>`` but ignores CSS list nesting, so depth is built
    by actually opening a nested list -- two spaces of indent per level, which is
    what markdown writers produce.
    """
    tag = "ol" if ordered else "ul"
    out: list[str] = []
    depth = 0
    for indent, text in items:
        level = min(indent // 2, 3)
        while depth < level + 1:
            out.append(f'<{tag} style="margin:4px 0 6px 0">')
            depth += 1
        while depth > level + 1:
            out.append(f"</{tag}>")
            depth -= 1
        out.append(
            f'<li style="margin-bottom:3px;color:{_TEXT}">'
            f"{_inline(text, doc_codes)}</li>"
        )
    out += [f"</{tag}>"] * depth
    return "".join(out)


def markdown_to_html(md: str, doc_codes: frozenset[str] = frozenset()) -> str:
    """Markdown as Claude writes it → HTML as Qt renders it.

    Block-level, one pass, no lookahead beyond the block being read. Anything the
    converter does not recognise falls through to a paragraph, so an unsupported
    construct degrades to readable text instead of disappearing.
    """
    lines = (md or "").replace("\r\n", "\n").split("\n")
    parts: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        if _FENCE_RE.match(line):
            i += 1
            block: list[str] = []
            while i < len(lines) and not _FENCE_RE.match(lines[i]):
                block.append(lines[i])
                i += 1
            i += 1  # closing fence, or the end of the text
            parts.append(_render_code_block(block, doc_codes))
            continue

        if line.lstrip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1
            parts.append(_render_table(block, doc_codes))
            continue

        if line.startswith(">"):
            block = []
            while i < len(lines) and lines[i].startswith(">"):
                block.append(lines[i].lstrip(">").strip())
                i += 1
            parts.append(_render_quote(block, doc_codes))
            continue

        if _RULE_RE.match(line):
            parts.append(_rule_html())
            i += 1
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            size, color = _HEADINGS.get(len(heading.group(1)), _HEADINGS[4])
            parts.append(
                f'<p style="font-size:{size};color:{color};font-weight:700;'
                f'margin:15px 0 5px 0">{_inline(heading.group(2), doc_codes)}</p>'
            )
            i += 1
            continue

        bullet = _BULLET_RE.match(line)
        ordered = _ORDERED_RE.match(line)
        if bullet or ordered:
            is_ordered = ordered is not None
            pattern = _ORDERED_RE if is_ordered else _BULLET_RE
            items: list[tuple[int, str]] = []
            while i < len(lines):
                m = pattern.match(lines[i])
                if not m:
                    break
                items.append((len(m.group(1)), m.group(2)))
                i += 1
            parts.append(_render_list(items, is_ordered, doc_codes))
            continue

        if line.strip():
            parts.append(
                f'<p style="color:{_TEXT};margin:6px 0;line-height:145%">'
                f"{_inline(line, doc_codes)}</p>"
            )
        i += 1

    return "".join(parts)


def user_turn_html(message: str) -> str:
    """The question, as a tinted block that reads as the start of a turn.

    A question and its answer used to run together in one column of text; giving
    the question a block of its own is what makes a scrolled-back conversation
    separable into turns.
    """
    return (
        f'<table width="100%" cellspacing="0" cellpadding="9" '
        f'bgcolor="{_USER_BG}"><tr>'
        f'<td width="3" bgcolor="{_USER_RULE}"></td>'
        f'<td style="color:{_USER_TEXT};font-size:13px">{_esc(message)}</td>'
        f"</tr></table>"
    )


def tool_chip_html(counts: dict[str, int]) -> str:
    """One chip for the whole answer's tool use, e.g. ``⚙ 8 DB queries``.

    Tool events used to be appended into the answer's own paragraph as they
    arrived, which put ``⚙ Bash`` eight times in front of the first word. The
    work is worth reporting; interleaving it with the prose is not.
    """
    if not counts:
        return ""
    total = sum(counts.values())
    if set(counts) == {"Bash"}:
        label = f"{total} DB quer{'y' if total == 1 else 'ies'}"
    else:
        label = " · ".join(
            f"{name} ×{n}" if n > 1 else name for name, n in counts.items()
        )
    return (
        f'<table cellspacing="0" cellpadding="4" bgcolor="{_TOOL_BG}"><tr><td>'
        f'<span style="color:{_TOOL_TEXT};font-size:11px">'
        f"&nbsp;⚙ {_esc(label)}&nbsp;</span></td></tr></table>"
    )


def spacer_html(px: int = 12) -> str:
    """Vertical gap between turns.

    Qt ignores a margin on an empty paragraph, and gives a table row a full line
    of text height whatever ``height`` says, so the gap is set by the font size
    of the single space inside it.
    """
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0">'
        f'<tr><td><span style="font-size:{max(1, px)}px">&nbsp;</span>'
        f"</td></tr></table>"
    )
