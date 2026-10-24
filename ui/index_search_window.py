"""
ui/index_search_window.py — the DB Search tab: search a database built by Create DB.

It reads the core/create_index_v3.py schema -- files, chunks with the pages
they sit on, doc_revisions and kks_tags -- and always opens it read-only. A
database without those tables (one from the old create_index2.1, or from
Create DB before pages, revisions and KKS tags were indexed) is not searched
in part: the tab says it needs rebuilding and offers to drop it from the list.

Selecting a result shows, beside the list, the part of its page where the
keyword is, boxed in red (core/hit_preview.py), drawn off the UI thread.
"""
import collections
import os
import json
import re
import sqlite3
from typing import NamedTuple

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QFileDialog,
    QMessageBox, QApplication, QLabel, QCheckBox, QStyledItemDelegate,
    QSplitter, QScrollArea,
)
from PySide6.QtCore import Qt, QTimer, QEvent, QRect, QThread, Signal
from PySide6.QtGui import QColor, QImage, QPixmap

import paths
from core import doc_source, fts_search, hit_preview, kks
from core.ai_grouper import GroupWorker
from ui import themes
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
_REQUIRED_TABLES = ("files", "files_fts", "chunks", "chunks_fts", "doc_revisions", "kks_tags")
_REQUIRED_CHUNK_COLUMNS = ("page_start", "page_end")

# Qt.UserRole on a result item holds its database; this holds its path there.
_PATH_ROLE = Qt.UserRole + 1

# The Create DB search's columns, less Lot, Disc, Type and Path (the path is on
# the Name tooltip, and double-click still opens the file). Every column can be
# resized and dragged to another place, and a click on its header sorts by it.
_COLUMNS = ["Name", "System", "Rev", "Source", "Pages"]
_COL_REV = _COLUMNS.index("Rev")
_COL_SOURCE = _COLUMNS.index("Source")
_COL_PAGES = _COLUMNS.index("Pages")
_COL_WIDTHS = {0: 460, 1: 80, 2: 110, 3: 90}   # starting widths; Pages takes the rest

# Pages sorts by how many pages carry the keyword -- the document that mentions
# it most -- rather than by the text "1–7, 9" (which would compare "1" with "3").
_PAGE_COUNT_ROLE = Qt.UserRole + 2
# The _Hit a row shows, for the preview.
_HIT_ROLE = Qt.UserRole + 3
# The preview's caption; amber, readable on the light and the dark themes, when
# the page is shown whole because the hit could not be marked on it.
_CAPTION_PLAIN = "font-size: 12px;"
_CAPTION_UNMARKED = "font-size: 12px; font-weight: 600; color: #D97706;"
_DIGITS = re.compile(r"(\d+)")

# A file that holds every word of the keyword, but not together, is listed
# after the phrase hits in grey italics.
_LOOSE_INK = "#8A94A3"
_LOOSE_TIP = "Has every word of the search, but not together as a phrase"


def _natural(text: str) -> list:
    """Sort key that reads numbers as numbers: "VP1-…-9" before "VP1-…-10"."""
    return [(0, int(p), "") if p.isdigit() else (1, 0, p.casefold())
            for p in _DIGITS.split(text) if p]


class _RemovableDbs(QStyledItemDelegate):
    """Draws a ✕ at the right of each database in the selector's list ("All
    DBs" has none). The click itself is caught by IndexSearchWidget.eventFilter."""

    BOX = 28                                  # width of the ✕ target, in pixels

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hover_row = -1                   # row whose ✕ is under the mouse

    def close_rect(self, rect: QRect) -> QRect:
        return QRect(rect.right() - self.BOX, rect.top(), self.BOX, rect.height())

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.data(Qt.UserRole) is None:
            return
        painter.save()
        # Mid grey reads on both the light and the dark themes' popups.
        painter.setPen(QColor("#EF4444" if index.row() == self.hover_row else "#9CA3AF"))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.close_rect(option.rect), Qt.AlignCenter, "✕")
        painter.restore()


class _Row(QTreeWidgetItem):
    """A file row: sorts naturally by text, and by page count in Pages."""

    def __lt__(self, other):
        tree = self.treeWidget()
        col = tree.sortColumn() if tree else 0
        if col == _COL_PAGES:
            return (self.data(col, _PAGE_COUNT_ROLE) or 0) < (other.data(col, _PAGE_COUNT_ROLE) or 0)
        return _natural(self.text(col)) < _natural(other.text(col))

# files columns every hit carries besides its id; ocr is spliced in per database.
_FILE_FIELDS = "f.name, f.path, f.type, f.system_code, f.is_scanned"


