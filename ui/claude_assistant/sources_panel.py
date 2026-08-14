"""ui/claude_assistant/sources_panel.py — the documents an answer rested on.

Sits under the orb and carries the same fact its orange markers do: which files
this answer cited. Cards and markers are two readings of one thing, so the code
colour is imported from the orb rather than copied, to stop them drifting apart.

Cards come in two depths because the app knows two different amounts:

* a chat answer yields only document codes, scraped out of the reply text, so
  the card is a code, a file name and a way to open it;
* a diagnosis yields structured evidence -- section, quote, and a verified flag
  set by checking the quote back against the DB -- so the card carries all of it.

The shallow card deliberately shows no verification state. "Not checked" and
"checked and wrong" are different claims, and rendering the first as the second
would put a warning on sound evidence.
"""
from __future__ import annotations

import os
from typing import NamedTuple

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QLabel, QMessageBox, QTextBrowser, QVBoxLayout, QWidget,
)

from ui.claude_assistant import copilot
# Same orange the orb paints cited neurons with: the panel and the markers name
# the same documents, and must not disagree about what that looks like.
from ui.claude_assistant.neural_orb_widget import _SOURCE_COLOR_HEX

_BG = "#06090f"
_CARD_BG = "#0d1b2a"
_BORDER = "#1a2535"
_TEXT = "#c3d3e3"
_MUTED = "#64809c"
_LINK = "#7ecfff"
_OK = "#4ade80"
_WARN = "#fbbf24"

# Cards past this point are still reachable by scrolling. The cap keeps a long
# evidence list from running the whole height of the column: the orb above sits
# at a fixed size and the legend under it must stay in view.
_MAX_PANEL_H = 340


class CitedSource(NamedTuple):
    """One document an answer cited.

    ``path`` is filled when the citation was already resolved against the file
    list the orb loads; diagnosis evidence arrives with a code only and is
    resolved on click instead. ``verified`` is None when there was no quote to
    check.
    """

    code: str
    path: str = ""
    section: str = ""
    quote: str = ""
    verified: bool | None = None


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


class CitedSourcesPanel(QWidget):
    """Cited-document cards, hidden entirely while there is nothing to show."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[CitedSource] = []
        self._db_path: str = ""

        self.setMaximumHeight(_MAX_PANEL_H)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._header = QLabel("CITED SOURCES")
        self._header.setStyleSheet(
            f"color: {_MUTED}; background: {_BG}; font-size: 10px;"
            f"font-weight: 600; letter-spacing: 1px;"
            f"padding: 6px 10px 4px 10px; border-top: 1px solid {_BORDER};"
        )

        self._view = QTextBrowser()
        # A scroll area asks for far more than this by default, which on a short
        # window makes the whole column taller than the space it has to live in.
        # The cards scroll, so a small floor costs nothing but the view of them.
        self._view.setMinimumHeight(40)
        self._view.setOpenLinks(False)
        self._view.setOpenExternalLinks(False)
        self._view.anchorClicked.connect(self._on_anchor)
        self._view.setStyleSheet(
            f"QTextBrowser {{ background: {_BG}; border: none;"
            f"padding: 0 8px 8px 8px; }}"
            # The default scrollbar is light grey and reads as a seam between
            # this panel and the orb above it.
            f"QScrollBar:vertical {{ background: {_BG}; width: 8px; margin: 0; }}"
            f"QScrollBar::handle:vertical {{ background: {_BORDER};"
            f"min-height: 24px; border-radius: 4px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {_MUTED}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical"
            f" {{ height: 0; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical"
            f" {{ background: {_BG}; }}"
        )

        lay.addWidget(self._header)
        lay.addWidget(self._view, 1)
        self.setVisible(False)

    # ── Public API ────────────────────────────────────────────────────
    def set_db_path(self, path: str) -> None:
        self._db_path = path or ""

    def set_sources(self, items: list[CitedSource]) -> None:
        self._items = list(items)
        self._render()

    def clear(self) -> None:
        self._items = []
        self._render()

    # ── Rendering ─────────────────────────────────────────────────────
    def _render(self) -> None:
        if not self._items:
            self._view.setHtml("")
            self.setVisible(False)
            return
        self._header.setText(f"CITED SOURCES · {len(self._items)}")
        self._view.setHtml(
            "".join(self._card_html(i, s) for i, s in enumerate(self._items))
        )
        self.setVisible(True)
        self._sync_height()

    def _sync_height(self) -> None:
        """Cap the panel at the height its cards actually need.

        A maximum rather than a fixed height: the column gives this panel a
        stretch, so it fills up to this figure and no further -- one card does
        not reserve the room six would -- while a short window can still take
        height back from it instead of clipping the cards off the bottom.
        """
        if not self._items:
            return
        doc = self._view.document()
        doc.setTextWidth(max(1, self._view.viewport().width()))
        needed = self._header.sizeHint().height() + int(doc.size().height()) + 12
        self.setMaximumHeight(min(_MAX_PANEL_H, needed))

    def resizeEvent(self, event):  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        # Card text rewraps at a new width, so the height it needs changes with
        # it. Guarded on width alone: reacting to our own height change would
        # loop.
        if event.oldSize().width() != event.size().width():
            self._sync_height()

    def _card_html(self, index: int, src: CitedSource) -> str:
        head = f'<b>{_esc(src.code)}</b>'
        if src.section:
            head += f'<span style="color:{_MUTED}"> › {_esc(src.section)}</span>'
        parts = [
            f'<div style="color:{_SOURCE_COLOR_HEX};font-size:11px">{head}</div>'
        ]

        name = os.path.basename(src.path) if src.path else ""
        if name:
            parts.append(
                f'<div style="color:{_MUTED};font-size:10px">{_esc(name)}</div>'
            )
        if src.quote:
            parts.append(
                f'<div style="color:{_TEXT};font-size:11px">"{_esc(src.quote)}"</div>'
            )
        if src.verified is True:
            parts.append(
                f'<div style="color:{_OK};font-size:10px">✓ Verified against the DB</div>'
            )
        elif src.verified is False:
            parts.append(
                f'<div style="color:{_WARN};font-size:10px">⚠ Quote not found in the DB</div>'
            )
        parts.append(
            f'<div style="margin-top:3px">'
            f'<a href="open:{index}" style="color:{_LINK};text-decoration:none">'
            f'📄 Open file</a></div>'
        )

        return (
            f'<table width="100%" bgcolor="{_CARD_BG}" border="0"'
            f' cellspacing="0" cellpadding="7">'
            f'<tr><td>{"".join(parts)}</td></tr></table>'
            f'<p style="margin:0;font-size:5px">&nbsp;</p>'
        )

    # ── Slots ─────────────────────────────────────────────────────────
    def _on_anchor(self, url: QUrl) -> None:
        """Click 'open:<index>' → open the file that citation resolved to."""
        text = url.toString()
        if not text.startswith("open:"):
            return
        try:
            index = int(text.split(":", 1)[1])
        except ValueError:
            return
        if not (0 <= index < len(self._items)):
            return

        src = self._items[index]
        path = src.path
        if not path and self._db_path and src.code:
            path = copilot.resolve_source_path(self._db_path, doc_number=src.code) or ""

        if not path or not os.path.exists(path):
            QMessageBox.information(
                self, "Not found",
                f"No source file found in this DB for:\n{src.code}",
            )
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as e:
            QMessageBox.warning(self, "Open file error", str(e))
