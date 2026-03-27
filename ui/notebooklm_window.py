"""
ui/notebooklm_window.py — NotebookLM integration window.
"""
import asyncio
import subprocess
import sys
import os
from pathlib import Path


def is_nlm_logged_in() -> bool:
    """Kiểm tra file storage_state.json đã tồn tại chưa (tức là đã login)."""
    try:
        from notebooklm.paths import get_storage_path
        return get_storage_path().exists()
    except Exception:
        return False

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QTextEdit, QLineEdit,
    QSplitter, QFileDialog, QMessageBox, QTabWidget, QWidget,
    QComboBox,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont


def _run_async(coro):
    """Chạy coroutine trong thread hiện tại."""
    return asyncio.run(coro)


# ── Workers ──────────────────────────────────────────────────────

class LoginWorker(QThread):
    done  = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self._proc = None

    def run(self):
        try:
            self._proc = subprocess.Popen(
                [sys.executable, "-m", "notebooklm", "login"],
                stdin=subprocess.PIPE,
            )
            self._proc.wait()
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))

    def confirm(self):
        """Gửi ENTER để lưu cookies sau khi đăng nhập xong trên browser."""
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.write(b"\n")
                self._proc.stdin.flush()
            except Exception:
                pass


class ListNotebooksWorker(QThread):
    done  = Signal(list)
    error = Signal(str)

    def run(self):
        try:
            from notebooklm import NotebookLMClient
            async def _fetch():
                async with await NotebookLMClient.from_storage() as client:
                    return await client.notebooks.list()
            notebooks = _run_async(_fetch())
            self.done.emit(notebooks)
        except Exception as e:
            self.error.emit(str(e))


class CreateNotebookWorker(QThread):
    done  = Signal(object)
    error = Signal(str)

    def __init__(self, title: str):
        super().__init__()
        self.title = title

    def run(self):
        try:
            from notebooklm import NotebookLMClient
            async def _create():
                async with await NotebookLMClient.from_storage() as client:
                    return await client.notebooks.create(title=self.title)
            nb = _run_async(_create())
            self.done.emit(nb)
        except Exception as e:
            self.error.emit(str(e))


class DeleteNotebookWorker(QThread):
    done  = Signal()
    error = Signal(str)

    def __init__(self, notebook_id: str):
        super().__init__()
        self.notebook_id = notebook_id

    def run(self):
        try:
            from notebooklm import NotebookLMClient
            async def _delete():
                async with await NotebookLMClient.from_storage() as client:
                    await client.notebooks.delete(self.notebook_id)
            _run_async(_delete())
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))


class AddSourceWorker(QThread):
    done  = Signal()
    error = Signal(str)

    def __init__(self, notebook_id: str, file_path: str):
        super().__init__()
        self.notebook_id = notebook_id
        self.file_path   = file_path

    def run(self):
        try:
            from notebooklm import NotebookLMClient
            from pathlib import Path
            async def _add():
                async with await NotebookLMClient.from_storage() as client:
                    await client.sources.add_file(self.notebook_id, Path(self.file_path), wait=True)
            _run_async(_add())
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))


_SUMMARIZE_PROMPT = (
    "Please provide a comprehensive summary of this document following its original structure and headings. "
    "Include: main topics, key findings or procedures, important technical data, "
    "warnings or critical notices, and key takeaways. "
    "Use plain text only — no markdown, no ### or ** symbols, no bullet asterisks. "
    "Use the document's own section titles as headings."
)


class NLMAutoSummarizeWorker(QThread):
    """Auto-pick first notebook (or create one) → upload → summarize → delete source."""
    done  = Signal(str)
    error = Signal(str)

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            from notebooklm import NotebookLMClient
            async def _work():
                async with await NotebookLMClient.from_storage() as client:
                    notebooks = await client.notebooks.list()
                    if notebooks:
                        nb = notebooks[0]
                        nb_id = getattr(nb, "id", None) or getattr(nb, "notebook_id", "")
                    else:
                        nb = await client.notebooks.create(title="Auto Summary")
                        nb_id = getattr(nb, "id", None) or getattr(nb, "notebook_id", "")
                    source = await client.sources.add_file(nb_id, Path(self.file_path), wait=True)
                    sid = getattr(source, "source_id", None) or getattr(source, "id", None)
                    result = await client.chat.ask(nb_id, _SUMMARIZE_PROMPT, source_ids=[sid])
                    await client.sources.delete(nb_id, sid)
                    return getattr(result, "answer", None) or str(result)
            text = _run_async(_work())
            self.done.emit(text)
        except Exception as e:
            self.error.emit(str(e))


