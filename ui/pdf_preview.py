# ui/pdf_preview.py
import os
import json
import fitz
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QComboBox, QFileDialog, QToolButton,
    QDialog, QFormLayout, QLineEdit, QMessageBox,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QImage, QTextCharFormat, QFont
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

import paths
from core.llm_client import create_llm_client, PROVIDERS
from core.llm_config import load_llm_config, save_llm_config, get_config_path, DEFAULT_CONFIG
from ui.notes_window import RichTextEdit


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
        self._doc              = None
        self._page_idx         = 0
        self._path             = None
        self._translate_worker = None
        self._original_text    = None
        self._translated_text  = None
        self._is_translated    = False
        self.setMinimumWidth(300)
        self.setFocusPolicy(Qt.WheelFocus)
        self._setup_ui()

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        # File name header
        self.lbl_name = QLabel("Select a PDF file to preview")
        self.lbl_name.setAlignment(Qt.AlignCenter)
        self.lbl_name.setWordWrap(True)
        self.lbl_name.setStyleSheet("font-size: 10px; padding: 2px;")
        lay.addWidget(self.lbl_name)

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
        vlay.setContentsMargins(0, 4, 0, 0)
        vlay.setSpacing(4)

        self.lbl_page = QLabel()
        self.lbl_page.setAlignment(Qt.AlignCenter)
        vlay.addWidget(self.lbl_page, 1)

        nav = QHBoxLayout()
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setFixedSize(36, 30)
        self.btn_prev.setEnabled(False)
        self.btn_prev.clicked.connect(self._prev_page)

        self.lbl_counter = QLabel("—")
        self.lbl_counter.setAlignment(Qt.AlignCenter)
        self.lbl_counter.setStyleSheet("font-size: 11px;")

        self.btn_next = QPushButton("▶")
        self.btn_next.setFixedSize(36, 30)
        self.btn_next.setEnabled(False)
        self.btn_next.clicked.connect(self._next_page)

        nav.addWidget(self.btn_prev)
        nav.addWidget(self.lbl_counter, 1)
        nav.addWidget(self.btn_next)
        vlay.addLayout(nav)

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

        btn_settings = QPushButton("⚙")
        btn_settings.setFixedSize(26, 26)
        btn_settings.setStyleSheet(_btn_ss)
        btn_settings.setToolTip("LLM Settings (API keys)")
        btn_settings.clicked.connect(self._open_llm_settings)
        toolbar.addWidget(btn_settings)

        self.btn_save = QPushButton("💾 Save")
        self.btn_save.setFixedHeight(26)
        self.btn_save.setStyleSheet(_btn_ss)
        self.btn_save.clicked.connect(self._save_note)
        toolbar.addWidget(self.btn_save)

        slay.addWidget(toolbar_widget)

        # Rich text editor
        self.txt_summary = RichTextEdit()
        self.txt_summary.setPlaceholderText(
            "No notes yet. Click 📓 NbLM to summarize with NotebookLM, or write your own notes here."
        )
        font = self.txt_summary.font()
        font.setPointSize(11)
        self.txt_summary.setFont(font)
        slay.addWidget(self.txt_summary, 1)

        self.tabs.addTab(sum_widget, "📝 Notes")

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
            if self._doc:
                self._doc.close()
            self._doc      = fitz.open(path)
            self._path     = path
            self._page_idx = 0
            self.lbl_name.setText(os.path.basename(path))
            self._render()
            self._load_existing_summary(path)
        except Exception:
            self.clear()

    def clear(self):
        if self._path:
            self._save_note(silent=True)
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:
                pass
            self._doc = None
        self._path     = None
        self._page_idx = 0
        self.lbl_name.setText("Select a PDF file to preview")
        self.lbl_page.clear()
        self.lbl_counter.setText("—")
        self.btn_prev.setEnabled(False)
        self.btn_next.setEnabled(False)
        self.txt_summary.clear()

    # ── Render trang ────────────────────────────────────────────
    def _render(self):
        if not self._doc:
            return
        page = self._doc[self._page_idx]

        vw = self.lbl_page.width()  - 8
        vh = self.lbl_page.height() - 8
        if vw < 100: vw = 400
        if vh < 100: vh = 500

        rect   = page.rect
        zoom_w = vw / rect.width  if rect.width  > 0 else 1.0
        zoom_h = vh / rect.height if rect.height > 0 else 1.0
        zoom   = min(zoom_w, zoom_h, 3.0)
        zoom   = max(zoom, 0.3)

        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        self.lbl_page.setPixmap(QPixmap.fromImage(img))

        total = len(self._doc)
        self.lbl_counter.setText(f"{self._page_idx + 1} / {total}")
        self.btn_prev.setEnabled(self._page_idx > 0)
        self.btn_next.setEnabled(self._page_idx < total - 1)

    def goto_page(self, page_num: int):
        if self._doc is not None:
            page_num = max(0, min(page_num, len(self._doc) - 1))
            self._page_idx = page_num
            self._render()

    def _prev_page(self):
        if self._doc and self._page_idx > 0:
            self._page_idx -= 1
            self._render()

    def _next_page(self):
        if self._doc and self._page_idx < len(self._doc) - 1:
            self._page_idx += 1
            self._render()

    def wheelEvent(self, event):
        if not self._doc:
            return
        if event.angleDelta().y() < 0:
            self._next_page()
        else:
            self._prev_page()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._doc:
            self._render()

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

    def _open_llm_summary(self):
        LLMSettingsDialog(self).exec()

    def _open_llm_settings(self):
        LLMSettingsDialog(self).exec()

    def closeEvent(self, event):
        if self._path:
            self._save_note(silent=True)
        if self._doc:
            self._doc.close()
            self._doc = None
        super().closeEvent(event)
