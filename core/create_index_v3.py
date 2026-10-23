"""
create_index_v3.py
==================
Cải tiến so với v2.1:
  1. Schema mới: thêm doc_number, lot, discipline, system_code, revision,
                 is_scanned, ocr, page_count, file_size_kb, indexed_date
                 (ocr = 1 only when the text came from OCR; see extract_pages)
  2. OCR tự động cho PDF dạng ảnh:
       - Tài liệu (commissioning, O&M, training): OCR toàn bộ trang
       - Bản vẽ kỹ thuật (P&ID, plan, drawing): OCR title block (nhanh hơn)
  3. FTS5 (Full-Text Search) – tìm kiếm nhanh hơn LIKE ~10-50x
  4. Parse metadata từ tên file theo quy ước VP1-[unit]-L[lot]-[disc]-[sys]-[no]
  5. Incremental index – bỏ qua file đã index, chỉ thêm file mới
  6. Hiển thị thêm cột: Lot, Discipline, Doc Number, Revision trong kết quả
  7. Results also show Source (OCR / Text / Scanned) and Pages -- the pages
     whose chunks match the search term
"""

import os, re, sys, io, sqlite3, json, csv, warnings, unicodedata, collections
from datetime import datetime

try:
    from core import doc_naming, doc_source, kks
except ImportError:                  # run as a script from inside core/
    import doc_naming, doc_source, kks

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QGridLayout,
    QWidget, QLabel, QLineEdit, QPushButton, QFileDialog, QTableWidget,
    QTableWidgetItem, QMessageBox, QProgressBar, QCheckBox, QComboBox,
    QGroupBox, QHeaderView, QStatusBar, QSplitter, QDialog, QListWidget
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QPixmap

warnings.filterwarnings("ignore")

def _use_bundled_tesseract():
    """Ưu tiên Tesseract đóng gói kèm app (build.ps1 copy vào thư mục 'tesseract').
    Chạy từ source không có thư mục này → giữ nguyên, dùng tesseract trên PATH."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    tess_dir = os.path.join(base, 'tesseract')
    if os.path.isfile(os.path.join(tess_dir, 'tesseract.exe')):
        os.environ['PATH'] = tess_dir + os.pathsep + os.environ.get('PATH', '')
        os.environ['TESSDATA_PREFIX'] = os.path.join(tess_dir, 'tessdata')

_use_bundled_tesseract()

# ─────────────────────────────────────────────────────────────────────────────
#  APP STYLESHEET  (modern navy/slate professional theme)
# ─────────────────────────────────────────────────────────────────────────────
APP_STYLE = """
/* ── Window shell ── */
QMainWindow {
    background-color: #1E293B;
}
QWidget#centralWidget {
    background-color: #1E293B;
}

/* ── App header bar ── */
QWidget#appHeader {
    background-color: #1E293B;
    border-bottom: 2px solid #3B82F6;
}

