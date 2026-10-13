"""ui/claude_assistant/trend_import.py — read trend/log files into the Trend
Data box.

Qt-free on purpose: paths in, one text block out, so the reader can be
exercised from a plain script.

The prompt budget is what shapes everything here. copilot.build_trend_block
hands the model at most TREND_MAX_CHARS of data, and a DCS export is routinely
twenty to eighty times that: one 8-hour shift sampled every 10 seconds is 2,880
rows per tag, where the budget holds about 170. Letting build_trend_block cut at
its character limit would show the model the quiet hours before the fault and
drop the fault itself, so the rows are thinned across the whole span instead,
the extremes of every numeric column are kept on purpose, and the header says
which rows were dropped -- a model told nothing about the sampling would read
consecutive rows as consecutive samples and get every rate of change wrong.
"""
from __future__ import annotations

import csv
import io
import math
import os
import re
from dataclasses import dataclass
from typing import Sequence

from ui.claude_assistant.copilot import TREND_MAX_CHARS

# Delimiters a plant export actually uses: comma, the semicolon Excel writes
# under a European locale, tab from a copied grid, and the pipe some historians
# emit.
_DELIMS = ",;\t|"

# A trend export is text; anything this size is the wrong file, and reading it
# would stall the UI thread before the first row is parsed. The second cap is
# on the whole selection, because every file is parsed before any is thinned.
_MAX_BYTES = 64 * 1024 * 1024
_MAX_TOTAL_BYTES = 192 * 1024 * 1024

# Columns scanned for extremes. Enough for time + a handful of tags, and a cap
# so a 200-column historian dump does not turn this into a full table scan.
_MAX_PEAK_COLS = 6

_NUM_RE = re.compile(r"[+-]?\d+(?:[.,]\d+)?")


@dataclass(frozen=True)
class FileReport:
    """What one file contributed."""

    name: str
    rows_read: int
    rows_kept: int
    step: int
    encoding: str
    delimiter: str

    @property
    def thinned(self) -> bool:
        return self.step > 1


@dataclass(frozen=True)
class ImportReport:
    """What the whole import contributed, and what it could not read."""

    files: tuple[FileReport, ...] = ()
    failures: tuple[tuple[str, str], ...] = ()
    chars: int = 0
    budget: int = 0

    def summary(self) -> str:
        """One line for the dialog, in the app's UI language."""
        if not self.files:
            return ""
        read = sum(f.rows_read for f in self.files)
        kept = sum(f.rows_kept for f in self.files)
        part = ["%d file" % len(self.files) + ("s" if len(self.files) > 1 else "")]
        if kept < read:
            steps = sorted({f.step for f in self.files if f.thinned})
            how = ("1 row in %d" % steps[0] if len(steps) == 1
                   else "1 row in %d–%d" % (steps[0], steps[-1]))
            part.append("%s rows -> %s kept (%s, peaks kept)"
                        % (f"{read:,}", f"{kept:,}", how))
        else:
            part.append("%s rows, all kept" % f"{read:,}")
        part.append("%s of %s chars" % (f"{self.chars:,}", f"{self.budget:,}"))
        return "  ·  ".join(part)

    def failure_text(self) -> str:
        """Why a file was skipped, one per line."""
        return "\n".join("%s — %s" % (n, why) for n, why in self.failures)


def _decode(raw: bytes) -> tuple[str, str]:
    """Text plus the encoding it came out as. Never raises.

    A UTF-16 export carries a BOM, so it is recognised rather than guessed.
    latin-1 is last because it decodes every byte sequence: the tags and
    timestamps that matter here are ASCII, and a mangled unit is better than a
    refused file.
    """
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return raw.decode("utf-16"), "utf-16"
        except ValueError:
            pass
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc), enc
        except ValueError:
            continue
    return raw.decode("latin-1", "replace"), "latin-1"


def _sniff(sample: str) -> str:
    """The column separator. Falls back to counting when Sniffer gives up."""
    try:
        return csv.Sniffer().sniff(sample, delimiters=_DELIMS).delimiter
    except csv.Error:
        pass
    head = sample.splitlines()[:5]
    counts = {d: sum(ln.count(d) for ln in head) for d in _DELIMS}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] else ","


def _read_rows(text: str, delim: str) -> list[list[str]]:
    """Non-empty rows, cells stripped. Blank lines and padding rows go."""
    rows = []
    for row in csv.reader(io.StringIO(text), delimiter=delim):
        cells = [c.strip() for c in row]
        if any(cells):
            rows.append(cells)
    return rows


def _line(row: Sequence[str]) -> str:
    """One row as the box shows it. Tab is the cheapest separator per char."""
    return "\t".join(row)


def _num(cell: str) -> float | None:
    """The leading number in a cell, or None. Handles "4,2" and "4.28 mm/s"."""
    m = _NUM_RE.search(cell.replace(" ", ""))
    if not m:
        return None
    s = m.group(0)
    # Both separators present means the comma groups thousands; a lone comma
    # under a European locale is the decimal point.
    s = s.replace(",", "") if "." in s and "," in s else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _peaks(body: list[list[str]]) -> set[int]:
    """Rows holding the highest and lowest value of each numeric column.

    Thinning a trend uniformly is what keeps the whole span visible, but it is
    also what loses the spike, and the spike is the reason anybody opens this
    dialog -- the diagnosis prompt asks the model for the peak value by name.
    """
    if len(body) < 3:
        return set()
    width = min(max(len(r) for r in body), _MAX_PEAK_COLS)
    found: set[int] = set()
    for c in range(width):
        vals = [(i, _num(r[c])) for i, r in enumerate(body) if c < len(r)]
        vals = [(i, v) for i, v in vals if v is not None]
        if len(vals) < 3:
            continue
        found.add(min(vals, key=lambda t: t[1])[0])
        found.add(max(vals, key=lambda t: t[1])[0])
    return found


