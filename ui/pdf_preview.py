# ui/pdf_preview.py
import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QFormLayout, QLineEdit, QMessageBox, QSplitter,
    QTabWidget, QComboBox, QFileDialog, QToolButton,
    QScrollArea, QMenu,
)
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QPixmap, QImage, QTextCharFormat, QFont, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

import paths
from core.llm_client import create_llm_client, PROVIDERS
from core.llm_config import (
    load_llm_config, save_llm_config, get_config_path,
    DEFAULT_OLLAMA_MODEL, DEFAULT_OPENROUTER_MODEL,
    DEFAULT_GROQ_MODEL, DEFAULT_GEMINI_MODEL,
)
from ui.notes_window import RichTextEdit


class MindMapPage(QWebEnginePage):
    """Custom page that intercepts console.log('mm:...') messages from the mind map HTML."""
    action = Signal(str)

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):  # noqa: N803
        if message.startswith("mm:"):
            self.action.emit(message)
        # suppress all other console noise silently


class LLMSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM Settings")
        self.setModal(True)
        self.setMinimumWidth(520)

        cfg = load_llm_config()
        layout = QVBoxLayout(self)
        form = QFormLayout()

        or_row = QHBoxLayout()
        self.ed_openrouter = QLineEdit(cfg.get("openrouter_api_key", ""))
        self.ed_openrouter.setEchoMode(QLineEdit.Password)
        btn_or = QPushButton("🔑 Get key")
        btn_or.setFixedWidth(80)
        btn_or.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://openrouter.ai/keys")))
        or_row.addWidget(self.ed_openrouter)
        or_row.addWidget(btn_or)
        form.addRow("OpenRouter API key:", or_row)

        groq_row = QHBoxLayout()
        self.ed_groq = QLineEdit(cfg.get("groq_api_key", ""))
        self.ed_groq.setEchoMode(QLineEdit.Password)
        btn_groq = QPushButton("🔑 Get key")
        btn_groq.setFixedWidth(80)
        btn_groq.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://console.groq.com/keys")))
        groq_row.addWidget(self.ed_groq)
        groq_row.addWidget(btn_groq)
        form.addRow("Groq API key:", groq_row)

        gemini_row = QHBoxLayout()
        self.ed_gemini = QLineEdit(cfg.get("gemini_api_key", ""))
        self.ed_gemini.setEchoMode(QLineEdit.Password)
        btn_gemini = QPushButton("🔑 Get key")
        btn_gemini.setFixedWidth(80)
        btn_gemini.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://aistudio.google.com/app/apikey")))
        gemini_row.addWidget(self.ed_gemini)
        gemini_row.addWidget(btn_gemini)
        form.addRow("Gemini API key:", gemini_row)

        self.ed_ollama_host = QLineEdit(cfg.get("ollama_host", "http://localhost:11434"))
        form.addRow("Ollama host:", self.ed_ollama_host)

        self.ed_ollama_model = QLineEdit(cfg.get("ollama_model", DEFAULT_OLLAMA_MODEL))
        form.addRow("Ollama model:", self.ed_ollama_model)

        self.ed_openrouter_model = QLineEdit(cfg.get("openrouter_model", DEFAULT_OPENROUTER_MODEL))
        form.addRow("OpenRouter model:", self.ed_openrouter_model)

        self.ed_groq_model = QLineEdit(cfg.get("groq_model", DEFAULT_GROQ_MODEL))
        form.addRow("Groq model:", self.ed_groq_model)

        self.ed_gemini_model = QLineEdit(cfg.get("gemini_model", DEFAULT_GEMINI_MODEL))
        form.addRow("Gemini model:", self.ed_gemini_model)

        self.cbo_translate = QComboBox()
        for key, label in PROVIDERS:
            self.cbo_translate.addItem(label, key)
        saved = cfg.get("translate_provider", "gemini")
        idx = self.cbo_translate.findData(saved)
        if idx >= 0:
            self.cbo_translate.setCurrentIndex(idx)
        form.addRow("Translate provider:", self.cbo_translate)

        layout.addLayout(form)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_save = QPushButton("Save")
        btn_cancel = QPushButton("Cancel")
        btn_save.clicked.connect(self.on_save)
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_save)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

        self.setStyleSheet("""
            QDialog {
                background: #F5F7FA;
                color: #1a1a1a;
            }
            QLabel {
                color: #1a1a1a;
                background: transparent;
                font-size: 13px;
                font-weight: 600;
            }
            QLineEdit {
                background: #FFFFFF;
                color: #1a1a1a;
                border: 1px solid #C0C8D8;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #4A90D9;
            }
            QPushButton {
                background: #E8EDF5;
                color: #1a1a1a;
                border: 1px solid #C0C8D8;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #D0DAF0;
                border: 1px solid #4A90D9;
            }
            QPushButton:pressed {
                background: #B8C8E8;
            }
        """)

    def on_save(self):
        cfg = load_llm_config()
        cfg["openrouter_api_key"]  = self.ed_openrouter.text().strip()
        cfg["groq_api_key"]        = self.ed_groq.text().strip()
        cfg["gemini_api_key"]      = self.ed_gemini.text().strip()
        cfg["ollama_host"]         = self.ed_ollama_host.text().strip() or "http://localhost:11434"
        cfg["ollama_model"]        = self.ed_ollama_model.text().strip() or DEFAULT_OLLAMA_MODEL
        cfg["openrouter_model"]    = self.ed_openrouter_model.text().strip() or DEFAULT_OPENROUTER_MODEL
        cfg["groq_model"]          = self.ed_groq_model.text().strip() or DEFAULT_GROQ_MODEL
        cfg["gemini_model"]        = self.ed_gemini_model.text().strip() or DEFAULT_GEMINI_MODEL
        cfg["translate_provider"]  = self.cbo_translate.currentData()
        try:
            save_llm_config(cfg)
            QMessageBox.information(self, "Saved", f"Saved to:\n{get_config_path()}")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save failed", f"{type(e).__name__}: {e}")


