from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush,
    QLinearGradient, QRadialGradient
)


class HudPanel(QWidget):
    """
    HUD Panel: góc vát + notch + glow (Ironman style)
    """
    def __init__(self, parent=None, notch=True):
        super().__init__(parent)
        self.notch = notch
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def _build_path(self, r: QRectF) -> QPainterPath:
        m = 12
        c = 26
        notch_w = 160
        notch_h = 18

        x0, y0 = r.left() + m, r.top() + m
        x1, y1 = r.right() - m, r.bottom() - m
        cx = (x0 + x1) / 2

        p = QPainterPath()
        p.moveTo(x0 + c, y0)

        if self.notch:
            p.lineTo(cx - notch_w/2, y0)
            p.lineTo(cx - notch_w/2 + notch_h, y0 - notch_h)
            p.lineTo(cx + notch_w/2 - notch_h, y0 - notch_h)
            p.lineTo(cx + notch_w/2, y0)

        # Góc phải trên: 2-nấc (tech cut)
        p.lineTo(x1 - c*1.6, y0)
        p.lineTo(x1 - c*0.9, y0 + c*0.4)
        p.lineTo(x1, y0 + c*1.1)

        p.lineTo(x1, y1 - c)
        p.lineTo(x1 - c, y1)
        p.lineTo(x0 + c, y1)
        p.lineTo(x0, y1 - c)
        p.lineTo(x0, y0 + c)
        p.closeSubpath()
        return p

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(self.rect())
        path = self._build_path(rect)

        # ===== 0) CLIP theo panel =====
        painter.save()
        painter.setClipPath(path)

        # ===== 1) NỀN 3D (base + vignette + noise nhẹ kiểu "kính") =====
        base = QLinearGradient(rect.topLeft(), rect.bottomRight())
        base.setColorAt(0.0, QColor(6, 10, 16, 245))
        base.setColorAt(0.6, QColor(4, 8, 12, 235))
        base.setColorAt(1.0, QColor(3, 6, 10, 250))
        painter.fillPath(path, QBrush(base))

        # Vignette (tối viền nhẹ để có chiều sâu)
        vig = QRadialGradient(rect.center(), max(rect.width(), rect.height()) * 0.75)
        vig.setColorAt(0.0, QColor(0, 0, 0, 0))
        vig.setColorAt(1.0, QColor(0, 0, 0, 90))
        painter.fillPath(path, QBrush(vig))

        painter.restore()

        # ===== 2) GLOW NGOÀI (cyan chủ đạo + amber nhấn) =====
        # Cyan layers
        for color, width in [
            (QColor(0, 220, 255, 28), 16),
            (QColor(0, 220, 255, 70), 10),
            (QColor(0, 220, 255, 170), 3),
        ]:
            pen = QPen(color, width)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path)

        # # Amber accent glow (mỏng thôi, tạo "màu phim")
        # amber_pen = QPen(QColor(255, 140, 40, 90), 2.2)
        # amber_pen.setJoinStyle(Qt.RoundJoin)
        # painter.setPen(amber_pen)
        # # vẽ 1 đoạn nhấn ở đáy (cảm giác có “module”)
        # y = rect.bottom() - 20
        # painter.drawLine(int(rect.left() + 80), int(y), int(rect.left() + 200), int(y))

        # ===== 3) BEVEL 3D: inner highlight + inner shadow =====
        inner = QPainterPath(path)
        # vẽ inner bằng cách "thu nhỏ" rect rồi build lại (nhẹ, ổn định)
        inner_rect = QRectF(rect.adjusted(5, 5, -5, -5))
        inner_path = self._build_path(inner_rect)

        # inner highlight (viền sáng phía trên-trái)
        hi = QLinearGradient(rect.topLeft(), rect.bottomRight())
        hi.setColorAt(0.0, QColor(220, 255, 255, 90))
        hi.setColorAt(0.35, QColor(220, 255, 255, 15))
        hi.setColorAt(1.0, QColor(220, 255, 255, 0))
        pen_hi = QPen(QBrush(hi), 1.2)
        pen_hi.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen_hi)
        painter.drawPath(inner_path)

        # inner shadow (tối phía dưới-phải)
        sh = QLinearGradient(rect.topLeft(), rect.bottomRight())
        sh.setColorAt(0.0, QColor(0, 0, 0, 0))
        sh.setColorAt(0.65, QColor(0, 0, 0, 30))
        sh.setColorAt(1.0, QColor(0, 0, 0, 90))
        pen_sh = QPen(QBrush(sh), 1.6)
        pen_sh.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen_sh)
        inner_rect2 = QRectF(rect.adjusted(7, 7, -7, -7))
        inner_path2 = self._build_path(inner_rect2)

        sh = QLinearGradient(rect.topLeft(), rect.bottomRight())
        sh.setColorAt(0.0, QColor(0, 0, 0, 0))
        sh.setColorAt(0.65, QColor(0, 0, 0, 35))
        sh.setColorAt(1.0, QColor(0, 0, 0, 120))

        pen_sh = QPen(QBrush(sh), 1.8)
        pen_sh.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen_sh)
        painter.drawPath(inner_path2)


        # ===== 4) VIỀN CORE (rõ nét) =====
        core = QPen(QColor(200, 255, 255, 230), 1.2)
        core.setJoinStyle(Qt.RoundJoin)
        painter.setPen(core)
        painter.drawPath(path)

        # # ===== 5) TECH LINES (micro detail) =====
        # tech_pen = QPen(QColor(0, 220, 255, 50), 1)
        # painter.setPen(tech_pen)

        # painter.drawLine(int(rect.left() + 40), int(rect.top() + 26),
        #                 int(rect.left() + 170), int(rect.top() + 26))

        # painter.drawLine(int(rect.right() - 210), int(rect.bottom() - 30),
        #                 int(rect.right() - 60), int(rect.bottom() - 30))

        # # amber micro accent
        # painter.setPen(QPen(QColor(255, 140, 40, 70), 1))
        # painter.drawLine(int(rect.right() - 180), int(rect.top() + 26),
        #                 int(rect.right() - 90), int(rect.top() + 26))

