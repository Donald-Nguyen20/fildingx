"""
ui/index_search_window.py — Tìm kiếm nội dung trong SQLite index databases.
"""
import os
import sqlite3

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QFileDialog,
    QMessageBox, QApplication,
)
from PySide6.QtCore import Qt

from ui.hud_widgets import qss_hud_metal_header_feel, qss_white_results


class IndexSearchWindow(QDialog):
    """Tìm kiếm từ khóa trong một hoặc nhiều SQLite database đã import."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(qss_hud_metal_header_feel() + qss_white_results())
        self.setWindowTitle("Search Indexed Databases")
        self.setGeometry(800, 200, 700, 400)

        self.db_paths: list = []

        main_layout = QVBoxLayout(self)
        h_layout = QHBoxLayout()

        self.import_btn = QPushButton("Import DB")
        self.db_selector = QComboBox()
        self.db_selector.addItem("All")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter keyword...")
        self.search_btn = QPushButton("Search")
        self.copy_name_btn = QPushButton("Copy Name")

        h_layout.addWidget(self.import_btn)
        h_layout.addWidget(self.db_selector)
        h_layout.addWidget(self.search_input)
        h_layout.addWidget(self.search_btn)
        h_layout.addWidget(self.copy_name_btn)

        self.result_table = QTreeWidget()
        self.result_table.setObjectName("resultsTree")
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setUniformRowHeights(True)
        self.result_table.setRootIsDecorated(False)
        self.result_table.setColumnCount(2)
        self.result_table.setHeaderLabels(["File Name", "Path"])
        self.result_table.setColumnWidth(0, 520)
        self.result_table.setColumnWidth(1, 260)

        main_layout.addLayout(h_layout)
        main_layout.addWidget(self.result_table)

        self.import_btn.clicked.connect(self._import_database)
        self.search_btn.clicked.connect(self._search)
        self.search_input.returnPressed.connect(self._search)
        self.copy_name_btn.clicked.connect(self._copy_name)
        self.result_table.itemDoubleClicked.connect(self._open_file)

    # ── private ──────────────────────────────────────────────────

    def _import_database(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select SQLite Databases", "", "SQLite Files (*.db *.sqlite)"
        )
        if paths:
            self.db_paths.extend(paths)
            self.db_selector.clear()
            self.db_selector.addItem("All")
            self.db_selector.addItems(self.db_paths)
            QMessageBox.information(self, "Imported", f"Imported {len(paths)} database(s).")

    def _search(self):
        if not self.db_paths:
            QMessageBox.warning(self, "No Database", "Please import at least one SQLite database first.")
            return
        keyword = self.search_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, "Input Error", "Please enter a keyword.")
            return

        selected = self.db_selector.currentText()
        rows = []
        if selected == "All":
            for db in self.db_paths:
                for row in self._search_single(db, keyword):
                    rows.append((*row, db))
        else:
            for row in self._search_single(selected, keyword):
                rows.append((*row, selected))

        self.result_table.clear()
        if rows:
            for name, path, _content, db_path in rows:
                item = QTreeWidgetItem([name, path])
                item.setData(0, Qt.UserRole, db_path)
                self.result_table.addTopLevelItem(item)
        else:
            QMessageBox.information(self, "No Results", "No files found.")

    def _search_single(self, db_path: str, keyword: str) -> list:
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT name, path, content FROM files WHERE name LIKE ? OR content LIKE ?",
                (f"%{keyword}%", f"%{keyword}%"),
            )
            rows = cur.fetchall()
            conn.close()
            return rows
        except Exception as e:
            QMessageBox.warning(self, "DB Error", f"Failed to search {db_path}: {e}")
            return []

    def _copy_name(self):
        item = self.result_table.currentItem()
        if item:
            QApplication.clipboard().setText(item.text(0))
            QMessageBox.information(self, "Copied", f"Copied: {item.text(0)}")
        else:
            QMessageBox.warning(self, "No Selection", "Please select a file.")

    def _open_file(self, item: QTreeWidgetItem, _column: int):
        try:
            relative_path = item.text(1)
            db_path = item.data(0, Qt.UserRole)
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT path FROM files WHERE name = 'BASE_PATH'")
            row = cur.fetchone()
            conn.close()
            if row:
                abs_path = os.path.join(row[0], relative_path)
                if os.path.exists(abs_path):
                    os.startfile(abs_path)
                else:
                    QMessageBox.warning(self, "Not Found", f"File not found:\n{abs_path}")
            else:
                QMessageBox.warning(self, "Error", "BASE_PATH not found in database.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open file: {e}")
