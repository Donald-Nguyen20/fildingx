"""ui/claude_assistant/widget.py — Chat UI dùng claude_agent_sdk (Claude Code session)."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import paths

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter,
    QPushButton, QLabel, QLineEdit, QTextEdit, QFileDialog,
)
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWebEngineWidgets import QWebEngineView

from ui.claude_assistant.agent import make_options
from ui.claude_assistant.worker import AgentWorker
from ui.claude_assistant.animations import PulsingOrb
from ui.claude_assistant.diagnosis_panel import DiagnosisPanel
from ui.claude_assistant import copilot

_MAX_RESULTS   = 5    # số file lấy từ DB
_MAX_CONTENT   = 800  # ký tự content mỗi file


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


def _search_db(db_path: str, keyword: str) -> list[tuple[str, str, str, str]]:
    """Trả về list (file_name, doc_number, heading, chunk_content) dùng FTS5 chunks_fts.
    Fallback về LIKE trên files nếu DB không có chunks_fts."""
    try:
        conn = sqlite3.connect(db_path)
        cur  = conn.cursor()

        # Thử FTS5 chunks_fts trước (chính xác, tiết kiệm token)
        try:
            fts_query = " OR ".join(f'{w}*' for w in keyword.split() if w)
            cur.execute(
                """
                SELECT f.name, COALESCE(f.doc_number,''), c.heading, c.content
                FROM chunks c
                JOIN files f ON f.id = c.file_id
                WHERE c.id IN (
                    SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?
                )
                  AND f.name != 'BASE_PATH'
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, _MAX_RESULTS),
            )
            rows = cur.fetchall()
            conn.close()
            if rows:
                return rows
        except Exception:
            pass

        # Fallback: FTS5 trên files_fts (chỉ lấy tên + đoạn đầu content)
        try:
            fts_query = " OR ".join(f'{w}*' for w in keyword.split() if w)
            cur.execute(
                """
                SELECT name, COALESCE(doc_number,''), '', content
                FROM files
                WHERE id IN (
                    SELECT rowid FROM files_fts WHERE files_fts MATCH ?
                )
                  AND name != 'BASE_PATH'
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, _MAX_RESULTS),
            )
            rows = cur.fetchall()
            conn.close()
            if rows:
                return rows
        except Exception:
            pass

        # Fallback cuối: LIKE search
        cur.execute(
            "SELECT name, COALESCE(doc_number,''), '', content FROM files "
            "WHERE (name LIKE ? OR content LIKE ?) AND name != 'BASE_PATH' LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", _MAX_RESULTS),
        )
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception:
        return []


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


class ClaudeAssistantWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: AgentWorker | None = None
        self._response_started = False
        self._db_path: str = ""
        self._orb_view: QWebEngineView | None = None
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

        lbl_title = QLabel("Claude Assistant")
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

        self._orb_view = QWebEngineView()
        self._orb_view.loadFinished.connect(self._on_orb_loaded)
        left_lay.addWidget(self._orb_view, 1)

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
        QTimer.singleShot(0, self._load_orb_html)

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
    def _load_orb_html(self):
        # Resolve path: works in dev mode and PyInstaller --onedir build
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            html_path = Path(sys._MEIPASS) / "ui" / "claude_assistant" / "neural_interface.html"
        else:
            html_path = Path(__file__).resolve().parent / "neural_interface.html"

        if not html_path.exists():
            self._orb_view.setHtml("<html><body></body></html>")
            return

        # Use setHtml to avoid file:// security restrictions in WebEngine
        try:
            html_content = html_path.read_text(encoding="utf-8")
            base_url = QUrl.fromLocalFile(str(html_path.parent) + "/")
            self._orb_view.setHtml(html_content, base_url)
        except Exception:
            url = QUrl.fromLocalFile(str(html_path))
            self._orb_view.load(url)

    def _on_orb_loaded(self, ok: bool):
        print(f"[orb] loadFinished ok={ok}")
        # Local file trên Windows có thể báo ok=False nhưng vẫn render được
        # nên inject JS bất kể ok để đảm bảo controls được ẩn
        js = """
(function() {
    var lbl  = document.getElementById('lbl');
    if (lbl)  lbl.style.display  = 'none';
    var ctrl = document.querySelector('.ctrl');
    if (ctrl) ctrl.style.display = 'none';

    document.body.style.overflow = 'hidden';
    document.body.style.margin   = '0';
    document.body.style.padding  = '0';
    setS(0);
})();
"""
        self._orb_view.page().runJavaScript(
            js, lambda r: print(f"[orb] js inject done, result={r}")
        )

    def _set_jarvis(self, state: int):
        # Mọi lần đổi state đều dừng idle timer; chỉ _schedule_idle() mới hẹn về REST
        if state != 0:
            self._idle_timer.stop()
        if self._orb_view is not None:
            self._orb_view.page().runJavaScript(f"setS({state})")

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
            self._orb_view.page().runJavaScript(f"streamPulse({intensity:.3f})")

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
        if path:
            self._lbl_db.setText(os.path.basename(path))
            self._lbl_db.setStyleSheet("""
                color: #334155; font-size: 11px;
                background: #f0fdf4; border: 1px solid #86efac;
                border-radius: 6px; padding: 2px 8px;
            """)
            self._lbl_db.setToolTip(path)
        else:
            self._lbl_db.setText("No DB selected")
            self._lbl_db.setStyleSheet("""
                color: #94a3b8; font-size: 11px;
                background: #f8fafc; border: 1px solid #e2e8f0;
                border-radius: 6px; padding: 2px 8px;
            """)
            self._lbl_db.setToolTip("")
        if persist:
            _save_db_path(path)

    def _pick_db(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select DB file", "", "SQLite DB (*.db *.sqlite)"
        )
        if path:
            self._apply_db_path(path)

    def _clear_db(self):
        self._apply_db_path("")

    def _build_db_context(self, msg: str) -> str:
        """Search DB dùng FTS5 chunks_fts, trả về context string."""
        if not self._db_path:
            return ""
        keywords = _extract_keywords(msg)
        query_str = " OR ".join(f"{w}*" for w in keywords) if keywords else msg

        rows = _search_db(self._db_path, query_str)
        if not rows:
            return ""

        parts = [f"[Ngữ cảnh tài liệu — DB: {os.path.basename(self._db_path)}]\n"]
        for fname, doc_num, heading, content in rows:
            label = f"[{doc_num}] {fname}" if doc_num else fname
            section = f" > {heading}" if heading else ""
            parts.append(f"### {label}{section}\n{(content or '').strip()}\n")
        parts.append("---\n")
        return "\n".join(parts)

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

        # Chế độ chẩn đoán / quick card cần DB
        if self._mode in ("diagnose", "quickcard") and not self._db_path:
            self._append(
                '<p style="color:#dc2626;margin:4px 0">'
                '⚠️ Please select a DB file first.</p>'
            )
            return

        self._inp_msg.clear()
        self._echo_user(msg)

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
        self._append('<p style="color:#166534;margin:2px 0"><b>Claude:</b> ')

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
        self._append('<p style="color:#166534;margin:2px 0"><b>Claude:</b> ')
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
