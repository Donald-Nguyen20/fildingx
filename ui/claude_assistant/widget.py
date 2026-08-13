"""ui/claude_assistant/widget.py — Chat UI dùng claude_agent_sdk (Claude Code session)."""
from __future__ import annotations

import html
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
    QPushButton, QLabel, QLineEdit, QTextEdit, QFileDialog,
    QDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QFont, QTextCursor

from ui.claude_assistant.agent import make_options
from ui.claude_assistant.worker import AgentWorker
from ui.claude_assistant.animations import PulsingOrb
from ui.claude_assistant.diagnosis_panel import DiagnosisPanel
from ui.claude_assistant.neural_orb_widget import NeuralOrbWidget
from ui.claude_assistant import copilot

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


def _resolve_cited_paths(
    lookup: list[tuple[str, str]], codes: list[str]
) -> list[str]:
    """Paths of the files whose name carries one of the cited codes."""
    resolved: list[str] = []
    seen: set[str] = set()
    for code in codes:
        hits = [path for name, path in lookup if code in name]
        if not hits or len(hits) > _MAX_PATHS_PER_CITATION:
            continue
        for path in hits:
            if path not in seen:
                seen.add(path)
                resolved.append(path)
    return resolved


def _query_search_paths(db_path: str, keyword: str, limit: int = 8000) -> list[str]:
    """Paths of every file matching the search, for lighting up the orb.

    The cap is deliberately high: the highlight has to show truthfully where
    hits sit across the whole document set, and a small cap would silently
    under-light entire regions of the orb."""
    fts_query = " OR ".join(f"{w}*" for w in keyword.split() if w)
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

            cur.execute(
                "SELECT path FROM files WHERE (name LIKE ? OR content LIKE ?) "
                "AND name != 'BASE_PATH' LIMIT ?",
                (f"%{keyword}%", f"%{keyword}%", limit),
            )
            return [r[0] for r in cur.fetchall() if r[0]]
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
_DB_LABEL_NONE = ("#94a3b8", "#f8fafc", "#e2e8f0")  # nothing selected
_DB_LABEL_OK = ("#334155", "#f0fdf4", "#86efac")    # readable, has documents
_DB_LABEL_BAD = ("#7c2d12", "#fff7ed", "#fdba74")   # unreadable, or indexed nothing


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

        # ── Splitter: Orb (left) | Chat (right) ──────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #1a2535; }")

        # Left — JARVIS orb + action buttons
        left = QWidget()
        left.setStyleSheet("background: #02040b;")
        left.setMinimumWidth(180)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        self._orb_view = NeuralOrbWidget()
        self._orb_view.neuron_clicked.connect(self._open_orb_file)
        self._orb_base_path = ""
        left_lay.addWidget(self._orb_view, 1)

        self._src_lbl = QLabel("")
        self._src_lbl.setWordWrap(True)
        self._src_lbl.setStyleSheet(
            "background: #120c06; color: #ff7e2e; font-size: 10px; "
            "padding: 5px 10px; border-top: 1px solid #3a220f;"
        )
        self._src_lbl.setVisible(False)
        left_lay.addWidget(self._src_lbl)

        self._legend_lbl = QLabel("")
        self._legend_lbl.setWordWrap(True)
        self._legend_lbl.setStyleSheet(
            "background: #06090f; color: #9fb3c8; font-size: 10px; "
            "padding: 6px 10px; border-top: 1px solid #1a2535;"
        )
        self._legend_lbl.setVisible(False)
        left_lay.addWidget(self._legend_lbl)

        # Action buttons (thay thế state buttons trong HTML)
        btn_frame = QWidget()
        btn_frame.setStyleSheet(
            "background: #06090f; border-top: 1px solid #1a2535;"
        )
        btn_grid = QGridLayout(btn_frame)
        btn_grid.setContentsMargins(8, 8, 8, 8)
        btn_grid.setSpacing(6)

        _ACTIONS = [
            ("🔍", "Find Docs",   "Find in document DB about: ",   1, "chat"),
            ("📝", "Make Report", "Create operation report about: ", 3, "chat"),
            ("🔬", "Diagnose",    "",                              2, "diagnose"),
            ("💬", "Ask",         "",                              0, "chat"),
            ("🪪", "Quick Card",  "",                              1, "quickcard"),
            ("🔧", "Work Pack",   "",                              1, "workpackage"),
            ("📈", "Trend Data",  "",                              2, "trend"),
        ]
        _btn_style = """
            QPushButton {
                background: #0d1b2a; color: #7ecfff;
                border: 1px solid #1a3a5c; border-radius: 8px;
                font-size: 11px; padding: 6px 4px;
            }
            QPushButton:hover   { background: #1a2f45; border-color: #4488cc; color: #aaddff; }
            QPushButton:pressed { background: #0a1520; }
        """
        for idx, (icon, label, prefix, state, mode) in enumerate(_ACTIONS):
            btn = QPushButton(f"{icon}\n{label}")
            btn.setStyleSheet(_btn_style)
            btn.setFixedHeight(52)
            btn.clicked.connect(
                lambda _checked, p=prefix, s=state, m=mode: self._on_action(p, s, m)
            )
            # nút lẻ cuối (số nút lẻ) trải hết 2 cột cho cân đối
            if idx == len(_ACTIONS) - 1 and len(_ACTIONS) % 2 == 1:
                btn_grid.addWidget(btn, idx // 2, 0, 1, 2)
            else:
                btn_grid.addWidget(btn, idx // 2, idx % 2)

        left_lay.addWidget(btn_frame)
        splitter.addWidget(left)

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

        # DB selector row
        db_row = QHBoxLayout()
        db_lbl = QLabel("DB:")
        db_lbl.setFixedWidth(52)
        db_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        self._lbl_db = QLabel("No DB selected")
        self._lbl_db.setStyleSheet("""
            color: #94a3b8; font-size: 11px;
            background: #f8fafc; border: 1px solid #e2e8f0;
            border-radius: 6px; padding: 2px 8px;
        """)
        self._btn_pick_db = QPushButton("📂 Select DB")
        self._btn_pick_db.setFixedHeight(26)
        self._btn_pick_db.setStyleSheet("""
            QPushButton {
                background: #f1f5f9; border: 1px solid #e2e8f0;
                border-radius: 5px; font-size: 11px; padding: 0 8px;
            }
            QPushButton:hover { background: #e0f2fe; }
        """)
        self._btn_pick_db.clicked.connect(self._pick_db)
        self._btn_clear_db = QPushButton("✕")
        self._btn_clear_db.setFixedSize(26, 26)
        self._btn_clear_db.setToolTip("Clear DB")
        self._btn_clear_db.setStyleSheet("""
            QPushButton {
                background: #f1f5f9; border: 1px solid #e2e8f0;
                border-radius: 5px; color: #94a3b8;
            }
            QPushButton:hover { background: #fee2e2; color: #dc2626; }
        """)
        self._btn_clear_db.clicked.connect(self._clear_db)
        db_row.addWidget(db_lbl)
        db_row.addWidget(self._lbl_db, 1)
        db_row.addWidget(self._btn_pick_db)
        db_row.addWidget(self._btn_clear_db)
        r_lay.addLayout(db_row)

        # Chat history
        self._chat = QTextEdit()
        self._chat.setReadOnly(True)
        self._chat.setFont(QFont("Segoe UI", 12))
        self._chat.setStyleSheet("""
            QTextEdit {
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
        self._btn_clear.clicked.connect(self._chat.clear)

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
        splitter.setSizes([340, 660])
        root.addWidget(splitter, 1)

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
        if show:
            self._diag_panel.show()
            self._splitter.setSizes([260, 420, 400])
        else:
            self._diag_panel.hide()
            self._splitter.setSizes([340, 660])

    def _apply_db_path(self, path: str, persist: bool = True):
        """Cập nhật state + UI + (tuỳ chọn) lưu xuống JSON. path='' = clear."""
        self._db_path = path
        self._diag_panel.set_db_path(path)

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
        elif snap.error:
            text = f"⚠ {os.path.basename(path)}"
            tip = f"{path}\n\nCould not read this database:\n{snap.error}"
            colors = _DB_LABEL_BAD
        elif snap.total_docs == 0:
            text = f"⚠ {os.path.basename(path)}"
            tip = f"{path}\n\nOpened, but it contains no indexed documents."
            colors = _DB_LABEL_BAD
        else:
            text = os.path.basename(path)
            tip = f"{path}\n\n{snap.total_docs:,} documents indexed."
            colors = _DB_LABEL_OK
        self._lbl_db.setText(text)
        self._lbl_db.setToolTip(tip)
        self._lbl_db.setStyleSheet(_db_label_style(*colors))

    def _update_orb_legend(self) -> None:
        """Render the folder breakdown below the orb from
        self._orb_view.folder_legend (name, colour, file_count).

        The COUNT carries the folder's colour, not a separate swatch: it is the
        number the eye is hunting for, and colouring it lets one folder's total
        be picked out of the row without a dot competing for the same space.
        Folder names stay on the label's own grey so the colours read as
        row markers rather than as emphasis on some folders over others."""
        legend = self._orb_view.folder_legend if self._orb_view is not None else []
        if not legend:
            self._legend_lbl.setVisible(False)
            self._legend_lbl.setText("")
            return
        rows = []
        for name, color, count in legend:
            tint = (f'<span style="color:rgb({color.red()},{color.green()},'
                    f'{color.blue()});font-weight:600;">{count:,}</span>')
            rows.append(f"{html.escape(name)} ({tint})")
        self._legend_lbl.setText("&nbsp;&nbsp;·&nbsp;&nbsp;".join(rows))
        self._legend_lbl.setVisible(True)

    def _open_orb_file(self, name: str, relative_path: str) -> None:
        if not self._orb_base_path:
            return
        abs_path = os.path.join(self._orb_base_path, relative_path)
        if os.path.exists(abs_path):
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
        keyword = " ".join(_extract_keywords(keyword)) or keyword.strip()
        self._hl_seq += 1
        if not (self._db_path and keyword):
            self._orb_view.clear_highlight()
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

    # ── Answer sources (provenance) ─────────────────────────────────────
    def _show_answer_sources(self) -> None:
        """Mark on the orb the documents the finished answer cited, so the
        numbers in it can be traced back to a file and checked.

        The search highlight is dropped at the same time: it answers a different
        question (where the topic lives) and leaving both on would blur which
        documents the answer actually rests on."""
        if self._orb_view is None:
            return
        codes = _extract_doc_codes(self._resp_buffer)
        paths = _resolve_cited_paths(self._doc_lookup, codes) if codes else []

        # Bump the sequence so a search query still in flight cannot land after
        # this and repaint over the sources.
        self._hl_seq += 1
        self._orb_view.clear_highlight()
        resolved = self._orb_view.set_source_files(paths)
        self._set_source_caption(len(resolved))

    def _clear_answer_sources(self) -> None:
        if self._orb_view is not None:
            self._orb_view.clear_sources()
        self._set_source_caption(0)

    def _set_source_caption(self, resolved: int) -> None:
        """Caption under the orb naming how many cited documents were located.

        Only files found in this DB are counted. A code that resolves to nothing
        is left silent on purpose: an answer may legitimately cite a standard or
        an external document, and flagging those as missing would cry wolf."""
        if not resolved:
            self._src_lbl.setVisible(False)
            self._src_lbl.setText("")
            return
        self._src_lbl.setText(
            f"◆ {resolved} source file(s) cited — click a marker to open"
        )
        self._src_lbl.setVisible(True)

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
        # The previous answer's sources belong to the previous answer.
        self._clear_answer_sources()
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
        """In dòng người dùng + mở đoạn trả lời của Claude vào khung chat."""
        self._set_busy(True)
        self._orb.set_active(True)
        self._set_jarvis(2)          # THINK — đang xử lý
        self._response_started = False
        self._resp_buffer = ""
        safe_msg = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self._append(
            f'<p style="color:#4f46e5;margin:8px 0 2px 0">'
            f'<b>You:</b> {safe_msg}</p><br>'
        )
        self._append('<p style="color:#166534;margin:2px 0"><b>Assistant:</b> ')

    def _run_agent(self, prompt: str, options):
        self._stream_chars = 0
        self._stream_timer.start()        # bắt đầu nuôi orb intensity
        self._worker = AgentWorker(prompt, options)
        self._worker.text_chunk.connect(self._on_text_chunk)
        self._worker.tool_used.connect(self._on_tool_used)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_text_chunk(self, text: str):
        self._resp_buffer += text
        self._stream_chars += len(text)   # nuôi orb intensity (throttle 200ms)
        safe = (text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace("\n", "<br>"))
        self._append(f'<span style="color:#1e293b">{safe}</span>')

    def _on_tool_used(self, tool_name: str):
        self._append(
            f'<span style="color:#b45309;font-size:11px"> ⚙️ {tool_name}</span>'
        )

    def _on_done(self):
        self._append("</p><br>")
        self._stream_timer.stop()
        self._stream_chars = 0
        self._set_busy(False)
        self._orb.set_active(False)
        self._set_jarvis(1)          # FOCUS — hoàn thành
        self._schedule_idle()        # vài giây sau tự về REST
        self._inp_msg.setFocus()
        self._show_answer_sources()  # orb marks the documents the answer cited

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