/* ── Content area (light slate) ── */
QWidget#contentArea {
    background-color: #F1F5F9;
}
QWidget {
    color: #1E293B;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}

/* ── Group boxes ── */
QGroupBox {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    margin-top: 8px;
    padding-top: 6px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    background-color: #FFFFFF;
    color: #1D4ED8;
    font-size: 12px;
}

/* ── Inputs ── */
QLineEdit {
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 5px;
    padding: 5px 8px;
    color: #1E293B;
    selection-background-color: #3B82F6;
}
QLineEdit:focus      { border: 1.5px solid #3B82F6; }
QLineEdit:read-only  { background: #F8FAFC; color: #475569; }

QComboBox {
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 5px;
    padding: 5px 8px;
    min-width: 110px;
    color: #1E293B;
}
QComboBox:focus { border: 1.5px solid #3B82F6; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    selection-background-color: #DBEAFE;
    selection-color: #1D4ED8;
}

/* ── Buttons ── */
QPushButton {
    background-color: #1D4ED8;
    color: #FFFFFF;
    border: none;
    border-radius: 5px;
    padding: 6px 14px;
    font-weight: 600;
    min-width: 72px;
}
QPushButton:hover    { background-color: #1E40AF; }
QPushButton:pressed  { background-color: #1E3A8A; }
QPushButton:disabled { background-color: #94A3B8; color: #E2E8F0; }
QPushButton#btnStart { background-color: #15803D; }
QPushButton#btnStart:hover   { background-color: #166534; }
QPushButton#btnStart:pressed { background-color: #14532D; }
QPushButton#btnStop  { background-color: #DC2626; }
QPushButton#btnStop:hover    { background-color: #B91C1C; }
QPushButton#btnStop:pressed  { background-color: #991B1B; }

/* ── Checkbox ── */
QCheckBox { color: #334155; spacing: 6px; background: transparent; }
QCheckBox::indicator {
    width: 15px; height: 15px;
    border: 1.5px solid #94A3B8;
    border-radius: 3px;
    background: #FFFFFF;
}
QCheckBox::indicator:checked {
    background-color: #1D4ED8;
    border-color: #1D4ED8;
}

/* ── Progress bar ── */
QProgressBar {
    background-color: #E2E8F0;
    border: none;
    border-radius: 5px;
    text-align: center;
    color: #475569;
    font-size: 11px;
    min-height: 14px;
    max-height: 14px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #60A5FA, stop:1 #1D4ED8);
    border-radius: 5px;
}

/* ── Table ── */
QTableWidget {
    background: #FFFFFF;
    gridline-color: #E2E8F0;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    alternate-background-color: #F8FAFC;
    font-size: 12px;
}
QTableWidget::item:selected {
    background-color: #DBEAFE;
    color: #1E293B;
}
QHeaderView::section {
    background-color: #1E293B;
    color: #F1F5F9;
    font-weight: 600;
    font-size: 12px;
    padding: 7px 8px;
    border: none;
    border-right: 1px solid #334155;
}
QHeaderView::section:last { border-right: none; }

/* ── Status bar ── */
QStatusBar {
    background-color: #0F172A;
    color: #94A3B8;
    font-size: 11px;
    padding: 2px 8px;
}

/* ── Labels (transparent bg so parent color shows) ── */
QLabel { color: #334155; background: transparent; }
"""

# ─────────────────────────────────────────────────────────────────────────────
#  LONG WINDOWS PATHS
# ─────────────────────────────────────────────────────────────────────────────
# Windows refuses a plain path over 260 characters unless long paths are enabled
# system-wide, which they are not on the machines this runs on. Documents buried
# that deep were found by the scan but failed to open, so they were missing from
# the index without a word of explanation. The extended-length prefix lifts the
# cap and both os.* and fitz accept it. Only used past 250 characters so the
# behaviour of every ordinary path is unchanged.
_EXT_PREFIX = '\\\\?\\'          # the literal \\?\
_UNC_PREFIX = '\\\\?\\UNC'       # the literal \\?\UNC


# What Windows and Office leave lying around beside the real documents. Their
# extension says .xlsx or .pdf, so the scan picked them up and the extractor
# then failed on every one: sixteen rows in the index whose entire content is
# the string "[Error: File is not a zip file]". "~$name.xlsx" is an Excel lock
# file, written while a workbook is open and deleted when it closes; "._name"
# is a macOS AppleDouble resource fork, created whenever the documents pass
# through a Mac or a Mac-formatted drive. None of them is a document.
_JUNK_RE = re.compile(r'^(?:~\$|\._)|^(?:thumbs\.db|desktop\.ini)$', re.IGNORECASE)


def _fs_path(path):
    """Return a path the Windows file APIs accept however long it is."""
    if os.name != 'nt' or len(path) < 250:
        return path
    if path.startswith(_EXT_PREFIX) or path.startswith('\\\\.\\'):
        return path
    full = os.path.abspath(path)
    if full.startswith('\\\\'):      # UNC share: \\server\share\... -> \\?\UNC\server\share\...
        return _UNC_PREFIX + full[1:]
    return _EXT_PREFIX + full


# ─────────────────────────────────────────────────────────────────────────────
#  SCHEMA
# ─────────────────────────────────────────────────────────────────────────────
SCHEMA_FILES = """
CREATE TABLE IF NOT EXISTS files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT,
    path          TEXT UNIQUE,
    type          TEXT,
    content       TEXT,
    doc_number    TEXT,
    lot           TEXT,
    discipline    TEXT,
    system_code   TEXT,
    revision      TEXT,
    is_scanned    INTEGER DEFAULT 0,
    ocr           INTEGER DEFAULT 0,
    page_count    INTEGER DEFAULT 0,
    file_size_kb  INTEGER DEFAULT 0,
    indexed_date  TEXT
)
"""
SCHEMA_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    name, doc_number, system_code, content,
    content='files', content_rowid='id',
    tokenize='unicode61'
)
"""
SCHEMA_TRIGGER_INSERT = """
CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
    INSERT INTO files_fts(rowid, name, doc_number, system_code, content)
    VALUES (new.id, new.name, new.doc_number, new.system_code, new.content);
END
"""
SCHEMA_TRIGGER_DELETE = """
CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, name, doc_number, system_code, content)
    VALUES ('delete', old.id, old.name, old.doc_number, old.system_code, old.content);
END
"""

# ── Chunks (bảng mới – dùng cho Cowork/Claude) ───────────────────────────────
SCHEMA_CHUNKS = """
CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id     INTEGER REFERENCES files(id) ON DELETE CASCADE,
    chunk_index INTEGER,
    heading     TEXT,
    content     TEXT,
    char_start  INTEGER,
    char_end    INTEGER,
    page_start  INTEGER,
    page_end    INTEGER
)
"""
# Added after the first databases were built; init_db() adds them to an older
# chunks table, since CREATE TABLE IF NOT EXISTS leaves an existing one alone.
CHUNK_PAGE_COLUMNS = ('page_start', 'page_end')
SCHEMA_CHUNKS_IDX = """
CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_id)
"""
SCHEMA_CHUNKS_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    heading, content,
    content='chunks', content_rowid='id',
    tokenize='unicode61'
)
"""
SCHEMA_CHUNKS_TRIGGER_I = """
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, heading, content)
    VALUES (new.id, new.heading, new.content);
END
"""
SCHEMA_CHUNKS_TRIGGER_D = """
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, heading, content)
    VALUES ('delete', old.id, old.heading, old.content);
END
"""

# An external-content FTS5 table needs an UPDATE trigger as well as INSERT and
# DELETE. Without one, any UPDATE on files/chunks leaves the index describing
# the old text and the row becomes unfindable by its new content.
SCHEMA_TRIGGER_UPDATE = """
CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, name, doc_number, system_code, content)
    VALUES ('delete', old.id, old.name, old.doc_number, old.system_code, old.content);
    INSERT INTO files_fts(rowid, name, doc_number, system_code, content)
    VALUES (new.id, new.name, new.doc_number, new.system_code, new.content);
END
"""
SCHEMA_CHUNKS_TRIGGER_U = """
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, heading, content)
    VALUES ('delete', old.id, old.heading, old.content);
    INSERT INTO chunks_fts(rowid, heading, content)
    VALUES (new.id, new.heading, new.content);
END
"""

# Optional semantic layer: one embedding per chunk and a note of the model that
# wrote them. Empty until a Create DB run ticks Semantic; a keyword-only database
# simply carries empty tables. The delete trigger keeps vectors in step with the
# chunks, since re-indexing a file drops its chunks and inserts new ids.
SCHEMA_CHUNK_VECTORS = """
CREATE TABLE IF NOT EXISTS chunk_vectors (
    chunk_id INTEGER PRIMARY KEY,
    vector   BLOB
)
"""
SCHEMA_SEMANTIC_META = """
CREATE TABLE IF NOT EXISTS semantic_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
)
"""
SCHEMA_VECTORS_TRIGGER_D = """
CREATE TRIGGER IF NOT EXISTS chunk_vectors_ad AFTER DELETE ON chunks BEGIN
    DELETE FROM chunk_vectors WHERE chunk_id = old.id;
END
"""

# Metadata lookups the assistant issues constantly. Without these, every
# "which documents have this doc_number / system_code" query is a full scan.
SCHEMA_FILES_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_files_doc    ON files(doc_number)",
    "CREATE INDEX IF NOT EXISTS idx_files_system ON files(system_code)",
    "CREATE INDEX IF NOT EXISTS idx_files_lotdis ON files(lot, discipline)",
)

# Which file is the latest revision of its document. Kept out of `files` on
# purpose: files_au re-indexes a row's whole content on any UPDATE, so writing a
# flag into every row would rewrite the full-text index for the whole library.
# Rebuilt from the file names at the end of every indexing run.
SCHEMA_DOC_REVISIONS = (
    """
CREATE TABLE IF NOT EXISTS doc_revisions (
    file_id     INTEGER PRIMARY KEY,
    doc_id      TEXT,
    revision    TEXT,
    rev_rank    INTEGER,
    is_latest   INTEGER
)
""",
    "CREATE INDEX IF NOT EXISTS idx_docrev_doc ON doc_revisions(doc_id)",
)

# KKS equipment tags found in the chunk text, one row per tag per chunk.
# tag is as written; tag_norm has the spaces and dashes taken out. The pattern
# lives in core/kks.py, which DB Search uses to look a typed tag up.
SCHEMA_KKS = (
    """
CREATE TABLE IF NOT EXISTS kks_tags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tag         TEXT,
    tag_norm    TEXT,
    file_id     INTEGER,
    chunk_id    INTEGER,
    page        INTEGER
)
""",
    "CREATE INDEX IF NOT EXISTS idx_kks_norm ON kks_tags(tag_norm)",
    "CREATE INDEX IF NOT EXISTS idx_kks_file ON kks_tags(file_id)",
)

# ─────────────────────────────────────────────────────────────────────────────
#  METADATA PARSER  (từ tên file theo quy ước VP1)
# ─────────────────────────────────────────────────────────────────────────────
# Pattern: VP1-[unit]-L[1-4]-[Disc]-[SysCode]-[Number][_RevXX]
_DOC_RE = re.compile(
    r'VP1-[^-]+-L(\d)-([A-Za-z])-([A-Za-z0-9]+)-\d+',
    re.IGNORECASE
)
# Revision, in the order it is looked for: an explicit "Rev" marker anywhere in
# the name, then the bare token straight after the document number
# ("...-10019-B.pdf", "..._10019_C_..."), then the as-built "AB0" anywhere.
#
# The explicit pattern used to need a "_" or "-" in front of "Rev" and took
# every letter and digit after it, so "Rev.AB0Schematic" was stored as the
# revision and "Manual Rev 2" had none. It now ends where the token does --
# (?![A-Z0-9]) rather than \b, because "_" is a word character and \b after
# "Rev.AB0_..." or "_REV B_" never matches.
_REV_EXPLICIT = re.compile(
    r'(?<![A-Z])REV(?:ISION)?[.\s_\-]*([A-Z]{1,2}\d{0,2}|\d{1,2})(?![A-Z0-9])',
    re.IGNORECASE
)
_REV_BARE = re.compile(
    r'^[-_ ]([A-Z]{1,2}\d{0,2}|\d{1,2})(?=[\s_.]|$)',
    re.IGNORECASE
)
# Words that sit where a revision would and are not one: "-HP Cleanup",
# "-LP Extraction", "-HV Test", "-IO Signal Check", "-1 OM Manual", "Rev.No.2".
_NOT_REVISIONS = frozenset({'HP', 'LP', 'HV', 'MV', 'LV', 'IO', 'AC', 'DC', 'NO', 'OM'})
_DOC_NO_RE = re.compile(
    r'(VP1-[^_\s]+?-\d+)',
    re.IGNORECASE
)

DISCIPLINE_MAP = {
    'A': 'Architectural', 'C': 'Civil/Structural',
    'E': 'Electrical',    'F': 'Commissioning',
    'G': 'General',       'I': 'Instrumentation & Control',
    'M': 'Mechanical',    'P': 'Piping',
    'Q': 'Quality',       'R': 'Process/PFD',
    'L': 'Layout',
}

def parse_metadata(filename):
    """Trả về dict: doc_number, lot, discipline, system_code, revision"""
    stem = os.path.splitext(filename)[0]
    meta = {'doc_number': '', 'lot': '', 'discipline': '', 'system_code': '', 'revision': ''}

    m = _DOC_RE.search(stem)
    if m:
        meta['lot']         = f"L{m.group(1)}"
        meta['discipline']  = m.group(2).upper()
        meta['system_code'] = m.group(3).upper()

    m2 = _DOC_NO_RE.search(stem)
    if m2:
        meta['doc_number'] = m2.group(1)

    meta['revision'] = _parse_revision(filename, stem, m2)
    return meta


def _clean_rev(rev):
    """Upper case, with full-width digits ("３") folded to ASCII."""
    return unicodedata.normalize('NFKC', rev or '').upper()


def _parse_revision(filename, stem, doc_no_match=None):
    for m in _REV_EXPLICIT.finditer(stem):
        rev = _clean_rev(m.group(1))
        if rev not in _NOT_REVISIONS:
            return rev

    doc = doc_naming.parse(filename)
    if doc is not None:
        rev = _clean_rev(doc.revision)
    elif doc_no_match is not None:
        # A VP1 number doc_naming does not recognise, e.g. "VP1-L1-Training-00001_RB_".
        m = _REV_BARE.match(stem[doc_no_match.end():])
        rev = _clean_rev(m.group(1)) if m else ''
    else:
        rev = ''
    if rev and rev not in _NOT_REVISIONS:
        return rev

    if 'AB0' in stem.upper():
        return 'AB0'
    return ''


# Revision order, lowest first: the lettered issues A..Z (with "B1" a re-issue
# of B), then the numbered ones 0, 1, 2..., then as-built AB0, AB1... "R2" is
# read as 2 and "RB" as B. Anything else -- "AE", "AA" -- gets no rank and is
# never called the latest. The order is this indexer's assumption, not a rule
# taken from a document-control procedure.
_RANK_TIER   = 1_000_000
_RANK_AB     = re.compile(r'AB(\d{1,2})')
_RANK_NUMBER = re.compile(r'R?(\d{1,2})')
_RANK_LETTER = re.compile(r'R?([A-Z])(\d{0,2})')


def _rev_rank(rev):
    """A sortable number for a revision from _parse_revision, or None."""
    if not rev:
        return None
    m = _RANK_AB.fullmatch(rev)
    if m:
        return 2 * _RANK_TIER + int(m.group(1)) * 1000
    m = _RANK_NUMBER.fullmatch(rev)
    if m:
        return _RANK_TIER + int(m.group(1)) * 1000
    m = _RANK_LETTER.fullmatch(rev)
    if m:
        sub = m.group(2)
        return (ord(m.group(1)) - 64) * 1000 + (int(sub) + 1 if sub else 0)
    return None


def rebuild_doc_revisions(conn):
    """Recompute doc_revisions from the file names; return how many rows it holds.

    Files that name the same document are compared by revision: the highest
    rank is the latest (two files sharing it, a PDF and its DWG say, are both
    latest) and the rest are not. A file whose revision has no rank is left
    NULL rather than guessed, and so is a file with no document number. A
    document held by one file only is latest whatever its revision says.

    The revision is parsed again from the name rather than read from
    files.revision, so a database indexed before the parser was fixed gets the
    corrected values here without its files rows being rewritten (see
    SCHEMA_DOC_REVISIONS for why they are not). Committing is left to the caller.
    """
    rows = []
    for file_id, name, doc_number in conn.execute(
            "SELECT id, name, doc_number FROM files WHERE name != 'BASE_PATH'"):
        doc = doc_naming.parse(name or '')
        doc_id = doc.doc_id if doc is not None else ((doc_number or '').upper() or None)
        rev = parse_metadata(name or '')['revision']
        rows.append((file_id, doc_id, rev, _rev_rank(rev)))

    by_doc = collections.defaultdict(list)
    for file_id, doc_id, _rev, rank in rows:
        if doc_id:
            by_doc[doc_id].append((file_id, rank))
    latest = {}
    for members in by_doc.values():
        if len(members) == 1:
            latest[members[0][0]] = 1
            continue
        top = max((rank for _, rank in members if rank is not None), default=None)
        for file_id, rank in members:
            latest[file_id] = None if rank is None else int(rank == top)

    cur = conn.cursor()
    cur.execute("DELETE FROM doc_revisions")
    cur.executemany(
        "INSERT INTO doc_revisions (file_id, doc_id, revision, rev_rank, is_latest) "
        "VALUES (?,?,?,?,?)",
        [(file_id, doc_id, rev, rank, latest.get(file_id))
         for file_id, doc_id, rev, rank in rows]
    )
    return len(rows)

# ─────────────────────────────────────────────────────────────────────────────
#  SCANNED PDF DETECTOR  &  OCR
# ─────────────────────────────────────────────────────────────────────────────
DRAWING_KEYWORDS = {
    'p&id', 'pid', 'plan', 'section', 'elevation', 'detail',
    'arrangement', 'general arrangement', 'layout', 'schematic',
    'foundation', 'reinforcement', 'isometric', 'single line',
    'wiring', 'cable', 'duct', 'piping', 'boring log', 'geological',
}

def _is_drawing_file(filename):
    low = filename.lower()
    return any(kw in low for kw in DRAWING_KEYWORDS)

def _preprocess(img, scale=1):
    """Tăng chất lượng ảnh trước OCR. scale=2 giúp đọc font nhỏ/kỹ thuật tốt hơn."""
    from PIL import ImageFilter, ImageEnhance
    img = img.convert('L')
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), resample=1)  # LANCZOS
    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = img.filter(ImageFilter.SHARPEN)
    img = img.filter(ImageFilter.SHARPEN)   # sharpen 2 lần cho font CAD
    return img

def _page_image(page, dpi):
    """One PDF page rasterised to a PIL image, via PyMuPDF.

    This used to go through pdf2image, which is a thin wrapper around the
    poppler binary -- a non-Python install that has to be unpacked and put on
    PATH by hand. PyMuPDF renders the same pages and is already a dependency:
    extract_content below opens every PDF with it to read the text layer, so
    dropping poppler removes the only part of this OCR chain that pip could not
    install.

    It also removes a silent failure. The pdf2image import sat outside the try
    blocks below, so on a machine without it the ModuleNotFoundError escaped to
    the caller's handler, which returned is_scanned=0 -- every scanned PDF was
    stored carrying the literal text "[Error: No module named 'pdf2image']" and
    labelled as though it had a perfectly good text layer. Nothing reported a
    problem and there was no way to filter those files out afterwards to retry.
    """
    from PIL import Image
    pix = page.get_pixmap(dpi=dpi)
    return Image.open(io.BytesIO(pix.tobytes("png")))

# max_pages decides how much of a scanned document exists in the index at all,
# and at the 20 it started on it was discarding 8,804 of the 12,565 pages in the
# 512 documents that come down this path -- 70% of them. An O&M manual of 440
# pages was indexed from its first 20, then answered questions as though that
# were the whole manual; a procedure on page 150 simply did not exist.
#
# 150 is where the measured cost curve bends. It leaves 13 documents truncated
# instead of 116, and every further step buys very little: 200 completes two
# more files for 576 more pages of OCR, 300 completes four more for 1,410. At
# ~6.2 s per page (measured here, tesseract 5.5) a full re-OCR of the 116
# affected files costs about nine hours, so the cap is also what keeps that job
# inside one night.
#
# That arithmetic is Tesseract's. PaddleOCR on the GPU measured 0.79 s per page
# (a 46-page procedure in 35 s), so there the cap only guards against a
# runaway scan: 1,000 pages is about 13 minutes for one document, and in the
# commissioning folder it truncated three files at 150 (239 to 280 pages).
OCR_MAX_PAGES_CPU = 150
OCR_MAX_PAGES_GPU = 1000


def _ocr_pages(pdf_path, max_pages=None, only=None):
    """OCR the pages of a printed document (commissioning, O&M, training).

    only, a set of page numbers, limits it to those pages -- the scanned pages
    of a PDF that is partly text layer; max_pages then caps how many of them
    are read, by default OCR_MAX_PAGES_GPU or _CPU for the engine in use.
    Returns (pages, error): pages is a list of (page number, text), and error
    is set -- with pages empty -- when nothing at all could be read.
    """
    try:
        import fitz
        try:
            from core import ocr_engine
        except ImportError:
            import ocr_engine
        paddle = ocr_engine.use_paddle()
        if not paddle:
            import pytesseract
        if max_pages is None:
            max_pages = OCR_MAX_PAGES_GPU if paddle else OCR_MAX_PAGES_CPU
        pages, failed, first_err = [], 0, ''
        with fitz.open(pdf_path) as pdf:
            for i in range(len(pdf)):
                if only is not None and i + 1 not in only:
                    continue
                if len(pages) >= max_pages:
                    break
                # Caught per page, not per document. The whole loop used to sit
                # inside the handler below, so a single unreadable page threw
                # away every page already read and the function returned
                # "[OCR Error: ...]" in place of the text. At 20 pages that lost
                # two minutes of work; at 150 it would lose a quarter of an hour
                # -- and index the document as a failure although 149 pages of
                # it had been read perfectly well.
                try:
                    if paddle:
                        text = ocr_engine.ocr_image_paddle(_page_image(pdf[i], 200))
                    else:
                        text = pytesseract.image_to_string(
                            _preprocess(_page_image(pdf[i], 200), scale=2),
                            lang='eng', config='--psm 3 --oem 3')
                except Exception as e:
                    failed += 1
                    first_err = first_err or f'{type(e).__name__}: {e}'
                    # Left in the text on purpose. A page dropped silently is
                    # indistinguishable from a page that was blank, which is the
                    # mistake this file has already been bitten by once.
                    text = f'[OCR failed on page {i + 1}: {e}]'
                pages.append((i + 1, text))
        if pages and failed == len(pages):
            # Nothing was read. Report it as a document-level failure so
            # _write_skip_log lists the file and it can be retried, rather than
            # storing a page of error markers as if it were the document.
            return [], f"[OCR Error: all {failed} page(s) failed; {first_err}]"
        return pages, ''
    except Exception as e:
        return [], f"[OCR Error: {e}]"

def _ocr_titleblock(pdf_path):
    """OCR title block (góc dưới phải) – dùng cho bản vẽ kỹ thuật.
    DPI 300 + upscale 2x + psm 11 để đọc chính xác tag/code kiểu 10HFE30 BR001.
    """
    # psm 11: sparse text – tốt cho title block có text rải rác nhiều ô
    _CFG = '--psm 11 --oem 3'
    try:
        import fitz
        try:
            from core import ocr_engine
        except ImportError:
            import ocr_engine
        paddle = ocr_engine.use_paddle()
        if not paddle:
            import pytesseract
        with fitz.open(pdf_path) as pdf:
            if not len(pdf):
                return ''
            img = _page_image(pdf[0], 300)
        w, h = img.size
        # Crop: 55% bên phải, 38% phía dưới → vùng title block
        crop = img.crop((int(w * 0.45), int(h * 0.62), w, h))
        if paddle:
            text = ocr_engine.ocr_image_paddle(crop)
        else:
            text = pytesseract.image_to_string(_preprocess(crop, scale=2),
                                               lang='eng', config=_CFG)
        return f"[TITLE BLOCK]\n{text}"
    except Exception as e:
        return f"[OCR Error: {e}]"

# A PDF page whose text layer holds less than this is a scanned page and gets
# OCR'd. Measured over the 25,518 pages of the commissioning folder: scanned
# pages carry 0-9 characters (52% of all pages), or 10-49 when a stamp or a
# reviewer's note sits on top ("Add this page", "For Review"); pages of real
# text start around 50 (a revision-record table page holds 50-99).
PAGE_TEXT_MIN = 50
# Scan samples this many pages of a longer PDF, evenly spread, to decide its
# "Cần OCR" count; reading every page of the folder's 316 PDFs took 87 s.
SCAN_SAMPLE_PAGES = 15


def scanned_pages(pages):
    """Numbers of the pages in [(page_no, text), ...] whose text layer is too
    thin to be the page's text."""
    return [no for no, t in pages if len((t or '').strip()) < PAGE_TEXT_MIN]


