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


class _Comparer(QThread):
    done   = Signal(list, list, str, str)
    failed = Signal(str)

    def __init__(self, sheet_id: str, name_a: str, name_b: str):
        super().__init__()
        self._sheet_id = sheet_id
        self._name_a   = name_a
        self._name_b   = name_b

    def run(self):
        try:
            rows_a = _fetch_rows(self._sheet_id, self._name_a)
            rows_b = _fetch_rows(self._sheet_id, self._name_b)
            self.done.emit(rows_a, rows_b, self._name_a, self._name_b)
        except Exception as e:
            self.failed.emit(str(e))


# ── Dialog ────────────────────────────────────────────────────────────────────

class _GoogleSheetWindow(QDialog):

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Check Google Sheet")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self.setGeometry(150, 100, 920, 660)
        self.setStyleSheet(themes.get_current()["qss"])

        self._loader   = None
        self._comparer = None
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

        self.btn_compare = QPushButton("🔍  Compare")
        self.btn_compare.setMinimumHeight(36)
        self.btn_compare.clicked.connect(lambda: self._run_compare())
        tab_form.addRow("", self.btn_compare)

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
            self.tab_a_edit.setText(names[0])
            self.tab_b_edit.setText(names[1])
        elif n == 1:
            self.tab_a_edit.setText(names[0])
        self.status_lbl.setText(
            f"Tìm thấy {n} tab(s). Đã điền 2 tab đầu — kiểm tra rồi bấm Compare."
        )

    def _on_load_failed(self, err: str):
        self.btn_load.setEnabled(True)
        self.status_lbl.setText("Load Tabs thất bại.")
        QMessageBox.critical(self, "Lỗi Load Tabs", str(err))

    def _run_compare(self):
        url    = self.url_edit.text().strip()
        name_a = self.tab_a_edit.text().strip()
        name_b = self.tab_b_edit.text().strip()

        if not url:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập Sheet URL.")
            return
        if not name_a or not name_b:
            QMessageBox.warning(self, "Thiếu tên tab", "Vui lòng nhập tên Tab A và Tab B.")
            return

        sheet_id = _extract_sheet_id(url)
        self.btn_compare.setEnabled(False)
        self.btn_load.setEnabled(False)
        self.status_lbl.setText(f"Đang fetch '{name_a}' và '{name_b}'…")
        self.result.clear()

        self._comparer = _Comparer(sheet_id, name_a, name_b)
        self._comparer.done.connect(self._on_compare_done)
        self._comparer.failed.connect(self._on_compare_failed)
        self._comparer.start()

    def _on_compare_done(
        self, rows_a: list, rows_b: list, name_a: str, name_b: str
    ):
        self.btn_compare.setEnabled(True)
        self.btn_load.setEnabled(True)
        _save_config({
            "sheet_url": self.url_edit.text().strip(),
            "tab_a":     name_a,
            "tab_b":     name_b,
        })

        def row_key(row: list) -> str:
            return "\t".join(str(c) for c in row)

        set_a   = {row_key(r) for r in rows_a}
        set_b   = {row_key(r) for r in rows_b}
        added   = sorted(set_b - set_a)
        deleted = sorted(set_a - set_b)

        lines = [
            f"📋 Tab A : {name_a}  ({len(rows_a)} dòng)",
            f"📋 Tab B : {name_b}  ({len(rows_b)} dòng)",
            "",
        ]
        if not added and not deleted:
            lines.append("✅ Hai tab giống hệt nhau — không có thay đổi.")
        else:
            if added:
                lines.append(f"➕ THÊM MỚI trong '{name_b}' — {len(added)} dòng:")
                for r in added:
                    lines.append(f"   + {r}")
                lines.append("")
            if deleted:
                lines.append(
                    f"➖ ĐÃ XÓA / không còn trong '{name_b}' — {len(deleted)} dòng:"
                )
                for r in deleted:
                    lines.append(f"   - {r}")

        self.result.setPlainText("\n".join(lines))
        self.status_lbl.setText(f"So sánh xong: '{name_a}'  →  '{name_b}'")

    def _on_compare_failed(self, err: str):
        self.btn_compare.setEnabled(True)
        self.btn_load.setEnabled(True)
        self.status_lbl.setText("Lỗi khi fetch.")
        QMessageBox.critical(self, "Lỗi Compare", str(err))