class _Hit(NamedTuple):
    """One file a search found."""
    name: str
    path: str          # relative to the database's BASE_PATH
    ftype: str
    system_code: str
    is_scanned: int
    ocr: object        # pages read by OCR; None from a database that did not record it
    page_count: int
    db: str
    revision: str
    superseded: bool   # a later revision of the same document is indexed too
    pages: str         # where the keyword is, e.g. "3, 7–8"; "" when unknown
    loose: bool = False   # has every word of the keyword, but not as a phrase


def _file_select(conn: sqlite3.Connection) -> str:
    """The files columns a _Hit is built from, after f.id."""
    return f"{_FILE_FIELDS}, {doc_source.ocr_column(conn, 'f.')}, f.page_count"


def _hit(row, db_path: str, revision: tuple, pages: str, loose: bool = False) -> _Hit:
    """row starts (id, *the _file_select columns); revision is (revision, superseded)."""
    _fid, name, path, ftype, sysc, scanned, ocr, page_count = row[:8]
    return _Hit(name, path, ftype or "", sysc or "",
                scanned or 0, ocr, page_count or 0, db_path, *revision, pages, loose)


class _OutdatedDB(Exception):
    """The database lacks part of the Create DB schema; args[0] lists what."""


class _NoEmbeddings(Exception):
    """Semantic search was asked of a database built without the Semantic tick."""


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


def _absolute_path(db_path: str, relative_path: str):
    """Where a result's file is on disk -- the database's BASE_PATH joined to
    the path stored for it -- or None when the database has no BASE_PATH."""
    conn = _connect_ro(db_path)
    try:
        row = conn.execute("SELECT path FROM files WHERE name = 'BASE_PATH'").fetchone()
    finally:
        conn.close()
    return os.path.join(row[0], relative_path) if row else None


class _PreviewJob(QThread):
    """Finds a result's spots and draws one of them, off the UI thread: the
    page has to be opened, and a large drawing takes a moment to read."""
    done = Signal(int, object, int, object)   # seq, spots or None, index, (rgb, w, h) or error

    def __init__(self, seq: int, hit, query: str, spots=None, index: int = 0,
                 whole: bool = False):
        super().__init__()
        self.seq, self.hit, self.query = seq, hit, query
        self.spots, self.index, self.whole = spots, index, whole

    def run(self):
        try:
            path = _absolute_path(self.hit.db, self.hit.path)
            if not path or not os.path.exists(path):
                raise FileNotFoundError(path or self.hit.path)
            spots = self.spots
            if spots is None:
                spots = hit_preview.locate(self.hit.db, path, self.hit.path, self.query,
                                           self.hit.pages, self.hit.loose)
            spot = spots[self.index]
            if self.whole:                      # every place on the page, not just this one
                spot = spot._replace(rects=tuple(
                    r for s in spots if s.page == spot.page for r in s.rects))
            image = hit_preview.render(path, spot, self.whole)
            self.done.emit(self.seq, spots, self.index, image)
        except FileNotFoundError as e:
            self.done.emit(self.seq, None, 0, f"File not found: {e}")
        except Exception as e:
            self.done.emit(self.seq, None, 0, f"No preview: {type(e).__name__}: {e}")


