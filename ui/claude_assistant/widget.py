"""ui/claude_assistant/widget.py — Chat UI dùng claude_agent_sdk (Claude Code session)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor

from ui.claude_assistant.agent import make_options
from ui.claude_assistant.worker import AgentWorker


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
            f'<p style="color:#4f46e5;margin:8px 0 4px 0">'
            f'<b>Bạn:</b> {safe_msg}</p>'
        )
        self._append(
            '<p style="color:#166534;margin:4px 0"><b>Claude:</b> '
        )

        system = self._inp_system.text().strip()
        options = make_options(system_prompt=system)

        self._worker = AgentWorker(msg, options)
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
