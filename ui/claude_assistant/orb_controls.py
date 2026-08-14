"""ui/claude_assistant/orb_controls.py — the band under the orb.

The orb draws the whole database at once, and until now nothing let you point
at part of it: the band below it carried cards that repeated what the answer
text had already said, twelve of them wanting 836px in a space capped at 340.
This is what took their place. A search box and a folder legend are two ways of
asking the orb the same question -- where does this live? -- and both are
answered in the gold the orb already lights search hits with.

The legend was a plain caption before. Making its rows clickable costs no extra
height and turns a caption into a control: the colours were already drawn, and
a folder is the one region of the orb a user can name without typing.

Search and folder are deliberately exclusive. They are the same question asked
two ways, and the orb has one highlight to answer with, so raising one lowers
the other rather than leaving the gold ambiguous about which asked for it.
"""
from __future__ import annotations

import html

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QVBoxLayout, QWidget,
)

# Imported rather than copied: the box tints itself with the colour the orb
# paints hits in, and a legend row lights up in it. If those ever disagreed the
# control would stop looking like the cause of what the orb does.
from ui.claude_assistant.neural_orb_widget import (
    _HIGHLIGHT_HEX, _SOURCE_COLOR_HEX,
)

_BG = "#06090f"
_FIELD_BG = "#0d141d"
_BORDER = "#1a2535"
_LINE = "#1e2b3a"
_INK = "#e6eef8"
_MUTED = "#64809c"
_HINT = "#5c7086"

_GOLD_HEX = _HIGHLIGHT_HEX

# Long enough that a typed word is not queried once per letter -- the search
# runs FTS against the real DB -- short enough that the orb still answers while
# typing rather than after it.
_DEBOUNCE_MS = 250

_FOLDER_SCHEME = "folder:"


