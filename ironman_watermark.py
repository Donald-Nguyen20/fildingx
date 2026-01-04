# ironman_watermark.py
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath


class IronmanWireframe(QWidget):
    """
    Ironman HUD Wireframe – rounded, glowing eyes, light 3D feel
    """
    def __init__(self, parent=None, opacity=0.08, line_width=2.0):
        super().__init__(parent)
        self.opacity = float(opacity)
        self.line_width = float(line_width)

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        # ====== POLYLINES ======
        self.polylines = [
            # Head outer
            [(0.50,0.08),(0.38,0.12),(0.30,0.25),(0.28,0.42),
             (0.32,0.62),(0.40,0.78),(0.50,0.88),
             (0.60,0.78),(0.68,0.62),(0.72,0.42),
             (0.70,0.25),(0.62,0.12),(0.50,0.08)],

            # Center ridge
            [(0.50,0.14),(0.50,0.32),(0.50,0.52),(0.50,0.74)],

            # Cheeks
            [(0.34,0.45),(0.40,0.52),(0.44,0.60)],
            [(0.66,0.45),(0.60,0.52),(0.56,0.60)],

            # Jaw inner
            [(0.40,0.80),(0.50,0.76),(0.60,0.80)],
        ]

        # ====== EYES (special) ======
        self.eyes = [
            [(0.36,0.36),(0.44,0.35),(0.47,0.38),(0.42,0.42),(0.36,0.41)],
            [(0.64,0.36),(0.56,0.35),(0.53,0.38),(0.58,0.42),(0.64,0.41)],
        ]

    # ------------------------------------------------------------------

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        r = QRectF(self.rect())
        w, h = r.width(), r.height()

        # ===== GLOW BACK (3D feel) =====
        p.setOpacity(self.opacity * 0.8)
        glow_pen = QPen(QColor(0, 220, 255, 50), self.line_width + 4.5)
        glow_pen.setCapStyle(Qt.RoundCap)
        glow_pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(glow_pen)
        self._draw_polylines_path(p, r, w, h)

        # ===== CORE LINES =====
        p.setOpacity(self.opacity)
        core_pen = QPen(QColor(0, 220, 255, 200), self.line_width)
        core_pen.setCapStyle(Qt.RoundCap)
        core_pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(core_pen)
        self._draw_polylines_path(p, r, w, h)

        # ===== EYES GLOW =====
        self._draw_eyes(p, r, w, h)

    # ------------------------------------------------------------------

    def _draw_polylines_path(self, p, r, w, h):
        for line in self.polylines:
            path = QPainterPath()
            pts = [QPointF(r.left()+x*w, r.top()+y*h) for x, y in line]

            path.moveTo(pts[0])
            for i in range(1, len(pts)):
                # pseudo-curve bằng midpoint
                mid = (pts[i-1] + pts[i]) / 2
                path.quadTo(pts[i-1], mid)

            path.lineTo(pts[-1])
            p.drawPath(path)

    # ------------------------------------------------------------------

    def _draw_eyes(self, p, r, w, h):
        for eye in self.eyes:
            pts = [QPointF(r.left()+x*w, r.top()+y*h) for x, y in eye]

            path = QPainterPath()
            path.moveTo(pts[0])
            for i in range(1, len(pts)):
                path.lineTo(pts[i])
            path.closeSubpath()

            # glow
            p.setOpacity(self.opacity * 1.6)
            p.setPen(QPen(QColor(120, 255, 255, 120), 5))
            p.drawPath(path)

            # core
            p.setOpacity(self.opacity * 2.2)
            p.setPen(QPen(QColor(200, 255, 255, 255), 2))
            p.drawPath(path)