def _missing_parts(conn: sqlite3.Connection) -> list:
    """What this database lacks of the Create DB schema; empty when it has it all."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    missing = [t for t in _REQUIRED_TABLES if t not in tables]
    if "chunks" in tables:
        have = {r[1] for r in conn.execute("PRAGMA table_info(chunks)")}
        missing += [f"chunks.{c}" for c in _REQUIRED_CHUNK_COLUMNS if c not in have]
    return missing


def _revisions(conn: sqlite3.Connection, ids: list) -> dict:
    """file id -> (revision, superseded) from the table Create DB rebuilds."""
    marks = ",".join("?" * len(ids))
    return {fid: (rev or "", latest == 0) for fid, rev, latest in conn.execute(
        f"SELECT file_id, revision, is_latest FROM doc_revisions WHERE file_id IN ({marks})",
        ids)}


def search_database(db_path: str, keyword: str, latest_only: bool = False) -> tuple:
    """One database's matches for keyword, closest first, and whether there
    were more than _RESULT_LIMIT of them.

    A file matches when its name contains the keyword or its text holds it as
    a phrase -- the words together and in order, however a line break or a
    dash splits them (core/fts_search.py). A keyword that is a whole KKS tag
    also matches every file the tag was found in, however it is spaced there
    ("10HAC10 AA001", "10HAC10-AA001"), and every longer tag it begins
    ("10HAC10" finds "10HAC10AA001"); typed without its unit ("HAC10 AA001")
    it finds the tag on every unit. After those come, marked loose, the files
    that hold every word of a several-word keyword but not together.
    latest_only leaves out files that a later revision of the same document
    supersedes; a file whose revision could not be ranked is always kept.

    A hit's pages are where the phrase or the tag is, or for a loose one where
    a chunk holds every word. A chunk that joined a short page to the next
    spans both, and the keyword may be on either, so both are listed; a file
    chunked whole (Word, Excel) has no pages, nor does one found by name only.

    Raises _OutdatedDB for a database without the Create DB schema, and
    sqlite3.Error for one that cannot be read.
    """
    conn = _connect_ro(db_path)
    try:
        missing = _missing_parts(conn)
        if missing:
            raise _OutdatedDB(missing)
        globs = kks.search_globs(keyword)
        strict, loose, params = fts_search.conditions(keyword, globs)
        params["limit"] = _RESULT_LIMIT + 1
        latest = ("AND f.id NOT IN (SELECT file_id FROM doc_revisions WHERE is_latest = 0)"
                  if latest_only else "")
        # Phrase, name and tag hits before the loose ones, so they survive the
        # cap. Among them, a file whose *name* carries the keyword is a closer
        # match than one that merely mentions it somewhere on page 300. Within
        # each part the order stays alphabetical. One row past the cap is
        # fetched purely to tell "exactly the cap" apart from "more than we
        # are showing".
        rows = conn.execute(
            f"""
            SELECT f.id, {_file_select(conn)}, NOT {strict} AS loose FROM files f
            WHERE ({strict} OR {loose})
              AND f.name != 'BASE_PATH'
              {latest}
            ORDER BY loose, (f.name LIKE :like) DESC, f.name
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
        pages = fts_search.hit_pages(conn, [r[0] for r in rows if not r[-1]],
                                     [r[0] for r in rows if r[-1]], keyword, globs)
        hits = [_hit(r, db_path, revisions.get(r[0], ("", False)),
                     doc_source.page_text(pages.get(r[0])), bool(r[-1]))
                for r in rows]
        return hits, capped
    finally:
        conn.close()


