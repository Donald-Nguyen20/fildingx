from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush,
    QLinearGradient, QRadialGradient
)
from ui import themes


class HudPanel(QWidget):
    """HUD Panel: góc vát + notch + glow — màu đọc từ themes.py"""

    def __init__(self, parent=None, notch=True):
        super().__init__(parent)
        self.notch = notch
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def _build_path(self, r: QRectF) -> QPainterPath:
        m, c = 12, 26
        notch_w, notch_h = 160, 18
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
        p.lineTo(x1 - c*1.6, y0);  p.lineTo(x1 - c*0.9, y0 + c*0.4)
        p.lineTo(x1, y0 + c*1.1);  p.lineTo(x1, y1 - c)
        p.lineTo(x1 - c, y1);      p.lineTo(x0 + c, y1)
        p.lineTo(x0, y1 - c);      p.lineTo(x0, y0 + c)
        p.closeSubpath()
        return p

    def paintEvent(self, event):
        h = themes.get_current()["hud"]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        path = self._build_path(rect)

        painter.save()
        painter.setClipPath(path)

        # 1) Base gradient
        base_colors = h["base"]
        stops = [0.0, 0.5, 1.0]
        base = QLinearGradient(rect.topLeft(), rect.bottomRight())
        for stop, c in zip(stops, base_colors):
            base.setColorAt(stop, QColor(*c))
        painter.fillPath(path, QBrush(base))

        # 2) Sheen overlay (optional)
        if h["sheen"]:
            sheen = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            for stop, c in zip([0.0, 0.3, 1.0], h["sheen"]):
                sheen.setColorAt(stop, QColor(*c))
            painter.fillPath(path, QBrush(sheen))

        # 3) Vignette
        vig_color = QColor(0, 60, 130, h["vig_a"]) if not h["vig_dark"] else QColor(0, 0, 0, h["vig_a"])
        vig = QRadialGradient(rect.center(), max(rect.width(), rect.height()) * 0.75)
        vig.setColorAt(0.0, QColor(0, 0, 0, 0))
        vig.setColorAt(1.0, vig_color)
        painter.fillPath(path, QBrush(vig))

        painter.restore()

        # 4) Glow
        for c, w in zip(h["glow"], h["glow_w"]):
            pen = QPen(QColor(*c), w)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path)

        # 5) Inner highlight
        inner_path = self._build_path(QRectF(rect.adjusted(5, 5, -5, -5)))
        hi = QLinearGradient(rect.topLeft(), rect.bottomRight())
        for stop, c in zip([0.0, 0.35, 1.0], h["hi"]):
            hi.setColorAt(stop, QColor(*c))
        pen_hi = QPen(QBrush(hi), 1.2)
        pen_hi.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen_hi)
        painter.drawPath(inner_path)

        # 6) Inner shadow
        inner_path2 = self._build_path(QRectF(rect.adjusted(7, 7, -7, -7)))
        sh = QLinearGradient(rect.topLeft(), rect.bottomRight())
        for stop, c in zip([0.0, 0.65, 1.0], h["sh"]):
            sh.setColorAt(stop, QColor(*c))
        pen_sh = QPen(QBrush(sh), 1.8)
        pen_sh.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen_sh)
        painter.drawPath(inner_path2)

        # 7) Core border
        core = QPen(QColor(*h["core"]), 1.1)
        core.setJoinStyle(Qt.RoundJoin)
        painter.setPen(core)
        painter.drawPath(path)


def qss_hud_metal_header_feel() -> str:
    return themes.get_current()["qss"]


def qss_white_results() -> str:
    # Lấy phần result zone từ qss hiện tại (dùng chung)
    return ""
