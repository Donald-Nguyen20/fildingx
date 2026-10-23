"""core/doc_source.py -- how a search result from a Create DB database is shown:
where the file's indexed text came from, and the pages the search term is on.

Shared by the Create DB search (core/create_index_v3.py) and the DB Search tab
(ui/index_search_window.py), so both present a file the same way. Qt-free.

files.is_scanned is 1 when at least half of a PDF's pages are scans; files.ocr
counts the pages read by OCR. A database built before files.ocr existed has no
such column, and its OCR'd scans cannot be told from un-OCR'd ones -- those get
their own label rather than a confident wrong one.
"""

SOURCE_HELP = ("OCR = scan read by OCR  |  Text+OCR = text layer, scanned pages "
               "OCR'd  |  Text = text layer  |  Scanned = scanned, not OCR'd")

# One set per kind of results page: a colour picked against white is unreadable
# on the dark themes, whose result trees are dark (see ui/themes.light_page).
_COLOURS = {
    True:  {'OCR': '#B45309', 'Text+OCR': '#0E7490', 'Scanned': '#DC2626',
            'Scanned/OCR': '#B45309', 'Text': '#15803D'},
    False: {'OCR': '#FBBF24', 'Text+OCR': '#22D3EE', 'Scanned': '#F87171',
            'Scanned/OCR': '#FBBF24', 'Text': '#4ADE80'},
}


def ocr_column(conn, alias=''):
    """SQL selecting files.ocr, or NULL from a database built before it."""
    has = 'ocr' in {r[1] for r in conn.execute("PRAGMA table_info(files)")}
    return f"{alias}ocr" if has else "NULL"


def source_label(is_scanned, ocr):
    """'OCR' (a scan, read by OCR), 'Text+OCR' (text layer, some scanned pages
    OCR'd), 'Scanned' (scans, not OCR'd), 'Text', or 'Scanned/OCR' for a scan
    in a database that did not record OCR (ocr is None)."""
    if ocr is None:
        return 'Scanned/OCR' if is_scanned else 'Text'
    if ocr:
        return 'OCR' if is_scanned else 'Text+OCR'
    return 'Scanned' if is_scanned else 'Text'


def source_tip(is_scanned, ocr, page_count):
    """Tooltip spelling out the label, with page counts where they are known."""
    return {
        'OCR':         f"{ocr} of {page_count} page(s) read by OCR - may be imperfect",
        'Text+OCR':    f"Text layer, plus {ocr} of {page_count} scanned page(s) read by OCR",
        'Scanned':     "Scanned, not OCR'd - only the file name is searchable",
        'Scanned/OCR': "Scanned. This database was built before OCR was recorded - "
                       "rebuild it to tell OCR'd files from the rest",
        'Text':        "Text layer - exact",
    }[source_label(is_scanned, ocr)]


def source_colour(label, light=True):
    """Text colour for a label on a light (True) or dark results page."""
    return _COLOURS[bool(light)][label]


def page_text(pages):
    """{1, 2, 3, 7, 12} -> "1–3, 7, 12". Every page is listed: a cut-off list
    ("…, (25 pages)") hid exactly the pages someone was looking for."""
    runs = []
    for p in sorted(pages or ()):
        if runs and p == runs[-1][1] + 1:
            runs[-1][1] = p
        else:
            runs.append([p, p])
    return ", ".join(str(a) if a == b else f"{a}–{b}" for a, b in runs)


def page_set(text):
    """The inverse of page_text: "1–3, 7" -> {1, 2, 3, 7}."""
    pages = set()
    for part in (text or "").replace("-", "–").split(","):
        a, _, b = part.strip().partition("–")
        if a.isdigit():
            pages.update(range(int(a), int(b if b.isdigit() else a) + 1))
    return pages
