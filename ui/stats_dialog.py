# ui/stats_dialog.py
import os
from datetime import datetime, timedelta
from collections import defaultdict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QScrollArea, QWidget, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPainter, QColor

from core.file_stats import query_stats


# ── GitHub contribution graph constants ──────────────────────────
CELL   = 9    # px mỗi ô vuông
GAP    = 2    # px khoảng cách
WEEKS  = 16   # số tuần hiển thị (16 tuần = ~4 tháng)

# Màu 5 mức như GitHub dark
LEVELS = [
    QColor("#2d333b"),   # 0 — trống
    QColor("#0e4429"),   # 1
    QColor("#006d32"),   # 2
    QColor("#26a641"),   # 3–4
    QColor("#39d353"),   # 5+
]

def _level(count: int) -> QColor:
    if count == 0: return LEVELS[0]
    if count == 1: return LEVELS[1]
    if count == 2: return LEVELS[2]
    if count <= 4: return LEVELS[3]
    return LEVELS[4]


def _heat_icon(rank: int, max_count: int, count: int) -> str:
    pct = count / max_count if max_count else 0
    if rank == 1:    return "🔥"
    if pct >= 0.75:  return "📈"
    if pct >= 0.4:   return "📄"
    return "🗒️"


# ── Contribution grid widget ─────────────────────────────────────
class _ContribGrid(QWidget):
    """
    Lưới WEEKS cột × 7 hàng (Mon–Sun), giống GitHub contribution graph.
    Mỗi ô = 1 ngày. Màu theo số lần mở trong ngày đó.
    """
    def __init__(self, history: list, parent=None):
        super().__init__(parent)

        # Đếm số lần mở theo từng ngày
        counts: defaultdict = defaultdict(int)
        for d in history:
            try:
                counts[datetime.strptime(d, "%Y-%m-%d").date()] += 1
            except Exception:
                pass

        today = datetime.now().date()
        # Thứ Hai của tuần hiện tại
        this_monday = today - timedelta(days=today.weekday())
        # Lùi về WEEKS-1 tuần
        start = this_monday - timedelta(weeks=WEEKS - 1)

        # Xây ma trận [col][row] = count, col=tuần, row=0(Mon)..6(Sun)
        self._grid = []
        cur = start
        for _ in range(WEEKS):
            col = []
            for _ in range(7):
                col.append(counts.get(cur, 0))
                cur += timedelta(days=1)
            self._grid.append(col)

        w = WEEKS * (CELL + GAP) - GAP
        h = 7 * (CELL + GAP) - GAP
        self.setFixedSize(w, h)
        self.setToolTip(f"Last {WEEKS} weeks")
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#161b22"))
        p.setPen(Qt.NoPen)
        for col, week in enumerate(self._grid):
            for row, cnt in enumerate(week):
                x = col * (CELL + GAP)
                y = row * (CELL + GAP)
                p.setBrush(_level(cnt))
                p.drawRoundedRect(x, y, CELL, CELL, 2, 2)
        p.end()