def mostly_scanned(n_scanned, n_pages):
    """is_scanned: at least half of the pages are scans."""
    return n_pages > 0 and n_scanned * 2 >= n_pages

# ─────────────────────────────────────────────────────────────────────────────
#  CONTENT EXTRACTORS
# ─────────────────────────────────────────────────────────────────────────────
def extract_content(file_path, use_ocr=True):
    """
    Trả về (content_text, is_scanned, page_count)
    """
    content, is_scanned, _ocr, page_count, _pages = extract_pages(file_path, use_ocr)
    return content, is_scanned, page_count


def extract_pages(file_path, use_ocr=True):
    """extract_content plus the text of each page: (content, is_scanned, ocr,
    page_count, pages).

    is_scanned is 1 when at least half of a PDF's pages are scans (see
    PAGE_TEXT_MIN), and for an image. ocr counts the pages whose text the OCR
    engine produced: the scanned pages of a PDF (all of them, or only those of
    a mostly-text PDF), 1 for a drawing's title block or an image, and 0 for a
    text-layer PDF, scans left un-OCR'd, every born-digital format and any
    extraction error. So is_scanned says "looks scanned", ocr "how much we read
    by OCR".

    pages is a list of (page number, text) for PDFs, slide decks and images,
    and None for formats that have no pages or when extraction failed. The
    content is exactly the pages joined with newlines, as it always was, so
    files.content does not change -- only the chunks learn where they came from.
    """
    ext = os.path.splitext(file_path)[1].lower()
    file_path = _fs_path(file_path)   # survive paths over the Windows 260 cap

    # ── PDF ──────────────────────────────────────────────────────────────────
    if ext == '.pdf':
        try:
            import fitz
            with fitz.open(file_path) as pdf:
                page_count = len(pdf)
                pages = [(i + 1, page.get_text('text')) for i, page in enumerate(pdf)]
            text = '\n'.join(t for _, t in pages)

            # Decided page by page. The whole file used to count as text layer
            # once it held 50 characters anywhere, so a 156-page scan whose one
            # typed page was the cover went un-OCR'd and was indexed as 680
            # characters -- seven such files, 1,375 pages, in a single folder.
            thin = scanned_pages(pages)
            scanned = 1 if mostly_scanned(len(thin), page_count) else 0
            if not thin:
                return text, 0, 0, page_count, pages        # text layer throughout
            if not use_ocr:
                return text, scanned, 0, page_count, pages  # scans left un-OCR'd

            # Caught here rather than left to the handler below, which answers
            # is_scanned=0. A mostly scanned PDF has no usable text layer no
            # matter what OCR then does with it, and recording it as though it
            # had one is the one error there is no recovering from: the file
            # looks indexed, reads as empty, and cannot be listed again to retry.
            # A mostly-text PDF whose scanned pages fail keeps its text layer.
            try:
                if _is_drawing_file(os.path.basename(file_path)):
                    # A drawing only ever has its title block read.
                    if not scanned:
                        return text, 0, 0, page_count, pages
                    tb = _ocr_titleblock(file_path)
                    if tb.startswith('[OCR Error:'):
                        return tb, 1, 0, page_count, None
                    return tb, 1, 1, page_count, [(1, tb)]
                read, error = _ocr_pages(file_path, only=set(thin))
                if error:
                    if scanned:
                        return error, 1, 0, page_count, None
                    return text, 0, 0, page_count, pages
                by_page = dict(read)
                merged = []
                for no, layer in pages:
                    if no not in by_page:
                        merged.append((no, layer))
                    elif layer.strip():
                        # Keep the little the layer had (a stamp, a note) verbatim;
                        # OCR may read it less exactly.
                        merged.append((no, f"{layer.strip()}\n{by_page[no]}"))
                    else:
                        merged.append((no, by_page[no]))
                n_ocr = sum(1 for t in by_page.values() if not t.startswith('[OCR failed'))
                return ('\n'.join(t for _, t in merged), scanned, n_ocr,
                        page_count, merged)
            except Exception as e:
                if scanned:
                    return f"[OCR Error: {e}]", 1, 0, page_count, None
                return text, 0, 0, page_count, pages

        except Exception as e:
            return f"[Error: {e}]", 0, 0, 0, None

    # ── WORD ─────────────────────────────────────────────────────────────────
    elif ext == '.docx':
        try:
            from docx import Document
            doc = Document(file_path)
            parts = [p.text for p in doc.paragraphs if p.text.strip()]
            # Đọc luôn bảng biểu trong docx
            for table in doc.tables:
                for row in table.rows:
                    row_text = ' | '.join(c.text.strip() for c in row.cells if c.text.strip())
                    if row_text:
                        parts.append(row_text)
            return '\n'.join(parts), 0, 0, 0, None
        except Exception as e:
            return f"[Error: {e}]", 0, 0, 0, None

    # ── EXCEL ────────────────────────────────────────────────────────────────
    elif ext == '.xlsx':
        try:
            from openpyxl import load_workbook
            wb = load_workbook(file_path, read_only=True, data_only=True)
            rows = []
            for sheet in wb.sheetnames:
                ws = wb[sheet]
                rows.append(f"[Sheet: {sheet}]")
                for row in ws.iter_rows(values_only=True):
                    cells = [str(c) for c in row if c is not None and str(c).strip() not in ('', 'None')]
                    if cells:
                        rows.append('\t'.join(cells))
            return '\n'.join(rows), 0, 0, 0, None
        except Exception as e:
            return f"[Error: {e}]", 0, 0, 0, None

    # ── POWERPOINT ───────────────────────────────────────────────────────────
    elif ext == '.pptx':
        try:
            from pptx import Presentation
            from pptx.util import Pt
            prs = Presentation(file_path)
            texts, pages = [], []
            for no, slide in enumerate(prs.slides, 1):
                on_slide = [shape.text for shape in slide.shapes
                            if hasattr(shape, 'text') and shape.text.strip()]
                if on_slide:         # an empty slide adds nothing, as before
                    texts.extend(on_slide)
                    pages.append((no, '\n'.join(on_slide)))
            return '\n'.join(texts), 0, 0, len(prs.slides), pages
        except Exception as e:
            return f"[Error: {e}]", 0, 0, 0, None

    # ── IMAGES ───────────────────────────────────────────────────────────────
    elif ext in ('.jpg', '.jpeg', '.png', '.tif', '.tiff'):
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(file_path)
            text = pytesseract.image_to_string(_preprocess(img), lang='eng', config='--psm 3')
            return text, 1, 1, 1, [(1, text)]   # image -> always OCR
        except Exception as e:
            return f"[Error: {e}]", 0, 0, 0, None

    # ── TEXT / CSV / JSON / HTML ──────────────────────────────────────────────
    elif ext == '.txt':
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read(), 0, 0, 0, None
        except Exception as e:
            return f"[Error: {e}]", 0, 0, 0, None

    elif ext == '.csv':
        try:
            rows = []
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                for row in csv.reader(f):
                    rows.append(', '.join(row))
            return '\n'.join(rows), 0, 0, 0, None
        except Exception as e:
            return f"[Error: {e}]", 0, 0, 0, None

    elif ext == '.json':
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                data = json.load(f)
            return json.dumps(data, indent=2, ensure_ascii=False), 0, 0, 0, None
        except Exception as e:
            return f"[Error: {e}]", 0, 0, 0, None

    elif ext in ('.html', '.htm', '.md'):
        try:
            from bs4 import BeautifulSoup
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                return BeautifulSoup(f, 'html.parser').get_text(), 0, 0, 0, None
        except Exception as e:
            return f"[Error: {e}]", 0, 0, 0, None

    return None, 0, 0, 0, None   # định dạng không hỗ trợ


# ─────────────────────────────────────────────────────────────────────────────
#  DATABASE HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def init_db(db_file):
    conn = sqlite3.connect(db_file)
    cur  = conn.cursor()
    # Connection-level only, so nothing about the database file changes: a
    # reader that opens it with mode=ro still sees an ordinary rollback-journal
    # database. WAL would be faster here but it persists in the file, and both
    # db_query.py and the Data Brain tab open this database read-only.
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA temp_store=MEMORY")
    cur.execute("PRAGMA cache_size=-65536")      # 64 MB of page cache
    cur.execute(SCHEMA_FILES)
    # files.ocr was added later; an older database gets it here (0 = unknown /
    # not OCR'd -- a rebuild fills it in properly).
    if 'ocr' not in {row[1] for row in cur.execute("PRAGMA table_info(files)")}:
        cur.execute("ALTER TABLE files ADD COLUMN ocr INTEGER DEFAULT 0")
    cur.execute(SCHEMA_FTS)
    cur.execute(SCHEMA_TRIGGER_INSERT)
    cur.execute(SCHEMA_TRIGGER_DELETE)
    cur.execute(SCHEMA_TRIGGER_UPDATE)
    cur.execute(SCHEMA_CHUNKS)
    have = {row[1] for row in cur.execute("PRAGMA table_info(chunks)")}
    for col in CHUNK_PAGE_COLUMNS:
        if col not in have:
            cur.execute(f"ALTER TABLE chunks ADD COLUMN {col} INTEGER")
    cur.execute(SCHEMA_CHUNKS_IDX)
    cur.execute(SCHEMA_CHUNKS_FTS)
    cur.execute(SCHEMA_CHUNKS_TRIGGER_I)
    cur.execute(SCHEMA_CHUNKS_TRIGGER_D)
    cur.execute(SCHEMA_CHUNKS_TRIGGER_U)
    cur.execute(SCHEMA_CHUNK_VECTORS)
    cur.execute(SCHEMA_SEMANTIC_META)
    cur.execute(SCHEMA_VECTORS_TRIGGER_D)
    for stmt in SCHEMA_FILES_IDX + SCHEMA_DOC_REVISIONS + SCHEMA_KKS:
        cur.execute(stmt)
    conn.commit()
    return conn

