"""
ui/index_search_window.py — the DB Search tab: search a database built by Create DB.

It reads the core/create_index_v3.py schema -- files, chunks with the pages
they sit on, doc_revisions and kks_tags -- and always opens it read-only. A
database without those tables (one from the old create_index2.1, or from
Create DB before pages, revisions and KKS tags were indexed) is not searched
in part: the tab says it needs rebuilding and offers to drop it from the list.
"""
import collections
import os
import json
import sqlite3
from typing import NamedTuple

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QFileDialog,
    QMessageBox, QApplication, QLabel, QCheckBox,
)
from PySide6.QtCore import Qt, QTimer

import paths
from core import kks
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

# What a database must hold before this tab searches it: the tables Create DB
# writes, and the page columns chunks gained after its first builds.
_REQUIRED_TABLES = ("files", "chunks", "doc_revisions", "kks_tags")
_REQUIRED_CHUNK_COLUMNS = ("page_start", "page_end")

# Runs of pages spelt out in the Pages column before the rest are only counted.
_PAGE_RUNS_SHOWN = 8

# Qt.UserRole on a result item holds its database; this holds its path there.
_PATH_ROLE = Qt.UserRole + 1


class _Hit(NamedTuple):
    """One file a search found."""
    name: str
    path: str          # relative to the database's BASE_PATH
    ftype: str
    db: str
    revision: str
    superseded: bool   # a later revision of the same document is indexed too
    pages: str         # where the keyword is, e.g. "3, 7–8"; "" when unknown


class _OutdatedDB(Exception):
    """The database lacks part of the Create DB schema; args[0] lists what."""


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


