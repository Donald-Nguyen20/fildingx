"""
core/hit_preview.py -- where a search hit is on its page, as a picture.

When a result is selected, DB Search shows the spot beside the list: the part
of the page around the KKS tag or the phrase, the hit boxed in red. Measured on
an A1 P&ID, a 200-dpi crop renders in under 0.04 s, so it can follow the
selection. Qt-free: locate() finds the spots and render() returns RGB bytes,
which the tab turns into an image.

A spot comes from one of two places. A tag on a page that PaddleOCR read --
a drawing sheet, a scan -- is in the tag_boxes table Create DB writes (a
database built before it has none). A tag or a phrase on a text-layer page is
found in the PDF's own words at the moment the result is selected, so it needs
no rebuild. Anything else -- a phrase on an OCR'd page, a semantic match --
shows its page whole, unmarked.
"""
import fnmatch
import os
import sqlite3
import unicodedata
from typing import NamedTuple

try:
    from core import doc_source, fts_search, kks
except ImportError:                  # run as a script from inside core/
    import doc_source, fts_search, kks

PDF = ('.pdf',)
IMAGES = ('.jpg', '.jpeg', '.png', '.tif', '.tiff')

PREVIEW_DPI = 200      # a crop; a tag's letters are about 25 px tall at this
CONTEXT = (150, 100)   # pt of page shown either side of a hit, across and down
WHOLE_MAX_PX = 1600    # long side of a whole-page view
SCAN_PAGES_MAX = 40    # text-layer pages read looking for the keyword
RECTS_MAX = 60         # boxes drawn on one page, for a common word
MARK = (220, 38, 38)


class Spot(NamedTuple):
    page: int          # 1-based
    rects: tuple       # ((x0, y0, x1, y1), ...) as fractions of the page as rendered
    marked: bool       # False: the page is shown whole, the hit not pinned on it


def _fold(text: str) -> str:
    """Lower case without accents, as the FTS index compares words."""
    text = unicodedata.normalize('NFKD', text.casefold())
    return ''.join(c for c in text if not unicodedata.combining(c))


def _union(rects):
    return (min(r[0] for r in rects), min(r[1] for r in rects),
            max(r[2] for r in rects), max(r[3] for r in rects))


def _covers(a, b) -> bool:
    """True when rectangle b lies mostly inside a."""
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area = max((b[2] - b[0]) * (b[3] - b[1]), 1e-12)
    return w * h / area > 0.6


def _box_spots(conn, file_id: int, globs: list) -> list:
    """Spots for a KKS tag from tag_boxes: one per place, a system label inside
    a full tag's box folded into it."""
    if not globs or not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'tag_boxes'").fetchone():
        return []
    rows = conn.execute(
        "SELECT page, x0, y0, x1, y1 FROM tag_boxes WHERE file_id = ? AND ("
        + " OR ".join(["tag_norm GLOB ?"] * len(globs)) + ") ORDER BY page, y0, x0",
        (file_id, *globs)).fetchall()
    kept = []
    # Largest first, so a full tag's box swallows the system label inside it.
    for page, *r in sorted(rows, key=lambda r: -(r[3] - r[1]) * (r[4] - r[2])):
        if not any(p == page and _covers(k, r) for p, k in kept):
            kept.append((page, tuple(r)))
    kept.sort(key=lambda s: (s[0], s[1][1], s[1][0]))
    return [Spot(page, (r,), True) for page, r in kept]


def _page_words(page):
    """The page's words in reading order: (rect as fractions, folded tokens,
    line key). Text coordinates are of the unrotated page; the rotation matrix
    puts them where the rendered page shows them."""
    import fitz
    mat, w, h = page.rotation_matrix, page.rect.width, page.rect.height
    out = []
    for x0, y0, x1, y1, word, block, line, _n in page.get_text('words'):
        r = fitz.Rect(x0, y0, x1, y1) * mat
        out.append(((r.x0 / w, r.y0 / h, r.x1 / w, r.y1 / h),
                    [_fold(t) for t in fts_search.words(word)], (block, line), word))
    return out


def _by_line(words, idx) -> tuple:
    """The rectangles of words[idx], one per line they run over."""
    lines = {}
    for i in idx:
        lines.setdefault(words[i][2], []).append(words[i][0])
    return tuple(_union(rs) for rs in lines.values())


def _find_terms(words, terms) -> list:
    """For each occurrence of a term -- a run of tokens, the last a prefix --
    the indexes of the words it covers."""
    stream = [(i, t) for i, w in enumerate(words) for t in w[1]]
    found = []
    for term in terms:
        n = len(term)
        for s in range(len(stream) - n + 1):
            toks = [stream[s + k][1] for k in range(n)]
            if toks[:-1] == term[:-1] and toks[-1].startswith(term[-1]):
                found.append(sorted({stream[s + k][0] for k in range(n)}))
    return found