def get_indexed_state(conn):
    """path -> (file_size_kb, indexed_date) for everything already indexed."""
    cur = conn.cursor()
    cur.execute("SELECT path, file_size_kb, indexed_date FROM files")
    return {row[0]: (row[1], row[2]) for row in cur.fetchall()}


def _is_unchanged(full_path, state):
    """True when the file on disk is still the one the index describes.

    Incremental used to compare the path alone, so a document revised in place
    -- a drawing re-issued at the next revision under the same file name, which
    is how this archive is kept -- was skipped for ever and the index went on
    answering from the superseded text. Size and modification time are what
    make a changed document index again. Anything unreadable or unparseable is
    treated as changed: re-indexing a file needlessly costs time, missing a
    revision costs a wrong answer.
    """
    if state is None:
        return False
    size_kb, indexed_date = state
    if not indexed_date:
        return False
    try:
        st = os.stat(_fs_path(full_path))
    except OSError:
        return False
    if size_kb != max(1, st.st_size // 1024):
        return False
    try:
        was = datetime.strptime(indexed_date, '%Y-%m-%d %H:%M')
    except (ValueError, TypeError):
        return False
    # indexed_date has minute resolution, so round the file's own time down to
    # the minute as well rather than re-indexing every document that happened
    # to be written in the same minute it was indexed.
    mtime = datetime.fromtimestamp(st.st_mtime).replace(second=0, microsecond=0)
    return mtime <= was

def insert_file(conn, name, rel_path, ext, content, meta, is_scanned, ocr, page_count, file_size_kb):
    """Insert the file, or refresh the row that already holds this path.

    Returns its row id. The previous INSERT OR IGNORE silently kept the old row
    on a re-index, so files.content could describe one extraction while chunks
    described another. Committing is left to the caller, which batches it.
    """
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO files
            (name, path, type, content, doc_number, lot, discipline,
             system_code, revision, is_scanned, ocr, page_count, file_size_kb, indexed_date)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(path) DO UPDATE SET
            name         = excluded.name,
            type         = excluded.type,
            content      = excluded.content,
            doc_number   = excluded.doc_number,
            lot          = excluded.lot,
            discipline   = excluded.discipline,
            system_code  = excluded.system_code,
            revision     = excluded.revision,
            is_scanned   = excluded.is_scanned,
            ocr          = excluded.ocr,
            page_count   = excluded.page_count,
            file_size_kb = excluded.file_size_kb,
            indexed_date = excluded.indexed_date
    """, (
        name, rel_path, ext, content,
        meta['doc_number'], meta['lot'], meta['discipline'],
        meta['system_code'], meta['revision'],
        is_scanned, ocr, page_count, file_size_kb,
        datetime.now().strftime('%Y-%m-%d %H:%M')
    ))
    cur.execute("SELECT id FROM files WHERE path=?", (rel_path,))
    row = cur.fetchone()
    return row[0] if row else None

# ─────────────────────────────────────────────────────────────────────────────
#  CHUNKING
# ─────────────────────────────────────────────────────────────────────────────
CHUNK_MAX     = 1200   # ký tự tối đa mỗi chunk
CHUNK_MIN     = 80     # ký tự tối thiểu để chunk có nghĩa
CHUNK_OVERLAP = 120    # ký tự overlap giữa 2 chunk liên tiếp
COMMIT_EVERY  = 50     # files per commit; one commit per file cost two fsyncs each

# Pattern phát hiện heading trong tài liệu kỹ thuật
_HEAD_RE = re.compile(
    r'^(?:'
    r'\d+(?:\.\d+){0,3}\.?\s{1,4}[A-Z]'   # "5.7.1  ALARM" hoặc "1. Introduction"
    r'|(?:SECTION|Section)\s+\d'           # "Section 6"
    r'|[A-Z][A-Z &/]{5,}$'                 # "MAINTENANCE SCHEDULE"
    r')',
    re.MULTILINE
)

# A line break however it is padded, and a run of one or more blank lines.
# PyMuPDF's get_text('text') writes " \n " between lines, so a blank line in a
# PDF arrives as " \n \n " and never as a bare "\n\n". Splitting on r'\n{2,}'
# therefore matched nothing at all on most documents: a 20 MB drawing became a
# handful of paragraphs of tens of thousands of characters each, no heading was
# ever shorter than the 120-character limit, and 58% of chunks ended up with an
# empty heading. These two patterns are what makes the split actually happen.
_WS_LINE = re.compile(r'[ \t\u00a0]*\n[ \t\u00a0]*')
_BLANKS  = re.compile(r'(?:\n[ \t\u00a0]*){2,}')

HEAD_MAX = 120   # a heading longer than this is just a line of text

# A drawing page with less text than this carries no title block worth a chunk.
DRAWING_PAGE_MIN = 20


def _is_head(unit):
    return len(unit) < HEAD_MAX and _HEAD_RE.match(unit) is not None


def _chunk_units(text):
    """Yield the smallest sensible pieces to assemble chunks from.

    Paragraphs where the document really has them, lines where it does not, and
    a hard slice as the last resort -- tables, BOMs and calculation sheets carry
    no sentence punctuation, so splitting them on '.!?' returned one "sentence"
    of tens of thousands of characters.
    """
    for para in _BLANKS.split(text.strip()):
        para = para.strip()
        if not para:
            continue
        if len(para) <= CHUNK_MAX:
            yield para
            continue
        lines = [ln.strip() for ln in _WS_LINE.split(para) if ln.strip()]
        if len(lines) > 1:
            for ln in lines:
                yield ln
            continue
        for sent in re.split(r'(?<=[.!?])\s+', para):
            while len(sent) > CHUNK_MAX:
                yield sent[:CHUNK_MAX]
                sent = sent[CHUNK_MAX:]
            if sent:
                yield sent


def _split_chunks(text, head=''):
    """Split text into a list of (heading, content) no longer than CHUNK_MAX.

    A heading only counts as one when something other than another heading
    follows it; a page of capitalised labels -- which is what a P&ID drawing
    extracts to -- is content, not three hundred nested sections. Text under
    CHUNK_MIN is carried into the next chunk instead of being dropped, so no
    part of the document is lost on the way into the index.

    head is the heading in force where text begins, for a page that continues
    a section started on an earlier one.
    """
    if not text or len(text.strip()) < CHUNK_MIN:
        return []

    chunks = []
    body, blen = [], 0               # the chunk under construction, and its exact length
    carry, carry_keep = '', False    # text that opens the next chunk
    head_open = False                # head was met in this text and no chunk carries it yet

    def close():
        """Finish the chunk under construction and decide what opens the next."""
        nonlocal body, blen, carry, carry_keep, head_open
        joined = ' '.join(body).strip()
        body, blen = [], 0
        if not joined:
            return
        if len(joined) >= CHUNK_MIN:
            chunks.append((head, joined))
            head_open = False
            carry = joined[-CHUNK_OVERLAP:] if len(joined) > CHUNK_OVERLAP else ''
            carry_keep = False       # overlap: a duplicate, safe to drop
        else:
            # Too short for a chunk: the text moves into the next one, under that
            # chunk's heading, so a heading of its own goes with it as text. It
            # used to be dropped -- the heading line was then in no chunk at all,
            # and a drawing label such as "DRAIN TANK" could not be found.
            if head_open:
                joined = f"{head} {joined}"
                head_open = False
            carry = (carry + ' ' + joined).strip() if carry_keep else joined
            carry_keep = True        # real text: must not be dropped
            if len(carry) > CHUNK_MAX:
                chunks.append((head, carry))
                carry, carry_keep = '', False

    def add(unit):
        nonlocal body, blen, carry, carry_keep
        if body and blen + 1 + len(unit) > CHUNK_MAX:
            close()
        if not body and carry:
            if carry_keep or len(carry) + 1 + len(unit) <= CHUNK_MAX:
                body, blen = [carry], len(carry)
            carry, carry_keep = '', False
        body.append(unit)
        blen += len(unit) + (1 if len(body) > 1 else 0)

    pending = None                   # a heading waiting to see what follows it
    for unit in _chunk_units(text):
        is_head = _is_head(unit)
        if pending is not None:
            if is_head:
                add(pending)         # nothing under it: it was content after all
            else:
                if body:
                    close()
                head, head_open = pending, True
            pending = None
        if is_head:
            pending = unit
            continue
        add(unit)
    if pending is not None:
        add(pending)

    if body:
        close()
    if carry and carry_keep:
        # The document ended on a fragment. Keep it rather than lose it.
        if chunks:
            h, b = chunks[-1]
            chunks[-1] = (h, (b + ' ' + carry).strip())
        else:
            chunks.append((head, carry))
    return chunks



def _head_of(units, inherited):
    """(first, last) heading on a page, each falling back to inherited.

    A heading counts by the same rule as in _split_chunks: something other
    than another heading follows it on the page.
    """
    found = [u for i, u in enumerate(units)
             if _is_head(u) and i + 1 < len(units) and not _is_head(units[i + 1])]
    if not found:
        return inherited, inherited
    return found[0], found[-1]


def _page_chunks(pages, is_drawing=False):
    """Chunk a document page by page.

    pages is [(page_no, text), ...]. Returns [(heading, content, page_start,
    page_end, breaks), ...], where breaks lists (offset in content, page_no)
    for each page the chunk takes in, so a position in it maps back to a page.

    A page that fits in CHUNK_MAX is one chunk, and a longer one is split by
    _split_chunks. A page shorter than CHUNK_MIN -- a cover, a page holding
    only "Page 3 of 40" -- joins the page after it, so a chunk can run over a
    page break ("pp. 45-46"); at the end of the document it joins the page
    before. Nothing is dropped. A drawing sheet is never merged: each sheet is
    its own chunk however short, and only a sheet with almost no text at all
    (under DRAWING_PAGE_MIN) is left out.
    """
    out = []
    head = ''                        # the heading in force where the next page begins
    pend = None                      # (heading, content, breaks) of short pages still waiting
    for page_no, text in pages:
        units = list(_chunk_units(text or ''))
        if not units:
            continue
        first, last = _head_of(units, head)
        joined = ' '.join(units)
        if len(joined) <= CHUNK_MAX:
            pieces = [(first, joined)]
        else:
            pieces = _split_chunks(text, head=head)
        head = last

        if is_drawing:
            if len(joined) >= DRAWING_PAGE_MIN:
                out.extend((h, b, page_no, page_no, [(0, page_no)]) for h, b in pieces)
            continue

        if len(joined) < CHUNK_MIN:
            if pend is None:
                pend = (first, joined, [(0, page_no)])
            else:
                ph, pc, pb = pend
                pend = (ph or first, pc + ' ' + joined, pb + [(len(pc) + 1, page_no)])
            if len(pend[1]) >= CHUNK_MIN:
                ph, pc, pb = pend
                out.append((ph, pc, pb[0][1], pb[-1][1], pb))
                pend = None
            continue

        records = [(h, b, page_no, page_no, [(0, page_no)]) for h, b in pieces]
        if pend is not None:
            # Under CHUNK_MIN, so this chunk ends at most that much over CHUNK_MAX.
            ph, pc, pb = pend
            h0, b0, _s, e0, _b = records[0]
            records[0] = (ph or h0, pc + ' ' + b0, pb[0][1], e0,
                          pb + [(len(pc) + 1, page_no)])
            pend = None
        out.extend(records)

    if pend is not None:
        ph, pc, pb = pend
        if out:
            h, b, s, _e, br = out[-1]
            shift = len(b) + 1
            out[-1] = (h, b + ' ' + pc, s, pb[-1][1],
                       br + [(off + shift, no) for off, no in pb])
        else:
            out.append((ph, pc, pb[0][1], pb[-1][1], pb))
    return out


def _page_at(breaks, pos):
    """The page a position in a chunk falls on, or None when pages are unknown."""
    page = None
    for off, no in breaks or ():
        if off > pos:
            break
        page = no
    return page


def insert_chunks(conn, file_id, content, pages=None, is_drawing=False):
    """Chia content thành chunks và lưu vào bảng chunks, with its KKS tags.

    With pages from extract_pages the document is chunked page by page and
    page_start / page_end say where each chunk sits (slide numbers for a
    PowerPoint file); without them, as for Word or Excel, it is chunked whole
    and both are NULL.

    char_start / char_end are offsets into the concatenated chunk stream, not
    into files.content: the chunks carry overlap, so the two do not line up.
    Nothing reads them today. Committing is left to the caller, which batches it.
    """
    cur = conn.cursor()
    # Clear this file's earlier chunks first, every time. They used to be
    # cleared only once there was something to replace them with, so a document
    # re-indexed to almost no text kept answering with what it used to say.
    cur.execute("DELETE FROM kks_tags WHERE file_id=?", (file_id,))
    cur.execute("DELETE FROM chunks WHERE file_id=?", (file_id,))

    if not content:
        return 0
    if pages:
        if not is_drawing and len(content.strip()) < CHUNK_MIN:
            return 0
        records = _page_chunks(pages, is_drawing)
    else:
        if len(content.strip()) < CHUNK_MIN:
            return 0
        records = [(h, b, None, None, None) for h, b in _split_chunks(content)]
    if not records:
        return 0

    tags, char_pos, prev_head = [], 0, None
    for idx, (heading, body, page_start, page_end, breaks) in enumerate(records):
        char_end = char_pos + len(body)
        cur.execute(
            "INSERT INTO chunks (file_id, chunk_index, heading, content, "
            "char_start, char_end, page_start, page_end) VALUES (?,?,?,?,?,?,?,?)",
            (file_id, idx, heading, body, char_pos, char_end, page_start, page_end)
        )
        chunk_id = cur.lastrowid
        char_pos = char_end

        found = {}                   # tag_norm -> (tag as written, page)
        for m in kks.KKS_RE.finditer(body):
            found.setdefault(kks.norm(m.group(0)),
                             (m.group(0), _page_at(breaks, m.start())))
        # A split chunk leaves its heading out of the body, and an inherited
        # one sits on an earlier page; read it where it first applies.
        if heading and heading != prev_head:
            for m in kks.KKS_RE.finditer(heading):
                found.setdefault(kks.norm(m.group(0)), (m.group(0), page_start))
        prev_head = heading
        tags.extend((tag, norm, file_id, chunk_id, page)
                    for norm, (tag, page) in found.items())

    cur.executemany(
        "INSERT INTO kks_tags (tag, tag_norm, file_id, chunk_id, page) VALUES (?,?,?,?,?)",
        tags
    )
    return len(records)




def _match_pages(cur, fts_query, file_ids):
    """file_id -> set of the pages whose chunks match fts_query.

    A chunk is one page, except short pages merged with a neighbour, so a hit
    in such a chunk reports its small page range. An older database without
    chunks or chunk page columns simply yields no pages.

    Every chunk of a section carries the section heading, but the heading is
    printed only where the section starts, so its words count for the first
    chunk it heads; further chunks need the match in their own text. Without
    that a word in a heading reported every page of the section. The DB Search
    tab applies the same rule.
    """
    found = {}
    if not fts_query or not file_ids:
        return found
    ids = list(file_ids)
    for i in range(0, len(ids), 500):          # stay under SQLite's variable limit
        part = ids[i:i + 500]
        try:
            rows = cur.execute(
                "SELECT file_id, page_start, page_end FROM ("
                "  SELECT id, file_id, page_start, page_end, heading,"
                "         LAG(heading) OVER (PARTITION BY file_id ORDER BY chunk_index) AS prev"
                f"  FROM chunks WHERE file_id IN ({','.join('?' * len(part))})"
                ") WHERE id IN (SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?)"
                "  AND (heading IS NOT prev"
                "       OR id IN (SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?))",
                [*part, fts_query, f"content : ({fts_query})"]).fetchall()
        except sqlite3.OperationalError:
            return {}
        for fid, ps, pe in rows:
            if ps is None:
                continue
            pe = pe if (pe is not None and pe >= ps) else ps
            found.setdefault(fid, set()).update(range(ps, pe + 1))
    return found


def search_db(conn, query, lot_filter='', disc_filter='', scanned_filter=''):
    """Rows of (name, path, type, lot, discipline, system_code, doc_number,
    revision, is_scanned, ocr, page_count, pages) -- ocr is how many pages
    were read by OCR, pages where the query appears, e.g. '3–5, 9', empty when
    it matched only the name or no query was given."""
    cur = conn.cursor()
    params = []
    where_clauses = ["name != 'BASE_PATH'"]   # the folder-root row, not a document
    fts_query = ''
    has_ocr = 'ocr' in {r[1] for r in cur.execute("PRAGMA table_info(files)")}

    if query.strip():
        # Bọc từng token trong ngoặc kép để FTS5 không nhầm số/ký tự đặc biệt
        # thành cú pháp column-filter (vd: "16" bị hiểu là cột số 16 → lỗi)
        tokens = query.strip().split()
        fts_query = ' '.join(f'"{t}"*' for t in tokens if t)
        where_clauses.append("id IN (SELECT rowid FROM files_fts WHERE files_fts MATCH ?)")
        params.append(fts_query)
    if lot_filter:
        where_clauses.append("lot = ?")
        params.append(lot_filter)
    if disc_filter:
        where_clauses.append("discipline = ?")
        params.append(disc_filter)
    # Matching doc_source.source_label(): 'text' = text layer only, 'ocr' = any page read
    # by OCR (OCR and Text+OCR), 'scanned' = mostly scans, none OCR'd. A
    # database from before files.ocr has no OCR rows to show.
    if scanned_filter == 'text':
        where_clauses.append("is_scanned = 0 AND ocr = 0" if has_ocr else "is_scanned = 0")
    elif scanned_filter == 'ocr':
        where_clauses.append("ocr > 0" if has_ocr else "0")
    elif scanned_filter == 'scanned':
        where_clauses.append("is_scanned = 1 AND ocr = 0" if has_ocr else "is_scanned = 1")

    sql = f"""
        SELECT id, name, path, type, lot, discipline, system_code, doc_number,
               revision, is_scanned, {'ocr' if has_ocr else 'NULL'}, page_count
        FROM files
    """
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    sql += " ORDER BY lot, discipline, name LIMIT 500"

    rows = cur.execute(sql, params).fetchall()
    pages = _match_pages(cur, fts_query, [r[0] for r in rows])
    return [(*r[1:], doc_source.page_text(pages.get(r[0]))) for r in rows]


# Result table layout; open_file reads the path back from COL_PATH.
# Doc Number is left out: it is already in the file name, and files.doc_number
# stays in the database for search, revisions and the Data Brain.
RESULT_COLUMNS = ["Name", "Lot", "Disc", "System", "Rev",
                  "Source", "Pages", "Type", "Path"]
COL_PATH = RESULT_COLUMNS.index("Path")


# ─────────────────────────────────────────────────────────────────────────────
#  WORKER THREAD
# ─────────────────────────────────────────────────────────────────────────────
class IndexWorker(QThread):
    progress   = Signal(int, int, str)   # current, total, filename
    finished   = Signal(int, int)        # added, skipped
    error      = Signal(str)
    preview    = Signal(str, bytes, list, int)  # name, page png, first chunks, total chunks

    def __init__(self, folder_path, db_file, use_ocr, incremental,
                 ext_filter=None, path_filter=None, semantic=False):
        super().__init__()
        self.folder_path = folder_path
        self.db_file     = db_file
        self.use_ocr     = use_ocr
        self.incremental = incremental
        self.ext_filter  = ext_filter    # set of extensions, e.g. {'.pdf'}
        self.path_filter = path_filter   # set of absolute paths (cho Cần OCR)
        self.semantic    = semantic      # also embed every chunk (optional)
        self._stop       = False
        self._detail     = False     # render a page preview per file while on
        self.skip_log    = ''        # path of the report, once there is one

    def stop(self):
        self._stop = True

    def set_detail(self, on):
        """Turn the live page preview on or off, safely mid-run. Off costs nothing."""
        self._detail = bool(on)

    def _emit_preview(self, full_path, ext, content, pages, is_scanned):
        """Render the file's first (or title-block) page and its chunks for the
        Detail panel. Only called while Detail is on, and throttled by the caller."""
        import io as _io
        name = os.path.basename(full_path)
        is_drawing = _is_drawing_file(name)
        if pages:
            recs = _page_chunks(pages, is_drawing)
            chunks = [(h, b) for h, b, _ps, _pe, _br in recs]
        else:
            chunks = _split_chunks(content)
        png = b''
        if ext == '.pdf':
            try:
                import fitz
                with fitz.open(full_path) as pdf:
                    if len(pdf):
                        pix = pdf[0].get_pixmap(dpi=110)
                        png = pix.tobytes("png")
            except Exception:
                png = b''
        self.preview.emit(name, png, chunks[:40], len(chunks))

    def run(self):
        try:
            conn = init_db(self.db_file)

            # Lưu BASE_PATH
            cur = conn.cursor()
            cur.execute("DELETE FROM files WHERE name='BASE_PATH'")
            cur.execute(
                "INSERT INTO files (name, path, type, content) VALUES (?,?,?,?)",
                ('BASE_PATH', self.folder_path, 'folder', '')
            )
            conn.commit()

            indexed_state = get_indexed_state(conn) if self.incremental else {}

            # Thu thập tất cả file
            all_files = []
            unsupported = {}   # extension -> how many files were passed over
            junk        = 0    # lock files and resource forks, never documents
            supported = {'.pdf','.docx','.xlsx','.pptx','.txt','.csv',
                         '.json','.html','.htm','.md',
                         '.jpg','.jpeg','.png','.tif','.tiff'}
            for root, _, fnames in os.walk(self.folder_path):
                for fname in fnames:
                    if _JUNK_RE.match(fname):
                        junk += 1
                        continue
                    _e = os.path.splitext(fname)[1].lower()
                    if _e in supported:
                        all_files.append(os.path.join(root, fname))
                    else:
                        unsupported[_e] = unsupported.get(_e, 0) + 1

            # Per-category build (ext_filter / path_filter): keep only the files in
            # scope, so the progress bar counts the real workload -- e.g. the 132
            # scanned PDFs behind the "Cần OCR" card, not every file walked. A full
            # build (no filter) leaves all_files untouched.
            if self.ext_filter or self.path_filter:
                all_files = [
                    p for p in all_files
                    if (not self.ext_filter
                        or os.path.splitext(p)[1].lower() in self.ext_filter)
                    and (not self.path_filter or p in self.path_filter)
                ]

            total    = len(all_files)
            added    = 0
            skipped  = 0
            failures = []      # (path, reason) -- written out at the end
            dirty    = 0       # documents written since the last commit
            import time
            last_preview = 0.0  # throttle the Detail preview so it never slows indexing

            for idx, full_path in enumerate(all_files):
                if self._stop:
                    break

                rel_path = os.path.relpath(full_path, self.folder_path)
                self.progress.emit(idx + 1, total, os.path.basename(full_path))

                # Incremental: skip only while the file on disk still matches
                # the row already in the index -- same size, not modified since.
                if self.incremental and _is_unchanged(full_path,
                                                      indexed_state.get(rel_path)):
                    skipped += 1
                    continue

                _ext = os.path.splitext(full_path)[1].lower()

                try:
                    ext          = _ext
                    file_size_kb = max(1, os.path.getsize(_fs_path(full_path)) // 1024)
                    meta         = parse_metadata(os.path.basename(full_path))

                    content, is_scanned, ocr, page_count, pages = extract_pages(
                        full_path, self.use_ocr)

                    if content is None:
                        skipped += 1
                        failures.append((full_path, 'no extractor for this format'))
                        continue

                    # extract_content reports most trouble as an "[Error: ...]"
                    # string rather than raising, and that string was then
                    # indexed as if it were the document. Still index it -- the
                    # row has to exist -- but say so in the report.
                    if content.startswith('[Error:') or content.startswith('[OCR Error:'):
                        failures.append((full_path, content[:200].strip()))

                    file_id = insert_file(
                        conn,
                        os.path.basename(full_path),
                        rel_path, ext, content,
                        meta, is_scanned, ocr, page_count, file_size_kb
                    )
                    if file_id:
                        insert_chunks(conn, file_id, content, pages,
                                      _is_drawing_file(os.path.basename(full_path)))
                    added += 1
                    if self._detail and (time.monotonic() - last_preview) > 0.4:
                        last_preview = time.monotonic()
                        try:
                            self._emit_preview(full_path, ext, content, pages, is_scanned)
                        except Exception:
                            pass
                    dirty += 1
                    if dirty >= COMMIT_EVERY:
                        conn.commit()
                        dirty = 0
                except Exception as e:
                    # A locked file, a corrupt PDF, an OCR crash, a path the OS
                    # will not open. Only OSError used to be caught, so anything
                    # else ended the whole run; and nothing was ever recorded,
                    # which is why 30 missing documents took measuring to find.
                    skipped += 1
                    failures.append((full_path, f'{type(e).__name__}: {e}'))
                    continue

            conn.commit()
            # Over the whole database, not just this run's files: a new
            # revision changes which of the older files is still the latest.
            try:
                rebuild_doc_revisions(conn)
                conn.commit()
            except Exception as e:
                conn.rollback()
                failures.append((self.db_file, f'latest-revision table not rebuilt: '
                                               f'{type(e).__name__}: {e}'))
            # Merge the FTS b-trees once, at the end. An index built a document
            # at a time leaves hundreds of thousands of small segments behind.
            try:
                cur3 = conn.cursor()
                cur3.execute("INSERT INTO files_fts(files_fts) VALUES('optimize')")
                cur3.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('optimize')")
                conn.commit()
            except Exception:
                pass

            # Semantic layer, last: embed every chunk that has no vector yet, so an
            # incremental run only tops up. A load/model failure is reported but does
            # not undo the keyword index already written.
            if self.semantic and not self._stop:
                try:
                    import core.semantic as semantic
                    if not semantic.available():
                        failures.append((self.db_file,
                                         'semantic skipped: fastembed not installed'))
                    else:
                        self.progress.emit(0, 0, 'Embedding chunks (semantic)...')
                        semantic.build_embeddings(
                            conn,
                            progress=lambda d, t: self.progress.emit(
                                d, t, f'Embedding chunks {d}/{t}'),
                            should_stop=lambda: self._stop,
                        )
                        conn.commit()
                except Exception as e:
                    failures.append((self.db_file,
                                     f'semantic embedding failed: '
                                     f'{type(e).__name__}: {e}'))

            self._write_skip_log(failures, unsupported, junk)
            conn.close()
            self.finished.emit(added, skipped)

        except Exception as e:
            self.error.emit(str(e))

    def _write_skip_log(self, failures, unsupported, junk=0):
        """Write what did not make it into the index, beside the database."""
        self.skip_log = ''
        if not failures and not unsupported and not junk:
            return
        path = os.path.splitext(self.db_file)[0] + '_skipped.txt'
        try:
            with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(f"Source folder : {self.folder_path}\n")
                fh.write(f"Written       : "
                         f"{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
                if unsupported:
                    fh.write("Formats with no extractor (never indexed):\n")
                    for ext, n in sorted(unsupported.items(), key=lambda kv: -kv[1]):
                        fh.write(f"  {ext or '(no extension)':<16}{n:>7} file(s)\n")
                    fh.write("\n")
                if junk:
                    fh.write(f"System / Office junk skipped by name: {junk} "
                             f"file(s) matching ~$*, ._*, thumbs.db, "
                             f"desktop.ini\n\n")
                if failures:
                    fh.write(f"Files that failed ({len(failures)}):\n")
                    for p, why in failures:
                        fh.write(f"  {p}\n      {why}\n")
            self.skip_log = path
        except Exception:
            self.skip_log = ''


# ─────────────────────────────────────────────────────────────────────────────
#  SCAN WORKER  (chỉ đếm file – không extract nội dung)
# ─────────────────────────────────────────────────────────────────────────────
class ScanWorker(QThread):
    progress = Signal(int, int)             # current, total
    finished = Signal(dict, int, list, list)  # counts, ocr_needed, scanned_paths, all_files

    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path

    def run(self):
        import fitz as _fitz
        counts        = {}
        ocr_needed    = 0
        scanned_paths = []

        all_files = []
        for root, _, fnames in os.walk(self.folder_path):
            for fname in fnames:
                all_files.append(os.path.join(root, fname))

        total = len(all_files)
        for idx, fpath in enumerate(all_files):
            ext = os.path.splitext(fpath)[1].lower()
            counts[ext] = counts.get(ext, 0) + 1

            if ext == '.pdf':
                try:
                    # The same rule extract_pages uses for is_scanned (it used to
                    # be "page 1 under 100 characters", so the count and what
                    # indexing then did disagreed), on an even sample of pages.
                    with _fitz.open(fpath) as pdf:
                        n = pdf.page_count
                        if n <= SCAN_SAMPLE_PAGES:
                            idxs = range(n)
                        else:
                            idxs = sorted({round(k * (n - 1) / (SCAN_SAMPLE_PAGES - 1))
                                           for k in range(SCAN_SAMPLE_PAGES)})
                        sample = [(i + 1, pdf[i].get_text('text')) for i in idxs]
                    if mostly_scanned(len(scanned_pages(sample)), len(sample)):
                        ocr_needed += 1
                        scanned_paths.append(fpath)
                except Exception:
                    pass

            self.progress.emit(idx + 1, total)

        self.finished.emit(counts, ocr_needed, scanned_paths, all_files)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN WINDOW
# ─────────────────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Indexer v3  –  Van Phong")
        self.setGeometry(80, 80, 1280, 780)
        self.db_file        = None
        self.worker         = None
        self.scan_worker    = None
        self._scanned_paths = []
        self._all_scanned   = []   # every file the last scan walked, for File list
        self._detail_dlg    = None  # the live preview dialog, created on first use
        self._build_ui()

    # ── UI ──────────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        root = QVBoxLayout(central)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── App header bar ───────────────────────────────────────────────────
        header = QWidget()
        header.setObjectName("appHeader")
        header.setFixedHeight(50)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(16, 0, 16, 0)
        lbl_app = QLabel("FILE INDEXER")
        lbl_app.setStyleSheet(
            "color:#F1F5F9; font-size:16px; font-weight:700;"
            " letter-spacing:2px; background:transparent;")
        lbl_ver = QLabel("v3")
        lbl_ver.setStyleSheet(
            "color:#60A5FA; font-size:15px; font-weight:700;"
            " background:transparent; margin-left:6px;")
        sep = QLabel("|")
        sep.setStyleSheet("color:#334155; font-size:18px; background:transparent;"
                          " margin:0 10px;")
        lbl_sub = QLabel("Van Phong 1  ·  Document Index & Search")
        lbl_sub.setStyleSheet(
            "color:#64748B; font-size:11px; background:transparent;")
        for w in (lbl_app, lbl_ver, sep, lbl_sub):
            h_lay.addWidget(w)
        h_lay.addStretch()
        lbl_hint = QLabel("Double-click row to open file")
        lbl_hint.setStyleSheet(
            "color:#475569; font-size:10px; font-style:italic; background:transparent;")
        h_lay.addWidget(lbl_hint)

        # ── Content wrapper (light background) ──────────────────────────────
        content = QWidget()
        content.setObjectName("contentArea")
        content_lay = QVBoxLayout(content)
        content_lay.setSpacing(6)
        content_lay.setContentsMargins(10, 8, 10, 6)

        root.addWidget(header)
        root.addWidget(content, 1)

        # ── Row 1: DB + Index side-by-side ──────────────────────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        # Database group
        db_box = QGroupBox("Database")
        db_lay = QGridLayout(db_box)
        db_lay.setSpacing(6)
        db_lay.setContentsMargins(10, 14, 10, 8)
        self.db_input = QLineEdit()
        self.db_input.setReadOnly(True)
        self.db_input.setPlaceholderText("No database selected…")
        btn_new_db  = QPushButton("New DB")
        btn_open_db = QPushButton("Open DB")
        btn_new_db.clicked.connect(self.new_db)
        btn_open_db.clicked.connect(self.open_db)
        db_lay.addWidget(QLabel("Path:"),   0, 0)
        db_lay.addWidget(self.db_input,     0, 1, 1, 2)
        db_lay.addWidget(btn_new_db,        1, 1)
        db_lay.addWidget(btn_open_db,       1, 2)
        db_lay.setColumnStretch(1, 1)

        # Index group
        idx_box = QGroupBox("Index Folder")
        idx_lay = QGridLayout(idx_box)
        idx_lay.setSpacing(6)
        idx_lay.setContentsMargins(10, 14, 10, 8)
        self.folder_input = QLineEdit()
        self.folder_input.setReadOnly(True)
        self.folder_input.setPlaceholderText("Select folder to index…")
        btn_folder = QPushButton("Browse")
        btn_folder.clicked.connect(self.browse_folder)
        btn_scan = QPushButton("🔍  Scan")
        btn_scan.clicked.connect(self.scan_folder)
        self.chk_ocr  = QCheckBox("OCR for scanned PDFs")
        self.chk_ocr.setChecked(True)
        self.chk_incr = QCheckBox("Incremental")
        self.chk_incr.setChecked(True)
        self.chk_semantic = QCheckBox("Semantic")
        self.chk_semantic.setChecked(False)
        self.chk_semantic.setToolTip(
            "Also embed every chunk for meaning-based search (multilingual-e5-large).\n"
            "Uses the GPU when available, else the CPU (slower to build; search stays fast).")
        self.btn_index = QPushButton("▶  Start Index")
        self.btn_index.setObjectName("btnStart")
        self.btn_index.clicked.connect(self.start_index)
        self.btn_stop  = QPushButton("■  Stop")
        self.btn_stop.setObjectName("btnStop")
        self.btn_stop.clicked.connect(self.stop_index)
        self.btn_stop.setEnabled(False)
        idx_lay.addWidget(QLabel("Folder:"),      0, 0)
        idx_lay.addWidget(self.folder_input,      0, 1, 1, 3)
        idx_lay.addWidget(btn_folder,             0, 4)
        idx_lay.addWidget(btn_scan,               0, 5)
        idx_lay.addWidget(self.chk_ocr,           1, 1)
        idx_lay.addWidget(self.chk_incr,          1, 2)
        idx_lay.addWidget(self.chk_semantic,      1, 3)
        idx_lay.addWidget(self.btn_index,         1, 4)
        idx_lay.addWidget(self.btn_stop,          1, 5)
        idx_lay.setColumnStretch(1, 1)
        idx_lay.setColumnStretch(3, 1)

        # Device / recommendation for the Semantic tick, filled just after the
        # window shows so the one-off onnxruntime import does not delay opening it.
        self.lbl_semantic_info = QLabel("")
        self.lbl_semantic_info.setWordWrap(True)
        self.lbl_semantic_info.setStyleSheet("font-size: 11px; color: #64748b;")
        idx_lay.addWidget(self.lbl_semantic_info, 2, 1, 1, 5)
        self.lbl_ocr_info = QLabel("")
        self.lbl_ocr_info.setWordWrap(True)
        self.lbl_ocr_info.setStyleSheet("font-size: 11px; color: #64748b;")
        idx_lay.addWidget(self.lbl_ocr_info, 3, 1, 1, 5)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(200, self._update_semantic_info)

        top_row.addWidget(db_box,  1)
        top_row.addWidget(idx_box, 2)

        # ── File Summary (hiển thị sau khi Scan) ────────────────────────────
        sum_box = QGroupBox("File Summary")
        sum_lay = QHBoxLayout(sum_box)
        sum_lay.setSpacing(8)
        sum_lay.setContentsMargins(10, 10, 10, 8)

        _INIT_STYLE = ("background:#F1F5F9; border:1px solid #CBD5E1;"
                       " border-radius:6px; font-size:11px; font-weight:600;"
                       " color:#94A3B8; padding:4px 14px; min-width:72px;")
        _BTN_STYLE  = ("font-size:10px; padding:1px 6px; min-width:0;"
                       " background:#E2E8F0; color:#475569; border-radius:4px;")

        def _stat_slot(name):
            w    = QWidget()
            w.setStyleSheet("background:transparent;")
            vlay = QVBoxLayout(w)
            vlay.setSpacing(3)
            vlay.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(f"{name}\n–")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(_INIT_STYLE)
            lbl.setFixedHeight(52)
            btn_list = QPushButton("File list")
            btn_list.setStyleSheet(_BTN_STYLE)
            btn_list.setFixedHeight(22)
            btn_list.setEnabled(False)
            btn = QPushButton("Tạo DB")
            btn.setStyleSheet(_BTN_STYLE)
            btn.setFixedHeight(22)
            btn.setEnabled(False)
            vlay.addWidget(lbl)
            vlay.addWidget(btn_list)
            vlay.addWidget(btn)
            return w, lbl, btn_list, btn

        w_total, self.lbl_stat_total, self.btn_list_total, self.btn_db_total = _stat_slot("Total")
        w_pdf,   self.lbl_stat_pdf,   self.btn_list_pdf,   self.btn_db_pdf   = _stat_slot("PDF")
        w_word,  self.lbl_stat_word,  self.btn_list_word,  self.btn_db_word  = _stat_slot("Word")
        w_excel, self.lbl_stat_excel, self.btn_list_excel, self.btn_db_excel = _stat_slot("Excel")
        w_ppt,   self.lbl_stat_ppt,   self.btn_list_ppt,   self.btn_db_ppt   = _stat_slot("PPT")
        w_img,   self.lbl_stat_img,   self.btn_list_img,   self.btn_db_img   = _stat_slot("Image")
        w_text,  self.lbl_stat_text,  self.btn_list_text,  self.btn_db_text  = _stat_slot("Text / Other")
        w_ocr,   self.lbl_stat_ocr,   self.btn_list_ocr,   self.btn_db_ocr   = _stat_slot("Cần OCR")

        for w in (w_total, w_pdf, w_word, w_excel, w_ppt, w_img, w_text, w_ocr):
            sum_lay.addWidget(w)

        # ── Row 2: Progress (compact) ────────────────────────────────────────
        prog_box = QGroupBox("Progress")
        prog_lay = QHBoxLayout(prog_box)
        prog_lay.setSpacing(10)
        prog_lay.setContentsMargins(10, 14, 10, 8)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.lbl_progress = QLabel("–")
        self.lbl_progress.setFixedWidth(90)
        self.lbl_current  = QLabel("")
        self.lbl_current.setStyleSheet("color: #64748B; font-style: italic;")
        self.btn_detail = QPushButton("Show Detail")
        self.btn_detail.setCheckable(True)
        self.btn_detail.setFixedHeight(24)
        self.btn_detail.setToolTip(
            "Live preview of each file's page and the chunks going into the DB.\n"
            "Turning it off costs nothing.")
        self.btn_detail.toggled.connect(self._toggle_detail)
        prog_lay.addWidget(self.progress_bar, 3)
        prog_lay.addWidget(self.lbl_progress)
        prog_lay.addWidget(self.lbl_current,  4)
        prog_lay.addWidget(self.btn_detail)

        # ── Row 3: Search ────────────────────────────────────────────────────
        srch_box = QGroupBox("Search")
        srch_lay = QHBoxLayout(srch_box)
        srch_lay.setSpacing(8)
        srch_lay.setContentsMargins(10, 14, 10, 8)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Keyword, Doc Number, System code…")
        self.search_input.returnPressed.connect(self.search_files)
        self.cmb_lot  = QComboBox()
        self.cmb_lot.addItems(["All Lots", "L1", "L2", "L3", "L4"])
        self.cmb_disc = QComboBox()
        self.cmb_disc.addItems([
            "All Disciplines",
            "A – Architectural", "C – Civil", "E – Electrical",
            "F – Commissioning", "G – General",
            "I – Instrumentation", "M – Mechanical",
            "P – Piping", "Q – Quality", "R – Process"])
        self.cmb_scan = QComboBox()
        self.cmb_scan.addItems(["All Files", "Text only", "OCR only", "Scanned (no OCR)"])
        btn_search = QPushButton("🔍  Search")
        btn_search.clicked.connect(self.search_files)
        self.lbl_results = QLabel("Results: –")
        self.lbl_results.setStyleSheet("color: #1D4ED8; font-weight: 700; min-width: 80px;")
        for w in (QLabel("Keyword:"), self.search_input,
                  QLabel("Lot:"), self.cmb_lot,
                  QLabel("Disc:"), self.cmb_disc,
                  self.cmb_scan, btn_search, self.lbl_results):
            srch_lay.addWidget(w)

        # ── Row 4: Result table (stretch) ────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(len(RESULT_COLUMNS))
        self.table.setHorizontalHeaderLabels(RESULT_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(COL_PATH, QHeaderView.Stretch)
        self.table.horizontalHeaderItem(RESULT_COLUMNS.index("Source")).setToolTip(
            doc_source.SOURCE_HELP)
        self.table.horizontalHeaderItem(RESULT_COLUMNS.index("Pages")).setToolTip(
            "Pages where the search term appears")
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemDoubleClicked.connect(self.open_file)

        # ── Row 5: Change Base Path (compact) ────────────────────────────────
        path_box = QGroupBox("Change Base Path  —  dùng khi chuyển DB sang máy khác")
        path_lay = QHBoxLayout(path_box)
        path_lay.setSpacing(8)
        path_lay.setContentsMargins(10, 14, 10, 8)
        self.old_path_input = QLineEdit()
        self.old_path_input.setPlaceholderText("Old base path…")
        self.new_path_input = QLineEdit()
        self.new_path_input.setPlaceholderText("New base path…")
        btn_change = QPushButton("Update Paths")
        btn_change.clicked.connect(self.change_path)
        for w in (QLabel("Old:"), self.old_path_input,
                  QLabel("→  New:"), self.new_path_input,
                  btn_change):
            path_lay.addWidget(w)

        # ── Assemble into content area ───────────────────────────────────────
        content_lay.addLayout(top_row)
        content_lay.addWidget(sum_box)
        content_lay.addWidget(prog_box)
        content_lay.addWidget(srch_box)
        content_lay.addWidget(self.table, 1)
        content_lay.addWidget(path_box)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

    # ── DB ACTIONS ──────────────────────────────────────────────────────────
    def new_db(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create New Database", "", "Database (*.db)")
        if path:
            if not path.endswith('.db'):
                path += '.db'
            self.db_file = path
            self.db_input.setText(path)
            init_db(path).close()
            self.statusBar().showMessage(f"New DB created: {path}")

    def open_db(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Database", "", "Database (*.db)")
        if path:
            self.db_file = path
            self.db_input.setText(path)
            try:
                conn = sqlite3.connect(path)
                cur  = conn.cursor()

                # Tự động điền folder từ BASE_PATH đã lưu trong DB
                cur.execute("SELECT path FROM files WHERE name='BASE_PATH'")
                row = cur.fetchone()
                if row:
                    base = row[0]
                    self.old_path_input.setText(base)
                    # Nếu folder vẫn tồn tại trên máy → điền luôn vào ô folder
                    if os.path.isdir(base):
                        self.folder_input.setText(base)

                # Thống kê nhanh
                cur.execute("SELECT COUNT(*) FROM files WHERE name != 'BASE_PATH'")
                total = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM files WHERE is_scanned=1")
                scanned = cur.fetchone()[0]
                cur.execute("""SELECT COUNT(*) FROM files
                               WHERE name != 'BASE_PATH'
                               AND (content IS NULL OR length(trim(content))=0)""")
                empty = cur.fetchone()[0]
                conn.close()

                self.statusBar().showMessage(
                    f"Opened: {os.path.basename(path)}  |  "
                    f"{total} files indexed  |  "
                    f"{scanned} scanned/OCR  |  "
                    f"{empty} empty (not extracted)"
                )

                # Nếu folder tự động điền được → thông báo sẵn sàng bổ sung
                if row and os.path.isdir(row[0]):
                    self.lbl_current.setText(
                        "✅  Folder auto-loaded. Tick 'Incremental' rồi click Start Index để bổ sung file mới.")
                elif row:
                    self.lbl_current.setText(
                        "⚠  Folder cũ không tìm thấy trên máy này. Dùng 'Browse Folder' hoặc 'Change Base Path'.")

            except Exception as e:
                self.statusBar().showMessage(f"Opened (could not read stats): {e}")

    # ── INDEX ACTIONS ────────────────────────────────────────────────────────
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Index")
        if folder:
            self.folder_input.setText(folder)

    # ── SCAN FOLDER ──────────────────────────────────────────────────────────
    def scan_folder(self):
        folder = self.folder_input.text()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "Error", "Please select a valid folder first.")
            return
        self.progress_bar.setValue(0)
        self.lbl_progress.setText("Scanning…")
        self.statusBar().showMessage("Scanning folder — đang mở từng PDF để kiểm tra text layer…")
        self.scan_worker = ScanWorker(folder)
        self.scan_worker.progress.connect(self._on_scan_progress)
        self.scan_worker.finished.connect(self._on_scan_done)
        self.scan_worker.start()

    def _on_scan_progress(self, current, total):
        pct = int(current / total * 100) if total else 0
        self.progress_bar.setValue(pct)
        self.lbl_progress.setText(f"{current}/{total}")

    def _on_scan_done(self, counts, ocr_needed, scanned_paths, all_files=None):
        self._scanned_paths = scanned_paths
        self._all_scanned   = all_files or []

        total = sum(counts.values())
        pdf   = counts.get('.pdf', 0)
        word  = counts.get('.docx', 0) + counts.get('.doc', 0)
        excel = counts.get('.xlsx', 0) + counts.get('.xls', 0)
        ppt   = counts.get('.pptx', 0) + counts.get('.ppt', 0)
        img   = sum(counts.get(e, 0) for e in ('.jpg', '.jpeg', '.png', '.tif', '.tiff'))
        txt   = sum(counts.get(e, 0) for e in ('.txt', '.csv', '.json', '.html', '.htm', '.md'))
        other = total - pdf - word - excel - ppt - img - txt

        def _upd(lbl, name, n, bg, fg='#1E293B', bdr=None):
            lbl.setText(f"{name}\n{n:,}")
            lbl.setStyleSheet(
                f"background:{bg}; border:1px solid {bdr or bg}; border-radius:6px;"
                f" font-size:11px; font-weight:700; color:{fg};"
                f" padding:4px 14px; min-width:72px;")

        _upd(self.lbl_stat_total, "Total",       total,        "#CBD5E1", "#1E293B", "#94A3B8")
        _upd(self.lbl_stat_pdf,   "PDF",          pdf,         "#DBEAFE", "#1D4ED8")
        _upd(self.lbl_stat_word,  "Word",         word,        "#DCFCE7", "#15803D")
        _upd(self.lbl_stat_excel, "Excel",        excel,       "#D1FAE5", "#065F46")
        _upd(self.lbl_stat_ppt,   "PPT",          ppt,         "#FEE2E2", "#DC2626")
        _upd(self.lbl_stat_img,   "Image",        img,         "#EDE9FE", "#7C3AED")
        _upd(self.lbl_stat_text,  "Text / Other", txt + other, "#FEF3C7", "#92400E")
        _upd(self.lbl_stat_ocr,   "Cần OCR",      ocr_needed,  "#FEE2E2", "#DC2626", "#FCA5A5")

        # Kích hoạt nút Tạo DB cho từng phân loại
        _WORD_EXT  = {'.docx', '.doc'}
        _EXCEL_EXT = {'.xlsx', '.xls'}
        _PPT_EXT   = {'.pptx', '.ppt'}
        _IMG_EXT   = {'.jpg', '.jpeg', '.png', '.tif', '.tiff'}
        _TEXT_EXT  = {'.txt', '.csv', '.json', '.html', '.htm', '.md'}

        def _wire(btn, label, ext_filter=None, path_filter=None):
            try: btn.clicked.disconnect()
            except RuntimeError: pass
            btn.setEnabled(True)
            btn.clicked.connect(
                lambda: self._create_category_db(label, ext_filter, path_filter))

        _wire(self.btn_db_total, "All Files")
        _wire(self.btn_db_pdf,   "PDF",          ext_filter={'.pdf'})
        _wire(self.btn_db_word,  "Word",          ext_filter=_WORD_EXT)
        _wire(self.btn_db_excel, "Excel",         ext_filter=_EXCEL_EXT)
        _wire(self.btn_db_ppt,   "PPT",           ext_filter=_PPT_EXT)
        _wire(self.btn_db_img,   "Image",         ext_filter=_IMG_EXT)
        _wire(self.btn_db_text,  "Text/Other",    ext_filter=_TEXT_EXT)
        if scanned_paths:
            _wire(self.btn_db_ocr, "Cần OCR",
                  path_filter=set(scanned_paths))
        else:
            self.btn_db_ocr.setEnabled(False)

        # File list buttons: same categories, but list the files rather than index.
        def _wire_list(btn, label, ext_filter=None, path_filter=None):
            try: btn.clicked.disconnect()
            except RuntimeError: pass
            btn.setEnabled(True)
            btn.clicked.connect(
                lambda: self._show_file_list(label, ext_filter, path_filter))

        _wire_list(self.btn_list_total, "All Files")
        _wire_list(self.btn_list_pdf,   "PDF",         ext_filter={'.pdf'})
        _wire_list(self.btn_list_word,  "Word",        ext_filter=_WORD_EXT)
        _wire_list(self.btn_list_excel, "Excel",       ext_filter=_EXCEL_EXT)
        _wire_list(self.btn_list_ppt,   "PPT",         ext_filter=_PPT_EXT)
        _wire_list(self.btn_list_img,   "Image",       ext_filter=_IMG_EXT)
        _wire_list(self.btn_list_text,  "Text/Other",  ext_filter=_TEXT_EXT)
        if scanned_paths:
            _wire_list(self.btn_list_ocr, "Cần OCR", path_filter=set(scanned_paths))
        else:
            self.btn_list_ocr.setEnabled(False)

        self.progress_bar.setValue(100)
        self.lbl_progress.setText(f"{total:,} files")
        self.statusBar().showMessage(
            f"Scan complete  –  {total:,} files  |  "
            f"PDF: {pdf:,}  Word: {word:,}  Excel: {excel:,}  "
            f"PPT: {ppt:,}  Image: {img:,}  Other: {txt+other:,}  |  "
            f"Cần OCR: {ocr_needed:,}")

    def _show_file_list(self, label, ext_filter=None, path_filter=None):
        """List the scanned files of a category in a filterable dialog.

        Double-clicking a row opens the file. Paths are shown relative to the
        scanned folder, the way the index stores them.
        """
        folder = self.folder_input.text()
        files = self._all_scanned or []
        if path_filter is not None:
            files = [f for f in files if f in path_filter]
        elif ext_filter is not None:
            files = [f for f in files if os.path.splitext(f)[1].lower() in ext_filter]

        def _rel(p):
            if folder and os.path.isdir(folder):
                try:
                    return os.path.relpath(p, folder)
                except ValueError:
                    return p
            return p
        rels = sorted(_rel(f) for f in files)

        dlg = QDialog(self)
        dlg.setWindowTitle(f"File list — {label}  ({len(rels):,} files)")
        dlg.resize(760, 520)
        v = QVBoxLayout(dlg)
        filt = QLineEdit()
        filt.setPlaceholderText("Filter by name…")
        lst = QListWidget()
        lst.addItems(rels)

        def _apply():
            t = filt.text().strip().lower()
            lst.clear()
            lst.addItems([r for r in rels if t in r.lower()] if t else rels)
        filt.textChanged.connect(_apply)

        def _open(item):
            if not folder:
                return
            try:
                os.startfile(os.path.join(folder, item.text()))
            except Exception:
                pass
        lst.itemDoubleClicked.connect(_open)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dlg.accept)
        v.addWidget(filt)
        v.addWidget(lst, 1)
        v.addWidget(btn_close)
        dlg.exec()

    def _create_category_db(self, label, ext_filter=None, path_filter=None):
        folder = self.folder_input.text()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "Error", "Please select a valid folder first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, f"Tạo DB — {label}", "", "Database (*.db)")
        if not path:
            return
        if not path.endswith('.db'):
            path += '.db'
        self.db_file = path
        self.db_input.setText(path)
        self.btn_index.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.worker = IndexWorker(
            folder, path,
            use_ocr=self.chk_ocr.isChecked(),
            incremental=False,
            ext_filter=ext_filter,
            path_filter=path_filter,
            semantic=self.chk_semantic.isChecked()
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.preview.connect(self._on_preview)
        self.worker.set_detail(self.btn_detail.isChecked())
        self.worker.start()

    # ── Live Detail preview ──────────────────────────────────────────────────
    def _toggle_detail(self, on):
        if on:
            self._open_detail_dialog()
        elif self._detail_dlg is not None:
            self._detail_dlg.hide()
        if self.worker is not None:
            self.worker.set_detail(on)

    def _open_detail_dialog(self):
        if self._detail_dlg is None:
            dlg = QDialog(self)
            dlg.setWindowTitle("Indexing Detail — page preview")
            dlg.resize(900, 620)
            lay = QVBoxLayout(dlg)
            self._detail_header = QLabel("Waiting for the next file…")
            self._detail_header.setStyleSheet("font-weight:600; color:#334155;")
            split = QSplitter(Qt.Horizontal)
            self._detail_img = QLabel("No page yet")
            self._detail_img.setAlignment(Qt.AlignCenter)
            self._detail_img.setStyleSheet(
                "background:#F8FAFC; border:1px solid #E2E8F0; color:#94A3B8;")
            self._detail_img.setMinimumWidth(340)
            self._detail_chunks = QListWidget()
            self._detail_chunks.setWordWrap(True)
            split.addWidget(self._detail_img)
            split.addWidget(self._detail_chunks)
            split.setSizes([470, 430])
            lay.addWidget(self._detail_header)
            lay.addWidget(split, 1)
            dlg.finished.connect(lambda _: self.btn_detail.setChecked(False))
            self._detail_dlg = dlg
        self._detail_dlg.show()
        self._detail_dlg.raise_()

    def _on_preview(self, name, png, chunks, total):
        if self._detail_dlg is None or not self._detail_dlg.isVisible():
            return
        self._detail_header.setText(f"{name}   —   {total} chunk(s) into the DB")
        if png:
            pm = QPixmap()
            pm.loadFromData(png)
            if not pm.isNull():
                self._detail_img.setPixmap(pm.scaled(
                    max(self._detail_img.width(), 100),
                    max(self._detail_img.height(), 100),
                    Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                self._detail_img.setText("(could not render page)")
        else:
            self._detail_img.setText("(no page image — not a PDF)")
        self._detail_chunks.clear()
        for i, (h, b) in enumerate(chunks, 1):
            head = f"{h} — " if h else ""
            snippet = (b or "")[:220].replace("\n", " ")
            self._detail_chunks.addItem(f"[{i}] {head}{snippet}")
        if total > len(chunks):
            self._detail_chunks.addItem(f"… (+{total - len(chunks)} more chunks)")

    def _update_semantic_info(self):
        """Fill the notice beside the Semantic tick: device and whether to use it."""
        try:
            import core.semantic as semantic
            status, msg = semantic.advice()
        except Exception as e:
            status, msg = "unavailable", f"Semantic unavailable: {e}"
        colour = {"GPU": "#15803d", "CPU": "#b45309"}.get(status, "#dc2626")
        icon = {"GPU": "⚡", "CPU": "🐢"}.get(status, "⚠")
        self.lbl_semantic_info.setStyleSheet(f"font-size: 11px; color: {colour};")
        self.lbl_semantic_info.setText(f"{icon}  Semantic will use {status}  —  {msg}")

        # OCR engine notice: PaddleOCR on GPU, Tesseract on CPU.
        try:
            import core.ocr_engine as ocr_engine
            engine, omsg = ocr_engine.advice()
        except Exception as e:
            engine, omsg = "Tesseract", f"OCR check failed: {e}"
        ocolour = "#15803d" if engine == "PaddleOCR" else "#b45309"
        oicon = "⚡" if engine == "PaddleOCR" else "🐢"
        self.lbl_ocr_info.setStyleSheet(f"font-size: 11px; color: {ocolour};")
        self.lbl_ocr_info.setText(f"{oicon}  OCR will use {engine}  —  {omsg}")

    def start_index(self):
        if not self.db_file:
            QMessageBox.warning(self, "Error", "Please create or open a database first.")
            return
        folder = self.folder_input.text()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "Error", "Please select a valid folder.")
            return

        self.btn_index.setEnabled(False)
        self.btn_stop.setEnabled(True)

        self.worker = IndexWorker(
            folder, self.db_file,
            use_ocr     = self.chk_ocr.isChecked(),
            incremental = self.chk_incr.isChecked(),
            semantic    = self.chk_semantic.isChecked()
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.preview.connect(self._on_preview)
        self.worker.set_detail(self.btn_detail.isChecked())
        self.worker.start()

    def stop_index(self):
        if self.worker:
            self.worker.stop()

    def _on_progress(self, current, total, fname):
        pct = int(current / total * 100) if total else 0
        self.progress_bar.setValue(pct)
        self.lbl_progress.setText(f"{current}/{total}  ({pct}%)")
        self.lbl_current.setText(fname[:80])

    def _on_finished(self, added, skipped):
        self.btn_index.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setValue(100)

        # Đọc số chunks đã tạo để hiển thị
        chunk_count = 0
        if self.db_file:
            try:
                conn = sqlite3.connect(self.db_file)
                cur  = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM chunks")
                chunk_count = cur.fetchone()[0]
                conn.close()
            except Exception:
                pass

        self.statusBar().showMessage(
            f"Indexing complete.  Added: {added}  |  Skipped: {skipped}  |  "
            f"Total chunks: {chunk_count:,}")
        log = getattr(self.worker, 'skip_log', '') if self.worker else ''
        QMessageBox.information(self, "Done",
            f"Indexing complete.\n\n"
            f"  Files added   : {added}\n"
            f"  Files skipped : {skipped}\n"
            f"  Chunks created: {chunk_count:,}\n\n"
            f"Chunks giúp Cowork/Claude tìm kiếm chính xác hơn và tiết kiệm token."
            + (f"\n\nWhat was left out is listed in:\n{log}" if log else ""))

    def _on_error(self, msg):
        self.btn_index.setEnabled(True)
        self.btn_stop.setEnabled(False)
        QMessageBox.critical(self, "Error", msg)

    # ── SEARCH ───────────────────────────────────────────────────────────────
    def search_files(self):
        if not self.db_file:
            QMessageBox.warning(self, "Error", "No database open.")
            return
        query = self.search_input.text().strip()

        lot_text  = self.cmb_lot.currentText()
        lot_filt  = '' if lot_text.startswith("All") else lot_text

        disc_text = self.cmb_disc.currentText()
        disc_filt = '' if disc_text.startswith("All") else disc_text.split(' ')[0]

        scan_filt = ('', 'text', 'ocr', 'scanned')[self.cmb_scan.currentIndex()]

        try:
            conn = sqlite3.connect(self.db_file)
            rows = search_db(conn, query, lot_filt, disc_filt, scan_filt)
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Search Error", str(e))
            return

        self.lbl_results.setText(f"Results: {len(rows)}")
        self.table.setRowCount(len(rows))

        DISC_COLOR = {
            'E': '#E8F4FD', 'M': '#FFF3E0', 'I': '#F3E5F5',
            'P': '#E8F5E9', 'A': '#FFF9C4', 'C': '#FCE4EC',
            'F': '#E0F2F1', 'G': '#F5F5F5',
        }

        col_source = RESULT_COLUMNS.index("Source")
        col_pages = RESULT_COLUMNS.index("Pages")

        for r_idx, row in enumerate(rows):
            (name, path, ftype, lot, disc, sys_code, _doc_no, rev,
             is_scan, ocr, page_count, pages) = row
            source = doc_source.source_label(is_scan, ocr)
            tip = doc_source.source_tip(is_scan, ocr, page_count)
            colour = QColor(doc_source.source_colour(source))   # rows are always light here
            bg = QColor(DISC_COLOR.get(disc, '#FFFFFF'))
            vals = [name, lot or '', disc or '', sys_code or '', rev or '',
                    source, pages, ftype, path]
            for c_idx, val in enumerate(vals):
                item = QTableWidgetItem(val or '')
                item.setBackground(bg)
                if c_idx == col_source or (c_idx == 0 and
                                           source in ('OCR', 'Scanned', 'Scanned/OCR')):
                    item.setForeground(colour)
                    item.setToolTip(tip)
                if c_idx == col_pages and pages:
                    item.setToolTip(f"Search term found on page(s): {pages}")
                self.table.setItem(r_idx, c_idx, item)

    # ── OPEN FILE ────────────────────────────────────────────────────────────
    def open_file(self, item):
        row      = item.row()
        rel_path = self.table.item(row, COL_PATH).text()
        try:
            conn = sqlite3.connect(self.db_file)
            cur  = conn.cursor()
            cur.execute("SELECT path FROM files WHERE name='BASE_PATH'")
            bp_row = cur.fetchone()
            conn.close()
            if not bp_row:
                QMessageBox.warning(self, "Error", "Base path not found in DB.")
                return
            full = os.path.join(bp_row[0], rel_path)
            if os.path.exists(full):
                # Fix Windows MAX_PATH (260 ký tự) cho đường dẫn dài
                if len(full) > 259:
                    full = '\\\\?\\' + full.replace('/', '\\')
                os.startfile(full)
            else:
                QMessageBox.warning(self, "File Not Found",
                    f"File not found:\n{full}\n\nUse 'Change Base Path' if folder was moved.")
        except OSError as e:
            if getattr(e, 'winerror', None) == 3:
                self.statusBar().showMessage(f"Bỏ qua: đường dẫn quá dài hoặc không tìm thấy file.")
                return
            QMessageBox.critical(self, "Error", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── CHANGE BASE PATH ─────────────────────────────────────────────────────
    def change_path(self):
        if not self.db_file:
            QMessageBox.warning(self, "Error", "No database open.")
            return
        old = self.old_path_input.text().strip()
        new = self.new_path_input.text().strip()
        if not old or not new:
            QMessageBox.warning(self, "Error", "Enter both old and new paths.")
            return
        try:
            conn = sqlite3.connect(self.db_file)
            cur  = conn.cursor()
            cur.execute("SELECT id, path FROM files")
            rows = cur.fetchall()
            updated = 0
            for fid, path in rows:
                if path and path.startswith(old):
                    cur.execute("UPDATE files SET path=? WHERE id=?",
                                (path.replace(old, new, 1), fid))
                    updated += 1
            conn.commit()
            conn.close()
            QMessageBox.information(self, "Done", f"Updated {updated} paths.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(APP_STYLE)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
