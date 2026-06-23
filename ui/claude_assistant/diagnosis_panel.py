"""ui/claude_assistant/diagnosis_panel.py — Panel kết quả Co-Pilot Sự Cố.

Trái: cây nguyên nhân gốc (xếp hạng theo confidence).
Phải: bằng chứng của nguyên nhân đang chọn (doc_number, section, quote) + nút mở file.
Dưới: nút sinh báo cáo KV-OP.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QFont, QColor, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QTextBrowser, QMessageBox, QComboBox,
)

from ui.claude_assistant import copilot


def _confidence_color(conf: int) -> QColor:
    """Xanh lá (cao) → vàng → đỏ (thấp) theo confidence."""
    if conf >= 60:
        return QColor("#16a34a")
    if conf >= 30:
        return QColor("#d97706")
    return QColor("#dc2626")


class DiagnosisPanel(QWidget):
    """Panel hiển thị cây nguyên nhân + bằng chứng. Ẩn khi không chẩn đoán."""

    generate_report = Signal(dict)   # phát khi bấm "Sinh báo cáo KV-OP"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db_path: str = ""
        self._diagnosis: dict = {}
        self._cur_evidence: list = []     # evidence của nguyên nhân đang chọn
        self._build_ui()
        self.refresh_history()

    # ── Build UI ──────────────────────────────────────────────────────
    def _build_ui(self):
        self.setStyleSheet("background: #ffffff;")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Header: tiêu đề + combo lịch sử
        hdr = QHBoxLayout()
        self._lbl_title = QLabel("🔬  Chẩn đoán sự cố")
        self._lbl_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self._lbl_title.setStyleSheet("color: #4f46e5; background: transparent;")
        hdr.addWidget(self._lbl_title)
        hdr.addStretch()

        self._history_combo = QComboBox()
        self._history_combo.setFixedHeight(26)
        self._history_combo.setMinimumWidth(150)
        self._history_combo.setToolTip("Tra lại các ca chẩn đoán cũ")
        self._history_combo.setStyleSheet("""
            QComboBox {
                background: #f1f5f9; border: 1px solid #e2e8f0;
                border-radius: 5px; color: #475569; font-size: 11px; padding: 0 6px;
            }
            QComboBox:hover { background: #e0e7ff; }
            QComboBox QAbstractItemView {
                background: #ffffff; color: #1e293b;
                selection-background-color: #e0e7ff;
            }
        """)
        self._history_combo.activated.connect(self._on_pick_history)
        hdr.addWidget(self._history_combo)
        root.addLayout(hdr)

        self._lbl_sub = QLabel("Chọn DB và mô tả triệu chứng để bắt đầu.")
        self._lbl_sub.setWordWrap(True)
        self._lbl_sub.setStyleSheet("color: #64748b; font-size: 11px; background: transparent;")
        root.addWidget(self._lbl_sub)

        # Splitter: cây nguyên nhân | bằng chứng
        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(1)
        split.setStyleSheet("QSplitter::handle { background: #e2e8f0; }")

        # ── Trái: cây nguyên nhân ──
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Nguyên nhân", "%"])
        self._tree.setRootIsDecorated(False)
        self._tree.setColumnWidth(0, 180)
        self._tree.header().setStretchLastSection(False)
        self._tree.header().setSectionResizeMode(0, self._tree.header().ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(1, self._tree.header().ResizeMode.Fixed)
        self._tree.setColumnWidth(1, 44)
        self._tree.setStyleSheet("""
            QTreeWidget {
                background: #f8fafc; border: 1px solid #e2e8f0;
                border-radius: 6px; color: #1e293b; font-size: 12px;
            }
            QTreeWidget::item { padding: 5px 4px; }
            QTreeWidget::item:selected { background: #e0e7ff; color: #312e81; }
            QHeaderView::section {
                background: #eef2f7; color: #64748b;
                border: none; border-bottom: 1px solid #e2e8f0; padding: 4px;
            }
        """)
        self._tree.currentItemChanged.connect(self._on_select_cause)
        split.addWidget(self._tree)

        # ── Phải: bằng chứng (mỗi evidence có link mở file riêng) ──
        self._evidence = QTextBrowser()
        self._evidence.setOpenLinks(False)
        self._evidence.setOpenExternalLinks(False)
        self._evidence.anchorClicked.connect(self._on_anchor)
        self._evidence.setStyleSheet("""
            QTextBrowser {
                background: #f8fafc; border: 1px solid #e2e8f0;
                border-radius: 6px; color: #1e293b; padding: 8px; font-size: 12px;
            }
        """)
        split.addWidget(self._evidence)
        split.setSizes([260, 320])
        root.addWidget(split, 1)

        # ── Nút sinh báo cáo ──
        self._btn_report = QPushButton("📝  Sinh báo cáo KV-OP")
        self._btn_report.setFixedHeight(38)
        self._btn_report.setEnabled(False)
        self._btn_report.setStyleSheet("""
            QPushButton {
                background: #4f46e5; color: white; border: none;
                border-radius: 8px; font-weight: 600; font-size: 13px;
            }
            QPushButton:hover    { background: #4338ca; }
            QPushButton:disabled { background: #e2e8f0; color: #94a3b8; }
        """)
        self._btn_report.clicked.connect(self._on_report)
        root.addWidget(self._btn_report)

    # ── Public API ────────────────────────────────────────────────────
    def set_db_path(self, path: str):
        self._db_path = path or ""

    def refresh_history(self):
        """Nạp lại danh sách ca cũ vào combo lịch sử."""
        hist = copilot.load_history()
        self._history_combo.blockSignals(True)
        self._history_combo.clear()
        self._history_combo.addItem(f"🕘 Lịch sử ({len(hist)})")
        for rec in hist:
            d = rec.get("diagnosis", {}) or {}
            sym = (d.get("symptom") or rec.get("symptom") or "")[:40]
            eq = d.get("equipment", "")
            ts = rec.get("time_label", "")
            label = f"{ts} • {sym}" + (f"  ({eq})" if eq else "")
            self._history_combo.addItem(label, d)
        self._history_combo.setCurrentIndex(0)
        self._history_combo.blockSignals(False)

    def _on_pick_history(self, idx: int):
        if idx <= 0:
            return
        d = self._history_combo.itemData(idx)
        if d:
            self.set_diagnosis(d, restored=True)

    def set_analyzing(self, symptom: str = ""):
        """Trạng thái đang phân tích."""
        self._tree.clear()
        self._evidence.clear()
        self._cur_evidence = []
        self._btn_report.setEnabled(False)
        self._diagnosis = {}
        sym = f"  «{symptom}»" if symptom else ""
        self._lbl_sub.setText(f"⏳ Đang suy luận đa tầng qua tài liệu…{sym}")

    def set_diagnosis(self, data: dict, restored: bool = False):
        """Đổ kết quả chẩn đoán vào panel. restored=True khi khôi phục lần gần nhất."""
        self._diagnosis = data or {}
        self._tree.clear()
        self._evidence.clear()
        self._cur_evidence = []

        causes = (data or {}).get("causes") or []
        if not causes:
            self._lbl_sub.setText("⚠️ Không tạo được cây nguyên nhân từ dữ liệu hiện có.")
            self._btn_report.setEnabled(False)
            return

        equip = data.get("equipment", "")
        sys_code = data.get("system_code", "")
        head = equip + (f"  ({sys_code})" if sys_code else "")
        prefix = "↺ Kết quả gần nhất — " if restored else ""
        self._lbl_sub.setText(f"{prefix}🛠 {head}" if head else f"{prefix}Kết quả chẩn đoán")

        for c in causes:
            conf = c.get("confidence", 0)
            item = QTreeWidgetItem([c.get("title", "Nguyên nhân"), f"{conf}%"])
            item.setData(0, Qt.UserRole, c)
            item.setForeground(1, QBrush(_confidence_color(conf)))
            f = item.font(1)
            f.setBold(True)
            item.setFont(1, f)
            self._tree.addTopLevelItem(item)

        self._tree.setCurrentItem(self._tree.topLevelItem(0))
        self._btn_report.setEnabled(True)

    def reset(self):
        self._tree.clear()
        self._evidence.clear()
        self._diagnosis = {}
        self._cur_evidence = []
        self._btn_report.setEnabled(False)
        self._lbl_sub.setText("Chọn DB và mô tả triệu chứng để bắt đầu.")

    # ── Slots ─────────────────────────────────────────────────────────
    def _on_select_cause(self, current: QTreeWidgetItem, _prev):
        if current is None:
            self._evidence.clear()
            self._cur_evidence = []
            return
        cause = current.data(0, Qt.UserRole) or {}
        self._render_evidence(cause)

    def _render_evidence(self, cause: dict):
        self._cur_evidence = cause.get("evidence") or []
        parts = []
        rationale = cause.get("rationale", "")
        if rationale:
            parts.append(
                f'<p style="color:#475569;margin:0 0 8px 0">{_esc(rationale)}</p>'
            )
        if not self._cur_evidence:
            parts.append('<p style="color:#94a3b8">Không có bằng chứng trích dẫn.</p>')

        for i, e in enumerate(self._cur_evidence):
            doc = _esc(e.get("doc_number", ""))
            sec = _esc(e.get("section", ""))
            quote = _esc(e.get("quote", ""))

            verified = e.get("verified")
            if verified is True:
                badge = '<span style="color:#16a34a;font-size:11px">✓ Đã xác minh</span>'
            elif verified is False:
                badge = '<span style="color:#d97706;font-size:11px">⚠ Chưa khớp DB</span>'
            else:
                badge = ""

            link = (
                f'&nbsp;&nbsp;<a href="open:{i}" '
                f'style="color:#4f46e5;text-decoration:none">📄 Mở file</a>'
                if e.get("doc_number") else ""
            )

            parts.append(
                '<div style="margin:0 0 10px 0;border-left:2px solid #6366f1;padding-left:8px">'
                f'<div style="color:#4f46e5;font-size:11px"><b>{doc}</b>'
                f'{(" › " + sec) if sec else ""}</div>'
                f'<div style="color:#334155;font-size:12px">"{quote}"</div>'
                f'<div style="margin-top:2px">{badge}{link}</div>'
                '</div>'
            )
        self._evidence.setHtml("".join(parts))

    def _on_anchor(self, url: QUrl):
        """Click link 'open:<index>' → mở file gốc của evidence tương ứng."""
        s = url.toString()
        if not s.startswith("open:"):
            return
        try:
            idx = int(s.split(":", 1)[1])
        except Exception:
            return
        if not (0 <= idx < len(self._cur_evidence)):
            return
        doc = self._cur_evidence[idx].get("doc_number", "")
        path = copilot.resolve_source_path(self._db_path, doc_number=doc)
        if path and os.path.exists(path):
            try:
                os.startfile(path)  # type: ignore[attr-defined]
            except Exception as e:
                QMessageBox.warning(self, "Lỗi mở file", str(e))
        else:
            QMessageBox.information(
                self, "Không tìm thấy",
                f"Không tìm thấy file gốc cho doc:\n{doc}",
            )

    def _on_report(self):
        if self._diagnosis.get("causes"):
            self.generate_report.emit(self._diagnosis)


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
