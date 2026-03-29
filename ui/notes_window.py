"""
ui/notes_window.py — NotesWindow (rich text + ảnh) và RichTextEdit.
"""
import os
import base64

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFileDialog, QMessageBox, QComboBox,
)
from PySide6.QtCore import QMimeData, QBuffer
from PySide6.QtGui import QImage


class RichTextEdit(QTextEdit):
    """QTextEdit hỗ trợ paste ảnh từ clipboard dưới dạng base64 HTML."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(True)

    def insertFromMimeData(self, source: QMimeData):
        if source.hasImage():
            image: QImage = source.imageData()
            buf = QBuffer()
            buf.open(QBuffer.ReadWrite)
            image.save(buf, "PNG")
            b64 = base64.b64encode(buf.data()).decode()
            self.textCursor().insertHtml(f'<img src="data:image/png;base64,{b64}">')
        else:
            super().insertFromMimeData(source)


class NotesWindow(QDialog):
    """Cửa sổ ghi chú rich-text cho từng file trong container."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_app = None          # gắn sau khi tạo: notes_window.main_app = self
        self.selected_container = None
        self.selected_file = None

        self.setWindowTitle("Notes")
        self.setGeometry(1300, 100, 800, 600)

        layout = QVBoxLayout(self)

        self.file_name_label = QLabel("Selected File: None")
        layout.addWidget(self.file_name_label)

        self.note_text = RichTextEdit()
        self.note_text.setAcceptRichText(True)
        layout.addWidget(self.note_text)

        # Button bar
        self.font_size_combo = QComboBox()
        self.font_size_combo.addItems([str(s) for s in range(8, 31, 2)])
        self.font_size_combo.setCurrentText("12")
        self.font_size_combo.currentTextChanged.connect(self._change_font_size)

        insert_btn = QPushButton("Insert Image")
        insert_btn.clicked.connect(self._insert_image)
        save_btn = QPushButton("Save Note")
        save_btn.clicked.connect(self._save_note)

        btn_row = QHBoxLayout()
        btn_row.addWidget(insert_btn)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(QLabel("Font Size:"))
        btn_row.addWidget(self.font_size_combo)
        layout.addLayout(btn_row)

    # ── private helpers ──────────────────────────────────────────

    def _change_font_size(self, size: str):
        font = self.note_text.currentFont()
        font.setPointSize(int(size))
        self.note_text.setCurrentFont(font)

    def _insert_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Images (*.png *.xpm *.jpg *.jpeg *.bmp)"
        )
        if path:
            import base64, os
            ext = os.path.splitext(path)[1].lower().lstrip(".")
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            cursor = self.note_text.textCursor()
            cursor.insertHtml(f'<img src="data:image/{ext};base64,{b64}">')

    def _save_note(self):
        if not (self.selected_container and self.selected_file):
            return
        note_content = {"text": self.note_text.toHtml()}
        container = self.main_app.containers[self.selected_container]
        for i, (fp, _) in enumerate(container):
            if fp == self.selected_file:
                container[i] = (fp, note_content)
                break
        self.main_app.save_data_to_file()
        QMessageBox.information(self, "Success", "Note saved successfully!")

    # ── public API ───────────────────────────────────────────────

    def display_note_for_file(self, container_name: str, file_path: str):
        self.selected_container = container_name
        self.selected_file = file_path
        self.file_name_label.setText(os.path.basename(file_path))

        for fp, note in self.main_app.containers[container_name]:
            if fp == file_path:
                if isinstance(note, str):
                    note = {"text": note}
                self.note_text.setHtml(note.get("text", ""))
                break

        self.show()
