"""ocr_bench.py -- measure Create DB's OCR before and after a change.

    python ocr_bench.py --docs "<folder of PDFs>"
    python ocr_bench.py --docs "<folder>" --sheet "<P&ID.pdf>=VP1-C-L2-P-MAW-00002"
                        --register "<sqlite with kks_xref>" --dpi 600

Document pages: up to --n A4 and --n A3 pages that carry a text layer are
picked from --docs (the same pages every run: the choice is kept in
ocr_bench_set.json beside the app), rendered and OCR'd as Create DB does, and
scored by the share of their text-layer words read back.

Drawing sheets: each --sheet "pdf[:page]=DRAWING-NO" is OCR'd whole at --dpi as
"OCR drawings" does, and its full tags (system + equipment part) are counted;
with --register, against the tags a register's kks_xref table lists for that
drawing. A register lists both units' tags for a sheet drawn once for unit 1,
so tags it lists for unit 2 are reported apart -- they are not on the paper.

Prints one line per set, with the share of time the GPU was busy. Reads the
PDFs and the register only; writes nothing but ocr_bench_set.json.
"""
import argparse
import collections
import json
import os
import random
import re
import sqlite3
import subprocess
import sys
import threading
import time

import fitz

import paths
from core import kks, ocr_engine
import core.create_index_v3 as idx

fitz.TOOLS.mupdf_display_errors(False)
WORD = re.compile(r"[A-Za-z]{3,}")
SET_FILE = os.path.join(paths.APP_DIR, "ocr_bench_set.json")


def pick_pages(folder, n):
    """{'a4': [[pdf, page], ...], 'a3': [...]} -- text-layer pages, fixed seed."""
    saved = {}
    if os.path.exists(SET_FILE):
        saved = json.load(open(SET_FILE, encoding="utf-8"))
        if saved.get("folder") == folder and saved.get("n") == n:
            return saved
    pdfs = []
    for dp, _, fn in os.walk(folder):
        pdfs += [os.path.join(dp, f) for f in fn if f.lower().endswith(".pdf") and "~$" not in f]
    random.seed(21)
    random.shuffle(pdfs)
    a3, a4 = [], []
    for p in pdfs:
        if len(a3) >= n and len(a4) >= n:
            break
        try:
            doc = fitz.open(p)
        except Exception:
            continue
        for i in random.sample(range(len(doc)), min(2, len(doc))):
            page = doc[i]
            side = max(page.rect.width, page.rect.height)
            if len(page.get_text("text").strip()) < 600 or page.get_images():
                continue
            if side > 1100 and len(a3) < n:
                a3.append([p, i])
            elif 800 < side < 900 and len(a4) < n:
                a4.append([p, i])
    chosen = {"folder": folder, "n": n, "a4": a4, "a3": a3}
    with open(SET_FILE, "w", encoding="utf-8") as f:
        json.dump(chosen, f, ensure_ascii=False, indent=1)
    return chosen


class GpuBusy:
    """Share of nvidia-smi samples with the GPU busy, taken in the background."""

    def __init__(self):
        self.samples, self.stopped = [], False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stopped:
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu",
                                      "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=5).stdout.strip()
                if out.isdigit():
                    self.samples.append(int(out))
            except Exception:
                return
            time.sleep(0.3)

    def stop(self):
        self.stopped = True
        self.thread.join()
        return sum(self.samples) / len(self.samples) if self.samples else None


def score_pages(pages):
    hit = total = 0
    start = time.time()
    for p, i in pages:
        page = fitz.open(p)[i]
        got = kks.fix_ocr_text(ocr_engine.ocr_image_paddle(idx._page_image(page, 200)))
        g = collections.Counter(w.lower() for w in WORD.findall(got))
        t = collections.Counter(w.lower() for w in WORD.findall(page.get_text("text")))
        hit += sum(min(c, g[w]) for w, c in t.items())
        total += sum(t.values())
    return hit / max(total, 1), (time.time() - start) / max(len(pages), 1)


def register_tags(register, drawing):
    con = sqlite3.connect(f"file:{register}?mode=ro", uri=True)
    return {kks.norm(r[0])[:12] for r in con.execute(
        "SELECT DISTINCT kks_full FROM kks_xref WHERE dwg_base = ?", (drawing,))}


def score_sheet(spec, dpi, register):
    target, _, drawing = spec.partition("=")
    pdf, _, page = target.rpartition(":") if re.search(r":\d+$", target) else (target, "", "1")
    idx._scan_dpi = lambda _page, d: d          # the bench reads every sheet at --dpi
    start = time.time()
    text = idx._ocr_sheets(pdf, {int(page): "scan"}, dpi).get(int(page), "")
    seconds = time.time() - start
    found = {kks.norm(m.group(0))[:12] for m in kks.KKS_RE.finditer(text)
             if len(kks.norm(m.group(0))) >= 12}
    line = f"{os.path.basename(pdf)[:40]} p{page}: {len(found)} full tags, {seconds:.1f}s"
    if register and drawing:
        listed = register_tags(register, drawing)
        printed = {t for t in listed if not t.startswith("20")}
        line += (f" | register: {len(found & printed)}/{len(printed)} of its unit-1/common tags"
                 f" ({len(listed) - len(printed)} unit-2 tags not counted)")
    return line


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--docs", help="folder to pick text-layer pages from")
    ap.add_argument("--n", type=int, default=10, help="pages of each size (default 10)")
    ap.add_argument("--sheet", action="append", default=[], help='"pdf[:page]=DRAWING-NO"')
    ap.add_argument("--register", help="sqlite database with a kks_xref table")
    ap.add_argument("--dpi", type=int, default=600)
    a = ap.parse_args()
    if not a.docs and not a.sheet:
        ap.error("give --docs and/or --sheet")
    print("OCR engine:", ocr_engine.advice()[0], "| GPU:", ocr_engine.gpu_available())
    from PIL import Image
    ocr_engine.ocr_image_paddle(Image.new("RGB", (300, 300), "white"))      # warm-up
    gpu = GpuBusy()
    if a.docs:
        chosen = pick_pages(a.docs, a.n)
        for size in ("a4", "a3"):
            if chosen[size]:
                share, secs = score_pages(chosen[size])
                print(f"{size.upper()} pages ({len(chosen[size])}): {share:.1%} of words read,"
                      f" {secs:.2f}s a page")
    for spec in a.sheet:
        print(score_sheet(spec, a.dpi, a.register))
    busy = gpu.stop()
    if busy is not None:
        print(f"GPU busy {busy:.0f}% of the time")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
