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

        ## ===== 1) NỀN 3D (Indigo AI - dịu mắt) =====
        base = QLinearGradient(rect.topLeft(), rect.bottomRight())
        base.setColorAt(0.0, QColor(255, 255, 255, 245))
        base.setColorAt(0.6, QColor(248, 250, 252, 245))
        base.setColorAt(1.0, QColor(240, 245, 250, 250))
        painter.fillPath(path, QBrush(base))



        # Vignette (tối viền nhẹ để có chiều sâu)
        vig = QRadialGradient(rect.center(), max(rect.width(), rect.height()) * 0.75)
        vig.setColorAt(0.0, QColor(0, 0, 0, 0))
        vig.setColorAt(1.0, QColor(0, 0, 0, 90))
        painter.fillPath(path, QBrush(vig))

        painter.restore()

        # ===== 2) GLOW NGOÀI (Cyan - mảnh, sạch, ít chói) =====
        for color, width in [
            (QColor(0, 220, 255, 16), 14),
            (QColor(0, 220, 255, 42), 9),
            (QColor(0, 220, 255, 105), 2.7),
        ]:
            pen = QPen(color, width)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path)



        # ===== 3) BEVEL 3D: inner highlight + inner shadow =====
        inner = QPainterPath(path)
        # vẽ inner bằng cách "thu nhỏ" rect rồi build lại (nhẹ, ổn định)
        inner_rect = QRectF(rect.adjusted(5, 5, -5, -5))
        inner_path = self._build_path(inner_rect)

        # inner highlight (cyan dịu, không trắng gắt)
        hi = QLinearGradient(rect.topLeft(), rect.bottomRight())
        hi.setColorAt(0.0, QColor(220, 255, 255, 55))
        hi.setColorAt(0.35, QColor(220, 255, 255, 12))
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


        # ===== 4) VIỀN CORE (cyan nét mảnh) =====
        core = QPen(QColor(200, 255, 255, 185), 1.1)
        core.setJoinStyle(Qt.RoundJoin)
        painter.setPen(core)
        painter.drawPath(path)