def search_database_semantic(db_path: str, keyword: str,
                             latest_only: bool = False) -> tuple:
    """Meaning-based matches for keyword, closest first, in the same (hits, capped)
    shape as search_database so the tab renders them identically.

    The query is embedded and compared against the chunk vectors stored when the
    database was built with Semantic ticked; a file's score is its best chunk, and
    its Pages column lists the pages those chunks sit on. Raises _OutdatedDB for a
    non-Create-DB database and _NoEmbeddings for one built without the vectors.
    """
    import core.semantic as semantic

    conn = _connect_ro(db_path)
    try:
        missing = _missing_parts(conn)
    finally:
        conn.close()
    if missing:
        raise _OutdatedDB(missing)
    if not semantic.has_embeddings(db_path):
        raise _NoEmbeddings(db_path)

    pairs = semantic.search(db_path, keyword, top_k=_RESULT_LIMIT * 4)
    if not pairs:
        return [], False

    conn = _connect_ro(db_path)
    try:
        cids = [c for c, _ in pairs]
        score = dict(pairs)
        marks = ",".join("?" * len(cids))
        chunk_of = {}   # chunk_id -> (file_id, page_start, page_end)
        for cid, fid, ps, pe in conn.execute(
                f"SELECT id, file_id, page_start, page_end FROM chunks "
                f"WHERE id IN ({marks})", cids):
            chunk_of[cid] = (fid, ps, pe)

        order = []                               # file ids, best chunk first
        seen = set()
        fpages = collections.defaultdict(set)
        for cid, _ in pairs:                     # already sorted by score, desc
            m = chunk_of.get(cid)
            if not m:
                continue
            fid, ps, pe = m
            if fid not in seen:
                seen.add(fid)
                order.append(fid)
            if ps is not None:
                fpages[fid].update(range(ps, (pe or ps) + 1))

        if latest_only:
            superseded = {r[0] for r in conn.execute(
                "SELECT file_id FROM doc_revisions WHERE is_latest = 0")}
            order = [f for f in order if f not in superseded]

        capped = len(order) > _RESULT_LIMIT
        order = order[:_RESULT_LIMIT]
        if not order:
            return [], False

        marks2 = ",".join("?" * len(order))
        frows = {r[0]: r for r in conn.execute(
            f"SELECT f.id, {_file_select(conn)} FROM files f WHERE f.id IN ({marks2})",
            order)}
        revisions = _revisions(conn, order)
        hits = []
        for fid in order:                        # keep score order
            fr = frows.get(fid)
            if fr is None or fr[1] == 'BASE_PATH':
                continue
            hits.append(_hit(fr, db_path, revisions.get(fid, ("", False)),
                             doc_source.page_text(fpages[fid])))
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
        self._no_embed_reported: set = set()   # databases without a semantic index
        self._last_keyword = ""
        self._last_semantic = False
        # The preview: a running job, at most one waiting (the latest asked
        # for -- keyboard scrolling skips the rows in between), and what the
        # panel shows. seq tells a stale answer from the one wanted.
        self._preview_jobs: list = []
        self._preview_next = None
        self._preview_seq = 0
        self._preview_hit = None
        self._spots: list = []
        self._spot_index = 0
        self._preview_pixmap = None
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
        # Each database in the list carries a ✕ that takes it off the list.
        self._db_delegate = _RemovableDbs(self.db_selector)
        self.db_selector.setItemDelegate(self._db_delegate)
        self.db_selector.view().setMouseTracking(True)
        self.db_selector.view().viewport().installEventFilter(self)
        self._refresh_selector()

        self.mode_selector = QComboBox()
        self.mode_selector.setFixedHeight(38)
        self.mode_selector.addItem("Keyword", "keyword")
        self.mode_selector.addItem("Semantic", "semantic")
        self.mode_selector.setToolTip(
            "Keyword: the words as a phrase in a name, the text or a KKS tag, then\n"
            "in grey the files that hold every word apart (fast).\n"
            "Semantic: match by meaning, across languages "
            "(needs a database built with Semantic ticked).")
        self.mode_selector.currentIndexChanged.connect(self._on_mode_changed)

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
        h_layout.addWidget(self.mode_selector)
        h_layout.addWidget(self.search_input, 1)
        h_layout.addWidget(self.chk_latest)
        h_layout.addWidget(self.search_btn)
        h_layout.addWidget(self.copy_name_btn)
        h_layout.addWidget(self.btn_group)

        # ── Semantic device / recommendation notice (shown in Semantic mode) ──
        self.lbl_semantic_hint = QLabel("")
        self.lbl_semantic_hint.setWordWrap(True)
        self.lbl_semantic_hint.setStyleSheet("font-size: 12px; padding: 2px 2px;")
        self.lbl_semantic_hint.setVisible(False)

        # ── Result count ─────────────────────────────────────────
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("color: #888; font-size: 12px;")

        # ── Result table ─────────────────────────────────────────
        self.result_table = QTreeWidget()
        self.result_table.setObjectName("resultsTree")
        self._stripe_rows()
        self.result_table.setUniformRowHeights(True)
        self.result_table.setRootIsDecorated(True)
        self.result_table.setColumnCount(len(_COLUMNS))
        self.result_table.setHeaderLabels(_COLUMNS)
        head = self.result_table.headerItem()
        sort_tip = "\nClick to sort; click again to reverse."
        head.setToolTip(0, "Double-click to open; hover for the file's path" + sort_tip)
        head.setToolTip(1, "System code" + sort_tip)
        head.setToolTip(_COL_REV, "Revision, marked when a later one of the same "
                                  "document is indexed" + sort_tip)
        head.setToolTip(_COL_SOURCE, doc_source.SOURCE_HELP + sort_tip)
        head.setToolTip(_COL_PAGES,
                        "Pages (PowerPoint: slides) the keyword or KKS tag was found on."
                        "\nClick to sort by how many pages that is; click again to reverse.")
        # Drag a header edge to resize a column, the header itself to move it.
        header = self.result_table.header()
        header.setSectionResizeMode(header.ResizeMode.Interactive)
        header.setSectionsMovable(True)
        header.setStretchLastSection(True)
        for col, width in _COL_WIDTHS.items():
            header.resizeSection(col, width)

        # ── Preview: where the keyword is on the selected result's page ──
        self.preview = QWidget()
        pv = QVBoxLayout(self.preview)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(4)
        bar = QHBoxLayout()
        self.lbl_preview = QLabel("")
        self.lbl_preview.setWordWrap(True)
        self.lbl_preview.setStyleSheet(_CAPTION_PLAIN)
        self.btn_prev_spot = QPushButton("◀")
        self.btn_next_spot = QPushButton("▶")
        # As tall as the toolbar's buttons: the themes pad a button by 8 px top
        # and bottom and 14 px each side, which cut the text off at 28 px.
        for b, tip in ((self.btn_prev_spot, "Previous place"), (self.btn_next_spot, "Next place")):
            b.setFixedSize(46, 38)
            b.setToolTip(tip)
        self.btn_whole = QPushButton("Whole page")
        self.btn_whole.setCheckable(True)
        self.btn_whole.setFixedHeight(38)
        self.btn_whole.setToolTip("Show the whole page, every place marked")
        bar.addWidget(self.lbl_preview, 1)
        bar.addWidget(self.btn_prev_spot)
        bar.addWidget(self.btn_next_spot)
        bar.addWidget(self.btn_whole)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_image = QLabel()
        self.preview_image.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.preview_image.setToolTip("Double-click to open the file")
        self.preview_scroll.setWidget(self.preview_image)
        pv.addLayout(bar)
        pv.addWidget(self.preview_scroll, 1)
        self.preview_scroll.viewport().installEventFilter(self)
        self.preview_image.installEventFilter(self)
        self._clear_preview()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.result_table)
        self.splitter.addWidget(self.preview)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([720, 480])

        main_layout.addLayout(h_layout)
        main_layout.addWidget(self.lbl_semantic_hint)
        main_layout.addWidget(self.lbl_count)
        main_layout.addWidget(self.splitter, 1)

        self.import_btn.clicked.connect(self._import_database)
        self.search_btn.clicked.connect(self._search)
        self.search_input.returnPressed.connect(self._search)
        self.chk_latest.toggled.connect(self._on_latest_toggled)
        self.copy_name_btn.clicked.connect(self._copy_name)
        self.btn_group.clicked.connect(self._run_group)
        self.result_table.itemDoubleClicked.connect(self._open_file)
        self.result_table.currentItemChanged.connect(
            lambda current, _previous: self._preview_item(current))
        self.btn_prev_spot.clicked.connect(lambda: self._step_spot(-1))
        self.btn_next_spot.clicked.connect(lambda: self._step_spot(1))
        self.btn_whole.toggled.connect(lambda _checked: self._render_spot())

    # ── private ──────────────────────────────────────────────────

    def _refill(self, items: list):
        """Replace the table's rows with items, in the order given.

        Sorting is off while they go in -- with it on, every insert re-sorts --
        and comes back with no column chosen, so a new result keeps its own
        order (name matches first, or the AI grouping) until a header is clicked.
        """
        table = self.result_table
        table.setSortingEnabled(False)
        table.clear()
        self._stripe_rows()
        table.addTopLevelItems(items)
        # Group headers open, once they are in the tree (before, it is ignored).
        stack = list(items)
        while stack:
            item = stack.pop()
            if item.childCount():
                item.setExpanded(True)
                stack.extend(item.child(i) for i in range(item.childCount()))
        table.header().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        table.setSortingEnabled(True)
        self._preview_item(None)

    def _stripe_rows(self):
        """Alternate row colours on a light results page only. No theme sets the
        alternate colour, so Qt's default -- near white -- striped the dark
        themes' tree and their light text could not be read on every other row.
        Checked again on each search, as the theme can change while running."""
        self.result_table.setAlternatingRowColors(themes.light_page())

    def _refresh_selector(self):
        current = self.db_selector.currentData()
        self.db_selector.clear()
        self.db_selector.addItem("All DBs")
        for p in self.db_paths:
            self.db_selector.addItem(os.path.basename(p), p)
            self.db_selector.setItemData(self.db_selector.count() - 1, p, Qt.ToolTipRole)
        if current in self.db_paths:              # keep the choice across a refresh
            self.db_selector.setCurrentIndex(self.db_selector.findData(current))
        # Wide enough for the longest name plus its ✕.
        fm = self.db_selector.fontMetrics()
        widest = max((fm.horizontalAdvance(self.db_selector.itemText(i))
                      for i in range(self.db_selector.count())), default=0)
        self.db_selector.view().setMinimumWidth(widest + _RemovableDbs.BOX + 40)

    def eventFilter(self, obj, event):
        """The ✕ in the database list: hover turns it red, a click on it takes
        that database off the list instead of selecting it. Also the preview:
        it is fitted to the panel's width, and a double-click opens the file."""
        scroll = getattr(self, "preview_scroll", None)   # filters run before it is built
        if scroll is not None and obj is scroll.viewport() and event.type() == QEvent.Resize:
            self._fit_preview()
            return False
        if obj is getattr(self, "preview_image", None) and \
                event.type() == QEvent.MouseButtonDblClick:
            item = self.result_table.currentItem()
            if item is not None:
                self._open_file(item, 0)
            return True
        view = self.db_selector.view()
        if obj is view.viewport() and event.type() in (
                QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            pos = event.position().toPoint()
            index = view.indexAt(pos)
            on_x = (index.isValid() and index.data(Qt.UserRole) is not None
                    and self._db_delegate.close_rect(view.visualRect(index)).contains(pos))
            if event.type() == QEvent.MouseMove:
                row = index.row() if on_x else -1
                if row != self._db_delegate.hover_row:
                    self._db_delegate.hover_row = row
                    view.viewport().update()
                return False
            if on_x:
                if event.type() == QEvent.MouseButtonRelease:
                    self._remove_db(index.data(Qt.UserRole))
                return True                       # neither select nor close on the ✕
        return super().eventFilter(obj, event)

    def _remove_db(self, path: str):
        """Take one database off DB Search's list. The file is not touched."""
        self.db_paths = [p for p in self.db_paths if p != path]
        _save_db_list(self.db_paths)
        self._outdated_reported.discard(path)
        self._no_embed_reported.discard(path)
        self._db_delegate.hover_row = -1
        self.db_selector.hidePopup()
        self._refresh_selector()
        self.lbl_count.setText(f"Removed {os.path.basename(path)} from the list "
                               "- the file itself is untouched; Import DB brings it back.")
        if self.db_paths:                         # reopen, to remove another
            QTimer.singleShot(0, self.db_selector.showPopup)

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
        semantic_mode = self.mode_selector.currentData() == "semantic"
        search_fn = search_database_semantic if semantic_mode else search_database
        rows = []
        capped = False
        outdated = []
        no_embed = []
        # The first semantic search of a session loads the model and the vectors;
        # keep the cursor busy so the pause does not look like a freeze.
        if semantic_mode:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for db in targets:
                try:
                    found, hit_cap = search_fn(db, keyword, latest_only)
                except _OutdatedDB:
                    outdated.append(db)
                    continue
                except _NoEmbeddings:
                    no_embed.append(db)
                    continue
                except Exception as e:
                    QMessageBox.warning(self, "DB Error", f"Failed to search {db}: {e}")
                    continue
                capped = capped or hit_cap
                rows.extend(found)
        finally:
            if semantic_mode:
                QApplication.restoreOverrideCursor()

        # Across databases too, every phrase hit before any loose one; the sort
        # is stable, so each database's own order holds within each part.
        rows.sort(key=lambda hit: hit.loose)
        self._last_rows = rows
        self._last_keyword, self._last_semantic = keyword, semantic_mode
        self._refill([self._make_item(hit) for hit in rows])
        skipped_note = (
            f" — {len(outdated)} database(s) skipped, built by an older Create DB."
            if outdated else ""
        )
        if no_embed:
            skipped_note += (f" — {len(no_embed)} database(s) have no embeddings; "
                             "rebuild with Semantic ticked.")
        if rows:
            capped_note = (
                f" — more than {_RESULT_LIMIT} matched, so only the closest are "
                "shown. Add another word to narrow it."
                if capped else ""
            )
            latest_note = " (latest revisions only)" if latest_only else ""
            apart = sum(hit.loose for hit in rows)
            apart_note = (f": {len(rows) - apart} with the phrase, {apart} in grey "
                          "with every word but not together" if apart else "")
            self.lbl_count.setText(
                f"Found {len(rows)} result(s) for \"{keyword}\"{latest_note}"
                f"{apart_note}{capped_note}{skipped_note}"
            )
            self.btn_group.setEnabled(True)
        else:
            self.lbl_count.setText(f"No results for \"{keyword}\"{skipped_note}")
            self.btn_group.setEnabled(False)
        self._report_outdated(outdated)
        self._report_no_embeddings(no_embed)

    def _on_mode_changed(self):
        semantic_mode = self.mode_selector.currentData() == "semantic"
        self.search_input.setPlaceholderText(
            "Describe what you mean (any language)..." if semantic_mode
            else "Enter keyword or KKS tag...")
        if not semantic_mode:
            self.lbl_semantic_hint.setVisible(False)
            return
        # Tell the user which device semantic will run on and whether it is worth it.
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            import core.semantic as semantic
            status, msg = semantic.advice()
        except Exception as e:
            status, msg = "unavailable", f"Semantic unavailable: {e}"
        finally:
            QApplication.restoreOverrideCursor()
        colour = {"GPU": "#15803d", "CPU": "#b45309"}.get(status, "#dc2626")
        icon = {"GPU": "⚡", "CPU": "🐢"}.get(status, "⚠")
        self.lbl_semantic_hint.setStyleSheet(
            f"font-size: 12px; padding: 2px 2px; color: {colour};")
        self.lbl_semantic_hint.setText(f"{icon}  {status}  —  {msg}")
        self.lbl_semantic_hint.setVisible(True)

    def _report_no_embeddings(self, dbs: list):
        """Explain, once a session for each, that a database carries no vectors."""
        new = [db for db in dbs if db not in self._no_embed_reported]
        if not new:
            return
        self._no_embed_reported.update(new)
        listed = "\n".join(f"  • {db}" for db in new)
        QMessageBox.information(
            self, "No Semantic Index",
            "Semantic search needs the embeddings that Create DB writes when "
            "Semantic is ticked, and these databases were built without them:\n\n"
            f"{listed}\n\n"
            "Rebuild them from Tools → Create DB with Semantic ticked (an incremental "
            "run tops up the files already indexed), or use Keyword search instead.",
        )

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
        source = doc_source.source_label(hit.is_scanned, hit.ocr)
        item = _Row([label or hit.name, hit.system_code, rev, source, hit.pages])
        item.setData(_COL_PAGES, _PAGE_COUNT_ROLE, len(doc_source.page_set(hit.pages)))
        item.setData(0, Qt.UserRole, hit.db)
        item.setData(0, _PATH_ROLE, hit.path)
        item.setData(0, _HIT_ROLE, hit)
        item.setToolTip(0, hit.path)
        if hit.pages:                             # the whole list, however narrow the column
            item.setToolTip(_COL_PAGES, hit.pages)
        # Coloured for the page it sits on: the results tree is dark under most
        # themes, where a colour chosen against white would not read.
        item.setForeground(_COL_SOURCE, QColor(
            doc_source.source_colour(source, themes.light_page())))
        item.setToolTip(_COL_SOURCE,
                        doc_source.source_tip(hit.is_scanned, hit.ocr, hit.page_count))
        if hit.superseded:
            item.setToolTip(_COL_REV, "A later revision of this document is in the database.")
        if hit.loose:
            # Mid grey reads on the light and the dark results trees alike;
            # Source keeps its own colour.
            font = item.font(0)
            font.setItalic(True)
            for col in range(len(_COLUMNS)):
                item.setFont(col, font)
                if col != _COL_SOURCE:
                    item.setForeground(col, QColor(_LOOSE_INK))
            item.setToolTip(0, f"{hit.path}\n{_LOOSE_TIP}")
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

        tops = []
        for grp in groups:
            label = grp["label"]
            files = grp["files"]  # [(filename, orig_idx), ...]
            header = QTreeWidgetItem([f"📂 {label}  ({len(files)} files)", ""])
            for fname, orig_idx in files:
                header.addChild(self._make_item(rows[orig_idx], fname))
            tops.append(header)

        # Two kinds of repeat, kept apart because they ask different questions:
        # several revisions leave you deciding which is current, while identical
        # copies only leave you deciding which folder to open.
        for title, sets in (
                (f"⚠️ Multiple Revisions  ({len(dupes)} document(s))", dupes),
                (f"📑 Same File in Several Folders  ({len(copies)} document(s))", copies)):
            section = self._duplicate_section(title, sets, rows)
            if section is not None:
                tops.append(section)
        self._refill(tops)

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

    def _duplicate_section(self, title: str, sets: list, rows: list):
        """A header item holding one sub-item per repeated document, or None."""
        if not sets:
            return None
        header = QTreeWidgetItem([title, ""])
        for entry in sets:
            sub = QTreeWidgetItem([f"  📄 {entry['base']}", ""])
            for fname, orig_idx in entry["files"]:
                sub.addChild(self._make_item(rows[orig_idx], fname))
            header.addChild(sub)
        return header

    def _open_file(self, item: QTreeWidgetItem, _column: int):
        db_path = item.data(0, Qt.UserRole)
        if not db_path:
            return  # group/dupe header row — nothing to open
        try:
            abs_path = _absolute_path(db_path, item.data(0, _PATH_ROLE))
            if abs_path:
                if os.path.exists(abs_path):
                    os.startfile(abs_path)
                else:
                    QMessageBox.warning(self, "Not Found", f"File not found:\n{abs_path}")
            else:
                QMessageBox.warning(self, "Error", "BASE_PATH not found in database.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open file: {e}")

    # ── Preview ──────────────────────────────────────────────────

    def _clear_preview(self, text: str = "Select a result to see where the keyword is "
                                         "on its page."):
        self._preview_hit, self._spots, self._spot_index = None, [], 0
        self._preview_pixmap = None
        self.preview_image.clear()
        self.lbl_preview.setStyleSheet(_CAPTION_PLAIN)
        self.lbl_preview.setText(text)
        self.btn_prev_spot.setEnabled(False)
        self.btn_next_spot.setEnabled(False)
        self.btn_whole.setEnabled(False)

    def _preview_item(self, item):
        """Show where the keyword is on the page of the row just selected."""
        self._preview_seq += 1                  # whatever is still drawing is stale now
        self._preview_next = None               # and so is whatever was waiting
        hit = item.data(0, _HIT_ROLE) if item is not None else None
        if hit is None:                         # nothing selected, or a group header
            self._clear_preview()
            return
        ext = os.path.splitext(hit.path)[1].lower()
        if ext not in hit_preview.PDF + hit_preview.IMAGES:
            self._clear_preview(f"No preview for {ext or 'this'} files - double-click to open.")
            return
        self._clear_preview("Finding the keyword on the page…")
        self._preview_hit = hit
        self._queue_preview(_PreviewJob(self._preview_seq, hit, self._last_keyword,
                                        whole=self.btn_whole.isChecked()))

    def _step_spot(self, step: int):
        if len(self._spots) > 1:
            self._spot_index = (self._spot_index + step) % len(self._spots)
            self._render_spot()

    def _render_spot(self):
        """Draw the current spot again: another place, or Whole page toggled."""
        if self._preview_hit is None or not self._spots:
            return
        self._preview_seq += 1
        self._queue_preview(_PreviewJob(self._preview_seq, self._preview_hit,
                                        self._last_keyword, self._spots,
                                        self._spot_index, self.btn_whole.isChecked()))

    def _queue_preview(self, job: _PreviewJob):
        """Start job, or keep it as the next one while another runs. PyMuPDF
        is used from one thread at a time."""
        self._preview_jobs = [j for j in self._preview_jobs if not j.isFinished()]
        if self._preview_jobs:
            self._preview_next = job
            return
        job.done.connect(self._on_preview)
        job.finished.connect(self._on_preview_job_finished)
        self._preview_jobs.append(job)
        job.start()

    def _on_preview_job_finished(self):
        job, self._preview_next = self._preview_next, None
        if job is not None:
            QTimer.singleShot(0, lambda: self._queue_preview(job))

    def _on_preview(self, seq: int, spots, index: int, image):
        if seq != self._preview_seq:
            return                              # the selection has moved on
        if spots is None:
            hit = self._preview_hit
            self._clear_preview(str(image))
            self._preview_hit = hit
            return
        self._spots, self._spot_index = spots, index
        data, w, h = image
        self._preview_pixmap = QPixmap.fromImage(
            QImage(data, w, h, 3 * w, QImage.Format_RGB888).copy())
        self._fit_preview()
        self.btn_prev_spot.setEnabled(len(spots) > 1)
        self.btn_next_spot.setEnabled(len(spots) > 1)
        self.btn_whole.setEnabled(True)
        # A page shown unmarked looks like a fault unless the reason stands out.
        self.lbl_preview.setStyleSheet(_CAPTION_PLAIN if spots[index].marked
                                       else _CAPTION_UNMARKED)
        self.lbl_preview.setText(self._caption(spots[index], index, len(spots)))

    def _caption(self, spot, index: int, count: int) -> str:
        if spot.marked:
            where = f"Page {spot.page}"
            return where + (f" - place {index + 1} of {count}" if count > 1 else "")
        if self._last_semantic:
            why = "a meaning match has no single place to mark"
        elif not self._preview_hit.pages:
            why = "it matched the file name"
        elif kks.search_globs(self._last_keyword):
            why = ("this tag was read by OCR and the database has no position for it - "
                   "rebuild it (with OCR drawings for drawings) to mark it")
        else:
            why = ("this page's text was read by OCR, where only KKS tags keep "
                   "their position")
        return f"Page {spot.page}, not marked: {why}."

    def _fit_preview(self):
        """The picture at the panel's width, never enlarged."""
        if self._preview_pixmap is None:
            return
        room = self.preview_scroll.viewport().width() - 4
        pixmap = self._preview_pixmap
        if 0 < room < pixmap.width():
            pixmap = pixmap.scaledToWidth(room, Qt.SmoothTransformation)
        self.preview_image.setPixmap(pixmap)


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
