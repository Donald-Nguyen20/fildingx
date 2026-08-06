"""
ui/index_search_window.py — Tìm kiếm nội dung trong SQLite index databases.
"""
import os
import json
import sqlite3

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QFileDialog,
    QMessageBox, QApplication, QLabel,
)
from PySide6.QtCore import Qt, QTimer

import paths
from core.ai_grouper import GroupWorker
from ui.hud_widgets import qss_hud_metal_header_feel, qss_white_results

_DB_LIST_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db_list.json")


def _load_db_list() -> list:
    try:
        if os.path.exists(_DB_LIST_FILE):
            with open(_DB_LIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_db_list(paths_list: list):
    try:
        with open(_DB_LIST_FILE, "w", encoding="utf-8") as f:
            json.dump(paths_list, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class IndexSearchWidget(QWidget):
    """Embedded widget — dùng trong tab hoặc dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.db_paths: list = _load_db_list()
        self._last_rows: list = []
        self._group_worker = None
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # ── Toolbar ──────────────────────────────────────────────
        h_layout = QHBoxLayout()

        self.import_btn = QPushButton("📂 Import DB")
        self.import_btn.setFixedHeight(38)

        self.db_selector = QComboBox()
        self.db_selector.setFixedHeight(38)
        self.db_selector.setMinimumWidth(160)
        self._refresh_selector()

        self.search_input = QLineEdit()
        self.search_input.setFixedHeight(38)
        self.search_input.setPlaceholderText("Enter keyword...")

        self.search_btn = QPushButton("🔍 Search")
        self.search_btn.setFixedHeight(38)

        self.copy_name_btn = QPushButton("📋 Copy")
        self.copy_name_btn.setFixedHeight(38)
        self.copy_name_btn.setToolTip("Copy file name")

        self.btn_group = QPushButton("🤖 Group")
        self.btn_group.setFixedHeight(38)
        self.btn_group.setEnabled(False)
        self.btn_group.setToolTip("Nhờ AI phân nhóm kết quả tìm kiếm theo loại tài liệu")

        h_layout.addWidget(self.import_btn)
        h_layout.addWidget(self.db_selector)
        h_layout.addWidget(self.search_input, 1)
        h_layout.addWidget(self.search_btn)
        h_layout.addWidget(self.copy_name_btn)
        h_layout.addWidget(self.btn_group)

        # ── Result count ─────────────────────────────────────────
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("color: #888; font-size: 12px;")

        # ── Result table ─────────────────────────────────────────
        self.result_table = QTreeWidget()
        self.result_table.setObjectName("resultsTree")
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setUniformRowHeights(True)
        self.result_table.setRootIsDecorated(True)
        self.result_table.setColumnCount(2)
        self.result_table.setHeaderLabels(["File Name", "Path"])
        self.result_table.header().setSectionResizeMode(0, self.result_table.header().ResizeMode.Stretch)
        self.result_table.header().setSectionResizeMode(1, self.result_table.header().ResizeMode.Stretch)

        main_layout.addLayout(h_layout)
        main_layout.addWidget(self.lbl_count)
        main_layout.addWidget(self.result_table)

        self.import_btn.clicked.connect(self._import_database)
        self.search_btn.clicked.connect(self._search)
        self.search_input.returnPressed.connect(self._search)
        self.copy_name_btn.clicked.connect(self._copy_name)
        self.btn_group.clicked.connect(self._run_group)
        self.result_table.itemDoubleClicked.connect(self._open_file)

    # ── private ──────────────────────────────────────────────────

    def _refresh_selector(self):
        self.db_selector.clear()
        self.db_selector.addItem("All DBs")
        for p in self.db_paths:
            self.db_selector.addItem(os.path.basename(p), p)

    def _import_database(self):
        selected, _ = QFileDialog.getOpenFileNames(
            self, "Select SQLite Databases", "", "SQLite Files (*.db *.sqlite)"
        )
        if selected:
            added = [p for p in selected if p not in self.db_paths]
            self.db_paths.extend(added)
            _save_db_list(self.db_paths)
            self._refresh_selector()
            self.lbl_count.setText(f"Imported {len(added)} database(s). Total: {len(self.db_paths)}")

    def _search(self):
        if not self.db_paths:
            QMessageBox.warning(self, "No Database", "Please import at least one SQLite database first.")
            return
        keyword = self.search_input.text().strip()
        if not keyword:
            return

        selected_data = self.db_selector.currentData()
        rows = []
        if selected_data is None:
            for db in self.db_paths:
                for row in self._search_single(db, keyword):
                    rows.append((*row, db))
        else:
            for row in self._search_single(selected_data, keyword):
                rows.append((*row, selected_data))

        self._last_rows = rows
        self.result_table.clear()
        if rows:
            for name, path, _type, db_path in rows:
                item = QTreeWidgetItem([name, path])
                item.setData(0, Qt.UserRole, db_path)
                self.result_table.addTopLevelItem(item)
            self.lbl_count.setText(f"Found {len(rows)} result(s) for \"{keyword}\"")
            self.btn_group.setEnabled(True)
        else:
            self.lbl_count.setText(f"No results for \"{keyword}\"")
            self.btn_group.setEnabled(False)

    def _search_single(self, db_path: str, keyword: str) -> list:
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            like = f"%{keyword}%"
            cur.execute(
                """
                SELECT name, path, type FROM files
                WHERE (name LIKE ? OR content LIKE ?)
                  AND name != 'BASE_PATH'
                ORDER BY name LIMIT 200
                """,
                (like, like),
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
            orig = self.copy_name_btn.text()
            self.copy_name_btn.setText("✅ Copied")
            QTimer.singleShot(1200, lambda: self.copy_name_btn.setText(orig))
        else:
            self.lbl_count.setText("Select a file first.")

    # ── AI Group ─────────────────────────────────────────────────

    def _run_group(self):
        if not self._last_rows:
            return
        from core.llm_config import load_llm_config
        provider = load_llm_config().get("translate_provider", "gemini")
        self.btn_group.setEnabled(False)
        self.btn_group.setText("⏳ Grouping…")
        pairs = [(name, path) for name, path, _type, _db in self._last_rows]
        self._group_worker = GroupWorker(pairs, provider)
        self._group_worker.done.connect(self._on_group_done)
        self._group_worker.error.connect(self._on_group_error)
        self._group_worker.start()

    def _on_group_done(self, result: dict):
        self.btn_group.setText("🤖 Group")
        self.btn_group.setEnabled(True)
        self._display_grouped(result)

    def _on_group_error(self, msg: str):
        self.btn_group.setText("🤖 Group")
        self.btn_group.setEnabled(True)
        QMessageBox.warning(self, "AI Group Error", msg)

    def _display_grouped(self, result: dict):
        # GroupWorker truncates to its first _MAX_FILES rows, preserving order —
        # so indices line up 1:1 with the same prefix of self._last_rows.
        rows = self._last_rows
        groups = result.get("groups", [])
        dupes = result.get("dupes", [])

        self.result_table.clear()
        total = 0

        for grp in groups:
            label = grp["label"]
            files = grp["files"]  # [(filename, orig_idx), ...]
            header = QTreeWidgetItem([f"📂 {label}  ({len(files)} files)", ""])
            header.setExpanded(True)
            for fname, orig_idx in files:
                _, fpath, _type, db_path = rows[orig_idx]
                child = QTreeWidgetItem([fname, fpath])
                child.setData(0, Qt.UserRole, db_path)
                header.addChild(child)
                total += 1
            self.result_table.addTopLevelItem(header)

        if dupes:
            dup_header = QTreeWidgetItem([f"⚠️ Multiple Revisions  ({len(dupes)} document(s))", ""])
            dup_header.setExpanded(True)
            for dup in dupes:
                sub = QTreeWidgetItem([f"  📄 {dup['base']}", ""])
                sub.setExpanded(True)
                for fname, orig_idx in dup["files"]:
                    _, fpath, _type, db_path = rows[orig_idx]
                    child = QTreeWidgetItem([fname, fpath])
                    child.setData(0, Qt.UserRole, db_path)
                    sub.addChild(child)
                dup_header.addChild(sub)
            self.result_table.addTopLevelItem(dup_header)

        self.lbl_count.setText(
            f"Grouped into {len(groups)} categories. "
            + (f"{len(dupes)} duplicate document(s) detected." if dupes else "")
        )

    def _open_file(self, item: QTreeWidgetItem, _column: int):
        db_path = item.data(0, Qt.UserRole)
        if not db_path:
            return  # group/dupe header row — nothing to open
        try:
            relative_path = item.text(1)
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


class IndexSearchWindow(QDialog):
    """Dialog wrapper — giữ lại cho backward compatibility."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(qss_hud_metal_header_feel() + qss_white_results())
        self.setWindowTitle("Search Indexed Databases")
        self.resize(960, 560)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.center().x() - self.width() // 2,
            screen.center().y() - self.height() // 2,
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(IndexSearchWidget(self))
