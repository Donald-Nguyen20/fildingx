# ui/pdf_preview.py
import os
import fitz  # pymupdf
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage


class PdfPreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc = None
        self._page_idx = 0
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

        # Page display — fit to widget, no scroll
        self.lbl_page = QLabel()
        self.lbl_page.setAlignment(Qt.AlignCenter)
        self.lbl_page.setStyleSheet("background: #1a1a2e; border-radius: 6px;")
        lay.addWidget(self.lbl_page, 1)

        # Navigation bar (giữ lại làm backup)
        nav = QHBoxLayout()
        nav.setSpacing(6)

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
        lay.addLayout(nav)

    def load(self, path: str):
        if not path or not path.lower().endswith(".pdf"):
            self.clear()
            return
        if not os.path.exists(path):
            self.clear()
            return
        try:
            if self._doc:
                self._doc.close()
            self._doc = fitz.open(path)
            self._page_idx = 0
            self.lbl_name.setText(os.path.basename(path))
            self._render()
        except Exception:
            self.clear()

    def clear(self):
        if self._doc:
            self._doc.close()
            self._doc = None
        self._page_idx = 0
        self.lbl_name.setText("Chọn file PDF để xem trước")
        self.lbl_page.clear()
        self.lbl_counter.setText("—")
        self.btn_prev.setEnabled(False)
        self.btn_next.setEnabled(False)

    def _render(self):
        if not self._doc:
            return
        page = self._doc[self._page_idx]

        # Fit trang vào vùng hiển thị (cả width lẫn height)
        vw = self.lbl_page.width() - 8
        vh = self.lbl_page.height() - 8
        if vw < 100: vw = 400
        if vh < 100: vh = 500

        rect = page.rect
        zoom_w = vw / rect.width  if rect.width  > 0 else 1.0
        zoom_h = vh / rect.height if rect.height > 0 else 1.0
        zoom = min(zoom_w, zoom_h, 3.0)
        zoom = max(zoom, 0.3)

        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        self.lbl_page.setPixmap(QPixmap.fromImage(img))

        total = len(self._doc)
        self.lbl_counter.setText(f"{self._page_idx + 1} / {total}")
        self.btn_prev.setEnabled(self._page_idx > 0)
        self.btn_next.setEnabled(self._page_idx < total - 1)

    def wheelEvent(self, event):
        if not self._doc:
            return
        if event.angleDelta().y() < 0:
            self._next_page()
        else:
            self._prev_page()
        event.accept()

    def _prev_page(self):
        if self._doc and self._page_idx > 0:
            self._page_idx -= 1
            self._render()

    def _next_page(self):
        if self._doc and self._page_idx < len(self._doc) - 1:
            self._page_idx += 1
            self._render()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._doc:
            self._render()

    def closeEvent(self, event):
        if self._doc:
            self._doc.close()
            self._doc = None
        super().closeEvent(event)
