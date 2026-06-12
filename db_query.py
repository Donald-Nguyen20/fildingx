"""db_query.py — Helper để Claude chạy SQL query read-only trên SQLite DB.

Usage:
    python db_query.py "<db_path>" "<sql>"
"""
import json
import sqlite3
import sys


def main():
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
        rows = cur.fetchall()
        cols = [d[0] for d in (cur.description or [])]
        print(json.dumps({"columns": cols, "rows": rows}, ensure_ascii=False, indent=2))
        conn.close()
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