def _tag_hits(words, globs) -> list:
    """Word indexes of every KKS tag on the page that globs stand for, read
    line by line however the tag is spaced or misread."""
    found, lines = [], {}
    for i, w in enumerate(words):
        lines.setdefault(w[2], []).append(i)
    for idx in lines.values():
        text, starts = '', []
        for i in idx:
            starts.append(len(text) + (1 if text else 0))
            text += (' ' if text else '') + words[i][3]
        fixed = kks.fix_ocr_text(text)
        scan = fixed if len(fixed) == len(text) else text
        for m in kks.KKS_RE.finditer(scan):
            if any(fnmatch.fnmatchcase(kks.norm(m.group(0)), g) for g in globs):
                found.append([i for i, s in zip(idx, starts)
                              if s < m.end() and s + len(words[i][3]) > m.start()])
    return found


def _text_spots(path: str, query: str, globs: list, loose: bool, pages: list) -> list:
    """Spots read from a PDF's text layer on the given pages: one per
    occurrence of the tag or phrase; for a loose hit, one per page with every
    term marked."""
    import fitz
    terms = []
    if loose:
        terms = [[_fold(t) for t in fts_search.words(part)] for part in query.split()]
    elif not globs:
        terms = [[_fold(t) for t in fts_search.words(query)]]
    terms = [t for t in terms if t]
    if not terms and not globs:
        return []
    spots = []
    with fitz.open(path) as pdf:
        for no in pages[:SCAN_PAGES_MAX]:
            if not 1 <= no <= len(pdf):
                continue
            words = _page_words(pdf[no - 1])
            hits = _tag_hits(words, globs) if globs else _find_terms(words, terms)
            if loose and hits:
                rects = [r for idx in hits for r in _by_line(words, idx)][:RECTS_MAX]
                spots.append(Spot(no, tuple(rects), True))
            else:
                spots += [Spot(no, _by_line(words, idx), True) for idx in hits[:RECTS_MAX]]
    return spots


def locate(db_path: str, abs_path: str, rel_path: str, query: str,
           pages_text: str, loose: bool = False) -> list:
    """The spots to show for one search hit, in page order -- never empty for
    a file that can be shown: with nothing pinned, its first page with the
    keyword (or page 1) comes back whole. [] for a type with no preview."""
    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in PDF + IMAGES:
        return []
    globs = kks.search_globs(query)
    pages = sorted(doc_source.page_set(pages_text))
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT id FROM files WHERE path = ?", (rel_path,)).fetchone()
        spots = _box_spots(conn, row[0], globs) if row else []
    finally:
        conn.close()
    if ext in PDF:
        seen = {s.page for s in spots}
        # A tag read by OCR is already placed; its page's text layer may hold it too.
        spots += _text_spots(abs_path, query, globs, loose,
                             [p for p in pages if p not in seen])
        spots.sort(key=lambda s: s.page)
    return spots or [Spot(pages[0] if pages else 1, (), False)]


def _draw(img, rects, to_px):
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    for r in rects:
        x0, y0, x1, y1 = to_px(r)
        d.rectangle([x0 - 5, y0 - 5, x1 + 5, y1 + 5], outline=MARK, width=3)


def render(abs_path: str, spot: Spot, whole: bool = False) -> tuple:
    """(rgb bytes, width, height) of the spot: the page around its first box,
    every box on it drawn in red -- or the whole page, for whole=True or a spot
    with nothing pinned."""
    from PIL import Image
    ext = os.path.splitext(abs_path)[1].lower()
    if ext in PDF:
        import fitz
        with fitz.open(abs_path) as pdf:
            page = pdf[min(max(spot.page, 1), len(pdf)) - 1]
            R = page.rect
            pts = [(r[0] * R.width, r[1] * R.height, r[2] * R.width, r[3] * R.height)
                   for r in spot.rects]
            if whole or not pts:
                clip = fitz.Rect(R)
            else:
                x0, y0, x1, y1 = pts[0]
                clip = fitz.Rect(x0 - CONTEXT[0], y0 - CONTEXT[1],
                                 x1 + CONTEXT[0], y1 + CONTEXT[1]) & R
            zoom = min(PREVIEW_DPI / 72, WHOLE_MAX_PX / max(clip.width, clip.height, 1))
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
            img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            _draw(img, pts, lambda r: ((r[0] - clip.x0) * zoom, (r[1] - clip.y0) * zoom,
                                       (r[2] - clip.x0) * zoom, (r[3] - clip.y0) * zoom))
    else:
        with Image.open(abs_path) as src:
            try:
                src.seek(max(spot.page, 1) - 1)
            except EOFError:
                src.seek(0)
            dpi = float((src.info.get('dpi') or (200, 200))[0] or 200)
            page = src.convert('RGB')
        W, H = page.size
        px = [(r[0] * W, r[1] * H, r[2] * W, r[3] * H) for r in spot.rects]
        if whole or not px:
            left, top = 0, 0
        else:
            cx, cy = CONTEXT[0] * dpi / 72, CONTEXT[1] * dpi / 72
            x0, y0, x1, y1 = px[0]
            left, top = max(0, int(x0 - cx)), max(0, int(y0 - cy))
            page = page.crop((left, top, min(W, int(x1 + cx)), min(H, int(y1 + cy))))
        _draw(page, px, lambda r: (r[0] - left, r[1] - top, r[2] - left, r[3] - top))
        scale = min(1.0, WHOLE_MAX_PX / max(page.size))
        img = page.resize((max(1, int(page.width * scale)), max(1, int(page.height * scale))),
                          Image.LANCZOS) if scale < 1 else page
    return img.tobytes(), img.width, img.height
