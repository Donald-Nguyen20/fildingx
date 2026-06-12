"""ui/claude_assistant/animations.py — PulsingOrb + NeuralBackground."""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class PulsingOrb(QWidget):
    """Vòng tròn nhấp nháy — idle: chậm/mờ, active: nhanh/sáng."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setStyleSheet("background: transparent;")
        self._phase   = 0.0
        self._active  = False
        self._timer   = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)           # ~30 fps

    def set_active(self, active: bool):
        self._active = active

    def _tick(self):
        self._phase = (self._phase + (0.12 if self._active else 0.03)) % (2 * math.pi)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx = self.width()  / 2
        cy = self.height() / 2
        pulse = (math.sin(self._phase) + 1) / 2     # 0 → 1

        # Glow rings (3 lớp)
        for i in range(3):
            r = 9 + i * 3 + pulse * 2.5
            a = int((70 if self._active else 22) * (1 - i / 3) * (0.3 + 0.7 * pulse))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(99, 102, 241, a))
            p.drawEllipse(QPointF(cx, cy), r, r)

        # Core orb
        core_a = int(210 * (0.6 + 0.4 * pulse)) if self._active else int(120 * (0.5 + 0.5 * pulse))
        p.setBrush(QColor(99, 102, 241, core_a))
        p.drawEllipse(QPointF(cx, cy), 5, 5)

        # Shine highlight
        p.setBrush(QColor(255, 255, 255, 160))
        p.drawEllipse(QPointF(cx - 1.2, cy - 1.8), 1.4, 1.4)


class NeuralBackground(QWidget):
    """Mạng nơ-ron động — nodes + kết nối di chuyển nhẹ làm background."""

    _NODE_COUNT = 30
    _MAX_DIST   = 140

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setStyleSheet("background: transparent;")
        self._nodes: list[dict] = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)           # 20 fps — nhẹ CPU

    # ── Init / resize ──────────────────────────────────────────────
    def _init_nodes(self):
        w = max(self.width(),  200)
        h = max(self.height(), 200)
        self._nodes = [
            {
                "x":  random.uniform(0, w),
                "y":  random.uniform(0, h),
                "vx": random.uniform(-0.22, 0.22),
                "vy": random.uniform(-0.22, 0.22),
                "r":  random.uniform(1.5, 3.2),
            }
            for _ in range(self._NODE_COUNT)
        ]

    def showEvent(self, event):
        super().showEvent(event)
        if not self._nodes:
            self._init_nodes()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._init_nodes()

    # ── Animation tick ─────────────────────────────────────────────
    def _tick(self):
        w, h = self.width(), self.height()
        for n in self._nodes:
            n["x"] += n["vx"]
            n["y"] += n["vy"]
            if not 0 <= n["x"] <= w:
                n["vx"] *= -1
            if not 0 <= n["y"] <= h:
                n["vy"] *= -1
        self.update()

    # ── Paint ──────────────────────────────────────────────────────
    def paintEvent(self, event):
        if not self._nodes:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        nodes = self._nodes
        md  = self._MAX_DIST
        md2 = md * md

        # Vẽ đường kết nối
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                dx = nodes[i]["x"] - nodes[j]["x"]
                dy = nodes[i]["y"] - nodes[j]["y"]
                d2 = dx * dx + dy * dy
                if d2 < md2:
                    alpha = int(38 * (1 - math.sqrt(d2) / md))
                    p.setPen(QPen(QColor(99, 102, 241, alpha), 0.9))
                    p.drawLine(
                        QPointF(nodes[i]["x"], nodes[i]["y"]),
                        QPointF(nodes[j]["x"], nodes[j]["y"]),
                    )

        # Vẽ nodes
        p.setPen(Qt.NoPen)
        for n in nodes:
            p.setBrush(QColor(99, 102, 241, 55))
            p.drawEllipse(QPointF(n["x"], n["y"]), n["r"], n["r"])