# ── Worker: dịch sang tiếng Việt ─────────────────────────────────
class TranslateWorker(QThread):
    done  = Signal(str)
    error = Signal(str)

    def __init__(self, text: str, provider: str):
        super().__init__()
        self.text     = text
        self.provider = provider

    def run(self):
        try:
            client = create_llm_client(self.provider)
            prompt = (
                "Translate the following technical document analysis into Vietnamese.\n"
                "RULES:\n"
                "- Keep ALL technical English terms as-is "
                "(e.g., trip, interlock, bearing, rotor, valve, RPM, bar, °C, ISO, IEC, etc.)\n"
                "- Only translate the explanatory text, descriptions, and analysis\n"
                "- Preserve all formatting: headings, bullet points, section numbers, ⚠️ symbols\n"
                "- Do NOT add or remove any content\n\n"
                f"{self.text}"
            )
            self.done.emit(client.generate(prompt))
        except Exception as e:
            self.error.emit(str(e))


# ── Helpers lưu/load summary ─────────────────────────────────────
def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))

def _load_summaries() -> dict:
    if not os.path.exists(paths.SUMMARIES_FILE):
        return {}
    try:
        with open(paths.SUMMARIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_summary(file_path: str, html: str):
    data = _load_summaries()
    data[_norm(file_path)] = html
    tmp = paths.SUMMARIES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, paths.SUMMARIES_FILE)