# ── Card từng file ───────────────────────────────────────────────
class _StatCard(QFrame):
    def __init__(self, rank: int, row: dict, max_count: int, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setStyleSheet("""
            QFrame#statCard {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 8px;
                margin: 2px 8px;
            }
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(12)

        # Rank
        lbl_rank = QLabel(f"#{rank}")
        lbl_rank.setFixedWidth(28)
        lbl_rank.setAlignment(Qt.AlignCenter)
        f = QFont(); f.setPointSize(10); f.setBold(True)
        lbl_rank.setFont(f)
        lbl_rank.setStyleSheet("color: #484f58;")
        lay.addWidget(lbl_rank)

        # Icon
        icon = QLabel(_heat_icon(rank, max_count, row["count"]))
        icon.setFixedWidth(22)
        icon.setAlignment(Qt.AlignCenter)
        fi = QFont(); fi.setPointSize(13)
        icon.setFont(fi)
        lay.addWidget(icon)

        # Tên + ngày
        info = QVBoxLayout()
        info.setSpacing(3)

        name = QLabel(row["name"])
        name.setToolTip(row["file"])
        fn = QFont(); fn.setPointSize(10); fn.setBold(True)
        name.setFont(fn)
        name.setStyleSheet("color: #e6edf3;")
        info.addWidget(name)

        lbl_last = QLabel(f"Last opened: {row['last_open']}")
        lbl_last.setStyleSheet("color: #8b949e; font-size: 9px;")
        info.addWidget(lbl_last)

        lay.addLayout(info, 1)

        # Contribution grid
        grid = _ContribGrid(row.get("history", []))
        lay.addWidget(grid, 0, Qt.AlignVCenter)

        # Count badge
        badge = QLabel(f"{row['count']}×")
        fb = QFont(); fb.setPointSize(13); fb.setBold(True)
        badge.setFont(fb)
        badge.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        badge.setStyleSheet("color: #3fb950;")
        badge.setFixedWidth(55)
        lay.addWidget(badge)


# ── Dialog chính ─────────────────────────────────────────────────
class StatsDialog(QDialog):
    def __init__(self, stats_path: str, parent=None):
        super().__init__(parent)
        self.stats_path = stats_path
        self.setWindowTitle("File Open Statistics")
        self.resize(880, 560)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog  { background: #0d1117; }
            QLabel   { color: #c9d1d9; }
            QComboBox {
                background: #161b22; color: #c9d1d9;
                border: 1px solid #30363d; border-radius: 6px; padding: 3px 8px;
            }
            QComboBox QAbstractItemView { background: #161b22; color: #c9d1d9; }
            QPushButton {
                background: #238636; color: white;
                border: none; border-radius: 6px; padding: 4px 14px;
                font-weight: bold;
            }
            QPushButton:hover { background: #2ea043; }
            QScrollBar:vertical {
                background: #0d1117; width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #30363d; border-radius: 4px;
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        # Filter row
        now = datetime.now()
        top = QHBoxLayout()

        top.addWidget(QLabel("Year:"))
        self.cbo_year = QComboBox()
        self.cbo_year.addItem("All", 0)
        for y in range(now.year, now.year - 6, -1):
            self.cbo_year.addItem(str(y), y)
        self.cbo_year.setCurrentIndex(1)
        top.addWidget(self.cbo_year)

        top.addWidget(QLabel("Month:"))
        self.cbo_month = QComboBox()
        self.cbo_month.addItem("All", 0)
        for i, m in enumerate(["Jan","Feb","Mar","Apr","May","Jun",
                                "Jul","Aug","Sep","Oct","Nov","Dec"], 1):
            self.cbo_month.addItem(m, i)
        top.addWidget(self.cbo_month)

        btn = QPushButton("View")
        btn.clicked.connect(self.refresh)
        top.addWidget(btn)
        top.addStretch()

        self.lbl_summary = QLabel()
        self.lbl_summary.setStyleSheet("color: #8b949e; font-size: 11px;")
        top.addWidget(self.lbl_summary)
        lay.addLayout(top)

        # Scroll
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; }")
        lay.addWidget(self.scroll)

        self.refresh()

    def refresh(self):
        year  = self.cbo_year.currentData()  or None
        month = self.cbo_month.currentData() or None
        rows  = query_stats(self.stats_path, year=year, month=month)

        container = QWidget()
        container.setStyleSheet("background: #0d1117;")
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(6)

        if not rows:
            lbl = QLabel("No data available for this period.")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #484f58; font-size: 12px;")
            vlay.addWidget(lbl)
        else:
            max_count = rows[0]["count"]
            for i, row in enumerate(rows, 1):
                vlay.addWidget(_StatCard(i, row, max_count))

        vlay.addStretch()
        self.scroll.setWidget(container)

        total = sum(r["count"] for r in rows)
        self.lbl_summary.setText(f"{len(rows)} file(s)  •  {total} open(s)")