def qss_hud_metal_header_feel() -> str:
    return r"""
    /* =========================================================
   /* =========================================================
   AI METAL PASTEL (BLUE) + GREEN HOVER
   - Pastel blue nhẹ, kim loại AI (sheen + glass)
   - Gradient tối từ TRÁI -> PHẢI
   - Hover nút: xanh lá (mint/ai-green)
   - Result zone vẫn trắng
========================================================= */

/* 1) WINDOW BACKGROUND (pastel blue metal, DARK->LIGHT from LEFT to RIGHT) */
QMainWindow, QWidget {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0    rgba(150, 175, 205, 255),  /* darker pastel steel-blue (LEFT) */
        stop:0.55 rgba(175, 200, 228, 255),  /* mid pastel */
        stop:1    rgba(210, 228, 245, 255)   /* lighter ice-blue (RIGHT) */
    );
}

/* 2) DEFAULT TEXT */
QWidget {
    color: rgba(10, 25, 45, 235);
    font-size: 13px;
}

/* 3) PANELS / CARDS (metal glass: nhẹ + sheen) */
QFrame, QGroupBox {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0    rgba(245, 250, 255, 160),  /* top sheen */
        stop:0.30 rgba(220, 236, 250, 145),  /* glass body */
        stop:0.75 rgba(200, 224, 245, 135),  /* metal body */
        stop:1    rgba(185, 212, 238, 140)   /* slightly deeper */
    );
    border: 1px solid rgba(40, 110, 160, 65); /* subtle steel border */
    border-radius: 12px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: rgba(10, 25, 45, 235);
    font-weight: 900;
}

/* 4) LABEL */
QLabel {
    background: transparent;
    border: none;
    color: rgba(10, 25, 45, 235);
    font-weight: 700;
}

/* 5) INPUT / COMBO / TEXTEDIT (soft white metal) */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {
    background: rgba(252, 254, 255, 245); /* off-white (không chói) */
    border: 1px solid rgba(60, 120, 165, 85);
    border-radius: 10px;
    padding: 7px 10px;
    color: rgba(10, 25, 45, 245);
    selection-background-color: rgba(90, 210, 255, 55);
}

QLineEdit::placeholder {
    color: rgba(10, 25, 45, 145);
}

/* Focus: cyan-ish hairline (AI feel) */
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
    background: rgba(255, 255, 255, 255);
    border: 1px solid rgba(0, 220, 255, 140);
}

/* Dropdown list */
QComboBox QAbstractItemView {
    background: rgba(252, 254, 255, 255);
    border: 1px solid rgba(60, 120, 165, 85);
    color: rgba(10, 25, 45, 245);
    selection-background-color: rgba(90, 210, 255, 45);
}

/* 6) BUTTONS (metal pastel blue) */
QPushButton, QToolButton {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0    rgba(210, 230, 248, 235),  /* highlight */
        stop:0.45 rgba(170, 205, 235, 235),  /* body */
        stop:1    rgba(145, 185, 220, 235)   /* deeper */
    );
    border: 1.5px solid rgba(40, 110, 160, 85);
    border-radius: 10px;
    padding: 8px 14px;
    font-weight: 900;
    color: rgba(10, 25, 45, 235);
}

/* Hover: GREEN (mint AI) */
QPushButton:hover, QToolButton:hover {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0    rgba(230, 255, 240, 245),
        stop:0.45 rgba(165, 235, 195, 245),
        stop:1    rgba(120, 210, 165, 245)
    );
    border: 1.5px solid rgba(40, 160, 110, 120);
    color: rgba(10, 35, 25, 245);
}

/* Pressed: deeper green */
QPushButton:pressed, QToolButton:pressed {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0    rgba(200, 245, 220, 255),
        stop:0.50 rgba(130, 215, 170, 255),
        stop:1    rgba(95, 185, 140, 255)
    );
    border: 1.5px solid rgba(35, 140, 95, 150);
}

/* Disabled */
QPushButton:disabled, QToolButton:disabled {
    background: rgba(205, 220, 235, 140);
    border: 1.5px solid rgba(40, 110, 160, 45);
    color: rgba(10, 25, 45, 120);
}

/* 7) SCROLLBAR */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 4px;
}
QScrollBar::handle:vertical {
    background: rgba(40, 110, 160, 70);
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(40, 110, 160, 110);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* 8) SPLITTER HANDLE */
QSplitter::handle {
    background: rgba(40, 110, 160, 35);
}

/* 9) WHITE RESULT ZONE */
QTreeWidget, QListWidget, QTableWidget, QTextBrowser {
    background: rgba(255, 255, 255, 255);
    color: rgba(15, 23, 42, 255);
    border: 1px solid rgba(180, 190, 200, 255);
    border-radius: 10px;
    padding: 8px;
}

QHeaderView::section {
    background: rgba(245, 247, 250, 255);
    color: rgba(15, 23, 42, 255);
    padding: 8px 10px;
    border: 1px solid rgba(210, 215, 220, 255);
    font-weight: 900;
}
git add
    """


def qss_white_results() -> str:
    return r"""
    /* ===== WHITE RESULT ZONE ===== */
    QTreeWidget, QListWidget, QTableWidget, QTextBrowser {
        background: rgba(255, 255, 255, 255);
        color: rgba(15, 23, 42, 255);
        border: 1px solid rgba(180, 190, 200, 255);
        border-radius: 10px;
        padding: 8px;
    }
    QHeaderView::section {
        background: rgba(245, 247, 250, 255);
        color: rgba(15, 23, 42, 255);
        padding: 8px 10px;
        border: 1px solid rgba(210, 215, 220, 255);
        font-weight: 900;
    }
    """


