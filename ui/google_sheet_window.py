"""
ui/google_sheet_window.py — So sánh nội dung 2 tab trong Google Sheet.

Fetch dữ liệu:
  - Không cần API key: dùng gviz/tq CSV (hoạt động với "Anyone with link").
  - Có API key: dùng Sheets API v4 (load tab names tự động).

Load tab names tự động:
  - Có API key → Sheets API v4 → auto-fill 2 ô tên tab.
  - Không có API key → user gõ tên tab thủ công (vẫn fetch được).
"""
import csv
import io
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QLineEdit, QTextEdit, QLabel,
    QGroupBox, QMessageBox,
)

from ui import themes
import paths


_CONFIG_FILE = paths.GSHEET_CONFIG_FILE


# ── Helpers ───────────────────────────────────────────────────────────────────

def show_google_sheet_window(parent) -> None:
    _GoogleSheetWindow(parent).exec()


def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_config(data: dict) -> None:
    try:
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _extract_sheet_id(url_or_id: str) -> str:
    if "spreadsheets/d/" in url_or_id:
        part = url_or_id.split("spreadsheets/d/")[1]
        return part.split("/")[0].split("?")[0]
    return url_or_id.strip()


def _get_tabs(spreadsheet_id: str) -> list[str]:
    """Tải XLSX và parse workbook.xml để lấy tên tabs — không cần API key."""
    url = (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        f"/export?format=xlsx"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        with z.open("xl/workbook.xml") as f:
            root = ET.parse(f).getroot()
    sheets_el = root.find(f"{{{ns}}}sheets")
    if sheets_el is None:
        return []
    return [s.get("name", "") for s in sheets_el.findall(f"{{{ns}}}sheet")]


def _fetch_rows(spreadsheet_id: str, tab_name: str) -> list[list[str]]:
    """Fetch dữ liệu tab qua gviz/tq CSV — không cần API key."""
    name = urllib.parse.quote(tab_name)
    url = (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        f"/gviz/tq?tqx=out:csv&sheet={name}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        content = resp.read().decode("utf-8-sig")
    return list(csv.reader(io.StringIO(content)))


# ── Workers ───────────────────────────────────────────────────────────────────

class _TabLoader(QThread):
    done   = Signal(list)
    failed = Signal(str)

    def __init__(self, sheet_id: str):
        super().__init__()
        self._sheet_id = sheet_id

    def run(self):
        try:
            self.done.emit(_get_tabs(self._sheet_id))
        except Exception as e:
            self.failed.emit(str(e))



# ── Auto-compare helpers ─────────────────────────────────────────────────────
import re as _re

_WR_RE     = _re.compile(r'WR[:\s]+(\d+)', _re.IGNORECASE)
_STATUS_RE = _re.compile(r'Status:\s*([^;]*)', _re.IGNORECASE)
_DEPT_RE   = _re.compile(r'Responsible Dept:\s*([^;]*)', _re.IGNORECASE)

_KNOWN_SECTIONS = [
    ("reliability_u1", ["RELIABILITY MAIN EQUIPMENT CONDITION, U1"]),
    ("nonroutine_u1",  ["NON-ROUNTINE  ACTIVITY_U1", "NON-ROUNTINE ACTIVITY_U1",
                        "NON-ROUTINE ACTIVITY_U1"]),
    ("concerns_u1",    ["CONCERNS_U1"]),
    ("ptw_u1",         ["PTW_U1"]),
    ("handover_u1",    ["HANDOVER_U1"]),
    ("reliability_u2", ["RELIABILITY MAIN EQUIPMENT CONDITION, U2"]),
    ("nonroutine_u2",  ["NON-ROUNTINE ACTIVITY_U2", "NON-ROUTINE ACTIVITY_U2"]),
    ("concerns_u2",    ["CONCERNS_U2"]),
    ("ptw_u2",         ["PTW_U2"]),
    ("handover_u2",    ["HANDOVER_U2"]),
]

_LABELS = {
    "reliability_u1": "RELIABILITY MAIN EQUIPMENT — U1",
    "reliability_u2": "RELIABILITY MAIN EQUIPMENT — U2",
    "nonroutine_u1":  "NON-ROUTINE ACTIVITY — U1",
    "nonroutine_u2":  "NON-ROUTINE ACTIVITY — U2",
    "concerns_u1":    "CONCERNS — U1",
    "concerns_u2":    "CONCERNS — U2",
    "ptw_u1":         "PERMIT TO WORK — U1",
    "ptw_u2":         "PERMIT TO WORK — U2",
    "handover_u1":    "HANDOVER — U1",
    "handover_u2":    "HANDOVER — U2",
}


def _find_row_idx(rows: list, keywords: list) -> int:
    for i, row in enumerate(rows):
        flat = " ".join(str(c).strip() for c in row)
        for kw in keywords:
            if kw.lower() in flat.lower():
                return i
    return -1


def _parse_sections(rows: list) -> dict:
    positions = []
    for key, kws in _KNOWN_SECTIONS:
        idx = _find_row_idx(rows, kws)
        if idx >= 0:
            positions.append((idx, key))
    positions.sort()
    result = {}
    for i, (start, key) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(rows)
        result[key] = rows[start:end]
    return result


def _parse_reliability(section_rows: list) -> dict:
    entries = {}
    for row in section_rows[1:]:
        if str(row[0]).strip():          # col A non-empty = BLR/TBN bắt đầu
            break
        desc   = str(row[1]).strip() if len(row) > 1 else ""
        wr_col = str(row[8]).strip() if len(row) > 8 else ""
        if not desc:
            continue
        m_wr   = _WR_RE.search(wr_col)
        m_st   = _STATUS_RE.search(wr_col)
        m_dept = _DEPT_RE.search(wr_col)
        wr_num = m_wr.group(1)   if m_wr   else None
        status = m_st.group(1).strip()   if m_st   else ""
        dept   = m_dept.group(1).strip() if m_dept else ""
        key    = wr_num if wr_num else desc[:60]
        entries[key] = {"wr": wr_num, "desc": desc, "status": status, "dept": dept}
    return entries


def _diff_reliability(a: dict, b: dict) -> list:
    def _k(x): return int(x) if str(x).isdigit() else 0
    lines = []
    ka, kb = set(a), set(b)
    for k in sorted(kb - ka, key=_k):
        e = b[k]
        tag = f"WR {e['wr']}" if e['wr'] else "—"
        lines.append(f"  + MỚI: {tag} — {e['desc'][:80]} [{e['dept']}]")
    for k in sorted(ka - kb, key=_k):
        e = a[k]
        tag = f"WR {e['wr']}" if e['wr'] else "—"
        lines.append(f"  - XÓA: {tag} — {e['desc'][:80]}")
    for k in sorted(ka & kb, key=_k):
        if a[k]["status"] != b[k]["status"]:
            tag = f"WR {b[k]['wr']}" if b[k]['wr'] else b[k]['desc'][:40]
            lines.append(f"  ~ STATUS: {tag} | '{a[k]['status']}' → '{b[k]['status']}'")
    return lines


def _extract_text(section_rows: list, cols: list) -> list:
    texts = []
    for row in section_rows[1:]:
        if str(row[0]).strip():
            break
        parts = [str(row[c]).strip() for c in cols if len(row) > c and str(row[c]).strip()]
        text = " | ".join(parts)
        if len(text) > 5 and text not in texts:
            texts.append(text)
    return texts


def _diff_text(list_a: list, list_b: list) -> list:
    set_a, set_b = set(list_a), set(list_b)
    lines  = [f"  + MỚI: {t}" for t in list_b if t not in set_a]
    lines += [f"  - BỎ:  {t}" for t in list_a if t not in set_b]
    return lines


class _AutoComparer(QThread):
    done  = Signal(str)
    error = Signal(str)

    def __init__(self, sheet_id: str, name_a: str, name_b: str, provider: str):
        super().__init__()
        self._sheet_id = sheet_id
        self._name_a   = name_a
        self._name_b   = name_b
        self._provider = provider

    def run(self):
        try:
            from core.llm_client import create_llm_client

            rows_a = _fetch_rows(self._sheet_id, self._name_a)
            rows_b = _fetch_rows(self._sheet_id, self._name_b)
            secs_a = _parse_sections(rows_a)
            secs_b = _parse_sections(rows_b)

            diff_parts = []

            # RELIABILITY — diff theo WR#
            for key in ("reliability_u1", "reliability_u2"):
                wr_a  = _parse_reliability(secs_a.get(key, []))
                wr_b  = _parse_reliability(secs_b.get(key, []))
                diff  = _diff_reliability(wr_a, wr_b)
                body  = "\n".join(diff) if diff else "  (Không thay đổi)"
                diff_parts.append(f"=== {_LABELS[key]} ===\n{body}")

            # Các section còn lại — diff theo text
            _SEC_COLS = {
                "nonroutine_u1": [2, 5],
                "nonroutine_u2": [2, 5],
                "concerns_u1":   [2, 3],
                "concerns_u2":   [2, 3],
                "ptw_u1":        [2, 6, 9],
                "ptw_u2":        [2, 6, 9],
                "handover_u1":   [2, 3],
                "handover_u2":   [2, 3],
            }
            for key, cols in _SEC_COLS.items():
                ta   = _extract_text(secs_a.get(key, []), cols)
                tb   = _extract_text(secs_b.get(key, []), cols)
                diff = _diff_text(ta, tb)
                if diff:
                    diff_parts.append(f"=== {_LABELS[key]} ===\n" + "\n".join(diff))

            structured = "\n\n".join(diff_parts)

            prompt = (
                "Bạn là chuyên gia phân tích nhật ký vận hành nhà máy điện.\n\n"
                f"So sánh 2 ca trực: [{self._name_a}] → [{self._name_b}]\n\n"
                f"Kết quả phân tích tự động:\n{structured}\n\n"
                "Viết báo cáo tóm tắt bằng tiếng Việt theo từng phần. "
                "Nhấn mạnh sự cố mới, thiết bị đổi trạng thái, hoạt động bất thường. "
                "Ngắn gọn, rõ ràng."
            )
            ai_text = create_llm_client(self._provider).generate(prompt)

            sep = "=" * 56
            self.done.emit(
                f"{sep}\n  {self._name_a}  →  {self._name_b}\n{sep}\n\n"
                f"{structured}\n\n"
                f"{'─' * 56}\n  AI SUMMARY\n{'─' * 56}\n\n"
                f"{ai_text}"
            )
        except Exception as e:
            self.error.emit(str(e))


# ── Dialog ────────────────────────────────────────────────────────────────────

class _GoogleSheetWindow(QDialog):

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Check Google Sheet")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self.setGeometry(150, 100, 920, 660)
        self.setStyleSheet(themes.get_current()["qss"])

        self._loader        = None
        self._auto_comparer = None
        cfg = _load_config()

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── Config ────────────────────────────────────────────────
        grp = QGroupBox("Cấu hình Google Sheet")
        form = QFormLayout(grp)
        form.setSpacing(8)

        self.url_edit = QLineEdit(cfg.get("sheet_url", ""))
        self.url_edit.setPlaceholderText(
            "https://docs.google.com/spreadsheets/d/…"
        )
        form.addRow("Sheet URL:", self.url_edit)

        btn_bar = QHBoxLayout()
        self.btn_load = QPushButton("🔄  Load Tabs")
        self.btn_load.setToolTip("Tự động tải danh sách tab và điền vào Tab A / Tab B.")
        self.btn_load.clicked.connect(lambda: self._load_tabs())
        btn_save = QPushButton("💾  Save Config")
        btn_save.clicked.connect(self._save_cfg)
        btn_bar.addWidget(self.btn_load)
        btn_bar.addWidget(btn_save)
        btn_bar.addStretch()
        form.addRow("", btn_bar)

        layout.addWidget(grp)

        # ── Tab selector ──────────────────────────────────────────
        tab_grp = QGroupBox("So sánh 2 tabs  (gõ tên tab hoặc dùng Load Tabs)")
        tab_form = QFormLayout(tab_grp)
        tab_form.setSpacing(8)

        self.tab_a_edit = QLineEdit(cfg.get("tab_a", ""))
        self.tab_a_edit.setPlaceholderText("Tên tab A (cũ hơn)")
        self.tab_b_edit = QLineEdit(cfg.get("tab_b", ""))
        self.tab_b_edit.setPlaceholderText("Tên tab B (mới hơn)")

        tab_form.addRow("Tab A (trước):", self.tab_a_edit)
        tab_form.addRow("Tab B (sau):",   self.tab_b_edit)

        self.btn_auto = QPushButton("🤖  Auto Compare")
        self.btn_auto.setMinimumHeight(36)
        self.btn_auto.setToolTip(
            "Tự động parse RELIABILITY, ACTIVITY, HANDOVER, PTW… rồi dùng AI tóm tắt"
        )
        self.btn_auto.clicked.connect(lambda: self._run_auto_compare())
        tab_form.addRow("", self.btn_auto)

        layout.addWidget(tab_grp)

        # ── Status + result ───────────────────────────────────────
        self.status_lbl = QLabel(
            "Nhập URL + tên 2 tab rồi bấm Compare  "
            "(hoặc bấm Load Tabs để tự điền)."
        )
        layout.addWidget(self.status_lbl)

        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setFont(QFont("Consolas", 10))
        layout.addWidget(self.result, 1)

    # ── Slots ─────────────────────────────────────────────────────

    def _save_cfg(self):
        _save_config({
            "sheet_url": self.url_edit.text().strip(),
            "tab_a":     self.tab_a_edit.text().strip(),
            "tab_b":     self.tab_b_edit.text().strip(),
        })
        self.status_lbl.setText("Config đã lưu.")

    def _load_tabs(self):
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "Thiếu URL", "Vui lòng nhập Sheet URL.")
            return
        sheet_id = _extract_sheet_id(url)
        self.btn_load.setEnabled(False)
        self.status_lbl.setText("Đang tải danh sách tabs… có thể mất vài giây.")

        self._loader = _TabLoader(sheet_id)
        self._loader.done.connect(self._on_tabs_loaded)
        self._loader.failed.connect(self._on_load_failed)
        self._loader.start()

    def _on_tabs_loaded(self, names: list):
        self.btn_load.setEnabled(True)
        n = len(names)
        if n >= 2:
            self.tab_a_edit.setText(names[1])  # cũ hơn
            self.tab_b_edit.setText(names[0])  # mới nhất (bên trái)
        elif n == 1:
            self.tab_a_edit.setText(names[0])
        self.status_lbl.setText(
            f"Tìm thấy {n} tab(s). Đã điền 2 tab đầu — kiểm tra rồi bấm Compare."
        )

    def _on_load_failed(self, err: str):
        self.btn_load.setEnabled(True)
        self.status_lbl.setText("Load Tabs thất bại.")
        QMessageBox.critical(self, "Lỗi Load Tabs", str(err))

    # ── Auto Compare slots ────────────────────────────────────────

    def _run_auto_compare(self):
        url    = self.url_edit.text().strip()
        name_a = self.tab_a_edit.text().strip()
        name_b = self.tab_b_edit.text().strip()

        if not url:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập Sheet URL.")
            return
        if not name_a or not name_b:
            QMessageBox.warning(self, "Thiếu tên tab", "Vui lòng nhập tên Tab A và Tab B.")
            return

        from core.llm_config import load_llm_config
        provider = load_llm_config().get("translate_provider", "gemini")
        _save_config({"sheet_url": url, "tab_a": name_a, "tab_b": name_b})

        self._set_busy(True)
        self.status_lbl.setText(
            f"🤖 Đang fetch & phân tích: [{name_a}] → [{name_b}]…"
        )
        self.result.clear()

        self._auto_comparer = _AutoComparer(
            _extract_sheet_id(url), name_a, name_b, provider
        )
        self._auto_comparer.done.connect(self._on_auto_done)
        self._auto_comparer.error.connect(self._on_auto_failed)
        self._auto_comparer.start()

    def _on_auto_done(self, text: str):
        self._set_busy(False)
        self.result.setPlainText(text)
        self.status_lbl.setText("Phân tích xong.")

    def _on_auto_failed(self, err: str):
        self._set_busy(False)
        self.status_lbl.setText("Lỗi Auto Compare.")
        QMessageBox.critical(self, "Lỗi Auto Compare", str(err))

    def _set_busy(self, busy: bool):
        for btn in (self.btn_load, self.btn_auto):
            btn.setEnabled(not busy)