def _thin(body: list[list[str]], budget: int) -> tuple[list[int], int]:
    """Indices of the rows that fit in budget, and the step they were taken at.

    Whole rows only: half a row of numbers reads as data and is not.
    """
    lines = [_line(r) for r in body]
    cost = lambda idx: sum(len(lines[i]) + 1 for i in idx)       # noqa: E731
    if cost(range(len(body))) <= budget:
        return list(range(len(body))), 1

    peaks = _peaks(body)
    step = max(2, math.ceil(cost(range(len(body))) / max(budget, 1)))
    while step < len(body):
        keep = set(range(0, len(body), step)) | {len(body) - 1} | peaks
        if cost(keep) <= budget:
            return sorted(keep), step
        step += max(1, step // 4)
    return ([0, len(body) - 1] if len(body) > 1 else [0]), max(1, len(body))


def _note(name: str, rows: int, step: int) -> str:
    """The comment line above a file's rows.

    It has to say that rows were dropped: a model shown every tenth sample with
    no warning reads consecutive lines as consecutive samples, and every rate of
    change it then reports is out by that factor.
    """
    note = "%s rows" % f"{rows:,}"
    if step > 1:
        note += (", sampled down to 1 row in %d plus the highest/lowest values"
                 " — rows in between were dropped, so consecutive lines are"
                 " NOT consecutive samples" % step)
    return "# %s — %s" % (os.path.basename(name), note)


def _block(name: str, rows: list[list[str]], budget: int
           ) -> tuple[str, FileReport]:
    """One file's text block: a comment line, the column row, then the data."""
    header, body = rows[0], rows[1:]
    head_line = _line(header)
    # Reserve the two fixed lines before thinning the body, so the assembled
    # block cannot come out over budget. The note is measured at its longest
    # form because its real length is not known until the step is chosen.
    fixed = len(head_line) + 1 + len(_note(name, len(body), 10 ** 9)) + 1
    picked, step = _thin(body, max(budget - fixed, 0)) if body else ([], 1)

    out = [_note(name, len(body), step), head_line]
    out.extend(_line(body[i]) for i in picked)
    return "\n".join(out), FileReport(
        name=os.path.basename(name), rows_read=len(body),
        rows_kept=len(picked), step=step, encoding="", delimiter="",
    )


def _parse(path: str) -> tuple[list[list[str]], str, str]:
    """Rows, encoding and delimiter for one file. Raises ValueError if unusable."""
    size = os.path.getsize(path)
    if size > _MAX_BYTES:
        raise ValueError("file is %.0f MB — too large to be a trend export"
                         % (size / 1048576))
    with open(path, "rb") as fh:
        raw = fh.read()
    if not raw.strip():
        raise ValueError("file is empty")
    text, enc = _decode(raw)
    delim = _sniff(text[:4096])
    rows = _read_rows(text, delim)
    if not rows:
        raise ValueError("no data rows found")
    return rows, enc, delim


def read_files(file_paths: Sequence[str], budget: int = TREND_MAX_CHARS
               ) -> tuple[str, ImportReport]:
    """Read trend files into one text block that fits budget characters.

    Files are parsed first, then filled smallest-first: a short file takes only
    what it needs and everything it leaves goes to the long ones, so importing
    a 3-row note alongside a full shift does not cost the shift a quarter of
    its rows. Blocks come out in the order the files were given.

    A file that cannot be read is reported rather than raising -- one bad
    export among five should not lose the other four.
    """
    budget = max(0, int(budget))
    failures: list[tuple[str, str]] = []
    parsed: list[tuple[int, str, list[list[str]], str, str]] = []
    bytes_read = 0

    for idx, path in enumerate(file_paths):
        name = os.path.basename(path) or path
        if bytes_read > _MAX_TOTAL_BYTES:
            failures.append((name, "too much data selected at once"))
            continue
        try:
            rows, enc, delim = _parse(path)
        except OSError as exc:
            failures.append((name, exc.strerror or str(exc)))
            continue
        except ValueError as exc:
            failures.append((name, str(exc)))
            continue
        bytes_read += sum(len(c) for r in rows for c in r)
        parsed.append((idx, path, rows, enc, delim))

    blocks: dict[int, str] = {}
    reports: dict[int, FileReport] = {}
    left = budget
    # Smallest first, so the share handed to each file is what is genuinely
    # left over rather than an equal slice taken before anyone has spent.
    order = sorted(parsed, key=lambda p: sum(len(c) + 1 for r in p[2] for c in r))

    for k, (idx, path, rows, enc, delim) in enumerate(order):
        remaining = len(order) - k
        share = left if remaining == 1 else max(0, left // remaining)
        if share < 80:
            failures.append((os.path.basename(path),
                             "no room left in the prompt budget"))
            continue
        block, rep = _block(path, rows, share)
        blocks[idx] = block
        reports[idx] = FileReport(rep.name, rep.rows_read, rep.rows_kept,
                                  rep.step, enc, delim)
        left = max(0, left - len(block) - 2)

    out = "\n\n".join(blocks[i] for i in sorted(blocks))
    # Last guard: trim to the final whole line if the assembled blocks still
    # run over, so nothing downstream has to cut a row in half.
    if len(out) > budget:
        out = out[:budget].rsplit("\n", 1)[0]
    return out, ImportReport(tuple(reports[i] for i in sorted(reports)),
                             tuple(failures), len(out), budget)