def _connect_ro(db_path: str) -> sqlite3.Connection:
    # Read-only, and a missing file is an error rather than a new empty one.
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _missing_parts(conn: sqlite3.Connection) -> list:
    """What this database lacks of the Create DB schema; empty when it has it all."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    missing = [t for t in _REQUIRED_TABLES if t not in tables]
    if "chunks" in tables:
        have = {r[1] for r in conn.execute("PRAGMA table_info(chunks)")}
        missing += [f"chunks.{c}" for c in _REQUIRED_CHUNK_COLUMNS if c not in have]
    return missing


def _page_text(pages: set) -> str:
    """{1, 2, 3, 7, 12} -> "1–3, 7, 12", spelling out only the first few runs."""
    runs = []
    for p in sorted(pages):
        if runs and p == runs[-1][1] + 1:
            runs[-1][1] = p
        else:
            runs.append([p, p])
    text = ", ".join(str(a) if a == b else f"{a}–{b}" for a, b in runs[:_PAGE_RUNS_SHOWN])
    if len(runs) > _PAGE_RUNS_SHOWN:
        text += f", … ({len(pages)} pages)"
    return text


def _hit_pages(conn: sqlite3.Connection, ids: list, like: str, tag) -> dict:
    """file id -> the pages its matches are on, as text.

    A chunk that joined a short page to the next spans both, and the keyword
    may be on either, so both are listed. A file chunked whole (Word, Excel)
    has no pages and gets none, as does one that matched only by name.
    """
    marks = ",".join("?" * len(ids))
    pages = collections.defaultdict(set)
    for fid, start, end in conn.execute(
            f"SELECT file_id, page_start, page_end FROM chunks "
            f"WHERE file_id IN ({marks}) AND page_start IS NOT NULL AND content LIKE ?",
            (*ids, like)):
        pages[fid].update(range(start, (end or start) + 1))
    if tag:
        for fid, page in conn.execute(
                f"SELECT file_id, page FROM kks_tags "
                f"WHERE file_id IN ({marks}) AND page IS NOT NULL AND tag_norm GLOB ?",
                (*ids, tag + "*")):
            pages[fid].add(page)
    return {fid: _page_text(p) for fid, p in pages.items()}


def _revisions(conn: sqlite3.Connection, ids: list) -> dict:
    """file id -> (revision, superseded) from the table Create DB rebuilds."""
    marks = ",".join("?" * len(ids))
    return {fid: (rev or "", latest == 0) for fid, rev, latest in conn.execute(
        f"SELECT file_id, revision, is_latest FROM doc_revisions WHERE file_id IN ({marks})",
        ids)}


def search_database(db_path: str, keyword: str, latest_only: bool = False) -> tuple:
    """One database's matches for keyword, closest first, and whether there
    were more than _RESULT_LIMIT of them.

    A file matches when its name or its text contains the keyword. A keyword
    that is a whole KKS tag also matches every file the tag was found in,
    however it is spaced there ("10HAC10 AA001", "10HAC10-AA001"), and every
    longer tag it begins ("10HAC10" finds "10HAC10AA001"). latest_only leaves
    out files that a later revision of the same document supersedes; a file
    whose revision could not be ranked is always kept.

    Raises _OutdatedDB for a database without the Create DB schema, and
    sqlite3.Error for one that cannot be read.
    """
    conn = _connect_ro(db_path)
    try:
        missing = _missing_parts(conn)
        if missing:
            raise _OutdatedDB(missing)
        like = f"%{keyword}%"
        tag = kks.search_key(keyword)
        params = {"like": like, "limit": _RESULT_LIMIT + 1}
        match = "f.name LIKE :like OR f.content LIKE :like"
        if tag:
            match += " OR f.id IN (SELECT file_id FROM kks_tags WHERE tag_norm GLOB :glob)"
            params["glob"] = tag + "*"
        latest = ("AND f.id NOT IN (SELECT file_id FROM doc_revisions WHERE is_latest = 0)"
                  if latest_only else "")
        # A file whose *name* carries the keyword is a closer match than one
        # that merely mentions it somewhere on page 300, so those come first
        # and survive the cap. Within each half the order stays alphabetical.
        # One row past the cap is fetched purely to tell "exactly the cap"
        # apart from "more than we are showing".
        rows = conn.execute(
            f"""
            SELECT f.id, f.name, f.path, f.type FROM files f
            WHERE ({match})
              AND f.name != 'BASE_PATH'
              {latest}
            ORDER BY (f.name LIKE :like) DESC, f.name
            LIMIT :limit
            """,
            params,
        ).fetchall()
        capped = len(rows) > _RESULT_LIMIT
        rows = rows[:_RESULT_LIMIT]
        if not rows:
            return [], False
        ids = [r[0] for r in rows]
        revisions = _revisions(conn, ids)
        pages = _hit_pages(conn, ids, like, tag)
        hits = [
            _Hit(name, path, ftype or "", db_path,
                 *revisions.get(fid, ("", False)), pages.get(fid, ""))
            for fid, name, path, ftype in rows
        ]
        return hits, capped
    finally:
        conn.close()


class IndexSearchWidget(QWidget):
    """Embedded widget — dùng trong tab hoặc dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.db_paths: list = _load_db_list()
        self._last_rows: list = []
        self._group_worker = None
        self._outdated_reported: set = set()   # told about this session already
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
        self.search_input.setPlaceholderText("Enter keyword or KKS tag...")

        self.chk_latest = QCheckBox("Latest revision only")
        self.chk_latest.setToolTip(
            "Hide files that a later revision of the same document supersedes")

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
        h_layout.addWidget(self.chk_latest)
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
        self.result_table.setColumnCount(4)
        self.result_table.setHeaderLabels(["File Name", "Rev", "Pages", "Path"])
        self.result_table.headerItem().setToolTip(
            1, "Revision, marked when a later one of the same document is indexed")
        self.result_table.headerItem().setToolTip(
            2, "Pages (PowerPoint: slides) the keyword or KKS tag was found on")
        header = self.result_table.header()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.Stretch)

        main_layout.addLayout(h_layout)
        main_layout.addWidget(self.lbl_count)
        main_layout.addWidget(self.result_table)

        self.import_btn.clicked.connect(self._import_database)
        self.search_btn.clicked.connect(self._search)
        self.search_input.returnPressed.connect(self._search)
        self.chk_latest.toggled.connect(self._on_latest_toggled)
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

    def _on_latest_toggled(self, _checked: bool):
        # Search again, so the list on screen never disagrees with the box.
        if self.db_paths and self.search_input.text().strip():
            self._search()

    def _search(self):
        if not self.db_paths:
            QMessageBox.warning(self, "No Database", "Please import at least one SQLite database first.")
            return
        keyword = self.search_input.text().strip()
        if not keyword:
            return

        selected_data = self.db_selector.currentData()
        targets = self.db_paths if selected_data is None else [selected_data]
        latest_only = self.chk_latest.isChecked()
        rows = []
        capped = False
        outdated = []
        for db in targets:
            try:
                found, hit_cap = search_database(db, keyword, latest_only)
            except _OutdatedDB:
                outdated.append(db)
                continue
            except Exception as e:
                QMessageBox.warning(self, "DB Error", f"Failed to search {db}: {e}")
                continue
            capped = capped or hit_cap
            rows.extend(found)

        self._last_rows = rows
        self.result_table.clear()
        skipped_note = (
            f" — {len(outdated)} database(s) skipped, built by an older Create DB."
            if outdated else ""
        )
        if rows:
            for hit in rows:
                self.result_table.addTopLevelItem(self._make_item(hit))
            capped_note = (
                f" — more than {_RESULT_LIMIT} matched, so only the closest are "
                "shown. Add another word to narrow it."
                if capped else ""
            )
            latest_note = " (latest revisions only)" if latest_only else ""
            self.lbl_count.setText(
                f"Found {len(rows)} result(s) for \"{keyword}\"{latest_note}"
                f"{capped_note}{skipped_note}"
            )
            self.btn_group.setEnabled(True)
        else:
            self.lbl_count.setText(f"No results for \"{keyword}\"{skipped_note}")
            self.btn_group.setEnabled(False)
        self._report_outdated(outdated)

    def _report_outdated(self, dbs: list):
        """Explain, once a session for each, why a database was skipped, and
        offer to take it off the list."""
        new = [db for db in dbs if db not in self._outdated_reported]
        if not new:
            return
        self._outdated_reported.update(new)
        listed = "\n".join(f"  • {db}" for db in new)
        reply = QMessageBox.question(
            self, "Database Needs Rebuilding",
            "DB Search reads the page numbers, latest revisions and KKS tags that "
            "Create DB indexes, and these databases were built without them:\n\n"
            f"{listed}\n\n"
            "Rebuild them from Tools → Create DB — into a new file, or with "
            "Incremental unticked, because an incremental run leaves the files it "
            "has already indexed as they were. Until then they are skipped.\n\n"
            "Remove them from DB Search's list now? The files themselves are not touched.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.db_paths = [p for p in self.db_paths if p not in new]
            _save_db_list(self.db_paths)
            self._refresh_selector()

    def _make_item(self, hit: _Hit, label: str = "") -> QTreeWidgetItem:
        rev = f"{hit.revision} (superseded)" if hit.superseded else hit.revision
        item = QTreeWidgetItem([label or hit.name, rev, hit.pages, hit.path])
        item.setData(0, Qt.UserRole, hit.db)
        item.setData(0, _PATH_ROLE, hit.path)
        if hit.superseded:
            item.setToolTip(1, "A later revision of this document is in the database.")
        return item

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
        pairs = [(hit.name, hit.path) for hit in self._last_rows]
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
                header.addChild(self._make_item(rows[orig_idx], fname))
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
                sub.addChild(self._make_item(rows[orig_idx], fname))
            header.addChild(sub)
        self.result_table.addTopLevelItem(header)

    def _open_file(self, item: QTreeWidgetItem, _column: int):
        db_path = item.data(0, Qt.UserRole)
        if not db_path:
            return  # group/dupe header row — nothing to open
        try:
            relative_path = item.data(0, _PATH_ROLE)
            conn = _connect_ro(db_path)
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
