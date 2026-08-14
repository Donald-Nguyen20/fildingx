"""ui/claude_assistant/widget.py — Chat UI dùng claude_agent_sdk (Claude Code session)."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import NamedTuple

import paths

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter,
    QPushButton, QToolButton, QLabel, QLineEdit, QTextEdit, QFileDialog,
    QDialog, QMessageBox, QSizePolicy, QTextBrowser,
)
from PySide6.QtCore import Qt, QRectF, QSize, QTimer, QThread, Signal
from PySide6.QtGui import (
    QFont, QFontMetrics, QIcon, QPainter, QPixmap, QTextCursor,
)

from ui.claude_assistant.agent import make_options
from ui.claude_assistant.worker import AgentWorker
from ui.claude_assistant.animations import PulsingOrb
from ui.claude_assistant.diagnosis_panel import DiagnosisPanel
from ui.claude_assistant.neural_orb_widget import (
    _CANVAS_H, _CANVAS_W, NeuralOrbWidget,
)
from ui.claude_assistant.orb_controls import OrbControls
from ui.claude_assistant.sources_panel import CitedSource, CitedSourcesPanel
from ui.claude_assistant import chat_render, copilot

def _load_saved_db_path() -> str:
    """Đọc đường dẫn DB đã lưu (nếu file còn tồn tại)."""
    try:
        with open(paths.CLAUDE_DB_FILE, "r", encoding="utf-8") as f:
            path = (json.load(f) or {}).get("db_path", "")
        return path if path and os.path.exists(path) else ""
    except Exception:
        return ""


def _save_db_path(path: str):
    """Lưu đường dẫn DB để lần sau khỏi import lại."""
    try:
        with open(paths.CLAUDE_DB_FILE, "w", encoding="utf-8") as f:
            json.dump({"db_path": path}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

_STOPWORDS = {
    "là", "gì", "vậy", "của", "và", "với", "có", "không", "trong",
    "tên", "hãy", "cho", "từ", "về", "này", "đó", "đây", "thì",
    "được", "bị", "những", "các", "một", "hay", "hoặc", "nào",
    "tôi", "bạn", "mình", "cho", "muốn", "cần", "biết", "nói",
    "the", "and", "for", "that", "this", "with", "are", "was",
}


def _extract_keywords(msg: str) -> list[str]:
    """Lấy các từ khóa có nghĩa từ câu hỏi (bỏ stopword, từ ngắn)."""
    words = msg.replace("?", " ").replace(",", " ").split()
    return [w for w in words if len(w) >= 3 and w.lower() not in _STOPWORDS]


# A document code is an uppercase token of at least three hyphenated segments
# (VP1-C-L3-G-HNC-50056, ABC-M-2201-001). Kept plant-agnostic on purpose: the DB
# decides whether a candidate is a real document, so the pattern only has to be
# generous enough never to miss a citation, not strict enough to prove one.
_DOC_CODE_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9}(?:-[A-Z0-9][A-Z0-9.]{0,9}){2,})\b")

# A citation resolves to one document plus its revisions -- measured across 400
# real codes: median 1 file, max 6. A code matching far more than that is too
# generic to be a citation, so it is dropped instead of lighting a whole region
# as though the answer had rested on all of it.
_MAX_PATHS_PER_CITATION = 25

# Workspace splitter columns: modes | orb | chat | diagnosis.
#
# The orb column is pinned to the same width in every state, diagnosis included.
# NeuralOrbWidget draws at min(w/620, h/560), and _OrbColumn hands it a box of
# exactly that aspect, so the width term is what the orb ends up drawn at: this
# number IS the orb's size. Letting another panel take width from this column
# resizes the orb, so width is taken from the chat column instead.
#
# The mode column is the width of proposal E's left rail, which is what makes
# its two-column grid of modes fit: 236 less the 14px side padding leaves 208
# for two 100px tiles and the 7px between them. At the 168 it used to be, a
# label like "Make Report" -- 66px at 11px type -- had no room beside its
# neighbour, which is why the modes used to run one per row.
_MODES_COL_W = 236
# It can still be dragged narrower than that, but not past the point where a
# tile stops holding its label: "Make Report" is 66px at 11px type, a tile pads
# it by 3px a side, and the column adds a 7px gutter and 14px margins.
_MODES_COL_MIN_W = 2 * (66 + 6) + 7 + 28
_ORB_COL_W = 700
_CHAT_COL_W = 600
# Chat and diagnosis split what is left when the diagnosis column is open.
_CHAT_COL_W_DIAG = 340
_DIAG_COL_W = 400

# The orb's own drawing aspect, taken from its canvas so the two cannot drift.
_ORB_ASPECT = _CANVAS_H / _CANVAS_W

# Column width less its 14px side margins and the DB label's own 8px padding
# and 1px border.
_DB_NAME_W = _MODES_COL_W - 48

# (icon, label, input prefix, orb state, mode) for the mode column.
_ACTIONS = [
    ("🔍", "Find Docs",   "Find in document DB about: ",    1, "chat"),
    ("📝", "Make Report", "Create operation report about: ", 3, "chat"),
    ("🔬", "Diagnose",    "",                                2, "diagnose"),
    ("💬", "Ask",         "",                                0, "chat"),
    # 📇 rather than the 🪪 this used to carry: Segoe UI Emoji has no glyph for
    # 🪪, so it drew as an empty box. This is also the icon proposal E gives it.
    ("📇", "Quick Card",  "",                                1, "quickcard"),
    ("🔧", "Work Pack",   "",                                1, "workpackage"),
    # State 5 rather than the 2 this used to share with Diagnose: it is the warm
    # red->yellow one, and Trend Data was the mode with no look of its own.
    ("📈", "Trend Data",  "",                                5, "trend"),
]

# What a mode button puts in front of the question. It is an instruction to
# Claude, not something to look for in the documents, so the orb's highlight
# takes it back off: searching for "Find in document DB about: X" asks the DB
# for files containing the word "Find", which is noise at best and, when every
# word has to match, drowns out X entirely.
_MODE_PREFIXES = tuple(sorted(
    (prefix for _icon, _label, prefix, _state, _mode in _ACTIONS if prefix),
    key=len, reverse=True,
))


def _strip_mode_prefix(msg: str) -> str:
    """The question a mode button asked, without the instruction it added."""
    for prefix in _MODE_PREFIXES:
        if msg.startswith(prefix):
            return msg[len(prefix):].strip()
    return msg

# Given the full width of the column and its own accent colour rather than a
# slot in the grid: it is the mode the tab opens in and the one every other mode
# falls back to when it finishes or is refused.
_PRIMARY_MODE = "Ask"

# Tile geometry, from proposal E: a 44px primary over a 2-column grid of 52px
# tiles with 7px between them.
_MODE_PRIMARY_H = 44
_MODE_TILE_H = 52
_MODE_GAP = 7
_MODE_ICON_PX = 15

# Colours are proposal E's tokens: panel #111823 on line #1e2b3a, labels in
# ink-2 #93a7bd, and the accent gradient for the primary. E paints one tile in
# its "hot" state -- border #2a4a63, label lifted to ink #e6eef8 -- which is the
# treatment used on hover here, since a still mockup has no other way to show a
# tile responding to the pointer.
_MODE_STYLE = """
    QToolButton {
        background: #111823; color: #93a7bd;
        border: 1px solid #1e2b3a; border-radius: 10px;
        font-size: 11px; padding: 0 3px;
    }
    QToolButton:hover   { background: #16202e; border-color: #2a4a63;
                          color: #e6eef8; }
    QToolButton:pressed { background: #0d141d; }
"""

_PRIMARY_MODE_STYLE = """
    QPushButton {
        background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                    stop: 0 #2ad0b8, stop: 1 #17a894);
        color: #05201c; border: none; border-radius: 10px;
        font-size: 14px; font-weight: 600;
    }
    QPushButton:hover   {
        background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                    stop: 0 #43e0c8, stop: 1 #1cbda6);
    }
    QPushButton:pressed { background: #17a894; }
"""

_DB_BTN_STYLE = """
    QPushButton {
        background: #0d2236; color: #7dd3fc;
        border: 1px solid #1e4d72; border-radius: 5px; font-size: 12px;
    }
    QPushButton:hover { background: #1a3a5c; }
"""

_DB_BTN_CLEAR_STYLE = """
    QPushButton {
        background: #0d1b2a; color: #64809c;
        border: 1px solid #1a2535; border-radius: 5px; font-size: 12px;
    }
    QPushButton:hover { background: #2a1215; color: #f87171;
                        border-color: #5c2a2f; }
"""


def _extract_doc_codes(text: str) -> list[str]:
    """Document codes cited in an answer, in first-mention order, deduplicated."""
    seen: dict[str, None] = {}
    for code in _DOC_CODE_RE.findall(text or ""):
        seen.setdefault(code, None)
    return list(seen)


def _build_doc_lookup(files: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """(UPPERCASE name, path) pairs for resolving cited codes to real files.

    Built from the file list the orb already loads, so selecting a DB costs no
    extra query. Matching on the file name rather than the doc_number column is
    deliberate: it keeps working on DBs that have no such column, and it still
    catches the ~3% of files whose name puts a sequence number or a note in
    front of the code."""
    return [(name.upper(), path) for name, path in files if name and path]


def _resolve_cited_sources(
    lookup: list[tuple[str, str]], codes: list[str]
) -> list[tuple[str, str]]:
    """(code, path) for the files whose name carries one of the cited codes.

    The code travels with the path so the orb markers and the cards under it are
    built from one traversal: two passes could disagree about which citations
    landed, and the panel would then be captioning dots that are not there.
    """
    resolved: list[tuple[str, str]] = []
    seen: set[str] = set()
    for code in codes:
        hits = [path for name, path in lookup if code in name]
        if not hits or len(hits) > _MAX_PATHS_PER_CITATION:
            continue
        for path in hits:
            if path not in seen:
                seen.add(path)
                resolved.append((code, path))
    return resolved


def _diagnosis_sources(data: dict) -> list[CitedSource]:
    """Evidence from every cause in tree order, one card per distinct quote.

    The same document is often cited by more than one cause; the quote is what
    makes an entry worth its own card, so that is what deduplicates.
    """
    out: list[CitedSource] = []
    seen: set[tuple[str, str]] = set()
    for cause in (data.get("causes") or []):
        for e in (cause.get("evidence") or []):
            code = str(e.get("doc_number") or "").strip()
            quote = str(e.get("quote") or "").strip()
            if not code or (code, quote) in seen:
                continue
            seen.add((code, quote))
            out.append(CitedSource(
                code=code,
                section=str(e.get("section") or "").strip(),
                quote=quote,
                verified=e.get("verified"),
            ))
    return out


# A word carrying no search value once it is on its own: FTS5 reads ":" as a
# column filter and the rest as operators, so a term containing one is a syntax
# error that takes the whole query down with it rather than just itself.
_FTS_PUNCT = ':"()*^-,.?!;'

# Words per LIKE scan. Each one is another substring pass over an 800MB content
# column, and past a handful the scan costs more than the extra precision buys.
_MAX_LIKE_WORDS = 6


def _fts_terms(keyword: str) -> list[str]:
    """The words of a search, cleaned of characters FTS5 reads as syntax."""
    return [w for w in (t.strip(_FTS_PUNCT) for t in keyword.split()) if w]


def _like_paths(cur, words: list[str], joiner: str, limit: int) -> list[str]:
    """Files whose name or content contains the words, all of them or any."""
    cond = f" {joiner} ".join(["(f.name LIKE ? OR f.content LIKE ?)"] * len(words))
    args: list = []
    for w in words:
        args += [f"%{w}%", f"%{w}%"]
    cur.execute(
        f"SELECT f.path FROM files f WHERE ({cond}) AND f.name != 'BASE_PATH' "
        f"LIMIT ?",
        (*args, limit),
    )
    return [r[0] for r in cur.fetchall() if r[0]]


def _query_search_paths(db_path: str, keyword: str, limit: int = 8000) -> list[str]:
    """Paths of every file matching the search, for lighting up the orb.

    The cap is deliberately high: the highlight has to show truthfully where
    hits sit across the whole document set, and a small cap would silently
    under-light entire regions of the orb.

    Two routes, because the DBs this opens are not all built alike. One carries
    chunks and an FTS index; the one in daily use is a single `files` table with
    no index at all, so on that one the FTS query raises and every search comes
    down to the LIKE below. That made the fallback the main path, and it was
    matching the whole question as one literal substring -- so anything longer
    than a phrase that appears verbatim in a document found nothing at all and
    the orb went dark. Matching word by word is what makes a real question
    answerable: all of the words first, and only if nothing holds all of them,
    any of them.
    """
    terms = _fts_terms(keyword)
    fts_query = " OR ".join(f"{w}*" for w in terms)
    try:
        with closing(sqlite3.connect(db_path)) as conn:
            cur = conn.cursor()
            try:
                if fts_query:
                    cur.execute(
                        """
                        SELECT DISTINCT f.path
                        FROM files f
                        WHERE f.id IN (
                            SELECT c.file_id FROM chunks c
                            WHERE c.id IN (
                                SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?
                            )
                        )
                          AND f.name != 'BASE_PATH'
                        LIMIT ?
                        """,
                        (fts_query, limit),
                    )
                    rows = cur.fetchall()
                    if rows:
                        return [r[0] for r in rows if r[0]]
            except Exception:
                pass

            words = terms[:_MAX_LIKE_WORDS] or [keyword.strip()]
            # Narrow first. A file holding every word of the question is what
            # was asked for; widening to any of them is the consolation prize,
            # and offering it first would light half the orb on the strength of
            # one common word.
            return (_like_paths(cur, words, "AND", limit)
                    or _like_paths(cur, words, "OR", limit))
    except Exception:
        return []


class _HighlightWorker(QThread):
    """Runs _query_search_paths off the UI thread.

    On the real DB this query takes up to ~0.5s, which would stall the window
    at the exact moment the user hits Enter.
    """

    found = Signal(list)

    def __init__(self, db_path: str, keyword: str, parent=None):
        super().__init__(parent)
        self._db_path = db_path
        self._keyword = keyword

    def run(self) -> None:
        self.found.emit(_query_search_paths(self._db_path, self._keyword))


class _DbSnapshot(NamedTuple):
    """Everything the orb needs from a DB, read in a single pass.

    `error` is the whole point of this type: an unreadable DB and an empty one
    both yield zero documents, but they must not look alike in the UI. Without
    the distinction a wrong or corrupt file reports itself as loaded while the
    orb falls back to its full-density decorative layout -- so the app appears
    to hold more data than a real DB does, and the user has no way to tell.
    """

    total_docs: int
    files: list[tuple[str, str]]
    base_path: str
    error: str  # "" when the DB was read successfully


def _read_db_snapshot(db_path: str, safety_cap: int = 50000) -> _DbSnapshot:
    """Read document count, file list and BASE_PATH over one connection.

    Every file is fetched (not sampled) so the orb can assign all of them to
    neurons -- grouping several files per neuron when there are more files than
    neurons -- and none get dropped. safety_cap only guards against an
    unexpectedly huge DB.
    """
    try:
        with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
            cur = conn.cursor()

            cur.execute("SELECT COUNT(*) FROM files WHERE name != 'BASE_PATH'")
            row = cur.fetchone()
            total = (row[0] if row else 0) or 0

            cur.execute(
                "SELECT name, path FROM files WHERE name != 'BASE_PATH' LIMIT ?",
                (safety_cap,),
            )
            files = cur.fetchall()

            cur.execute("SELECT path FROM files WHERE name = 'BASE_PATH'")
            row = cur.fetchone()
            base = row[0] if row else ""

        return _DbSnapshot(total, files, base, "")
    except Exception as exc:
        return _DbSnapshot(0, [], "", str(exc) or exc.__class__.__name__)


_EMPTY_DB_SNAPSHOT = _DbSnapshot(0, [], "", "")

# (text, background, border) for each state the DB label can be in.
# Dark palette: the DB row sits under the orb, on the dark column, because the
# orb IS this database drawn out -- the label naming it belongs beside it rather
# than at the top of the white chat pane.
_DB_LABEL_NONE = ("#64809c", "#0d1b2a", "#1a2535")  # nothing selected
_DB_LABEL_OK = ("#c3d3e3", "#0d2236", "#1e4d72")    # readable, has documents
_DB_LABEL_BAD = ("#fbbf24", "#231603", "#4a3a14")   # unreadable, or indexed nothing


def _column_header(text: str) -> QLabel:
    """Section caption in the left column ("SOURCE", "MODE")."""
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color: #64809c; font-size: 10px; font-weight: 600;"
        "letter-spacing: 1px; background: transparent; padding-left: 2px;"
    )
    return lbl


def _emoji_icon(ch: str, px: int) -> QIcon:
    """An emoji as an icon, so a mode tile can size its glyph apart from its label.

    A button carries one font for the whole of its text, so an "icon over
    label" string would draw both at the same size -- and proposal E draws the
    glyph at 15px over an 11px label. Handing the glyph over as an icon lets
    setIconSize decide it. Rendered at twice the size and marked as such so it
    stays sharp on a scaled display.
    """
    scale = 2
    pm = QPixmap(px * scale, px * scale)
    pm.setDevicePixelRatio(scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    font = QFont("Segoe UI Emoji")
    font.setPixelSize(px)
    p.setFont(font)
    p.drawText(QRectF(0, 0, px, px), Qt.AlignCenter, ch)
    p.end()
    return QIcon(pm)


def _db_label_style(fg: str, bg: str, border: str) -> str:
    return (
        f"color: {fg}; font-size: 11px;"
        f"background: {bg}; border: 1px solid {border};"
        "border-radius: 6px; padding: 2px 8px;"
    )


def _bundled_claude() -> str:
    """Đường dẫn bundled claude.exe đi kèm claude_agent_sdk."""
    try:
        import claude_agent_sdk
        p = Path(claude_agent_sdk.__file__).parent / "_bundled" / (
            "claude.exe" if sys.platform == "win32" else "claude"
        )
        if p.exists():
            return str(p)
    except Exception:
        pass
    return "claude"


class _OrbColumn(QWidget):
    """Column that holds the orb to the top at exactly the size it draws.

    NeuralOrbWidget scales to min(w/620, h/560) and centres the result, so a box
    taller than that ratio pads the orb with dead space above and below. Giving
    the box the drawing's own aspect removes the padding: the orb sits at the top
    of the column and every pixel below it is free for the citation cards.
    """

    # Left below the orb on a short window, so the legend and the cited cards
    # are not squeezed to nothing before the orb gives anything up.
    _MIN_BELOW = 150

    def __init__(self, orb: QWidget, parent=None):
        super().__init__(parent)
        # Qt fills a stylesheet background for a plain QWidget but not for a
        # subclass of one, so without this the column's own colour is dropped and
        # whatever the active theme paints behind it shows through instead.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._orb = orb
        self._orb_h = 0

    def resizeEvent(self, event):  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        # Exactly the height the drawing uses at this width, so there is no dead
        # padding and the orb sits flush at the top -- unless the column is too
        # short to afford that, in which case the orb shrinks before the cards do.
        # The floor stays well under _MIN_BELOW so this stays solvable: the
        # height asked for here is always less than the height it is read from,
        # which is what keeps the column able to shrink into a short window.
        h = min(round(self.width() * _ORB_ASPECT),
                max(80, self.height() - self._MIN_BELOW))
        # Guarded: setFixedHeight relayouts, and an unguarded write would keep
        # answering its own resize.
        if h != self._orb_h:
            self._orb_h = h
            self._orb.setFixedHeight(h)


class TrendDataDialog(QDialog):
    """Dialog dán dữ liệu trend/log nhiều dòng + mô tả triệu chứng để chẩn đoán."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📈 Trend / Log Data Analysis")
        self.resize(580, 440)

        lay = QVBoxLayout(self)
        lay.setSpacing(6)

        lbl_sym = QLabel("Fault symptom (short description):")
        self.inp_symptom = QLineEdit()
        self.inp_symptom.setPlaceholderText("e.g. IDF-A bearing vibration rising")
        lay.addWidget(lbl_sym)
        lay.addWidget(self.inp_symptom)

        lbl_data = QLabel("Trend / log data (paste from DCS trend, Excel log sheet…):")
        self.inp_data = QTextEdit()
        self.inp_data.setAcceptRichText(False)
        self.inp_data.setPlaceholderText(
            "Time\tTag\tValue\n"
            "02:00\tIDF-A brg vib\t4.2 mm/s\n"
            "02:30\tIDF-A brg vib\t6.8 mm/s\n"
            "(paste bảng số liệu — giữ nguyên cột/tab)"
        )
        self.inp_data.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        lay.addWidget(lbl_data)
        lay.addWidget(self.inp_data, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("🔬 Analyze")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._on_ok)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        lay.addLayout(btn_row)

    def _on_ok(self):
        if not self.inp_symptom.text().strip():
            QMessageBox.warning(self, "Missing symptom",
                                "Please enter a short fault symptom description.")
            return
        if not self.inp_data.toPlainText().strip():
            QMessageBox.warning(self, "Missing data",
                                "Please paste the trend / log data to analyze.")
            return
        self.accept()

    def values(self) -> tuple[str, str]:
        return self.inp_symptom.text().strip(), self.inp_data.toPlainText().strip()


class ClaudeAssistantWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: AgentWorker | None = None
        self._response_started = False
        self._db_path: str = ""
        self._orb_view: NeuralOrbWidget | None = None
        self._hl_seq: int = 0
        self._doc_lookup: list[tuple[str, str]] = []  # (UPPERCASE name, path)
        self._mode: str = "chat"          # "chat" | "diagnose" | "report"
        self._resp_buffer: str = ""       # gom full text để parse JSON chẩn đoán
        self._diag_retried: bool = False  # đã thử retry JSON 1 lần chưa
        self._cur_symptom: str = ""       # triệu chứng của lượt chẩn đoán hiện tại

        # Where in the chat document the answer being streamed begins, so that
        # the plain text shown while it arrives can be swapped for the rendered
        # markdown once it is complete. -1 means no answer is open.
        self._ans_start: int = -1
        self._tool_counts: dict[str, int] = {}   # tools this answer used
        self._cited_codes: frozenset[str] = frozenset()  # codes that resolved

        # Idle timer — sau khi hoàn thành/lỗi, orb tự về REST sau vài giây
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(lambda: self._set_jarvis(0))

        # Streaming intensity — đếm ký tự token, throttle 200ms đẩy 1 lần sang orb
        self._stream_chars = 0
        self._stream_timer = QTimer(self)
        self._stream_timer.setInterval(200)
        self._stream_timer.timeout.connect(self._pump_stream_intensity)

        self._build_ui()

        # Khôi phục DB đã import lần trước (không ghi lại file)
        saved = _load_saved_db_path()
        if saved:
            self._apply_db_path(saved, persist=False)

    # ── Build UI ──────────────────────────────────────────────────────
    def _build_ui(self):
        self.setStyleSheet("ClaudeAssistantWidget { background: #02040b; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header (full width, dark) ─────────────────────────────
        hdr_w = QWidget()
        hdr_w.setFixedHeight(44)
        hdr_w.setStyleSheet(
            "background: #06090f; border-bottom: 1px solid #1a2535;"
        )
        hdr = QHBoxLayout(hdr_w)
        hdr.setContentsMargins(12, 0, 12, 0)
        hdr.setSpacing(8)

        self._orb = PulsingOrb()

        lbl_title = QLabel("Assistant")
        lbl_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lbl_title.setStyleSheet("color: #88ccff; background: transparent;")

        self._lbl_status = QLabel("✅  Claude Code session")
        self._lbl_status.setStyleSheet(
            "color: #16a34a; font-size: 11px; background: transparent;"
        )

        self._btn_login = QPushButton("🔑 Login")
        self._btn_login.setFixedHeight(26)
        self._btn_login.setToolTip("Open Claude Code login window")
        self._btn_login.setStyleSheet("""
            QPushButton {
                background: #0d2236; color: #7dd3fc;
                border: 1px solid #1e4d72; border-radius: 5px;
                font-size: 11px; padding: 0 8px;
            }
            QPushButton:hover { background: #1a3a5c; }
        """)
        self._btn_login.clicked.connect(self._on_login)

        hdr.addWidget(self._orb)
        hdr.addWidget(lbl_title)
        hdr.addStretch()
        hdr.addWidget(self._btn_login)
        hdr.addWidget(self._lbl_status)
        root.addWidget(hdr_w)

        # ── Splitter: Modes | Orb | Chat | Diagnosis ─────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #1a2535; }")

        splitter.addWidget(self._build_modes_column())
        splitter.addWidget(self._build_orb_column())

        # Right — chat panel (white)
        right = QWidget()
        right.setStyleSheet("background: #ffffff;")
        r_lay = QVBoxLayout(right)
        r_lay.setContentsMargins(10, 8, 10, 8)
        r_lay.setSpacing(6)

        # System prompt row
        sp_row = QHBoxLayout()
        sp_lbl = QLabel("System:")
        sp_lbl.setFixedWidth(52)
        sp_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        self._inp_system = QLineEdit()
        self._inp_system.setPlaceholderText(
            "You are a smart assistant. Answer in English."
        )
        self._inp_system.setStyleSheet("""
            QLineEdit {
                background: #f8fafc; border: 1px solid #e2e8f0;
                border-radius: 6px; color: #334155;
                padding: 3px 8px; font-size: 11px;
            }
            QLineEdit:focus { border-color: #6366f1; }
        """)
        sp_row.addWidget(sp_lbl)
        sp_row.addWidget(self._inp_system, 1)
        r_lay.addLayout(sp_row)

        # Chat history. A browser rather than a plain edit: answers carry
        # document codes, and only a browser reports a click on one so the file
        # behind it can be opened.
        self._chat = QTextBrowser()
        self._chat.setOpenLinks(False)        # 'doc:' is ours, not the shell's
        self._chat.setOpenExternalLinks(False)
        self._chat.anchorClicked.connect(self._on_chat_anchor)
        self._chat.setReadOnly(True)
        self._chat.setFont(QFont("Segoe UI", 12))
        self._chat.setStyleSheet("""
            QTextBrowser {
                background: #f8fafc; border: 1px solid #e2e8f0;
                border-radius: 8px; color: #1e293b; padding: 10px;
            }
        """)
        r_lay.addWidget(self._chat, 1)

        # Input bar
        input_row = QHBoxLayout()
        self._inp_msg = QLineEdit()
        self._inp_msg.setPlaceholderText("Type a question… (Enter to send)")
        self._inp_msg.setFixedHeight(36)
        self._inp_msg.setStyleSheet("""
            QLineEdit {
                background: #ffffff; border: 1px solid #cbd5e1;
                border-radius: 8px; color: #1e293b;
                padding: 0 10px; font-size: 13px;
            }
            QLineEdit:focus { border-color: #6366f1; }
        """)
        self._inp_msg.returnPressed.connect(self._on_send)

        self._btn_send = QPushButton("📤  Send")
        self._btn_send.setFixedSize(88, 36)
        self._btn_send.setStyleSheet("""
            QPushButton {
                background: #6366f1; color: white;
                border: none; border-radius: 8px;
                font-weight: 600; font-size: 13px;
            }
            QPushButton:hover    { background: #4f46e5; }
            QPushButton:pressed  { background: #4338ca; }
            QPushButton:disabled { background: #c7d2fe; color: #ffffff; }
        """)
        self._btn_send.clicked.connect(self._on_send)

        self._btn_clear = QPushButton("🗑")
        self._btn_clear.setFixedSize(36, 36)
        self._btn_clear.setToolTip("Clear chat")
        self._btn_clear.setStyleSheet("""
            QPushButton {
                background: #f1f5f9; border: 1px solid #e2e8f0;
                border-radius: 8px; color: #64748b; font-size: 14px;
            }
            QPushButton:hover {
                background: #fee2e2; color: #dc2626; border-color: #fca5a5;
            }
        """)
        self._btn_clear.clicked.connect(self._clear_chat)

        input_row.addWidget(self._inp_msg, 1)
        input_row.addWidget(self._btn_send)
        input_row.addWidget(self._btn_clear)
        r_lay.addLayout(input_row)

        splitter.addWidget(right)

        # Panel chẩn đoán (Co-Pilot Sự Cố) — ẩn cho tới khi vào chế độ chẩn đoán
        self._diag_panel = DiagnosisPanel()
        self._diag_panel.set_db_path(self._db_path)
        self._diag_panel.generate_report.connect(self._on_generate_report)
        self._diag_panel.hide()
        splitter.addWidget(self._diag_panel)

        self._splitter = splitter
        # Only the chat column stretches. The two left columns hold a fixed
        # layout and the orb column IS the orb's size, so growing the window
        # must not feed width into them.
        for i, stretch in enumerate((0, 0, 1, 0)):
            splitter.setStretchFactor(i, stretch)
        splitter.setSizes([_MODES_COL_W, _ORB_COL_W, _CHAT_COL_W, 0])
        root.addWidget(splitter, 1)

    def _build_modes_column(self) -> QWidget:
        """The seven modes, lifted out from under the orb into their own column.

        Laid out as proposal E draws them: Ask across the full width in the
        accent colour, then the other six as a two-column grid of tiles with
        the icon stacked over the label. Ask is the mode the tab opens in and
        the one every other mode falls back to, so it reads as the default
        rather than as the fourth cell of a grid.

        The six keep the order they have in _ACTIONS, which fills the grid the
        way E has it -- Find Docs beside Make Report, Diagnose beside Quick
        Card, Work Pack beside Trend Data.
        """
        col = QWidget()
        col.setStyleSheet("background: #06090f;")
        col.setMinimumWidth(_MODES_COL_MIN_W)
        lay = QVBoxLayout(col)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(_MODE_GAP)

        lay.addWidget(_column_header("SOURCE"))
        lay.addWidget(self._build_db_row())
        lay.addSpacing(6)
        lay.addWidget(_column_header("MODE"))

        by_label = {a[1]: a for a in _ACTIONS}
        lay.addWidget(self._build_mode_button(by_label[_PRIMARY_MODE]))

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)  # the column's own spacing sets the gap
        grid.setSpacing(_MODE_GAP)
        rest = [a for a in _ACTIONS if a[1] != _PRIMARY_MODE]
        for i, action in enumerate(rest):
            grid.addWidget(self._build_mode_button(action), i // 2, i % 2)
        lay.addLayout(grid)

        lay.addStretch(1)
        return col

    def _build_mode_button(self, action: tuple) -> QWidget:
        """One mode: the primary as a wide button, the rest as grid tiles."""
        icon, label, prefix, state, mode = action
        if label == _PRIMARY_MODE:
            btn = QPushButton(f"{icon}  {label}")
            btn.setFixedHeight(_MODE_PRIMARY_H)
            btn.setStyleSheet(_PRIMARY_MODE_STYLE)
        else:
            btn = QToolButton()
            btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            btn.setIcon(_emoji_icon(icon, _MODE_ICON_PX))
            btn.setIconSize(QSize(_MODE_ICON_PX + 3, _MODE_ICON_PX + 3))
            btn.setText(label)
            btn.setFixedHeight(_MODE_TILE_H)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet(_MODE_STYLE)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(
            lambda _checked=False, p=prefix, s=state, m=mode:
            self._on_action(p, s, m)
        )
        return btn

    def _build_orb_column(self) -> QWidget:
        """The orb, and under it the controls that aim it.

        Everything here is about one database: the orb is that DB laid out, and
        the band below is how you point at part of it -- a search box and a
        folder legend, both answered in the orb's own highlight. The orb is
        pinned to the top at its drawn size rather than centred, so the height
        it is not using goes to the bottom instead of to padding.

        The cited-sources panel survives for diagnoses only. A diagnosis card
        carries a section, a quote and a verified flag, none of which exist
        anywhere else; a chat answer's card carried a code the answer text had
        already printed and linked, so for chat it said nothing twice.
        """
        self._orb_view = NeuralOrbWidget()
        self._orb_view.neuron_clicked.connect(self._open_orb_file)
        self._orb_base_path = ""

        col = _OrbColumn(self._orb_view)
        col.setStyleSheet("background: #02040b;")
        # A minimum, not a fixed width: the splitter handle still works, so the
        # orb can be made bigger by hand as it always could. What is fixed is
        # that nothing else takes width from it on its own.
        col.setMinimumWidth(200)
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Stretch 0: its height comes from the column's width, not from whatever
        # is left over once the panels below have taken theirs.
        lay.addWidget(self._orb_view, 0)

        self._orb_controls = OrbControls()
        self._orb_controls.search_changed.connect(self._highlight_search_hits)
        self._orb_controls.folder_picked.connect(self._highlight_folder)
        lay.addWidget(self._orb_controls, 0)

        self._sources_panel = CitedSourcesPanel()
        self._sources_panel.set_db_path(self._db_path)
        # Stretch 1 against a maximum the panel sets from its own content: it
        # grows to fit its cards and no further, and on a short window the
        # layout can still take height back from it rather than clip it.
        lay.addWidget(self._sources_panel, 1)

        # Whatever height none of the three claims ends up here, at the bottom,
        # rather than being shared out as padding between them.
        lay.addStretch(0)

        return col

    def _build_db_row(self) -> QWidget:
        """Which database everything on this tab is answering from.

        Stacked rather than in one row: at this column width a name, a count and
        two buttons side by side would leave the file name a few dozen pixels and
        nothing readable in them.
        """
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self._lbl_db = QLabel("No DB selected")
        self._lbl_db.setStyleSheet(_db_label_style(*_DB_LABEL_NONE))

        # The document count, stated rather than left in a tooltip: it is what
        # separates a DB that loaded from one that opened and held nothing.
        self._lbl_db_count = QLabel("")
        self._lbl_db_count.setStyleSheet(
            "color: #64809c; font-size: 10px; background: transparent;"
            "padding-left: 2px;"
        )

        self._btn_pick_db = QPushButton("📂  Select DB")
        self._btn_pick_db.setFixedHeight(26)
        self._btn_pick_db.setToolTip("Select DB")
        self._btn_pick_db.setCursor(Qt.PointingHandCursor)
        self._btn_pick_db.setStyleSheet(_DB_BTN_STYLE)
        self._btn_pick_db.clicked.connect(self._pick_db)

        self._btn_clear_db = QPushButton("✕")
        self._btn_clear_db.setFixedSize(26, 26)
        self._btn_clear_db.setToolTip("Clear DB")
        self._btn_clear_db.setCursor(Qt.PointingHandCursor)
        self._btn_clear_db.setStyleSheet(_DB_BTN_CLEAR_STYLE)
        self._btn_clear_db.clicked.connect(self._clear_db)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(6)
        btn_row.addWidget(self._btn_pick_db, 1)
        btn_row.addWidget(self._btn_clear_db)

        lay.addWidget(self._lbl_db)
        lay.addWidget(self._lbl_db_count)
        lay.addLayout(btn_row)
        return box

    # ── JARVIS orb control ────────────────────────────────────────────
    def _set_jarvis(self, state: int):
        # Mọi lần đổi state đều dừng idle timer; chỉ _schedule_idle() mới hẹn về REST
        if state != 0:
            self._idle_timer.stop()
        if self._orb_view is not None:
            self._orb_view.setS(state)

    def _schedule_idle(self, delay_ms: int = 6000):
        """Hẹn orb tự về REST sau khi không còn hoạt động."""
        self._idle_timer.start(delay_ms)

    def _pump_stream_intensity(self):
        """Throttle 200ms: quy đổi số ký tự token đã nhận → cường độ orb (0..1)."""
        chars = self._stream_chars
        self._stream_chars = 0
        if chars <= 0:
            return
        intensity = min(1.0, chars / 25.0)  # ~25 ký tự/200ms = full intensity
        if self._orb_view is not None:
            self._orb_view.stream_pulse(intensity)

    # ── Helpers ───────────────────────────────────────────────────────
    def _on_action(self, prefix: str, state: int, mode: str = "chat"):
        """Bấm action button: đổi orb state + chế độ + pre-fill input."""
        self._set_jarvis(state)
        self._mode = mode

        if mode == "diagnose":
            if not self._db_path:
                self._append(
                    '<p style="color:#dc2626;margin:4px 0">'
                    '⚠️ Please select a DB file before diagnosing.</p>'
                )
            self._show_diag_panel(True)
            last = copilot.load_last_diagnosis()
            if last and last.get("causes"):
                self._diag_panel.set_diagnosis(last, restored=True)
            else:
                self._diag_panel.reset()
            self._inp_msg.clear()
            self._inp_msg.setPlaceholderText("Describe the fault symptom… (Enter to diagnose)")
        elif mode == "quickcard":
            self._show_diag_panel(False)
            if not self._db_path:
                self._append(
                    '<p style="color:#dc2626;margin:4px 0">'
                    '⚠️ Please select a DB file first.</p>'
                )
            self._inp_msg.clear()
            self._inp_msg.setPlaceholderText("Enter equipment name… (Enter to build card)")
        elif mode == "workpackage":
            self._show_diag_panel(False)
            if not self._db_path:
                self._append(
                    '<p style="color:#dc2626;margin:4px 0">'
                    '⚠️ Please select a DB file first.</p>'
                )
            self._inp_msg.clear()
            self._inp_msg.setPlaceholderText(
                "Describe the job… e.g. Replace IDF-A bearing (Enter to build package)"
            )
        elif mode == "trend":
            if not self._db_path:
                self._mode = "chat"
                self._append(
                    '<p style="color:#dc2626;margin:4px 0">'
                    '⚠️ Please select a DB file before analyzing trend data.</p>'
                )
                return
            dlg = TrendDataDialog(self)
            if dlg.exec() == QDialog.Accepted:
                symptom, data_text = dlg.values()
                self._run_trend_diagnosis(symptom, data_text)
            else:
                self._mode = "chat"
                self._set_jarvis(0)
            return
        else:
            self._show_diag_panel(False)
            self._inp_msg.setPlaceholderText("Type a question… (Enter to send)")
            self._inp_msg.setText(prefix)
            self._inp_msg.setCursorPosition(len(prefix))

        self._inp_msg.setFocus()

    def _show_diag_panel(self, show: bool):
        """Open/close the diagnosis column, taking its width from chat only.

        The orb column keeps _ORB_COL_W in both states: it used to be squeezed
        to 260 here, which quietly shrank the orb -- and with it the click target
        on every neuron -- the moment diagnosis opened.
        """
        if show:
            self._diag_panel.show()
            self._splitter.setSizes(
                [_MODES_COL_W, _ORB_COL_W, _CHAT_COL_W_DIAG, _DIAG_COL_W]
            )
        else:
            self._diag_panel.hide()
            self._splitter.setSizes([_MODES_COL_W, _ORB_COL_W, _CHAT_COL_W, 0])

    def _apply_db_path(self, path: str, persist: bool = True):
        """Cập nhật state + UI + (tuỳ chọn) lưu xuống JSON. path='' = clear."""
        self._db_path = path
        self._diag_panel.set_db_path(path)
        self._sources_panel.set_db_path(path)

        snap = _read_db_snapshot(path) if path else _EMPTY_DB_SNAPSHOT
        self._show_db_status(path, snap)

        if persist:
            _save_db_path(path)
        if self._orb_view is not None:
            self._orb_base_path = snap.base_path
            self._doc_lookup = _build_doc_lookup(snap.files)
            self._orb_view.set_documents(snap.total_docs, snap.files)
            self._update_orb_legend()
            self._clear_answer_sources()

    def _show_db_status(self, path: str, snap: _DbSnapshot) -> None:
        """Put the DB label in the state the data actually justifies.

        A DB that failed to open, and one that opened with nothing indexed in
        it, must not look like a loaded DB. The orb falls back to its default
        decorative layout in both cases -- which is denser than a real small DB
        renders -- so a green "selected" label beside it would read as "loaded"
        when in fact no document is reachable.
        """
        if not path:
            text, tip, colors = "No DB selected", "", _DB_LABEL_NONE
            count = ""
        elif snap.error:
            text = f"⚠ {os.path.basename(path)}"
            tip = f"{path}\n\nCould not read this database:\n{snap.error}"
            colors = _DB_LABEL_BAD
            count = "could not be read"
        elif snap.total_docs == 0:
            text = f"⚠ {os.path.basename(path)}"
            tip = f"{path}\n\nOpened, but it contains no indexed documents."
            colors = _DB_LABEL_BAD
            count = "no documents indexed"
        else:
            text = os.path.basename(path)
            tip = f"{path}\n\n{snap.total_docs:,} documents indexed."
            colors = _DB_LABEL_OK
            count = f"{snap.total_docs:,} documents"

        # Elided against the column's own width rather than the label's: this
        # runs before the first layout, when the label does not have one yet.
        fm = QFontMetrics(self._lbl_db.font())
        self._lbl_db.setText(fm.elidedText(text, Qt.ElideMiddle, _DB_NAME_W))
        self._lbl_db.setToolTip(tip)
        self._lbl_db.setStyleSheet(_db_label_style(*colors))
        self._lbl_db_count.setText(count)
        self._lbl_db_count.setToolTip(tip)

    def _update_orb_legend(self) -> None:
        """Hand the folder breakdown to the control band under the orb."""
        legend = self._orb_view.folder_legend if self._orb_view is not None else []
        self._orb_controls.set_legend(legend)

    def _abs_source_path(self, relative_path: str) -> str:
        """Where a file the DB lists actually is on disk.

        `files.path` is stored relative to the BASE_PATH row, so a value taken
        straight from that column exists nowhere. Everything that opens a source
        file resolves it here -- the orb's neurons, the cited-source cards and
        the document codes inside an answer all read the same column, and each
        place that joined it by hand was one more place to forget to.
        """
        if not relative_path or os.path.isabs(relative_path):
            return relative_path
        return (os.path.join(self._orb_base_path, relative_path)
                if self._orb_base_path else relative_path)

    def _open_orb_file(self, name: str, relative_path: str) -> None:
        abs_path = self._abs_source_path(relative_path)
        if abs_path and os.path.exists(abs_path):
            try:
                os.startfile(abs_path)  # type: ignore[attr-defined]
            except Exception:
                pass

    def _pick_db(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select DB file", "", "SQLite DB (*.db *.sqlite)"
        )
        if path:
            self._apply_db_path(path)

    def _clear_db(self):
        self._apply_db_path("")

    def _highlight_search_hits(self, keyword: str) -> None:
        """Light up the orb neurons holding files that match the search."""
        if self._orb_view is None:
            return
        keyword = _strip_mode_prefix(keyword.strip())
        keyword = " ".join(_extract_keywords(keyword)) or keyword.strip()
        self._hl_seq += 1
        if not (self._db_path and keyword):
            self._orb_view.clear_highlight()
            self._orb_controls.set_hits(0)
            return

        seq = self._hl_seq
        worker = _HighlightWorker(self._db_path, keyword, self)
        worker.found.connect(lambda paths, s=seq: self._on_highlight_found(paths, s))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_highlight_found(self, paths: list, seq: int) -> None:
        # Queries finish out of order; a superseded one must not repaint the orb.
        if seq != self._hl_seq or self._orb_view is None:
            return
        self._orb_view.highlight_files(paths)
        # Counted from the orb, not from len(paths): the query can return files
        # this DB's orb was never built with, and the number under it has to
        # mean the same set the gold above it does.
        self._orb_controls.set_hits(len(self._orb_view.highlight_hits()))

    def _highlight_folder(self, name: str) -> None:
        """Light the region of the orb one legend folder occupies.

        No DB query: the orb was handed every file when it was built, so a
        folder is answered from memory and lands in the same frame as the click.
        The sequence still moves, because a search fired a moment ago is still
        in flight and would otherwise arrive and overwrite this.
        """
        if self._orb_view is None:
            return
        self._hl_seq += 1
        if not name:
            self._orb_view.clear_highlight()
            self._orb_controls.set_hits(0)
            return
        self._orb_view.highlight_files(self._orb_view.folder_files(name))
        self._orb_controls.set_hits(len(self._orb_view.highlight_hits()))

    # ── Answer sources (provenance) ─────────────────────────────────────
    def _show_answer_sources(self) -> None:
        """Mark on the orb the documents the finished answer cited, so the
        numbers in it can be traced back to a file and checked.

        The search highlight is dropped at the same time: it answers a different
        question (where the topic lives) and leaving both on would blur which
        documents the answer actually rests on. Only when there is something to
        drop it for, though -- an answer that cites nothing the DB holds would
        otherwise take the gold away and put nothing in its place, leaving a
        blank orb after a question that did find its topic."""
        if self._orb_view is None:
            return
        codes = _extract_doc_codes(self._resp_buffer)
        cited = _resolve_cited_sources(self._doc_lookup, codes) if codes else []

        # Bump the sequence so a search query still in flight cannot land after
        # this and repaint over the sources.
        self._hl_seq += 1
        resolved = self._orb_view.set_source_files([p for _, p in cited])
        if resolved:
            # Empty the control band that asked for the gold too: a box still
            # holding a word the orb is no longer showing would be claiming a
            # highlight it does not own.
            self._orb_view.clear_highlight()
            self._orb_controls.reset()

        # Only files this DB actually holds are counted, so the markers on the
        # orb and the number under it always mean the same set. A code that
        # resolves to nothing stays silent on purpose: an answer may legitimately
        # cite an external standard, and flagging those would cry wolf.
        found = set(resolved)
        shown = [(code, path) for code, path in cited if path in found]
        # A count and a tooltip, not a card each. Every code here is already
        # printed in the answer above and already opens its file when clicked;
        # what the band adds is how many of them the orange markers stand for.
        self._orb_controls.set_cited(sorted({code for code, _ in shown}))
        # Handed to the renderer so a code in the answer text becomes a link
        # only when there is a file behind it to open.
        self._cited_codes = frozenset(code for code, _ in shown)

    def _clear_answer_sources(self) -> None:
        if self._orb_view is not None:
            self._orb_view.clear_sources()
        self._orb_controls.set_cited([])
        self._sources_panel.clear()

    def _on_chat_anchor(self, url) -> None:
        """Click a document code in an answer → open that file.

        Resolved through the same lookup the orb markers and the source cards
        use, so all three agree on which file a code names.
        """
        text = url.toString()
        if not text.startswith(chat_render.DOC_LINK_SCHEME):
            return
        code = text[len(chat_render.DOC_LINK_SCHEME):]
        hits = _resolve_cited_sources(self._doc_lookup, [code])
        path = self._abs_source_path(next((p for _, p in hits if p), ""))
        if not path or not os.path.exists(path):
            QMessageBox.information(
                self, "Not found",
                f"No source file found in this DB for:\n{code}",
            )
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as e:
            QMessageBox.warning(self, "Open file error", str(e))

    def _load_claude_md(self) -> str:
        """Đọc CLAUDE.md cạnh app (theo paths.APP_DIR) làm system context.

        Dùng APP_DIR để khi đóng gói (.exe) chỉ cần copy CLAUDE.md cạnh exe là
        chạy đúng — nhất quán với db_query.py / report_helper.py (Bash cwd=APP_DIR).
        """
        try:
            import paths
            with open(os.path.join(paths.APP_DIR, "CLAUDE.md"), "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""

    def _append(self, html: str):
        self._chat.moveCursor(QTextCursor.End)
        self._chat.insertHtml(html)
        self._chat.moveCursor(QTextCursor.End)

    def _clear_chat(self):
        """Empty the transcript, and forget where the open answer started.

        The position is an offset into the document that just went away; left
        behind, the next answer would be written from a stale one.
        """
        self._chat.clear()
        self._ans_start = -1

    def _set_busy(self, busy: bool):
        self._inp_msg.setEnabled(not busy)
        self._btn_send.setEnabled(not busy)
        self._btn_send.setText("⏳" if busy else "📤  Send")

    # ── Slots ─────────────────────────────────────────────────────────
    def _on_login(self):
        """Mở cửa sổ console chạy 'claude login' để đăng nhập."""
        cli = _bundled_claude()
        if sys.platform == "win32":
            subprocess.Popen(
                [cli, "login"],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            subprocess.Popen([cli, "login"])

    def _on_send(self):
        msg = self._inp_msg.text().strip()
        if not msg:
            return

        # Chế độ chẩn đoán / quick card / work package cần DB
        if self._mode in ("diagnose", "quickcard", "workpackage") and not self._db_path:
            self._append(
                '<p style="color:#dc2626;margin:4px 0">'
                '⚠️ Please select a DB file first.</p>'
            )
            return

        self._inp_msg.clear()
        self._echo_user(msg)
        # The previous answer's sources belong to the previous answer, and so
        # does anything the control band was still pointing at: the question
        # about to be sent is what the orb answers from here.
        self._clear_answer_sources()
        self._orb_controls.reset()
        self._highlight_search_hits(msg)

        system = self._inp_system.text().strip()
        claude_md = self._load_claude_md()

        if self._mode == "diagnose":
            self._diag_retried = False
            self._cur_symptom = msg
            self._diag_panel.set_analyzing(msg)
            diag_system = copilot.build_diagnosis_system_prompt(self._db_path, claude_md)
            merged_system = (diag_system + "\n" + system).strip()
            options = make_options(system_prompt=merged_system, db_path=self._db_path)
            precedent = copilot.build_precedent_block(msg)   # hop ⑤ — đối chiếu ca cũ
            prompt = copilot.build_diagnosis_prompt(msg, precedent)
        elif self._mode == "quickcard":
            qc_system = copilot.build_quickcard_system_prompt(self._db_path, claude_md)
            merged_system = (qc_system + "\n" + system).strip()
            options = make_options(system_prompt=merged_system, db_path=self._db_path)
            prompt = copilot.build_quickcard_prompt(msg)
        elif self._mode == "workpackage":
            wp_system = copilot.build_workpackage_system_prompt(self._db_path, claude_md)
            merged_system = (wp_system + "\n" + system).strip()
            options = make_options(system_prompt=merged_system, db_path=self._db_path)
            prompt = copilot.build_workpackage_prompt(msg)
        elif self._db_path:
            db_system = (
                f'Bạn là trợ lý kỹ thuật Nhà máy Nhiệt điện Van Phong 1 BOT.\n'
                f'File DB tài liệu: "{self._db_path}"\n\n'
                f'Để truy vấn DB, dùng lệnh Bash:\n'
                f'  python db_query.py "{self._db_path}" "SQL query"\n\n'
                f'Ví dụ tìm tài liệu:\n'
                f'  python db_query.py "{self._db_path}" "SELECT name,doc_number,system_code'
                f' FROM files WHERE id IN (SELECT rowid FROM files_fts WHERE files_fts MATCH'
                f" 'IDF*') AND name!='BASE_PATH' LIMIT 10\"\n\n"
                f'Ví dụ tìm nội dung (dùng khi làm báo cáo):\n'
                f'  python db_query.py "{self._db_path}" "SELECT f.name,c.heading,c.content'
                f' FROM chunks c JOIN files f ON f.id=c.file_id WHERE c.id IN'
                f" (SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'IDF*')"
                f' ORDER BY rank LIMIT 8"\n\n'
                f'CHỈ dùng câu lệnh SELECT. Không chạy lệnh shell khác.\n'
            )
            if claude_md:
                db_system = claude_md + "\n\n" + db_system
            merged_system = (db_system + "\n" + system).strip()
            options = make_options(system_prompt=merged_system, db_path=self._db_path)
            prompt = msg
        else:
            merged_system = system
            options = make_options(system_prompt=merged_system)
            prompt = msg

        self._run_agent(prompt, options)

    def _run_trend_diagnosis(self, symptom: str, data_text: str):
        """📈 Trend Data: chẩn đoán kèm dữ liệu trend/log — tái dùng pipeline diagnose."""
        self._mode = "diagnose"
        self._show_diag_panel(True)

        n_lines = len([ln for ln in data_text.splitlines() if ln.strip()])
        self._echo_user(f"📈 {symptom}  (+ {n_lines} lines of trend/log data)")

        self._diag_retried = False
        self._cur_symptom = symptom
        self._diag_panel.set_analyzing(symptom)

        system = self._inp_system.text().strip()
        claude_md = self._load_claude_md()
        diag_system = copilot.build_diagnosis_system_prompt(self._db_path, claude_md)
        merged_system = (diag_system + "\n" + system).strip()
        options = make_options(system_prompt=merged_system, db_path=self._db_path)

        precedent = copilot.build_precedent_block(symptom)
        trend = copilot.build_trend_block(data_text)
        prompt = copilot.build_diagnosis_prompt(symptom, precedent, trend)
        self._run_agent(prompt, options)

    def _on_generate_report(self, diagnosis: dict):
        """Panel yêu cầu sinh báo cáo KV-OP từ cây nguyên nhân.

        Cách C: Claude chỉ trả JSON nội dung (KHÔNG Bash, không sinh script) →
        app tự render .docx bằng report_helper trong _on_done.
        """
        self._mode = "report"
        self._echo_user("📝 Generate KV-OP report from diagnosis")
        self._set_jarvis(3)

        prompt = copilot.build_report_content_prompt(diagnosis)
        system = (
            "Bạn là kỹ sư lập báo cáo vận hành Nhà máy Nhiệt điện Van Phong 1 BOT. "
            "Chỉ trả về JSON nội dung báo cáo, không viết script, không tạo file."
        )
        options = make_options(system_prompt=system)   # không db_path → không Bash
        self._run_agent(prompt, options)

    def _echo_user(self, msg: str):
        """Print the question as its own block and open a turn for the answer.

        Nothing is opened for the answer here: it is streamed as plain text and
        replaced by the rendered document in _finalize_answer, so the turn's
        start is recorded at the first thing that actually arrives.
        """
        self._set_busy(True)
        self._orb.set_active(True)
        self._set_jarvis(2)          # THINK — đang xử lý
        self._response_started = False
        self._resp_buffer = ""
        self._tool_counts = {}
        self._cited_codes = frozenset()
        self._ans_start = -1
        self._append(chat_render.user_turn_html(msg) + chat_render.spacer_html(8))

    def _run_agent(self, prompt: str, options):
        self._stream_chars = 0
        self._stream_timer.start()        # bắt đầu nuôi orb intensity
        self._worker = AgentWorker(prompt, options)
        self._worker.text_chunk.connect(self._on_text_chunk)
        self._worker.tool_used.connect(self._on_tool_used)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _mark_answer_start(self):
        """Remember where this answer begins, at the first thing it prints.

        Recorded lazily rather than in _echo_user because a retry runs the agent
        again without echoing anything, and it must get a region of its own
        instead of overwriting the answer above it.
        """
        if self._ans_start < 0:
            self._chat.moveCursor(QTextCursor.End)
            self._ans_start = self._chat.textCursor().position()

    def _on_text_chunk(self, text: str):
        self._resp_buffer += text
        self._stream_chars += len(text)   # nuôi orb intensity (throttle 200ms)
        # Streamed as plain text on purpose: markdown cannot be rendered from a
        # half-arrived table or heading. _finalize_answer replaces this whole
        # region with the rendered document once the answer is complete.
        self._mark_answer_start()
        safe = (text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace("\n", "<br>"))
        self._append(f'<span style="color:#1e293b">{safe}</span>')

    def _on_tool_used(self, tool_name: str):
        """Count the call, and show it on a line of its own while it happens.

        The line is live feedback only -- it sits in the region _finalize_answer
        replaces, and comes back as a single chip above the answer. It used to be
        appended into the answer's own paragraph, which put one ``⚙ Bash`` per
        call in front of the first word of the reply.
        """
        self._tool_counts[tool_name] = self._tool_counts.get(tool_name, 0) + 1
        self._mark_answer_start()
        self._append(
            f'<p style="color:#b45309;font-size:11px;margin:1px 0">'
            f'⚙️ {tool_name}</p>'
        )

    def _finalize_answer(self):
        """Swap the streamed plain text for the rendered document.

        One replacement over the region the answer occupies: the markdown is
        only complete now, and re-rendering per chunk would reflow the pane on
        every keystroke of output.
        """
        if self._ans_start < 0:
            return
        body = chat_render.markdown_to_html(self._resp_buffer, self._cited_codes)
        if not body and not self._tool_counts:
            self._ans_start = -1
            return
        cursor = self._chat.textCursor()
        cursor.setPosition(self._ans_start)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertHtml(
            chat_render.tool_chip_html(self._tool_counts)
            + body
            + chat_render.spacer_html(14)
        )
        self._ans_start = -1
        self._chat.moveCursor(QTextCursor.End)

    def _on_done(self):
        self._stream_timer.stop()
        self._stream_chars = 0
        self._set_busy(False)
        self._orb.set_active(False)
        self._set_jarvis(1)          # FOCUS — hoàn thành
        self._schedule_idle()        # vài giây sau tự về REST
        self._inp_msg.setFocus()
        # Sources first: it resolves the cited codes against the DB, and only a
        # code that resolved is worth turning into a link in the text below.
        self._show_answer_sources()  # orb marks the documents the answer cited
        self._finalize_answer()

        # Chẩn đoán: parse khối JSON cây nguyên nhân → đổ vào panel
        if self._mode == "diagnose":
            data = copilot.extract_diagnosis_json(self._resp_buffer)
            if not data and not self._diag_retried:
                # #3 — parse fail: nhắc Claude xuất lại đúng JSON (1 lần)
                self._diag_retried = True
                self._retry_diagnosis_json()
                return
            if data:
                if not data.get("symptom"):
                    data["symptom"] = self._cur_symptom
                data = copilot.verify_diagnosis(self._db_path, data)  # #1
                copilot.append_history(data)                          # #5 lưu lịch sử
                self._diag_panel.refresh_history()
                # Diagnosis carries section, quote and a verified flag, none of
                # which a scraped code has; replace the shallow cards with it.
                self._sources_panel.set_sources(_diagnosis_sources(data))
            self._diag_panel.set_diagnosis(data or {})
        elif self._mode == "report":
            self._mode = "chat"
            self._render_report_from_buffer()
        elif self._mode == "quickcard":
            self._mode = "chat"
            self._render_quickcard_from_buffer()
        elif self._mode == "workpackage":
            self._mode = "chat"
            self._render_workpackage_from_buffer()

    def _render_workpackage_from_buffer(self):
        """Parse JSON work package → app render .docx → mở file."""
        wp = copilot.extract_workpackage_json(self._resp_buffer)
        if not wp:
            self._append(
                '<p style="color:#dc2626;margin:6px 0">'
                '⚠️ Could not read work package content (JSON). Please try again.</p>'
            )
            return
        try:
            path = copilot.render_workpackage(wp)
        except Exception as e:
            safe = str(e).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            self._append(
                f'<p style="color:#dc2626;margin:6px 0"><b>Work package generation error:</b> {safe}</p>'
            )
            return
        safe_path = path.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self._append(
            f'<p style="color:#166534;margin:6px 0">'
            f'✅ Work package created:<br><b>{safe_path}</b></p>'
        )
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _render_quickcard_from_buffer(self):
        """Parse JSON thẻ tra cứu → app render .docx → mở file."""
        card = copilot.extract_quickcard_json(self._resp_buffer)
        if not card:
            self._append(
                '<p style="color:#dc2626;margin:6px 0">'
                '⚠️ Could not read card content (JSON). Please try again.</p>'
            )
            return
        try:
            path = copilot.render_quickcard(card)
        except Exception as e:
            safe = str(e).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            self._append(
                f'<p style="color:#dc2626;margin:6px 0"><b>Card generation error:</b> {safe}</p>'
            )
            return
        safe_path = path.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self._append(
            f'<p style="color:#166534;margin:6px 0">'
            f'✅ Quick reference card created:<br><b>{safe_path}</b></p>'
        )
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _render_report_from_buffer(self):
        """Cách C: parse JSON nội dung báo cáo → app render .docx → mở file."""
        rep = copilot.extract_report_json(self._resp_buffer)
        if not rep:
            self._append(
                '<p style="color:#dc2626;margin:6px 0">'
                '⚠️ Could not read report content (JSON). Please try again.</p>'
            )
            return
        try:
            path = copilot.render_report(rep)
        except Exception as e:
            safe = str(e).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            self._append(
                f'<p style="color:#dc2626;margin:6px 0"><b>Report generation error:</b> {safe}</p>'
            )
            return
        safe_path = path.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self._append(
            f'<p style="color:#166534;margin:6px 0">'
            f'✅ KV-OP report created:<br><b>{safe_path}</b></p>'
        )
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _retry_diagnosis_json(self):
        """#3 — yêu cầu Claude định dạng lại khối JSON từ câu trả lời trước."""
        self._set_busy(True)
        self._orb.set_active(True)
        self._set_jarvis(2)
        self._append(
            '<p style="color:#94a3b8;margin:6px 0;font-size:11px">'
            '↻ Reformatting result…</p>'
        )
        self._append('<p style="color:#166534;margin:2px 0"><b>Assistant:</b> ')
        prompt = copilot.build_retry_json_prompt(self._resp_buffer)
        self._resp_buffer = ""
        options = make_options(system_prompt="Bạn là trợ lý định dạng JSON chính xác.")
        self._run_agent(prompt, options)

    def _on_error(self, msg: str):
        # Render whatever did arrive before the error, and close the region:
        # left open, the next answer would replace from here and take the error
        # message down with it.
        self._finalize_answer()
        safe = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self._append(
            f'<p style="color:#dc2626;margin:4px 0"><b>Error:</b> {safe}</p>'
        )
        self._stream_timer.stop()
        self._stream_chars = 0
        self._set_busy(False)
        self._orb.set_active(False)
        self._set_jarvis(4)          # OVERLOAD — lỗi
        self._schedule_idle(8000)    # lỗi giữ lâu hơn rồi mới về REST