class OrbControls(QWidget):
    """Search box and clickable folder legend, driving the orb's highlight.

    Emits rather than acts: the DB query and the orb both live with the parent
    widget, and this band's job is to say what was asked for, not to answer it.
    """

    search_changed = Signal(str)
    # The folder to light, or "" to light nothing.
    folder_picked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._legend: list[tuple[str, QColor, int]] = []
        self._active_folder = ""
        # Set while the box is being emptied by code rather than by the user,
        # so _on_typed can ignore it. A guard rather than blockSignals: the
        # built-in clear button tracks textChanged too, and blocking the signal
        # left a ✕ sitting on an empty box.
        self._muted = False

        # Scoped to this class, and WA_StyledBackground so a bare QWidget
        # actually paints it: an unscoped rule would put the top border on every
        # child as well, framing the search box and each legend row.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"OrbControls {{ background: {_BG};"
            f" border-top: 1px solid {_BORDER}; }}"
        )
        # The band is as tall as its two rows need and no taller; spare height
        # in the column belongs at the bottom, not stretched through here.
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 8)
        lay.setSpacing(6)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search the orb…")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(28)
        self._search.setStyleSheet(
            f"QLineEdit {{ background: {_FIELD_BG}; color: {_INK};"
            f" border: 1px solid {_LINE}; border-radius: 8px;"
            f" padding: 0 8px; font-size: 11px; }}"
            f"QLineEdit:focus {{ border-color: {_GOLD_HEX}; }}"
            f"QLineEdit:disabled {{ color: {_HINT}; border-color: {_BORDER}; }}"
        )
        self._search.textChanged.connect(self._on_typed)
        self._search.returnPressed.connect(self._flush)

        # How many documents the last answer cited, which is what the orange
        # markers on the orb above are. One line rather than one card each: the
        # answer text already names every code and already links it, so a card
        # per citation was the same fact told a third time.
        self._cited = QLabel("")
        self._cited.setStyleSheet(
            f"color: {_SOURCE_COLOR_HEX}; font-size: 10px; font-weight: 600;"
            f"background: transparent;"
        )
        self._cited.setVisible(False)

        # How many files the lit region stands for. Without it the orb shows a
        # spread of gold that could equally be five documents or five hundred,
        # and the user has no way to tell when they have seen them all.
        self._hits = QLabel("")
        self._hits.setStyleSheet(
            f"color: {_GOLD_HEX}; font-size: 10px; font-weight: 600;"
            f"background: transparent;"
        )
        self._hits.setVisible(False)

        row.addWidget(self._search, 1)
        row.addWidget(self._hits, 0)
        row.addWidget(self._cited, 0)
        lay.addLayout(row)

        self._legend_lbl = QLabel("")
        self._legend_lbl.setWordWrap(True)
        self._legend_lbl.setTextFormat(Qt.RichText)
        self._legend_lbl.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        self._legend_lbl.linkActivated.connect(self._on_folder_link)
        # Maximum, not the default Preferred: a label allowed to grow would take
        # the column's spare height and leave its rows floating in an empty band.
        self._legend_lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self._legend_lbl.setStyleSheet(
            f"color: {_MUTED}; font-size: 10px; background: transparent;"
        )
        self._legend_lbl.setVisible(False)
        lay.addWidget(self._legend_lbl)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._flush)

    # ── Public API ────────────────────────────────────────────────────
    def set_legend(self, legend: list[tuple[str, QColor, int]]) -> None:
        self._legend = list(legend)
        if self._active_folder not in {n for n, _, _ in self._legend}:
            self._active_folder = ""
        # An empty legend means the orb holds no files, which is exactly when
        # searching it cannot answer. Saying so beats leaving a box that takes
        # typing and never responds.
        loaded = bool(self._legend)
        self._search.setEnabled(loaded)
        self._search.setPlaceholderText(
            "🔍  Search the orb…" if loaded else "Select a DB to search")
        self._render_legend()

    def set_cited(self, codes: list[str]) -> None:
        """Name how many documents the answer rested on, and which."""
        if not codes:
            self._cited.setVisible(False)
            self._cited.setText("")
            self._cited.setToolTip("")
            return
        self._cited.setText(f"◆ {len(codes)} cited")
        self._cited.setToolTip(
            "Documents this answer cited, marked on the orb:\n• "
            + "\n• ".join(codes)
        )
        self._cited.setVisible(True)

    def set_hits(self, n: int) -> None:
        """Say how many files the lit region of the orb stands for."""
        if n <= 0:
            self._hits.setVisible(False)
            self._hits.setText("")
            self._hits.setToolTip("")
            return
        self._hits.setText(f"◆ {n:,} file" + ("s" if n != 1 else ""))
        self._hits.setToolTip(
            "Files behind the gold on the orb.\n"
            "Hover a lit neuron to see which of them it holds, "
            "or click it to open one."
        )
        self._hits.setVisible(True)

    def reset(self) -> None:
        """Drop both controls without asking the orb to repaint.

        Used when something else has already taken the highlight over -- an
        answer's citations, or a fresh question -- so the box must stop claiming
        gold it no longer owns.
        """
        self._debounce.stop()
        self._active_folder = ""
        self._clear_search_silently()
        self.set_hits(0)
        self._render_legend()

    # ── Internals ─────────────────────────────────────────────────────
    def _clear_search_silently(self) -> None:
        """Empty the box without asking the orb to repaint on the way out."""
        if not self._search.text():
            return
        self._muted = True
        try:
            self._search.clear()
        finally:
            self._muted = False

    # ── Rendering ─────────────────────────────────────────────────────
    def _render_legend(self) -> None:
        if not self._legend:
            self._legend_lbl.setText("")
            self._legend_lbl.setVisible(False)
            return
        rows = []
        for name, color, count in self._legend:
            dot = f"#{color.red():02x}{color.green():02x}{color.blue():02x}"
            on = name == self._active_folder
            # Qt's rich text gives every <a> the palette's link colour and an
            # underline, and ignores inline style on the anchor itself, so the
            # row is coloured on a span inside it instead.
            style = (f"color:{_GOLD_HEX};font-weight:600" if on
                     else f"color:{_MUTED}")
            # Every space inside a row is non-breaking, so the wrap lands
            # between rows and never inside one. The rows used to be joined by
            # non-breaking spaces instead, which left the line break with
            # nowhere to go but the middle of a folder name -- "1." ending one
            # line and "Comissioning 337" starting the next.
            label = html.escape(name).replace(" ", "&nbsp;")
            rows.append(
                f'<a href="{_FOLDER_SCHEME}{html.escape(name)}"'
                f' style="text-decoration:none">'
                f'<span style="{style};text-decoration:none">'
                f'<span style="color:{dot}">●</span>&nbsp;{label}'
                f'&nbsp;<span style="color:{dot};font-weight:600">{count:,}</span>'
                f'</span></a>'
            )
        # Two non-breaking spaces to set the rows apart, then one ordinary space
        # as the only place the line is allowed to break.
        self._legend_lbl.setText("&nbsp;&nbsp; ".join(rows))
        self._legend_lbl.setVisible(True)

    # ── Slots ─────────────────────────────────────────────────────────
    def _on_typed(self, _text: str) -> None:
        if self._muted:
            return
        if self._active_folder:
            # Typing supersedes the folder: one highlight, one question.
            self._active_folder = ""
            self._render_legend()
        self._debounce.start()

    def _flush(self) -> None:
        self._debounce.stop()
        self.search_changed.emit(self._search.text().strip())

    def _on_folder_link(self, link: str) -> None:
        if not link.startswith(_FOLDER_SCHEME):
            return
        name = link[len(_FOLDER_SCHEME):]
        # Clicking the lit row again puts the orb back, so there is a way out
        # that does not require finding some other control.
        self._active_folder = "" if name == self._active_folder else name
        self._debounce.stop()
        self._clear_search_silently()
        self._render_legend()
        self.folder_picked.emit(self._active_folder)
