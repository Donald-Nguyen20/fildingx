"""db_query.py — Helper để Claude chạy SQL query read-only trên SQLite DB.

Usage:
    python db_query.py "<db_path>" "<sql>"
"""
import json
import sqlite3
import sys

# A SELECT written without a LIMIT can hand back the whole corpus: files.content
# alone holds 684 MB of extracted document text, and one row of it would fill
# any model's context on its own. The caps below are what the answer is allowed
# to carry. Truncating silently would be worse than not truncating at all --
# the fragment would be summarised as if it were the complete result -- so
# anything cut sets "truncated" and says what to do about it.
MAX_ROWS  = 200          # rows per answer
MAX_CHARS = 120_000      # total text per answer, roughly 30k tokens
MAX_CELL  = 4_000        # per cell; a chunk is ~1.2k, a files.content cell is unbounded


def main():
    # Document text comes out of the plant's own files, not out of this program,
    # and json.dumps is called with ensure_ascii=False. Roughly 40% of the
    # indexed chunks carry a character the Windows console codepage cannot
    # encode -- primes in dimensions, Greek letters in formulas, katakana in the
    # Toshiba manuals -- and each one would otherwise end the query with a
    # UnicodeEncodeError reported as though the database itself had failed.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if len(sys.argv) < 3:
        print("Usage: db_query.py <db_path> <sql>")
        sys.exit(1)

    db_path = sys.argv[1]
    sql     = sys.argv[2].strip()

    # Chỉ cho phép SELECT
    if not sql.upper().lstrip().startswith("SELECT"):
        print("ERROR: Chỉ cho phép câu lệnh SELECT.")
        sys.exit(1)

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur  = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in (cur.description or [])]

        # One row past the cap, so the answer can report that more exist
        # without reading them -- the same trick ui/index_search_window.py uses.
        raw  = cur.fetchmany(MAX_ROWS + 1)
        more = len(raw) > MAX_ROWS
        raw  = raw[:MAX_ROWS]

        rows, budget, cut_cells = [], MAX_CHARS, 0
        for row in raw:
            if budget <= 0:
                more = True
                break
            out = []
            for v in row:
                if isinstance(v, str) and len(v) > MAX_CELL:
                    v = v[:MAX_CELL] + f"\u2026 [+{len(v) - MAX_CELL} chars cut]"
                    cut_cells += 1
                out.append(v)
                budget -= len(v) if isinstance(v, str) else 8
            rows.append(out)

        payload = {"columns": cols, "rows": rows}
        if more or cut_cells:
            why = []
            if more:
                why.append(f"only the first {len(rows)} row(s) are shown")
            if cut_cells:
                why.append(f"{cut_cells} long cell(s) were cut at {MAX_CELL} chars")
            payload["truncated"] = True
            payload["note"] = ("; ".join(why) +
                               ". Narrow the query -- add WHERE, COUNT(*), "
                               "substr() or LIMIT -- rather than treating this "
                               "as the complete result.")
        print(json.dumps(payload, ensure_ascii=False))
        conn.close()
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
