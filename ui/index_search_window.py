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

# How many rows one database may contribute to a search.
#
# The old cap of 200, taken in plain alphabetical order, quietly threw away the
# most relevant half of every large result. "VP1-" sorts near the end of the
# alphabet, so on a search for "pump" -- 2642 matches, 2206 of them properly
# numbered VP1 documents -- the first 200 names held just 23 of them. The
# library's own documents were the ones being cut.
_RESULT_LIMIT = 500


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
        targets = self.db_paths if selected_data is None else [selected_data]
        rows = []
        capped = False
        for db in targets:
            found, hit_cap = self._search_single(db, keyword)
            capped = capped or hit_cap
            for row in found:
                rows.append((*row, db))

        self._last_rows = rows
        self.result_table.clear()
        if rows:
            for name, path, _type, db_path in rows:
                item = QTreeWidgetItem([name, path])
                item.setData(0, Qt.UserRole, db_path)
                self.result_table.addTopLevelItem(item)
            capped_note = (
                f" — more than {_RESULT_LIMIT} matched, so only the closest are "
                "shown. Add another word to narrow it."
                if capped else ""
            )
            self.lbl_count.setText(
                f"Found {len(rows)} result(s) for \"{keyword}\"{capped_note}"
            )
            self.btn_group.setEnabled(True)
        else:
            self.lbl_count.setText(f"No results for \"{keyword}\"")
            self.btn_group.setEnabled(False)

    def _search_single(self, db_path: str, keyword: str) -> tuple:
        """Search one database. Returns (rows, whether the cap was reached)."""
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            like = f"%{keyword}%"
            # A file whose *name* carries the keyword is a closer match than one
            # that merely mentions it somewhere on page 300, so those come first
            # and survive the cap. Within each half the order stays alphabetical.
            # One row past the cap is fetched purely to tell "exactly the cap"
            # apart from "more than we are showing".
            cur.execute(
                """
                SELECT name, path, type FROM files
                WHERE (name LIKE ? OR content LIKE ?)
                  AND name != 'BASE_PATH'
                ORDER BY (name LIKE ?) DESC, name
                LIMIT ?
                """,
                (like, like, like, _RESULT_LIMIT + 1),
            )
            rows = cur.fetchall()
            conn.close()
            return rows[:_RESULT_LIMIT], len(rows) > _RESULT_LIMIT
        except Exception as e:
            QMessageBox.warning(self, "DB Error", f"Failed to search {db_path}: {e}")
            return [], False

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
        copies = result.get("copies", [])

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

        # Two kinds of repeat, kept apart because they ask different questions:
        # several revisions leave you deciding which is current, while identical
        # copies only leave you deciding which folder to open.
        self._add_duplicate_section(
            f"⚠️ Multiple Revisions  ({len(dupes)} document(s))", dupes, rows)
        self._add_duplicate_section(
            f"📑 Same File in Several Folders  ({len(copies)} document(s))",
            copies, rows)

        note = result.get("note", "")
        self.lbl_count.setText(
            f"Grouped into {len(groups)} categories. "
            + (f"{len(dupes)} document(s) with several revisions. " if dupes else "")
            + (f"{len(copies)} duplicated file(s). " if copies else "")
            + note
        )
        # A fallback or a cut-off reply is easy to miss in a small grey label,
        # and both mean the grouping on screen is not what was asked for. A
        # note that only reports a few files labelled offline does not earn a
        # dialog -- it stays in the label, where it can be read and ignored.
        if result.get("alert"):
            QMessageBox.warning(self, "AI Group", note)

    def _add_duplicate_section(self, title: str, sets: list, rows: list):
        if not sets:
            return
        header = QTreeWidgetItem([title, ""])
        header.setExpanded(True)
        for entry in sets:
            sub = QTreeWidgetItem([f"  📄 {entry['base']}", ""])
            sub.setExpanded(True)
            for fname, orig_idx in entry["files"]:
                _, fpath, _type, db_path = rows[orig_idx]
                child = QTreeWidgetItem([fname, fpath])
                child.setData(0, Qt.UserRole, db_path)
                sub.addChild(child)
            header.addChild(sub)
        self.result_table.addTopLevelItem(header)

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