# ── Widget chính ─────────────────────────────────────────────────
class PdfPreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._path             = None
        self._translate_worker = None
        self._original_text    = None
        self._translated_text  = None
        self._is_translated    = False
        self._online_mindmap_nb_id  = None   # notebook_id khi dùng mind map online
        self._online_mindmap_html   = None   # HTML cache cho fullscreen
        self._online_mindmap_title  = ""
        self._mindmap_shown_path    = None   # path của file đang hiển thị mind map local (None = đang hiện online hoặc chưa hiện gì)
        self.setMinimumWidth(300)
        self.setFocusPolicy(Qt.WheelFocus)
        self._setup_ui()

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: none; }
            QTabBar::tab {
                background: rgba(255,255,255,10);
                color: rgba(220,230,255,180);
                padding: 6px 18px;
                border-radius: 4px;
                margin-right: 2px;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background: rgba(40,180,110,50);
                color: white;
                border-bottom: 2px solid rgba(60,210,140,220);
            }
            QTabBar::tab:hover { background: rgba(255,255,255,20); }
        """)
        lay.addWidget(self.tabs, 1)

        # ── Tab 1: PDF viewer ─────────────────────────────────────
        viewer_widget = QWidget()
        viewer_widget.setObjectName("pdfContent")
        vlay = QVBoxLayout(viewer_widget)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        # Search bar (Ctrl+F to toggle)
        self._pdf_search_bar = QWidget()
        self._pdf_search_bar.setStyleSheet("""
            QWidget { background: #2b3050; }
            QLineEdit {
                background: #3a4070;
                color: #e0e8ff;
                border: 1px solid #5068c0;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 12px;
            }
            QLabel { color: #a8b8d8; background: transparent; font-size: 13px; }
            QPushButton {
                background: #404878;
                color: #e0e8ff;
                border: 1px solid #6070a8;
                border-radius: 4px;
                font-size: 10px;
                padding: 2px 6px;
            }
            QPushButton:hover { background: #5060a0; }
        """)
        _sl = QHBoxLayout(self._pdf_search_bar)
        _sl.setContentsMargins(8, 3, 8, 3)
        _sl.setSpacing(4)
        _sl.addWidget(QLabel("🔍"))
        self._pdf_search_edit = QLineEdit()
        self._pdf_search_edit.setPlaceholderText("Search in PDF…")
        self._pdf_search_edit.returnPressed.connect(self._pdf_find_next)
        self._pdf_search_edit.textChanged.connect(
            lambda t: self.pdf_view.page().findText(t)
        )
        _sl.addWidget(self._pdf_search_edit, 1)
        self._pdf_match_label = QLabel("")
        self._pdf_match_label.setFixedWidth(64)
        _sl.addWidget(self._pdf_match_label)
        _btn_prev = QPushButton("Prev")
        _btn_prev.setToolTip("Find previous (Shift+Enter)")
        _btn_next = QPushButton("Next")
        _btn_next.setToolTip("Find next (Enter)")
        _btn_cls  = QPushButton("Close")
        _btn_cls.setToolTip("Close search bar (Esc)")
        for _b in (_btn_prev, _btn_next, _btn_cls):
            _b.setFixedHeight(26)
        _btn_prev.clicked.connect(self._pdf_find_prev)
        _btn_next.clicked.connect(self._pdf_find_next)
        _btn_cls.clicked.connect(self._close_pdf_search)
        _sl.addWidget(_btn_prev)
        _sl.addWidget(_btn_next)
        _sl.addWidget(_btn_cls)
        self._pdf_search_bar.setVisible(False)
        vlay.addWidget(self._pdf_search_bar)

        self.pdf_view = QWebEngineView()
        self.pdf_view.settings().setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        self.pdf_view.settings().setAttribute(QWebEngineSettings.WebAttribute.PdfViewerEnabled, True)
        self.pdf_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.pdf_view.customContextMenuRequested.connect(self._show_pdf_context_menu)
        vlay.addWidget(self.pdf_view, 1)

        self.tabs.addTab(viewer_widget, "📄 Page")

        # ── Tab 2: Notes + Summary ────────────────────────────────
        sum_widget = QWidget()
        sum_widget.setObjectName("pdfContent")
        slay = QVBoxLayout(sum_widget)
        slay.setContentsMargins(0, 4, 0, 0)
        slay.setSpacing(4)

        # Toolbar: font + format + generate + save
        toolbar_widget = QWidget()
        toolbar = QHBoxLayout(toolbar_widget)
        toolbar.setContentsMargins(6, 4, 6, 4)
        toolbar.setSpacing(4)

        # Font size
        self.cbo_font_size = QComboBox()
        self.cbo_font_size.addItems([str(s) for s in range(8, 32)])
        self.cbo_font_size.setCurrentText("15")
        self.cbo_font_size.setFixedWidth(54)
        self.cbo_font_size.currentTextChanged.connect(self._change_font_size)
        toolbar.addWidget(QLabel("Size:"))
        toolbar.addWidget(self.cbo_font_size)

        # Bold
        _btn_ss = "padding: 2px 6px; font-size: 11px;"

        self.btn_bold = QToolButton()
        self.btn_bold.setText("B")
        self.btn_bold.setCheckable(True)
        self.btn_bold.setFixedSize(28, 26)
        self.btn_bold.setStyleSheet(_btn_ss + "font-weight: bold;")
        self.btn_bold.clicked.connect(self._toggle_bold)
        toolbar.addWidget(self.btn_bold)

        self.btn_italic = QToolButton()
        self.btn_italic.setText("I")
        self.btn_italic.setCheckable(True)
        self.btn_italic.setFixedSize(28, 26)
        self.btn_italic.setStyleSheet(_btn_ss + "font-style: italic;")
        self.btn_italic.clicked.connect(self._toggle_italic)
        toolbar.addWidget(self.btn_italic)

        toolbar.addStretch(1)

        btn_img = QPushButton("🖼 Image")
        btn_img.setFixedHeight(26)
        btn_img.setStyleSheet(_btn_ss)
        btn_img.setToolTip("Insert image")
        btn_img.clicked.connect(self._insert_image)
        toolbar.addWidget(btn_img)

        self.btn_translate = QPushButton("🌐 VI")
        self.btn_translate.setFixedHeight(26)
        self.btn_translate.setStyleSheet(_btn_ss)
        self.btn_translate.setToolTip("Toggle English / Vietnamese")
        self.btn_translate.clicked.connect(self._toggle_translate)
        toolbar.addWidget(self.btn_translate)

        self.btn_nlm_summary = QPushButton("📓 NbLM")
        self.btn_nlm_summary.setFixedHeight(26)
        self.btn_nlm_summary.setStyleSheet(_btn_ss)
        self.btn_nlm_summary.setToolTip("Summarize with NotebookLM (upload → get guide → delete)")
        self.btn_nlm_summary.clicked.connect(self._nlm_summarize)
        toolbar.addWidget(self.btn_nlm_summary)

        self.btn_mind_map = QPushButton("🗺 Mind Map")
        self.btn_mind_map.setFixedHeight(26)
        self.btn_mind_map.setStyleSheet(_btn_ss)
        self.btn_mind_map.setToolTip("Generate mind map with NotebookLM")
        self.btn_mind_map.clicked.connect(self._nlm_mind_map)
        toolbar.addWidget(self.btn_mind_map)

        self.btn_regen_map = QPushButton("🔄")
        self.btn_regen_map.setFixedSize(26, 26)
        self.btn_regen_map.setStyleSheet(_btn_ss)
        self.btn_regen_map.setToolTip("Regenerate mind map (clears cache)")
        self.btn_regen_map.setVisible(False)
        self.btn_regen_map.clicked.connect(self._regen_mind_map)
        toolbar.addWidget(self.btn_regen_map)

        self.btn_fullscreen_map = QPushButton("⛶")
        self.btn_fullscreen_map.setFixedSize(26, 26)
        self.btn_fullscreen_map.setStyleSheet(_btn_ss)
        self.btn_fullscreen_map.setToolTip("Open mind map fullscreen")
        self.btn_fullscreen_map.setVisible(False)
        self.btn_fullscreen_map.clicked.connect(self._open_mindmap_fullscreen)
        toolbar.addWidget(self.btn_fullscreen_map)

        self.btn_save = QPushButton("💾 Save")
        self.btn_save.setFixedHeight(26)
        self.btn_save.setStyleSheet(_btn_ss)
        self.btn_save.clicked.connect(self._save_note)
        toolbar.addWidget(self.btn_save)

        slay.addWidget(toolbar_widget)

        # Vertical splitter: text notes (top) | mind map (bottom)
        self._notes_splitter = QSplitter(Qt.Vertical)
        notes_splitter = self._notes_splitter

        # Rich text editor
        self.txt_summary = RichTextEdit()
        self.txt_summary.setPlaceholderText(
            "No notes yet. Click 📓 NbLM to summarize with NotebookLM, or write your own notes here."
        )
        font = self.txt_summary.font()
        font.setPointSize(11)
        self.txt_summary.setFont(font)
        notes_splitter.addWidget(self.txt_summary)

        # Mind map viewer (hidden until generated)
        try:
            self._web_view = QWebEngineView()
            self._mm_page = MindMapPage(self._web_view)
            self._mm_page.action.connect(self._on_mindmap_action)
            self._web_view.setPage(self._mm_page)
            self._web_view.setContextMenuPolicy(Qt.NoContextMenu)
            self._web_view.setVisible(False)
            notes_splitter.addWidget(self._web_view)
        except Exception:
            self._web_view = None

        notes_splitter.setStretchFactor(0, 2)
        notes_splitter.setStretchFactor(1, 3)
        slay.addWidget(notes_splitter, 1)

        self.tabs.addTab(sum_widget, "📝 Notes")

        sc = QShortcut(QKeySequence("Ctrl+F"), self)
        sc.activated.connect(self._on_find_shortcut)

    def _on_find_shortcut(self):
        if self.tabs.currentIndex() == 0:
            self._toggle_pdf_search()

    def _toggle_pdf_search(self):
        visible = not self._pdf_search_bar.isVisible()
        self._pdf_search_bar.setVisible(visible)
        if visible:
            self._pdf_search_edit.setFocus()
            self._pdf_search_edit.selectAll()
        else:
            self.pdf_view.page().findText("")
            self._pdf_match_label.setText("")

    def _close_pdf_search(self):
        self._pdf_search_bar.setVisible(False)
        self.pdf_view.page().findText("")
        self._pdf_match_label.setText("")

    def _pdf_find_next(self):
        text = self._pdf_search_edit.text()
        self.pdf_view.page().findText(
            text, QWebEnginePage.FindFlags(), self._on_find_result
        )

    def _pdf_find_prev(self):
        text = self._pdf_search_edit.text()
        self.pdf_view.page().findText(
            text,
            QWebEnginePage.FindFlag.FindBackward,
            self._on_find_result,
        )

    def _on_find_result(self, result) -> None:
        n = result.numberOfMatches()
        if n == 0:
            self._pdf_match_label.setText("No match" if self._pdf_search_edit.text() else "")
        else:
            self._pdf_match_label.setText(f"{result.activeMatch()}/{n}")

    def _show_pdf_context_menu(self, pos):
        """Hiển thị menu ngữ cảnh tối giản cho PDF viewer."""
        menu = QMenu(self)
        copy_action = menu.addAction("Copy")
        copy_action.triggered.connect(lambda: self.pdf_view.page().triggerAction(QWebEnginePage.Copy))
        copy_action.setEnabled(self.pdf_view.page().hasSelection())
        menu.addSeparator()
        find_action = menu.addAction("Find…\tCtrl+F")
        find_action.triggered.connect(self._toggle_pdf_search)
        menu.exec(self.pdf_view.mapToGlobal(pos))

    # ── Load file ────────────────────────────────────────────────
    def load(self, path: str):
        if not path or not path.lower().endswith(".pdf"):
            self.clear()
            return
        if not os.path.exists(path):
            self.clear()
            return
        # Auto-save ghi chú file cũ trước khi chuyển
        if self._path and self._path != path:
            self._save_note(silent=True)
        try:
            self._path     = path
            
            url = QUrl.fromLocalFile(path)
            self.pdf_view.setUrl(url)
            self._load_existing_summary(path)
        except Exception:
            self.clear()

    def clear(self):
        if self._path:
            self._save_note(silent=True)
        self._path     = None
        self._mindmap_shown_path = None
        self.pdf_view.setHtml("")
        self.txt_summary.clear()

    def goto_page(self, page_num: int):
        if self._path:
            url = QUrl.fromLocalFile(self._path)
            url.setFragment(f"page={page_num + 1}")
            self.pdf_view.setUrl(url)

    # ── Font & format ────────────────────────────────────────────
    def _change_font_size(self, size: str):
        fmt = QTextCharFormat()
        fmt.setFontPointSize(float(size))
        self.txt_summary.mergeCurrentCharFormat(fmt)
        self.txt_summary.setFocus()

    def _toggle_bold(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Bold if self.btn_bold.isChecked() else QFont.Normal)
        self.txt_summary.mergeCurrentCharFormat(fmt)
        self.txt_summary.setFocus()

    def _toggle_italic(self):
        fmt = QTextCharFormat()
        fmt.setFontItalic(self.btn_italic.isChecked())
        self.txt_summary.mergeCurrentCharFormat(fmt)
        self.txt_summary.setFocus()

    def _insert_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select image", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if path:
            import base64
            ext = os.path.splitext(path)[1].lower().lstrip(".")
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            cursor = self.txt_summary.textCursor()
            cursor.insertHtml(f'<img src="data:image/{ext};base64,{b64}">')

    # ── Save / Load ──────────────────────────────────────────────
    def _load_existing_summary(self, path: str):
        data = _load_summaries()
        html = data.get(_norm(path), "")
        if html:
            self.txt_summary.setHtml(html)
        else:
            self.txt_summary.clear()

    def _save_note(self, silent: bool = False):
        if not self._path:
            return
        html = self.txt_summary.toHtml()
        _save_summary(self._path, html)
        if not silent:
            self.btn_save.setText("✅ Saved")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1500, lambda: self.btn_save.setText("💾 Save"))

    def _toggle_translate(self):
        if not self._original_text:
            return
        if self._is_translated:
            self.txt_summary.setPlainText(self._original_text)
            self._is_translated = False
            self.btn_translate.setText("🌐 VI")
        else:
            if self._translated_text:
                # Dùng cache, không gọi API
                self.txt_summary.setPlainText(self._translated_text)
                self._is_translated = True
                self.btn_translate.setText("🌐 EN")
            else:
                self.btn_translate.setEnabled(False)
                self.btn_translate.setText("⏳")
                provider = load_llm_config().get("translate_provider", "gemini")
                self._translate_worker = TranslateWorker(self._original_text, provider)
                self._translate_worker.done.connect(self._on_translate_done)
                self._translate_worker.error.connect(self._on_translate_error)
                self._translate_worker.start()

    def _on_translate_done(self, result: str):
        self._translated_text = result
        self.txt_summary.setPlainText(result)
        self._is_translated = True
        self.btn_translate.setEnabled(True)
        self.btn_translate.setText("🌐 EN")

    def _on_translate_error(self, msg: str):
        self.txt_summary.setPlainText(f"Translation error: {msg}")
        self.btn_translate.setEnabled(True)
        self.btn_translate.setText("🌐 VI")

    def _nlm_summarize(self):
        if not self._path:
            return
        from ui.notebooklm_window import is_nlm_logged_in, NLMAutoSummarizeWorker
        if not is_nlm_logged_in():
            QMessageBox.warning(self, "Not Logged In",
                "Please log in to NotebookLM first.\n\nGo to the 📓 NotebookLM tab and click 🔑 Switch Account.")
            return
        self.btn_nlm_summary.setEnabled(False)
        self.btn_nlm_summary.setText("⏳")
        self.txt_summary.setPlainText("Uploading to NotebookLM and generating summary…")
        self._nlm_worker = NLMAutoSummarizeWorker(self._path)
        self._nlm_worker.done.connect(self._on_nlm_done)
        self._nlm_worker.error.connect(self._on_nlm_error)
        self._nlm_worker.start()

    def _on_nlm_done(self, text: str):
        self._original_text   = text
        self._translated_text = None
        self._is_translated   = False
        self.btn_translate.setText("🌐 VI")
        self.txt_summary.setPlainText(text)
        self.btn_nlm_summary.setEnabled(True)
        self.btn_nlm_summary.setText("📓 NbLM")

    def _on_nlm_error(self, msg: str):
        self.txt_summary.setPlainText(f"NotebookLM error: {msg}")
        self.btn_nlm_summary.setEnabled(True)
        self.btn_nlm_summary.setText("📓 NbLM")

    def _mindmap_path(self) -> str | None:
        """Return path to cached mindmap HTML for current file, or None."""
        if not self._path:
            return None
        import hashlib, paths
        h = hashlib.md5(self._path.encode()).hexdigest()[:12]
        os.makedirs(paths.MINDMAP_DIR, exist_ok=True)
        return os.path.join(paths.MINDMAP_DIR, f"{h}.html")

    def _nlm_mind_map(self):
        try:
            self._nlm_mind_map_impl()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.btn_mind_map.setEnabled(True)
            self.btn_mind_map.setText("🗺 Mind Map")
            QMessageBox.critical(self, "Mind Map Error", f"Lỗi khi tạo mind map:\n\n{e}")

    def _nlm_mind_map_impl(self):
        if not self._path:
            QMessageBox.warning(self, "No File", "Chưa mở file PDF nào trong Preview.")
            return
        if self._web_view is None:
            QMessageBox.warning(self, "Not Available",
                "QWebEngineView is not installed.\nInstall PySide6-WebEngine to use Mind Map.")
            return
        # Toggle: if already showing THIS file's map, hide it. If it's showing
        # a different file's map (or an online map), fall through and (re)generate
        # for the current file instead of just hiding it.
        if self._web_view.isVisible() and self._mindmap_shown_path == self._path:
            self._web_view.setVisible(False)
            self.btn_regen_map.setVisible(False)
            self.btn_fullscreen_map.setVisible(False)
            self.btn_mind_map.setText("🗺 Mind Map")
            return
        # Check cache first
        cached = self._mindmap_path()
        if cached and os.path.isfile(cached):
            with open(cached, "r", encoding="utf-8") as f:
                html = f.read()
            self._mindmap_shown_path = self._path
            self._show_mindmap(html)
            return
        # Need to generate — check login
        from ui.notebooklm_window import is_nlm_logged_in, MindMapWorker
        if not is_nlm_logged_in():
            QMessageBox.warning(self, "Not Logged In",
                "Please log in to NotebookLM first.\n\nGo to the 📓 NotebookLM tab and click 🔑 Switch Account.")
            return
        self.btn_mind_map.setEnabled(False)
        self.btn_mind_map.setText("⏳")
        self._web_view.setHtml("<p style='font-family:sans-serif;color:#cdd6f4;padding:16px'>Generating mind map…</p>")
        self._show_mindmap_panel()
        self._mindmap_shown_path = self._path
        _nlm = getattr(self.window(), "notebooklm_widget", None)
        _lang = getattr(_nlm, "_current_language", "en")
        self._mindmap_worker = MindMapWorker(self._path, _lang)
        self._mindmap_worker.done.connect(self._on_mindmap_done)
        self._mindmap_worker.error.connect(self._on_mindmap_error)
        self._mindmap_worker.start()

    def show_mindmap_online(self, notebook_id: str, source_id: str, title: str):
        try:
            self._show_mindmap_online_impl(notebook_id, source_id, title)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.btn_mind_map.setEnabled(True)
            self.btn_mind_map.setText("🗺 Mind Map")
            QMessageBox.critical(self, "Mind Map Error", f"Lỗi khi tạo mind map:\n\n{e}")

    def _show_mindmap_online_impl(self, notebook_id: str, source_id: str, title: str):
        """Tạo mind map từ source trên NbLM, hiển thị trong Notes panel (không cần file local)."""
        if self._web_view is None:
            QMessageBox.warning(self, "Not Available",
                "QWebEngineView is not installed.\nInstall PySide6-WebEngine to use Mind Map.")
            return
        from ui.notebooklm_window import is_nlm_logged_in, MindMapWorkerOnline
        if not is_nlm_logged_in():
            QMessageBox.warning(self, "Not Logged In",
                "Please log in to NotebookLM first.")
            return
        self._online_mindmap_nb_id = notebook_id
        self._online_mindmap_title = title
        self._online_mindmap_html  = None
        self._mindmap_shown_path   = None
        self.btn_mind_map.setEnabled(False)
        self.btn_mind_map.setText("⏳")
        self._web_view.setHtml("<p style='font-family:sans-serif;color:#cdd6f4;padding:16px'>Generating mind map…</p>")
        self._show_mindmap_panel()
        _nlm = getattr(self.window(), "notebooklm_widget", None)
        _lang = getattr(_nlm, "_current_language", "en")
        self._mindmap_worker = MindMapWorkerOnline(notebook_id, title, source_id, _lang)
        self._mindmap_worker.done.connect(self._on_mindmap_online_done)
        self._mindmap_worker.error.connect(self._on_mindmap_error)
        self._mindmap_worker.start()

    def _on_mindmap_online_done(self, html: str):
        self._online_mindmap_html = html
        self._web_view.setHtml(html)
        self.btn_mind_map.setEnabled(True)
        self.btn_mind_map.setText("🗺 Mind Map")

    def _show_mindmap_panel(self):
        self._web_view.setVisible(True)
        self.btn_regen_map.setVisible(True)
        self.btn_fullscreen_map.setVisible(True)
        total = self._notes_splitter.height()
        self._notes_splitter.setSizes([max(100, total // 2), max(200, total // 2)])
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i).startswith("📝"):
                self.tabs.setCurrentIndex(i)
                break

    def _show_mindmap(self, html: str):
        self._web_view.setHtml(html)
        self._show_mindmap_panel()

    def _on_mindmap_action(self, action: str):
        if action == "mm:fullscreen":
            self._open_mindmap_fullscreen()
        elif action.startswith("mm:ask:"):
            node_name = action[len("mm:ask:"):]
            self._ask_nlm_about_node(node_name)
        elif action.startswith("mm:page:"):
            try:
                page_num = int(action[len("mm:page:"):])
            except ValueError:
                return
            self._open_source_at_page(page_num)

    def _open_source_at_page(self, page_num: int):
        """Open the mindmap source file at the given 1-based page number."""
        from ui.notebooklm_window import _lookup_source_path
        # Try online mindmap source first
        title = getattr(self, "_online_mindmap_title", None)
        file_path = None
        if title:
            file_path = _lookup_source_path(title)
        # Fall back to currently loaded file (local mindmap)
        if not file_path:
            file_path = self._path
        if not file_path or not os.path.isfile(file_path):
            return
        if file_path != self._path:
            self.load(file_path)
        self.goto_page(page_num - 1)

    def _ask_nlm_about_node(self, node_name: str):
        """Switch to NbLM tab, auto-select notebook, and ask about the node."""
        from ui.notebooklm_window import NotebookLMWidget
        from PySide6.QtCore import QTimer
        main = self.window()
        nlm = getattr(main, "notebooklm_widget", None)
        if nlm is None:
            return
        # Switch to NbLM tab first
        tabs = getattr(main, "_search_tabs", None)
        if tabs:
            for i in range(tabs.count()):
                if isinstance(tabs.widget(i), NotebookLMWidget):
                    tabs.setCurrentIndex(i)
                    break
        # Try auto-select notebook from source map
        if self._path:
            nlm.select_notebook_for_file(self._path)
        elif self._online_mindmap_nb_id:
            # Mind map was generated online — select that notebook directly
            from PySide6.QtCore import Qt as _Qt
            for i in range(nlm.lst_notebooks.topLevelItemCount()):
                item = nlm.lst_notebooks.topLevelItem(i)
                if item.data(0, _Qt.UserRole) == self._online_mindmap_nb_id:
                    nlm.lst_notebooks.setCurrentItem(item)
                    break
        # Check notebook is selected (auto or manual)
        if not nlm._current_notebook_id:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Notebook",
                "Could not find a matching notebook.\nPlease select one in the NbLM tab first.")
            return
        QTimer.singleShot(150, lambda: nlm.ask_from_mindmap(node_name))

    def _open_mindmap_fullscreen(self):
        """Open mind map in a maximized dialog."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout
        cached = self._mindmap_path()
        has_cache = cached and os.path.isfile(cached)
        has_online = bool(self._online_mindmap_html)
        if not has_cache and not has_online:
            return
        title = os.path.basename(self._path) if self._path else self._online_mindmap_title
        dlg = QDialog(self)
        dlg.setWindowTitle("Mind Map — " + title)
        dlg.setLayout(QVBoxLayout())
        dlg.layout().setContentsMargins(0, 0, 0, 0)
        view = QWebEngineView()
        page = MindMapPage(view)
        view.setPage(page)
        view.setContextMenuPolicy(Qt.NoContextMenu)
        if has_cache:
            view.load(QUrl.fromLocalFile(cached))
        else:
            view.setHtml(self._online_mindmap_html)
        dlg.layout().addWidget(view)
        dlg.showMaximized()
        dlg.exec()

    def _regen_mind_map(self):
        """Delete cache and regenerate mind map for current file."""
        cached = self._mindmap_path()
        if cached and os.path.isfile(cached):
            try:
                os.remove(cached)
            except Exception:
                pass
        self._web_view.setVisible(False)
        self.btn_regen_map.setVisible(False)
        self._nlm_mind_map()

    def _on_mindmap_done(self, html: str):
        # Save to cache
        cached = self._mindmap_path()
        if cached:
            try:
                with open(cached, "w", encoding="utf-8") as f:
                    f.write(html)
            except Exception:
                pass
        self._web_view.setHtml(html)
        self.btn_mind_map.setEnabled(True)
        self.btn_mind_map.setText("🗺 Mind Map")

    def _on_mindmap_error(self, msg: str):
        self._web_view.setHtml(
            f"<p style='font-family:sans-serif;color:red;padding:16px'>Mind map error: {msg}</p>")
        self.btn_mind_map.setEnabled(True)
        self.btn_mind_map.setText("🗺 Mind Map")

    def _open_llm_summary(self):
        LLMSettingsDialog(self).exec()

    def closeEvent(self, event):
        if self._path:
            self._save_note(silent=True)
        super().closeEvent(event)
