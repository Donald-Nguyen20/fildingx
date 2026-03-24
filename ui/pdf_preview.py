# ui/pdf_preview.py
import os
import json
import fitz
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QComboBox, QFileDialog, QToolButton,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QImage, QTextCharFormat, QFont

import paths
from core.llm_client import create_llm_client, PROVIDERS
from ui.notes_window import RichTextEdit


# ── Worker: chạy LLM ở background ────────────────────────────────
class SummaryWorker(QThread):
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
                "Bạn là chuyên gia phân tích tài liệu kỹ thuật. "
                "Đọc toàn bộ nội dung tài liệu dưới đây và viết bản tóm tắt CHI TIẾT theo cấu trúc sau:\n\n"
                "1. **Tổng quan**: Tên tài liệu, mục đích, phạm vi áp dụng, đối tượng sử dụng.\n"
                "2. **Nội dung từng phần**: Với MỖI phần/chương/mục trong tài liệu, mô tả:\n"
                "   - Tiêu đề phần đó\n"
                "   - Nội dung cụ thể (giữ nguyên thông số kỹ thuật, con số, đơn vị, tên thiết bị, mã hiệu)\n"
                "   - Yêu cầu hoặc điều kiện quan trọng trong phần đó\n"
                "3. **Thông số & dữ liệu quan trọng**: Liệt kê tất cả thông số kỹ thuật, giá trị giới hạn, điều kiện vận hành.\n"
                "4. **Cảnh báo & lưu ý bắt buộc**: Tất cả warning, caution, note quan trọng.\n"
                "5. **Quy trình / Các bước thực hiện** (nếu có): Mô tả từng bước cụ thể.\n"
                "6. **Kết luận**: Điểm mấu chốt cần nhớ khi làm việc với tài liệu này.\n\n"
                "Trả lời bằng ngôn ngữ của tài liệu. "
                "KHÔNG được bỏ qua thông tin kỹ thuật quan trọng. "
                "Viết đầy đủ, cụ thể, tránh nói chung chung.\n\n"
                f"{self.text[:30000]}"
            )
            result = client.generate(prompt)
            self.done.emit(result)
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
        self._doc      = None
        self._page_idx = 0
        self._path     = None
        self._worker   = None
        self.setMinimumWidth(300)
        self.setFocusPolicy(Qt.WheelFocus)
        self._setup_ui()

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        # File name header
        self.lbl_name = QLabel("Chọn file PDF để xem trước")
        self.lbl_name.setAlignment(Qt.AlignCenter)
        self.lbl_name.setWordWrap(True)
        self.lbl_name.setStyleSheet("color: #8b949e; font-size: 10px; padding: 2px;")
        lay.addWidget(self.lbl_name)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: none; background: #13131f; }
            QTabBar::tab {
                background: rgba(255,255,255,8);
                color: #8b949e;
                padding: 5px 14px;
                border-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected { background: rgba(40,180,110,50); color: white; }
        """)
        lay.addWidget(self.tabs, 1)

        # ── Tab 1: PDF viewer ─────────────────────────────────────
        viewer_widget = QWidget()
        vlay = QVBoxLayout(viewer_widget)
        vlay.setContentsMargins(0, 4, 0, 0)
        vlay.setSpacing(4)

        self.lbl_page = QLabel()
        self.lbl_page.setAlignment(Qt.AlignCenter)
        self.lbl_page.setStyleSheet("background: #1a1a2e; border-radius: 6px;")
        vlay.addWidget(self.lbl_page, 1)

        nav = QHBoxLayout()
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setFixedSize(36, 30)
        self.btn_prev.setEnabled(False)
        self.btn_prev.clicked.connect(self._prev_page)

        self.lbl_counter = QLabel("—")
        self.lbl_counter.setAlignment(Qt.AlignCenter)
        self.lbl_counter.setStyleSheet("color: #8b949e; font-size: 11px;")

        self.btn_next = QPushButton("▶")
        self.btn_next.setFixedSize(36, 30)
        self.btn_next.setEnabled(False)
        self.btn_next.clicked.connect(self._next_page)

        nav.addWidget(self.btn_prev)
        nav.addWidget(self.lbl_counter, 1)
        nav.addWidget(self.btn_next)
        vlay.addLayout(nav)

        self.tabs.addTab(viewer_widget, "📄 Trang")

        # ── Tab 2: Notes + Summary ────────────────────────────────
        sum_widget = QWidget()
        slay = QVBoxLayout(sum_widget)
        slay.setContentsMargins(0, 4, 0, 0)
        slay.setSpacing(4)

        # Toolbar: font + định dạng + generate + save
        toolbar_widget = QWidget()
        toolbar_widget.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,12);
                border-radius: 6px;
            }
            QLabel { color: #c9d1d9; font-size: 11px; background: transparent; }
            QComboBox {
                background: #2d333b; color: #e6edf3;
                border: 1px solid #444c56; border-radius: 4px;
                padding: 2px 6px; font-size: 11px;
            }
            QComboBox QAbstractItemView { background: #2d333b; color: #e6edf3; }
            QToolButton, QPushButton {
                background: #2d333b; color: #e6edf3;
                border: 1px solid #444c56; border-radius: 4px;
                font-size: 11px; padding: 2px 6px;
            }
            QToolButton:hover, QPushButton:hover { background: #373e47; }
            QToolButton:checked { background: rgba(40,180,110,80); border-color: rgba(60,210,140,180); }
        """)
        toolbar = QHBoxLayout(toolbar_widget)
        toolbar.setContentsMargins(6, 4, 6, 4)
        toolbar.setSpacing(4)

        # Font size
        self.cbo_font_size = QComboBox()
        self.cbo_font_size.addItems([str(s) for s in range(8, 31, 2)])
        self.cbo_font_size.setCurrentText("12")
        self.cbo_font_size.setFixedWidth(54)
        self.cbo_font_size.currentTextChanged.connect(self._change_font_size)
        toolbar.addWidget(QLabel("Size:"))
        toolbar.addWidget(self.cbo_font_size)

        # Bold
        self.btn_bold = QToolButton()
        self.btn_bold.setText("B")
        self.btn_bold.setCheckable(True)
        self.btn_bold.setFixedSize(28, 26)
        self.btn_bold.setStyleSheet(self.btn_bold.styleSheet() + "font-weight: bold;")
        self.btn_bold.clicked.connect(self._toggle_bold)
        toolbar.addWidget(self.btn_bold)

        # Italic
        self.btn_italic = QToolButton()
        self.btn_italic.setText("I")
        self.btn_italic.setCheckable(True)
        self.btn_italic.setFixedSize(28, 26)
        self.btn_italic.setStyleSheet(self.btn_italic.styleSheet() + "font-style: italic;")
        self.btn_italic.clicked.connect(self._toggle_italic)
        toolbar.addWidget(self.btn_italic)

        toolbar.addStretch(1)

        # Insert image
        btn_img = QPushButton("🖼 Ảnh")
        btn_img.setFixedHeight(26)
        btn_img.setToolTip("Chèn ảnh")
        btn_img.clicked.connect(self._insert_image)
        toolbar.addWidget(btn_img)

        # Provider + Generate
        self.cbo_provider = QComboBox()
        for key, label in PROVIDERS:
            self.cbo_provider.addItem(label, key)
        self.cbo_provider.setFixedWidth(140)
        toolbar.addWidget(self.cbo_provider)

        self.btn_generate = QPushButton("⚡ AI")
        self.btn_generate.setFixedHeight(26)
        self.btn_generate.setToolTip("Generate summary")
        self.btn_generate.clicked.connect(self._generate_summary)
        toolbar.addWidget(self.btn_generate)

        # Save
        self.btn_save = QPushButton("💾 Save")
        self.btn_save.setFixedHeight(26)
        self.btn_save.clicked.connect(self._save_note)
        toolbar.addWidget(self.btn_save)

        slay.addWidget(toolbar_widget)

        # Rich text editor
        self.txt_summary = RichTextEdit()
        self.txt_summary.setPlaceholderText(
            "Chưa có ghi chú. Bấm ⚡ để AI tóm tắt, hoặc tự ghi chú tại đây."
        )
        self.txt_summary.setStyleSheet("""
            QTextEdit {
                background: #1a1a2e;
                color: #c9d1d9;
                border: none;
                border-radius: 6px;
                padding: 8px;
                font-size: 12px;
            }
        """)
        slay.addWidget(self.txt_summary, 1)

        self.tabs.addTab(sum_widget, "📝 Ghi chú")

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
        if self._doc:
            self._doc.close()
            self._doc = None
        self._path     = None
        self._page_idx = 0
        self.lbl_name.setText("Chọn file PDF để xem trước")
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
            self, "Chọn ảnh", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if path:
            self.txt_summary.textCursor().insertImage(path)

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

    # ── Generate summary ─────────────────────────────────────────
    def _generate_summary(self):
        if not self._path or not self._doc:
            return
        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("…")
        self.txt_summary.setPlainText("Đang xử lý…")

        text = "\n".join(page.get_text("text") for page in self._doc).strip()
        if not text:
            self.txt_summary.setPlainText("Không đọc được nội dung PDF.")
            self.btn_generate.setEnabled(True)
            self.btn_generate.setText("⚡")
            return

        provider = self.cbo_provider.currentData()
        self._worker = SummaryWorker(text, provider)
        self._worker.done.connect(self._on_summary_done)
        self._worker.error.connect(self._on_summary_error)
        self._worker.start()

    def _on_summary_done(self, result: str):
        self.txt_summary.setPlainText(result)
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("⚡")

    def _on_summary_error(self, msg: str):
        self.txt_summary.setPlainText(f"Lỗi: {msg}")
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("⚡")

    def closeEvent(self, event):
        if self._path:
            self._save_note(silent=True)
        if self._doc:
            self._doc.close()
            self._doc = None
        super().closeEvent(event)
