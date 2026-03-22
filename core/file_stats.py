# core/file_stats.py
import json
import os
from datetime import datetime
from typing import Dict, List


def _load(path: str) -> Dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: Dict, path: str):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def record_open(file_path: str, stats_path: str):
    """Ghi nhận 1 lần mở file."""
    data = _load(stats_path)
    entry = data.get(file_path, {"count": 0, "history": []})
    entry["count"] += 1
    entry["last_open"] = datetime.now().strftime("%Y-%m-%d")
    entry["history"].append(datetime.now().strftime("%Y-%m-%d"))
    data[file_path] = entry
    _save(data, stats_path)


def query_stats(stats_path: str, year: int = None, month: int = None) -> List[Dict]:
    """
    Trả về danh sách dict đã lọc theo năm/tháng, sắp xếp count giảm dần.
    Mỗi dict: {file, name, count, last_open}
    """
    data = _load(stats_path)
    results = []
    for fp, entry in data.items():
        history = entry.get("history", [])
        if year or month:
            count = 0
            for d in history:
                try:
                    dt = datetime.strptime(d, "%Y-%m-%d")
                    if year and dt.year != year:
                        continue
                    if month and dt.month != month:
                        continue
                    count += 1
                except Exception:
                    pass
        else:
            count = entry.get("count", 0)

        if count == 0:
            continue
        results.append({
            "file":      fp,
            "name":      os.path.basename(fp),
            "count":     count,
            "last_open": entry.get("last_open", ""),
            "history":   history,
        })

    results.sort(key=lambda x: x["count"], reverse=True)
    return results
