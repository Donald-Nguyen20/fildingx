"""ui/claude_assistant/widget.py — Chat UI dùng claude_agent_sdk (Claude Code session)."""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit, QFileDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor

from ui.claude_assistant.agent import make_options
from ui.claude_assistant.worker import AgentWorker

_MAX_RESULTS   = 5    # số file lấy từ DB
_MAX_CONTENT   = 800  # ký tự content mỗi file

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
        self._build_ui()

    # ── Build UI ──────────────────────────────────────────────────────
    def _build_ui(self):
        self.setStyleSheet("""
            ClaudeAssistantWidget {
                background: #ffffff;
            }
            ClaudeAssistantWidget QLabel {
                color: #1e293b;
                background: transparent;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        # Header
        header = QHBoxLayout()
        lbl_title = QLabel("🤖  Claude Assistant")
        lbl_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self._lbl_status = QLabel("✅  Claude Code session")
        self._lbl_status.setStyleSheet("color: #16a34a; font-size: 11px;")

        self._btn_login = QPushButton("🔑 Đăng nhập")
        self._btn_login.setFixedHeight(26)
        self._btn_login.setToolTip("Mở cửa sổ đăng nhập Claude Code")
        self._btn_login.setStyleSheet("""
            QPushButton {
                background: #e0f2fe; color: #0369a1;
                border: 1px solid #7dd3fc; border-radius: 5px;
                font-size: 11px; padding: 0 8px;
            }
            QPushButton:hover { background: #bae6fd; }
        """)
        self._btn_login.clicked.connect(self._on_login)

        header.addWidget(lbl_title)
        header.addStretch()
        header.addWidget(self._btn_login)
        header.addWidget(self._lbl_status)
        root.addLayout(header)

        # System prompt
        sp_row = QHBoxLayout()
        sp_lbl = QLabel("System:")
        sp_lbl.setFixedWidth(52)
        sp_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        self._inp_system = QLineEdit()
        self._inp_system.setPlaceholderText("Bạn là trợ lý thông minh, trả lời bằng tiếng Việt.")
        self._inp_system.setStyleSheet("""
            QLineEdit {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                color: #334155;
                padding: 3px 8px;
                font-size: 11px;
            }
            QLineEdit:focus { border-color: #6366f1; }
        """)
        sp_row.addWidget(sp_lbl)
        sp_row.addWidget(self._inp_system, 1)
        root.addLayout(sp_row)

        # DB selector row
        db_row = QHBoxLayout()
        db_lbl = QLabel("DB:")
        db_lbl.setFixedWidth(52)
        db_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        self._lbl_db = QLabel("Chưa chọn file DB")
        self._lbl_db.setStyleSheet("""
            color: #94a3b8; font-size: 11px;
            background: #f8fafc; border: 1px solid #e2e8f0;
            border-radius: 6px; padding: 2px 8px;
        """)
        self._btn_pick_db = QPushButton("📂 Chọn DB")
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
        self._btn_clear_db.setToolTip("Bỏ chọn DB")
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
        root.addLayout(db_row)

        # Chat history
        self._chat = QTextEdit()
        self._chat.setReadOnly(True)
        self._chat.setFont(QFont("Segoe UI", 12))
        self._chat.setStyleSheet("""
            QTextEdit {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                color: #1e293b;
                padding: 10px;
            }
        """)
        root.addWidget(self._chat, 1)

        # Input bar
        input_row = QHBoxLayout()
        self._inp_msg = QLineEdit()
        self._inp_msg.setPlaceholderText("Nhập câu hỏi… (Enter để gửi)")
        self._inp_msg.setFixedHeight(36)
        self._inp_msg.setStyleSheet("""
            QLineEdit {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                color: #1e293b;
                padding: 0 10px;
                font-size: 13px;
            }
            QLineEdit:focus { border-color: #6366f1; }
        """)
        self._inp_msg.returnPressed.connect(self._on_send)

        self._btn_send = QPushButton("📤  Gửi")
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
        self._btn_clear.setToolTip("Xoá hội thoại")
        self._btn_clear.setStyleSheet("""
            QPushButton {
                background: #f1f5f9;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                color: #64748b;
                font-size: 14px;
            }
            QPushButton:hover { background: #fee2e2; color: #dc2626; border-color: #fca5a5; }
        """)
        self._btn_clear.clicked.connect(self._chat.clear)

        input_row.addWidget(self._inp_msg, 1)
        input_row.addWidget(self._btn_send)
        input_row.addWidget(self._btn_clear)
        root.addLayout(input_row)

    # ── Helpers ───────────────────────────────────────────────────────
    def _pick_db(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file DB", "", "SQLite DB (*.db *.sqlite)"
        )
        if path:
            self._db_path = path
            self._lbl_db.setText(os.path.basename(path))
            self._lbl_db.setStyleSheet("""
                color: #334155; font-size: 11px;
                background: #f0fdf4; border: 1px solid #86efac;
                border-radius: 6px; padding: 2px 8px;
            """)
            self._lbl_db.setToolTip(path)

    def _clear_db(self):
        self._db_path = ""
        self._lbl_db.setText("Chưa chọn file DB")
        self._lbl_db.setStyleSheet("""
            color: #94a3b8; font-size: 11px;
            background: #f8fafc; border: 1px solid #e2e8f0;
            border-radius: 6px; padding: 2px 8px;
        """)
        self._lbl_db.setToolTip("")

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
        """Đọc CLAUDE.md trong thư mục app làm system context."""
        try:
            md_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "CLAUDE.md",
            )
            with open(md_path, "r", encoding="utf-8") as f:
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
        self._btn_send.setText("⏳" if busy else "📤  Gửi")

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

        self._inp_msg.clear()
        self._set_busy(True)
        self._response_started = False

        safe_msg = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self._append(
            f'<p style="color:#4f46e5;margin:8px 0 2px 0">'
            f'<b>Bạn:</b> {safe_msg}</p>'
            f'<br>'
        )
        self._append(
            '<p style="color:#166534;margin:2px 0"><b>Claude:</b> '
        )

        system = self._inp_system.text().strip()
        db_context = self._build_db_context(msg)

        if db_context:
            claude_md = self._load_claude_md()
            db_system = (
                "Bạn là trợ lý kỹ thuật Nhà máy Nhiệt điện Van Phong 1 BOT. "
                "Dưới đây là ngữ cảnh tài liệu được trích từ DB nội bộ (chunks FTS5). "
                "Hãy trả lời dựa trên ngữ cảnh được cung cấp. "
                "Không cần dùng Glob, Read hay tool tìm file — dữ liệu đã có sẵn bên dưới."
            )
            if claude_md:
                db_system = claude_md + "\n\n" + db_system
            merged_system = (db_system + " " + system).strip()
            prompt = f"{db_context}\nCâu hỏi: {msg}"
        else:
            merged_system = system
            prompt = msg

        options = make_options(system_prompt=merged_system)

        self._worker = AgentWorker(prompt, options)
        self._worker.text_chunk.connect(self._on_text_chunk)
        self._worker.tool_used.connect(self._on_tool_used)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_text_chunk(self, text: str):
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
        self._set_busy(False)
        self._inp_msg.setFocus()

    def _on_error(self, msg: str):
        safe = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self._append(
            f'<p style="color:#dc2626;margin:4px 0"><b>Lỗi:</b> {safe}</p>'
        )
        self._set_busy(False)