class NLMSummarizeWorker(QThread):
    """Upload file → chat.ask(summarize) → delete source."""
    done  = Signal(str)
    error = Signal(str)

    def __init__(self, notebook_id: str, file_path: str):
        super().__init__()
        self.notebook_id = notebook_id
        self.file_path   = file_path

    def run(self):
        try:
            from notebooklm import NotebookLMClient
            async def _work():
                async with await NotebookLMClient.from_storage() as client:
                    source = await client.sources.add_file(
                        self.notebook_id, Path(self.file_path), wait=True
                    )
                    sid = getattr(source, "source_id", None) or getattr(source, "id", None)
                    result = await client.chat.ask(
                        self.notebook_id,
                        _SUMMARIZE_PROMPT,
                        source_ids=[sid],
                    )
                    await client.sources.delete(self.notebook_id, sid)
                    return getattr(result, "answer", None) or str(result)
            text = _run_async(_work())
            self.done.emit(text)
        except Exception as e:
            self.error.emit(str(e))


class ChatWorker(QThread):
    done  = Signal(str, list)   # answer, deduplicated citations
    error = Signal(str)

    def __init__(self, notebook_id: str, question: str):
        super().__init__()
        self.notebook_id = notebook_id
        self.question    = question

    def run(self):
        try:
            from notebooklm import NotebookLMClient
            async def _chat():
                async with await NotebookLMClient.from_storage() as client:
                    result = await client.chat.ask(self.notebook_id, self.question)
                    # Build source_id → title map
                    src_map = {}
                    try:
                        sources = await client.sources.list(self.notebook_id)
                        for s in sources:
                            sid   = getattr(s, "source_id", None) or getattr(s, "id", "")
                            title = getattr(s, "title", None) or getattr(s, "name", "") or ""
                            if sid:
                                src_map[sid] = title
                    except Exception:
                        pass
                    return result, src_map
            result, src_map = _run_async(_chat())
            text = getattr(result, "answer", None) or getattr(result, "message", None) or getattr(result, "text", None) or str(result)

            seen, citations = set(), []
            for c in (getattr(result, "references", None) or []):
                quote  = (getattr(c, "cited_text", None) or "").strip()
                src_id = getattr(c, "source_id", "") or ""
                if quote and quote not in seen:
                    seen.add(quote)
                    citations.append({"text": quote, "source": src_map.get(src_id, "")})

            self.done.emit(text, citations)
        except Exception as e:
            self.error.emit(str(e))


# ── Notebook Picker Dialog (used from external windows) ──────────

