"""
ui/list_files_window.py — Cửa sổ danh sách file trong thư mục.
Bao gồm: lọc theo định dạng/kích thước, xoá, copy, đổi tên hàng loạt.
"""
import os
import webbrowser

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QFileDialog,
    QMessageBox, QLCDNumber, QApplication,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor


def show_list_files_window(parent) -> None:
    """Mở dialog chọn thư mục rồi hiển thị cửa sổ danh sách file."""
    folder = QFileDialog.getExistingDirectory(parent, "Select Folder")
    if not folder:
        return
    _ListFilesWindow(parent, folder).exec()


class _ListFilesWindow(QDialog):
    """Dialog nội bộ — dùng qua show_list_files_window()."""

    def __init__(self, parent, folder_path: str):
        super().__init__(parent)
        self.setWindowTitle("List of Files")
        self.setGeometry(700, 100, 1100, 600)

        self._all_files: list = []   # [(name, path, size_mb)]

        layout = QVBoxLayout(self)

        # LCD đếm file
        self.lcd = QLCDNumber()
        self.lcd.setDigitCount(6)
        palette = self.lcd.palette()
        palette.setColor(QPalette.WindowText, QColor("black"))
        palette.setColor(QPalette.Light, QColor("Blue"))
        palette.setColor(QPalette.Dark, QColor("black"))
        self.lcd.setPalette(palette)

        # Filter controls
        self.format_combo = QComboBox()
        self.format_combo.addItem("All")
        self.min_size = QLineEdit()
        self.min_size.setPlaceholderText("Min size (MB)")
        self.max_size = QLineEdit()
        self.max_size.setPlaceholderText("Max size (MB)")
        size_btn    = QPushButton("Filter by Size")
        delete_btn  = QPushButton("Delete Selected")
        copy_btn    = QPushButton("Copy to Clipboard")
        rename_btn  = QPushButton("Batch Rename")

        # Tree
        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Select", "Filename", "Path", "Size (MB)"])
        self.tree.setColumnWidth(0, 50)
        self.tree.setColumnWidth(1, 550)
        self.tree.setColumnWidth(2, 400)
        self.tree.setColumnWidth(3, 50)
        self.tree.setSelectionMode(QTreeWidget.MultiSelection)
        self.tree.itemDoubleClicked.connect(self._open_file)
        self.tree.itemClicked.connect(self._toggle_checkbox)

        layout.addWidget(self.tree)

        bar = QHBoxLayout()
        for w in [self.lcd, self.format_combo, delete_btn, copy_btn,
                  self.min_size, self.max_size, size_btn, rename_btn]:
            bar.addWidget(w)
        layout.addLayout(bar)

        # Signals
        size_btn.clicked.connect(self._filter_by_size)
        delete_btn.clicked.connect(self._delete_selected)
        copy_btn.clicked.connect(self._copy_clipboard)
        rename_btn.clicked.connect(self._open_batch_rename)
        self.format_combo.currentTextChanged.connect(self._filter_by_format)

        self._load_files(folder_path)

    # ── load ─────────────────────────────────────────────────────

    def _load_files(self, folder_path: str):
        extensions: set = set()
        for root, _, files in os.walk(folder_path):
            for name in files:
                path = os.path.join(root, name)
                try:
                    size_mb = os.path.getsize(path) / (1024 * 1024)
                except Exception:
                    size_mb = 0.0
                extensions.add(os.path.splitext(name)[1].lower())
                self._all_files.append((name, path, size_mb))

        self.format_combo.addItems(sorted(extensions))
        self._refresh_tree(self._all_files)

    # ── tree helpers ──────────────────────────────────────────────

    def _refresh_tree(self, files: list):
        self.tree.clear()
        for name, path, size_mb in files:
            item = QTreeWidgetItem(["", name, os.path.dirname(path), f"{size_mb:.2f}"])
            item.setData(1, Qt.UserRole, {"filename": name, "path": path})
            item.setCheckState(0, Qt.Unchecked)
            self.tree.addTopLevelItem(item)
        self.lcd.display(len(files))

    def _toggle_checkbox(self, item: QTreeWidgetItem, column: int):
        if column == 0:
            item.setCheckState(
                0, Qt.Unchecked if item.checkState(0) == Qt.Checked else Qt.Checked
            )

    # ── filters ──────────────────────────────────────────────────

    def _filter_by_format(self, ext: str):
        if ext == "All":
            self._refresh_tree(self._all_files)
        else:
            self._refresh_tree([(n, p, s) for n, p, s in self._all_files if p.endswith(ext)])

    def _filter_by_size(self):
        try:
            lo = float(self.min_size.text()) if self.min_size.text() else 0.0
            hi = float(self.max_size.text()) if self.max_size.text() else float("inf")
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Please enter valid numbers for size range.")
            return
        self._refresh_tree([(n, p, s) for n, p, s in self._all_files if lo <= s <= hi])

    # ── actions ──────────────────────────────────────────────────

    def _open_file(self, item: QTreeWidgetItem, _col: int):
        data = item.data(1, Qt.UserRole) or {}
        path = data.get("path", "")
        if path and os.path.exists(path):
            webbrowser.open(path)
        else:
            QMessageBox.warning(self, "Not Found", "File does not exist or path is invalid.")

    def _delete_selected(self):
        root = self.tree.invisibleRootItem()
        to_delete = [
            (os.path.join(root.child(i).text(2), root.child(i).text(1)), root.child(i))
            for i in reversed(range(root.childCount()))
            if root.child(i).checkState(0) == Qt.Checked
        ]
        if not to_delete:
            QMessageBox.information(self, "Notice", "No files selected for deletion.")
            return
        reply = QMessageBox.question(
            self, "Confirm", f"Delete {len(to_delete)} file(s)?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            for path, item in to_delete:
                try:
                    os.remove(path)
                    root.removeChild(item)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to delete {os.path.basename(path)}: {e}")
            QMessageBox.information(self, "Done", "Selected files deleted.")

    def _copy_clipboard(self):
        root = self.tree.invisibleRootItem()
        lines = [
            f"{root.child(i).text(1)}\t{root.child(i).text(2)}"
            for i in range(root.childCount())
        ]
        QApplication.clipboard().setText("\n".join(lines))
        QMessageBox.information(self, "Copied", "Filenames and paths copied to clipboard.")

    def _open_batch_rename(self):
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select at least one file.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Batch Rename")
        dlg.setGeometry(500, 300, 400, 200)
        layout = QVBoxLayout(dlg)

        prefix_in  = QLineEdit(); prefix_in.setPlaceholderText("Prefix")
        suffix_in  = QLineEdit(); suffix_in.setPlaceholderText("Suffix")
        replace_in = QLineEdit(); replace_in.setPlaceholderText("Text to Replace")

        for w in [prefix_in, suffix_in, replace_in]:
            layout.addWidget(w)

        ok_btn = QPushButton("Rename")
        ok_btn.clicked.connect(
            lambda: self._do_rename(selected, prefix_in.text(), suffix_in.text(), replace_in.text(), dlg)
        )
        layout.addWidget(ok_btn)
        dlg.exec()

    def _do_rename(self, items: list, prefix: str, suffix: str, replace_text: str, dialog: QDialog):
        for item in items:
            old_name = item.text(1)
            folder   = item.text(2)
            old_path = os.path.join(folder, old_name)
            if not os.path.exists(old_path):
                QMessageBox.critical(self, "Error", f"File not found: {old_path}")
                continue
            new_name = old_name.replace(replace_text, "") if replace_text else old_name
            new_name = f"{prefix}{new_name}{suffix}"
            new_path = os.path.join(folder, new_name)
            try:
                os.rename(old_path, new_path)
                item.setText(1, new_name)
                item.setData(1, Qt.UserRole, {"filename": new_name, "path": new_path})
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Rename failed: {e}")
        QMessageBox.information(self, "Done", "Batch rename complete.")
        dialog.accept()
