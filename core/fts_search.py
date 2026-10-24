"""
core/fts_search.py -- the keyword search that DB Search and the Create DB
window both run on a Create DB database. Qt-free.

A query of several words is looked for as a phrase -- the words together and
in that order, the last one possibly longer ("emergency stop" also finds
"Emergency stops") -- and then as every word somewhere in the file (see
all_words for what counts as one). Measured on
the commissioning set (133 files), "boiler feed pump" is in 1 file as a phrase
and in 23 by its words, "turbine trip" in 3 and 32: most of the second kind
only happen to hold the words. Phrase hits come first and the rest are marked
loose, so a screen can show them apart rather than drop them.

The full-text index is used rather than LIKE on the text. It finds a phrase
that a line break, a dash or a double space splits ("EMERGENCY\\nSTOP" on an
OCR page, which LIKE missed), and answers in about a millisecond where LIKE
reads every file's text (0.01-0.08 s on those 133 files, seconds on a whole
library). LIKE did catch words that RapidOCR's bundled Chinese recogniser ran
together ("SteamandDrainSystem"); the English model rarely does that, and a
database OCR'd before it is better rebuilt.
"""
import re
import sqlite3

# What FTS5's unicode61 tokenizer keeps as one token: letters and digits.
_WORD = re.compile(r'[^\W_]+')


def words(query: str) -> list:
    return _WORD.findall(query or '')


def phrase(query: str) -> str:
    """FTS5 query for the words as a phrase, the last one a prefix; '' for none."""
    w = words(query)
    return f'"{" ".join(w)}"*' if w else ''


def all_words(query: str) -> str:
    """FTS5 query for every space-separated term anywhere, each a prefix -- ''
    for a query of one term, where it would find nothing the phrase does not.

    A term holding punctuation stays one phrase: "VP1-C-L2 pump" wants
    "VP1 C L2" together and "pump" anywhere. Split into its pieces, "VP1-C-L2"
    alone added 53 files on the commissioning set, found by any word that
    starts with "c"."""
    terms = [w for w in (words(t) for t in (query or '').split()) if w]
    return ' '.join(f'"{" ".join(t)}"*' for t in terms) if len(terms) > 1 else ''


def conditions(query: str, globs: list, f: str = 'f') -> tuple:
    """(strict, loose, params): SQL conditions on a files row aliased f, with
    named parameters.

    strict holds for a file whose name contains the query, whose text holds it
    as a phrase, or that carries a KKS tag the kks.search_globs patterns globs
    stand for; loose for one that has every word, not together ('0' for a
    one-word query). Select on (strict OR loose) and order by NOT (strict) to
    put the phrase hits first.
    """
    params = {'like': f'%{query.strip()}%'}
    strict = [f"{f}.name LIKE :like"]
    if phrase(query):
        strict.append(f"{f}.id IN (SELECT rowid FROM files_fts WHERE files_fts MATCH :phrase)")
        params['phrase'] = phrase(query)
    if globs:
        strict.append(f"{f}.id IN (SELECT file_id FROM kks_tags WHERE "
                      + " OR ".join(f"tag_norm GLOB :g{i}" for i in range(len(globs))) + ")")
        params.update({f'g{i}': g for i, g in enumerate(globs)})
    loose = '0'
    if all_words(query):
        loose = f"{f}.id IN (SELECT rowid FROM files_fts WHERE files_fts MATCH :words)"
        params['words'] = all_words(query)
    return '(' + ' OR '.join(strict) + ')', loose, params


def match_pages(conn, file_ids, fts_query: str) -> dict:
    """file_id -> set of the pages whose chunks match fts_query.

    A chunk is one page, except short pages merged with a neighbour, so a hit
    in such a chunk reports its small page range. An older database without
    chunks or chunk page columns simply yields no pages.

    Every chunk of a section carries the section heading, but the heading is
    printed only where the section starts, so its words count for the first
    chunk it heads; further chunks need the match in their own text. Without
    that a word in a heading reported every page of the section.
    """
    found = {}
    if not fts_query or not file_ids:
        return found
    ids = list(file_ids)
    for i in range(0, len(ids), 500):          # stay under SQLite's variable limit
        part = ids[i:i + 500]
        try:
            rows = conn.execute(
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


def hit_pages(conn, strict_ids, loose_ids, query: str, globs: list) -> dict:
    """file_id -> set of pages for a search's hits: where the phrase is for a
    strict hit, where a chunk holds every word for a loose one, and where a KKS
    tag the query stands for was read, for either."""
    pages = match_pages(conn, strict_ids, phrase(query))
    for fid, more in match_pages(conn, loose_ids, all_words(query)).items():
        pages.setdefault(fid, set()).update(more)
    ids = set(strict_ids) | set(loose_ids)
    if globs and ids:
        for fid, page in conn.execute(
                "SELECT file_id, page FROM kks_tags WHERE page IS NOT NULL AND ("
                + " OR ".join(["tag_norm GLOB ?"] * len(globs)) + ")", globs):
            if fid in ids:
                pages.setdefault(fid, set()).add(page)
    return pages