class NLMNotebookPickerDialog(QDialog):
    """Show list of notebooks, return selected notebook_id."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Notebook")
        self.setFixedSize(360, 280)
        self.selected_id = None

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Select a notebook to summarize into:"))

        self.lst = QListWidget()
        lay.addWidget(self.lst, 1)

        btns = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setFixedHeight(32)
        ok_btn.clicked.connect(self._accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(32)
        cancel_btn.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        lay.addLayout(btns)

        self._load()

    def _load(self):
        self.lst.addItem(QListWidgetItem("⏳ Loading…"))
        w = ListNotebooksWorker()
        w.done.connect(self._on_loaded)
        w.error.connect(lambda e: (self.lst.clear(), self.lst.addItem(f"Error: {e}")))
        self._worker = w
        w.start()

    def _on_loaded(self, notebooks):
        self.lst.clear()
        for nb in notebooks:
            title = getattr(nb, "title", None) or getattr(nb, "name", str(nb))
            nb_id = getattr(nb, "id", None) or getattr(nb, "notebook_id", "")
            item  = QListWidgetItem(f"📓 {title}")
            item.setData(Qt.UserRole, nb_id)
            self.lst.addItem(item)
        if self.lst.count():
            self.lst.setCurrentRow(0)

    def _accept(self):
        item = self.lst.currentItem()
        if item:
            self.selected_id = item.data(Qt.UserRole)
            self.accept()

    @staticmethod
    def pick(parent=None) -> str | None:
        if not is_nlm_logged_in():
            QMessageBox.warning(
                parent, "Not Logged In",
                "Please log in to NotebookLM first.\n\nGo to the 📓 NotebookLM tab and click 🔑 Login Google."
            )
            return None
        dlg = NLMNotebookPickerDialog(parent)
        if dlg.exec() == QDialog.Accepted:
            return dlg.selected_id
        return None


# ── Embedded Widget ───────────────────────────────────────────────

class NotebookLMWidget(QWidget):
    """Embedded widget — dùng trong tab hoặc dialog."""


    def __init__(self, parent=None):
        super().__init__(parent)

        self._current_notebook_id = None
        self._workers = []

        self._setup_ui()

        # Auto-load nếu đã có session
        if is_nlm_logged_in():
            self.lbl_status.setText("🟢 Logged in")
            self._load_notebooks()
        else:
            self.lbl_status.setText("⚪ Not logged in")

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(8, 8, 8, 8)

        # ── Header: Login + status ────────────────────────────────
        header = QHBoxLayout()
        self.lbl_status = QLabel("⚪ Not logged in")
        self.lbl_status.setStyleSheet("font-size: 12px; color: #a6adc8;")
        self.lbl_status.setMaximumWidth(320)
        self.btn_login = QPushButton("🔑 Switch Account")
        self.btn_login.setFixedHeight(32)
        self.btn_login.clicked.connect(self._login)
        self.btn_save_login = QPushButton("✅ Save Login")
        self.btn_save_login.setFixedHeight(32)
        self.btn_save_login.setEnabled(False)
        self.btn_save_login.setToolTip("Bấm sau khi đã đăng nhập xong trên browser")
        self.btn_save_login.clicked.connect(self._save_login)
        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.setFixedHeight(32)
        self.btn_refresh.clicked.connect(self._load_notebooks)
        header.addWidget(self.lbl_status)
        header.addStretch()
        header.addWidget(self.btn_login)
        header.addWidget(self.btn_save_login)
        header.addWidget(self.btn_refresh)
        lay.addLayout(header)

        # ── Splitter: notebooks list | main panel ─────────────────
        splitter = QSplitter(Qt.Horizontal)

        # Left: notebook list
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(6)

        lbl_nb = QLabel("📓 Notebooks")
        lbl_nb.setStyleSheet("font-weight: bold; font-size: 13px;")
        left_lay.addWidget(lbl_nb)

        self.lst_notebooks = QListWidget()
        self.lst_notebooks.currentItemChanged.connect(self._on_notebook_selected)
        left_lay.addWidget(self.lst_notebooks, 1)

        nb_btn_row = QHBoxLayout()
        nb_btn_row.setSpacing(4)
        self.btn_new_nb = QPushButton("➕ New")
        self.btn_new_nb.setFixedHeight(34)
        self.btn_new_nb.clicked.connect(self._create_notebook)
        self.btn_del_nb = QPushButton("🗑 Delete")
        self.btn_del_nb.setFixedHeight(34)
        self.btn_del_nb.setEnabled(False)
        self.btn_del_nb.clicked.connect(self._delete_notebook)
        nb_btn_row.addWidget(self.btn_new_nb)
        nb_btn_row.addWidget(self.btn_del_nb)
        left_lay.addLayout(nb_btn_row)

        splitter.addWidget(left)

        # Right: tabs
        right = QTabWidget()

        # Tab 1: Chat
        chat_widget = QWidget()
        chat_lay = QVBoxLayout(chat_widget)
        chat_lay.setSpacing(6)

        self.lbl_nb_name = QLabel("Select a notebook →")
        self.lbl_nb_name.setStyleSheet("font-size: 13px; font-weight: bold; color: #89b4fa;")
        chat_lay.addWidget(self.lbl_nb_name)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setPlaceholderText("Chat history will appear here…")
        self.chat_display.setStyleSheet("font-size: 18px;")
        chat_lay.addWidget(self.chat_display, 1)

        input_row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Ask a question about your documents…")
        self.chat_input.setFixedHeight(36)
        self.chat_input.returnPressed.connect(self._send_chat)
        self.btn_send = QPushButton("Send ➤")
        self.btn_send.setFixedHeight(36)
        self.btn_send.setEnabled(False)
        self.btn_send.clicked.connect(self._send_chat)
        input_row.addWidget(self.chat_input, 1)
        input_row.addWidget(self.btn_send)
        chat_lay.addLayout(input_row)

        right.addTab(chat_widget, "💬 Chat")

        # Tab 2: Sources
        src_widget = QWidget()
        src_lay = QVBoxLayout(src_widget)
        src_lay.setSpacing(6)

        src_lay.addWidget(QLabel("Files added to this notebook:"))
        self.lst_sources = QListWidget()
        src_lay.addWidget(self.lst_sources, 1)

        src_btn_row = QHBoxLayout()
        self.btn_add_file = QPushButton("📄 Add File")
        self.btn_add_file.setFixedHeight(30)
        self.btn_add_file.setEnabled(False)
        self.btn_add_file.clicked.connect(self._add_file)
        src_btn_row.addWidget(self.btn_add_file)
        src_btn_row.addStretch()
        src_lay.addLayout(src_btn_row)

        right.addTab(src_widget, "📎 Sources")

        splitter.addWidget(right)
        splitter.setSizes([240, 760])

        lay.addWidget(splitter, 1)

    # ── Auth ─────────────────────────────────────────────────────

    def _login(self):
        self.btn_login.setEnabled(False)
        self.lbl_status.setText("🔄 Opening browser for login…")
        self._login_worker = LoginWorker()
        self._login_worker.done.connect(self._on_login_done)
        self._login_worker.error.connect(self._on_login_error)
        self._workers.append(self._login_worker)
        self._login_worker.start()
        self.btn_save_login.setEnabled(True)

    def _save_login(self):
        if hasattr(self, "_login_worker"):
            self._login_worker.confirm()
        self.btn_save_login.setEnabled(False)
        self.lbl_status.setText("🔄 Saving login…")

    def _on_login_done(self):
        self.lbl_status.setText("🟢 Logged in")
        self.btn_login.setEnabled(True)
        self._load_notebooks()

    def _on_login_error(self, msg: str):
        self.lbl_status.setText("🔴 Login failed")
        self.btn_login.setEnabled(True)
        QMessageBox.critical(self, "Login Error", msg)

    # ── Notebooks ─────────────────────────────────────────────────

    def _load_notebooks(self):
        self.lbl_status.setText("🔄 Loading notebooks…")
        w = ListNotebooksWorker()
        w.done.connect(self._on_notebooks_loaded)
        w.error.connect(lambda e: (
            self.lbl_status.setText("🔴 Auth expired — click Switch Account"),
            self.lbl_status.setToolTip(e),
        ))
        self._workers.append(w)
        w.start()

    def _on_notebooks_loaded(self, notebooks):
        self.lst_notebooks.clear()
        for nb in notebooks:
            title = getattr(nb, "title", None) or getattr(nb, "name", str(nb))
            nb_id  = getattr(nb, "id", None) or getattr(nb, "notebook_id", "")
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, nb_id)
            self.lst_notebooks.addItem(item)
        self.lbl_status.setText(f"🟢 {len(notebooks)} notebook(s) loaded")

    def _create_notebook(self):
        from PySide6.QtWidgets import QInputDialog
        title, ok = QInputDialog.getText(self, "New Notebook", "Notebook title:")
        if not ok or not title.strip():
            return
        w = CreateNotebookWorker(title.strip())
        w.done.connect(lambda nb: self._load_notebooks())
        w.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
        self._workers.append(w)
        w.start()

    def _delete_notebook(self):
        item = self.lst_notebooks.currentItem()
        if not item:
            return
        title = item.text()
        nb_id = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "Delete Notebook",
            f"Delete \"{title}\"?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.btn_del_nb.setEnabled(False)
        w = DeleteNotebookWorker(nb_id)
        w.done.connect(lambda: self._load_notebooks())
        w.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
        self._workers.append(w)
        w.start()

    def _on_notebook_selected(self, current, _prev):
        if not current:
            self.btn_del_nb.setEnabled(False)
            return
        self._current_notebook_id = current.data(Qt.UserRole)
        self.lbl_nb_name.setText(f"📓 {current.text()}")
        self.btn_del_nb.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.btn_add_file.setEnabled(True)
        self.chat_display.clear()

    # ── Chat ──────────────────────────────────────────────────────

    def _send_chat(self):
        if not self._current_notebook_id:
            return
        question = self.chat_input.text().strip()
        if not question:
            return
        self.chat_display.append(f"<b style='color:#89b4fa'>You:</b> {question}")
        self.chat_input.clear()
        self.btn_send.setEnabled(False)

        w = ChatWorker(self._current_notebook_id, question)
        w.done.connect(self._on_chat_done)
        w.error.connect(self._on_chat_error)
        self._workers.append(w)
        w.start()

    def _on_chat_done(self, text: str, citations: list):
        html = self._md_to_html(text)
        self.chat_display.append(f"<b style='color:#a6e3a1'>NotebookLM:</b><br>{html}")
        if citations:
            parts = []
            for i, c in enumerate(citations, 1):
                quote  = c.get("text", "")
                source = c.get("source", "")
                short  = quote[:150] + ("…" if len(quote) > 150 else "")
                parts.append(
                    f"<span style='color:#15803d'>[{i}]"
                    + (f" <span style='color:#1d4ed8'>{source}</span>" if source else "")
                    + f"</span> <i style='color:#374151'>\"{short}\"</i>"
                )
            self.chat_display.append(
                "<span style='font-size:15px;color:#b45309'>──────────────── Sources ────────────────</span><br>"
                + "<br>".join(parts)
            )
        self.chat_display.append("<br>")
        self.btn_send.setEnabled(True)

    @staticmethod
    def _md_to_html(text: str) -> str:
        """Convert basic markdown to HTML for display."""
        import re
        lines = text.split("\n")
        out = []
        for line in lines:
            # Headers
            if line.startswith("### "):
                out.append(f"<b style='font-size:18px;color:#6c27b0'>{line[4:]}</b>")
            elif line.startswith("## "):
                out.append(f"<b style='font-size:18px;color:#1565c0'>{line[3:]}</b>")
            elif line.startswith("# "):
                out.append(f"<b style='font-size:18px;color:#0d47a1'>{line[2:]}</b>")
            elif line.startswith("- ") or line.startswith("* "):
                out.append(f"&nbsp;&nbsp;• {line[2:]}")
            elif line.strip() == "":
                out.append("<br>")
            else:
                out.append(line)
        result = "<br>".join(out)
        # Bold **text**
        result = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", result)
        # Italic *text*
        result = re.sub(r"\*(.+?)\*", r"<i>\1</i>", result)
        return result

    def _on_chat_error(self, msg: str):
        self.chat_display.append(f"<b style='color:#f38ba8'>Error:</b> {msg}")
        self.btn_send.setEnabled(True)

    # ── Sources ───────────────────────────────────────────────────

    def _add_file(self):
        if not self._current_notebook_id:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select File", "",
            "Documents (*.pdf *.txt *.docx *.pptx *.md)"
        )
        if not path:
            return
        self.btn_add_file.setEnabled(False)
        w = AddSourceWorker(self._current_notebook_id, path)
        w.done.connect(self._on_source_added)
        w.error.connect(lambda e: (
            QMessageBox.critical(self, "Error", e),
            self.btn_add_file.setEnabled(True),
        ))
        self._workers.append(w)
        w.start()

    def _on_source_added(self):
        self.btn_add_file.setEnabled(True)
        self.lst_sources.addItem(QListWidgetItem("✅ File added"))
        QMessageBox.information(self, "Success", "File added to notebook!")


# ── Dialog wrapper (backward compat) ─────────────────────────────

class NotebookLMWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("NotebookLM")
        self.resize(1000, 680)
        self.setModal(False)
        self.setStyleSheet("QDialog { background: #1e2030; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(NotebookLMWidget(self))

        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.center().x() - self.width() // 2,
            screen.center().y() - self.height() // 2,
        )
