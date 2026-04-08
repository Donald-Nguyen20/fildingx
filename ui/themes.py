"""
ui/themes.py — 6 bộ màu cho toàn app.
Mỗi theme gồm:
  - name : tên hiển thị
  - hud  : dict màu cho HudPanel (vẽ bằng Python/QPainter)
  - qss  : stylesheet toàn app
"""

# ── helper ────────────────────────────────────────────────────────────────────
def _c(r, g, b, a=255):
    return (r, g, b, a)

# ── 6 THEMES ──────────────────────────────────────────────────────────────────
THEMES = [

    # ── 0) ORIGINAL: Metal Pastel Blue ────────────────────────────────────────
    {
        "name": "Metal Blue",
        "hud": {
            "base":    [_c(255,255,255,245), _c(248,250,252,245), _c(240,245,250,250)],
            "sheen":   None,
            "vig_a":   90,
            "vig_dark": False,
            "glow":    [_c(0,220,255,16), _c(0,220,255,42), _c(0,220,255,105)],
            "glow_w":  [14, 9, 2.7],
            "hi":      [_c(220,255,255,55), _c(220,255,255,12), _c(220,255,255,0)],
            "sh":      [_c(0,0,0,0), _c(0,0,0,35), _c(0,0,0,120)],
            "core":    _c(200,255,255,185),
        },
        "qss": r"""
QMainWindow, QWidget {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 rgba(55,65,85,255), stop:0.45 rgba(72,85,105,255), stop:1 rgba(95,110,130,255));
}
QWidget { color: rgba(220,230,245,235); font-size: 13px; }
QFrame, QGroupBox {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(245,250,255,160), stop:0.3 rgba(220,236,250,145),
        stop:0.75 rgba(200,224,245,135), stop:1 rgba(185,212,238,140));
    border: 1px solid rgba(40,110,160,65); border-radius: 12px;
}
QGroupBox::title { subcontrol-origin:margin; subcontrol-position:top left;
    padding:0 8px; color:rgba(220,230,245,235); font-weight:900; }
QLabel { background:transparent; border:none; color:rgba(220,230,245,235); font-weight:700; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {
    background:rgba(252,254,255,245); border:1px solid rgba(60,120,165,85);
    border-radius:10px; padding:7px 10px; color:rgba(10,25,45,245);
    selection-background-color:rgba(20,20,40,210); selection-color:rgba(255,255,255,255);
}
QLineEdit::placeholder { color:rgba(10,25,45,145); }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
    background:rgba(255,255,255,255); border:1px solid rgba(0,220,255,140);
}
QComboBox QAbstractItemView {
    background:rgba(252,254,255,255); border:1px solid rgba(60,120,165,85);
    color:rgba(10,25,45,245); selection-background-color:rgba(20,20,40,210); selection-color:rgba(255,255,255,255);
}
QPushButton, QToolButton {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(210,230,248,235), stop:0.45 rgba(170,205,235,235), stop:1 rgba(145,185,220,235));
    border:1.5px solid rgba(40,110,160,85); border-radius:10px;
    padding:8px 14px; font-weight:900; color:rgba(10,25,45,235);
}
QPushButton:hover, QToolButton:hover {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(230,255,240,245), stop:0.45 rgba(165,235,195,245), stop:1 rgba(120,210,165,245));
    border:1.5px solid rgba(40,160,110,120); color:rgba(10,35,25,245);
}
QPushButton:pressed, QToolButton:pressed {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(200,245,220,255), stop:0.5 rgba(130,215,170,255), stop:1 rgba(95,185,140,255));
    border:1.5px solid rgba(35,140,95,150);
}
QPushButton:disabled, QToolButton:disabled {
    background:rgba(205,220,235,140); border:1.5px solid rgba(40,110,160,45); color:rgba(10,25,45,120);
}
QScrollBar:vertical { background:transparent; width:10px; margin:4px; }
QScrollBar::handle:vertical { background:rgba(40,110,160,70); border-radius:5px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:rgba(40,110,160,110); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0px; }
QSplitter::handle { background:rgba(40,110,160,35); }
QTreeWidget, QListWidget, QTableWidget, QTextBrowser, QWidget#pdfContent {
    background:rgba(255,255,255,255); color:rgba(15,23,42,255);
    border:1px solid rgba(180,190,200,255); border-radius:10px; padding:8px;
}
QHeaderView::section {
    background:rgba(245,247,250,255); color:rgba(15,23,42,255);
    padding:8px 10px; border:1px solid rgba(210,215,220,255); font-weight:900;
}
""",
    },

    # ── 1) Deep Navy Gold ─────────────────────────────────────────────────────
    {
        "name": "Navy Gold",
        "hud": {
            "base":    [_c(22,28,55,250), _c(18,24,46,250), _c(14,20,38,255)],
            "sheen":   [_c(255,210,100,22), _c(255,200,80,8), _c(255,180,50,0)],
            "vig_a":   110,
            "vig_dark": True,
            "glow":    [_c(255,200,50,14), _c(255,210,80,38), _c(255,215,100,110)],
            "glow_w":  [16, 9, 2.5],
            "hi":      [_c(255,230,150,60), _c(255,215,100,15), _c(255,200,80,0)],
            "sh":      [_c(0,0,0,0), _c(0,0,0,40), _c(0,0,0,130)],
            "core":    _c(255,215,100,180),
        },
        "qss": r"""
QMainWindow, QWidget {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 rgba(15,20,42,255), stop:0.45 rgba(20,26,52,255), stop:1 rgba(25,33,65,255));
}
QWidget { color: rgba(240,225,185,235); font-size: 13px; }
QFrame, QGroupBox {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(255,220,120,38), stop:0.3 rgba(240,200,90,28),
        stop:0.75 rgba(220,175,65,22), stop:1 rgba(200,155,50,30));
    border:1px solid rgba(255,200,80,55); border-radius:12px;
}
QGroupBox::title { subcontrol-origin:margin; subcontrol-position:top left;
    padding:0 8px; color:rgba(255,230,160,245); font-weight:900; }
QLabel { background:transparent; border:none; color:rgba(240,225,185,235); font-weight:700; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {
    background:rgba(12,16,34,235); border:1px solid rgba(255,200,80,70);
    border-radius:10px; padding:7px 10px; color:rgba(240,225,185,245);
    selection-background-color:rgba(20,20,40,230); selection-color:rgba(255,255,255,255);
}
QLineEdit::placeholder { color:rgba(240,225,185,100); }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
    background:rgba(18,24,48,250); border:1px solid rgba(255,215,0,180);
}
QComboBox QAbstractItemView {
    background:rgba(20,26,52,255); border:1px solid rgba(255,200,80,70);
    color:rgba(240,225,185,245); selection-background-color:rgba(20,20,40,230); selection-color:rgba(255,255,255,255);
}
QPushButton, QToolButton {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(255,225,130,230), stop:0.45 rgba(240,195,85,230), stop:1 rgba(215,165,50,230));
    border:1.5px solid rgba(200,150,40,120); border-radius:10px;
    padding:8px 14px; font-weight:900; color:rgba(20,15,5,240);
}
QPushButton:hover, QToolButton:hover {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(255,240,170,245), stop:0.45 rgba(255,210,100,245), stop:1 rgba(230,175,60,245));
    border:1.5px solid rgba(255,215,0,160); color:rgba(15,10,0,245);
}
QPushButton:pressed, QToolButton:pressed {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(220,175,70,255), stop:0.5 rgba(195,148,45,255), stop:1 rgba(170,125,30,255));
    border:1.5px solid rgba(180,135,30,160);
}
QPushButton:disabled, QToolButton:disabled {
    background:rgba(60,55,40,120); border:1.5px solid rgba(120,100,50,60); color:rgba(180,160,110,100);
}
QScrollBar:vertical { background:transparent; width:10px; margin:4px; }
QScrollBar::handle:vertical { background:rgba(255,200,80,65); border-radius:5px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:rgba(255,215,0,110); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0px; }
QSplitter::handle { background:rgba(255,200,80,30); }
QTreeWidget, QListWidget, QTableWidget, QTextBrowser, QWidget#pdfContent {
    background:rgba(12,16,34,245); color:rgba(235,220,175,255);
    border:1px solid rgba(255,200,80,60); border-radius:10px; padding:8px;
}
QHeaderView::section {
    background:rgba(22,28,55,255); color:rgba(255,215,100,245);
    padding:8px 10px; border:1px solid rgba(255,200,80,50); font-weight:900;
}
""",
    },

    # ── 2) Obsidian Emerald ───────────────────────────────────────────────────
    {
        "name": "Emerald",
        "hud": {
            "base":    [_c(10,16,14,255), _c(12,20,17,255), _c(8,14,12,255)],
            "sheen":   [_c(0,200,100,20), _c(0,180,80,8), _c(0,150,60,0)],
            "vig_a":   130,
            "vig_dark": True,
            "glow":    [_c(0,200,100,14), _c(0,220,110,38), _c(0,255,136,115)],
            "glow_w":  [16, 9, 2.5],
            "hi":      [_c(100,255,180,55), _c(60,220,140,14), _c(0,180,100,0)],
            "sh":      [_c(0,0,0,0), _c(0,0,0,45), _c(0,0,0,140)],
            "core":    _c(0,255,136,175),
        },
        "qss": r"""
QMainWindow, QWidget {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 rgba(10,14,12,255), stop:0.45 rgba(13,19,16,255), stop:1 rgba(16,24,20,255));
}
QWidget { color: rgba(185,235,210,230); font-size: 13px; }
QFrame, QGroupBox {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(0,200,100,30), stop:0.3 rgba(0,180,85,20),
        stop:0.75 rgba(0,155,70,16), stop:1 rgba(0,135,60,24));
    border:1px solid rgba(0,220,110,50); border-radius:12px;
}
QGroupBox::title { subcontrol-origin:margin; subcontrol-position:top left;
    padding:0 8px; color:rgba(120,255,180,245); font-weight:900; }
QLabel { background:transparent; border:none; color:rgba(185,235,210,230); font-weight:700; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {
    background:rgba(6,10,8,235); border:1px solid rgba(0,220,110,65);
    border-radius:10px; padding:7px 10px; color:rgba(185,235,210,245);
    selection-background-color:rgba(20,20,40,230); selection-color:rgba(255,255,255,255);
}
QLineEdit::placeholder { color:rgba(185,235,210,90); }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
    background:rgba(8,14,11,250); border:1px solid rgba(0,255,136,180);
}
QComboBox QAbstractItemView {
    background:rgba(10,16,13,255); border:1px solid rgba(0,220,110,65);
    color:rgba(185,235,210,245); selection-background-color:rgba(20,20,40,230); selection-color:rgba(255,255,255,255);
}
QPushButton, QToolButton {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(60,200,130,220), stop:0.45 rgba(30,175,105,220), stop:1 rgba(10,150,85,220));
    border:1.5px solid rgba(0,180,90,110); border-radius:10px;
    padding:8px 14px; font-weight:900; color:rgba(5,20,12,245);
}
QPushButton:hover, QToolButton:hover {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(100,255,175,240), stop:0.45 rgba(55,230,145,240), stop:1 rgba(20,200,115,240));
    border:1.5px solid rgba(0,255,136,160); color:rgba(2,14,8,245);
}
QPushButton:pressed, QToolButton:pressed {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(30,165,100,255), stop:0.5 rgba(15,140,80,255), stop:1 rgba(5,115,60,255));
    border:1.5px solid rgba(0,160,80,160);
}
QPushButton:disabled, QToolButton:disabled {
    background:rgba(20,40,28,110); border:1.5px solid rgba(0,120,60,50); color:rgba(100,160,120,90);
}
QScrollBar:vertical { background:transparent; width:10px; margin:4px; }
QScrollBar::handle:vertical { background:rgba(0,200,100,60); border-radius:5px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:rgba(0,255,136,105); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0px; }
QSplitter::handle { background:rgba(0,200,100,28); }
QTreeWidget, QListWidget, QTableWidget, QTextBrowser, QWidget#pdfContent {
    background:rgba(6,10,8,245); color:rgba(185,235,210,255);
    border:1px solid rgba(0,200,100,55); border-radius:10px; padding:8px;
}
QHeaderView::section {
    background:rgba(10,16,13,255); color:rgba(80,255,160,245);
    padding:8px 10px; border:1px solid rgba(0,200,100,45); font-weight:900;
}
""",
    },

    # ── 3) Midnight Violet ────────────────────────────────────────────────────
    {
        "name": "Violet",
        "hud": {
            "base":    [_c(22,10,45,255), _c(28,14,58,255), _c(18,8,38,255)],
            "sheen":   [_c(140,80,255,22), _c(120,60,220,9), _c(100,40,180,0)],
            "vig_a":   130,
            "vig_dark": True,
            "glow":    [_c(130,60,255,14), _c(150,80,255,40), _c(170,100,255,118)],
            "glow_w":  [16, 9, 2.5],
            "hi":      [_c(200,160,255,58), _c(170,120,255,15), _c(140,90,255,0)],
            "sh":      [_c(0,0,0,0), _c(0,0,0,48), _c(0,0,0,145)],
            "core":    _c(155,90,255,180),
        },
        "qss": r"""
QMainWindow, QWidget {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 rgba(20,10,42,255), stop:0.45 rgba(26,13,54,255), stop:1 rgba(32,16,65,255));
}
QWidget { color: rgba(215,200,255,230); font-size: 13px; }
QFrame, QGroupBox {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(140,80,255,32), stop:0.3 rgba(120,60,230,22),
        stop:0.75 rgba(100,45,200,17), stop:1 rgba(85,35,175,25));
    border:1px solid rgba(155,90,255,52); border-radius:12px;
}
QGroupBox::title { subcontrol-origin:margin; subcontrol-position:top left;
    padding:0 8px; color:rgba(200,170,255,245); font-weight:900; }
QLabel { background:transparent; border:none; color:rgba(215,200,255,230); font-weight:700; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {
    background:rgba(14,7,30,238); border:1px solid rgba(155,90,255,68);
    border-radius:10px; padding:7px 10px; color:rgba(215,200,255,245);
    selection-background-color:rgba(20,20,40,230); selection-color:rgba(255,255,255,255);
}
QLineEdit::placeholder { color:rgba(215,200,255,90); }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
    background:rgba(18,10,38,252); border:1px solid rgba(180,130,255,185);
}
QComboBox QAbstractItemView {
    background:rgba(18,9,38,255); border:1px solid rgba(155,90,255,65);
    color:rgba(215,200,255,245); selection-background-color:rgba(20,20,40,230); selection-color:rgba(255,255,255,255);
}
QPushButton, QToolButton {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(175,130,255,220), stop:0.45 rgba(145,100,240,220), stop:1 rgba(115,72,210,220));
    border:1.5px solid rgba(130,80,230,115); border-radius:10px;
    padding:8px 14px; font-weight:900; color:rgba(12,6,28,245);
}
QPushButton:hover, QToolButton:hover {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(210,175,255,242), stop:0.45 rgba(175,130,255,242), stop:1 rgba(140,95,235,242));
    border:1.5px solid rgba(180,130,255,165); color:rgba(8,4,20,245);
}
QPushButton:pressed, QToolButton:pressed {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(120,80,210,255), stop:0.5 rgba(95,60,185,255), stop:1 rgba(72,42,160,255));
    border:1.5px solid rgba(110,70,200,165);
}
QPushButton:disabled, QToolButton:disabled {
    background:rgba(40,25,70,110); border:1.5px solid rgba(90,55,150,50); color:rgba(140,110,200,90);
}
QScrollBar:vertical { background:transparent; width:10px; margin:4px; }
QScrollBar::handle:vertical { background:rgba(155,90,255,62); border-radius:5px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:rgba(180,130,255,110); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0px; }
QSplitter::handle { background:rgba(155,90,255,28); }
QTreeWidget, QListWidget, QTableWidget, QTextBrowser, QWidget#pdfContent {
    background:rgba(14,7,30,246); color:rgba(215,200,255,255);
    border:1px solid rgba(155,90,255,58); border-radius:10px; padding:8px;
}
QHeaderView::section {
    background:rgba(20,10,42,255); color:rgba(190,150,255,245);
    padding:8px 10px; border:1px solid rgba(155,90,255,48); font-weight:900;
}
""",
    },

    # ── 4) Carbon Rose Gold ───────────────────────────────────────────────────
    {
        "name": "Rose Gold",
        "hud": {
            "base":    [_c(22,18,22,255), _c(28,23,27,255), _c(18,14,18,255)],
            "sheen":   [_c(232,160,130,22), _c(210,140,110,9), _c(185,115,90,0)],
            "vig_a":   135,
            "vig_dark": True,
            "glow":    [_c(220,140,110,14), _c(235,155,125,40), _c(248,175,148,115)],
            "glow_w":  [16, 9, 2.5],
            "hi":      [_c(255,210,190,58), _c(235,180,158,15), _c(210,155,130,0)],
            "sh":      [_c(0,0,0,0), _c(0,0,0,50), _c(0,0,0,148)],
            "core":    _c(232,165,140,178),
        },
        "qss": r"""
QMainWindow, QWidget {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 rgba(20,16,20,255), stop:0.45 rgba(26,21,25,255), stop:1 rgba(32,26,30,255));
}
QWidget { color: rgba(245,228,218,230); font-size: 13px; }
QFrame, QGroupBox {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(232,155,125,30), stop:0.3 rgba(210,135,108,20),
        stop:0.75 rgba(188,115,92,16), stop:1 rgba(168,98,78,24));
    border:1px solid rgba(232,160,135,50); border-radius:12px;
}
QGroupBox::title { subcontrol-origin:margin; subcontrol-position:top left;
    padding:0 8px; color:rgba(248,210,192,245); font-weight:900; }
QLabel { background:transparent; border:none; color:rgba(245,228,218,230); font-weight:700; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {
    background:rgba(14,10,12,238); border:1px solid rgba(220,150,125,68);
    border-radius:10px; padding:7px 10px; color:rgba(245,228,218,245);
    selection-background-color:rgba(20,20,40,230); selection-color:rgba(255,255,255,255);
}
QLineEdit::placeholder { color:rgba(245,228,218,88); }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
    background:rgba(18,13,16,252); border:1px solid rgba(248,185,165,188);
}
QComboBox QAbstractItemView {
    background:rgba(18,14,16,255); border:1px solid rgba(220,150,125,65);
    color:rgba(245,228,218,245); selection-background-color:rgba(20,20,40,230); selection-color:rgba(255,255,255,255);
}
QPushButton, QToolButton {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(240,185,162,222), stop:0.45 rgba(218,155,130,222), stop:1 rgba(192,125,102,222));
    border:1.5px solid rgba(195,128,105,115); border-radius:10px;
    padding:8px 14px; font-weight:900; color:rgba(28,12,8,245);
}
QPushButton:hover, QToolButton:hover {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(255,215,198,242), stop:0.45 rgba(240,185,165,242), stop:1 rgba(215,155,135,242));
    border:1.5px solid rgba(240,175,155,165); color:rgba(22,8,5,245);
}
QPushButton:pressed, QToolButton:pressed {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(185,120,98,255), stop:0.5 rgba(162,100,80,255), stop:1 rgba(138,80,62,255));
    border:1.5px solid rgba(165,105,85,165);
}
QPushButton:disabled, QToolButton:disabled {
    background:rgba(48,35,32,110); border:1.5px solid rgba(130,85,70,50); color:rgba(185,148,132,88);
}
QScrollBar:vertical { background:transparent; width:10px; margin:4px; }
QScrollBar::handle:vertical { background:rgba(220,150,125,62); border-radius:5px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:rgba(245,180,158,112); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0px; }
QSplitter::handle { background:rgba(220,150,125,28); }
QTreeWidget, QListWidget, QTableWidget, QTextBrowser, QWidget#pdfContent {
    background:rgba(14,10,12,246); color:rgba(245,228,218,255);
    border:1px solid rgba(220,150,125,55); border-radius:10px; padding:8px;
}
QHeaderView::section {
    background:rgba(20,16,18,255); color:rgba(240,185,162,245);
    padding:8px 10px; border:1px solid rgba(210,140,115,48); font-weight:900;
}
""",
    },

    # ── 5) Arctic Frost ───────────────────────────────────────────────────────
    {
        "name": "Arctic",
        "hud": {
            "base":    [_c(235,242,252,255), _c(225,235,250,255), _c(212,226,246,255)],
            "sheen":   [_c(255,255,255,120), _c(220,238,255,55), _c(190,220,255,0)],
            "vig_a":   30,
            "vig_dark": False,
            "glow":    [_c(0,140,255,16), _c(0,160,255,42), _c(0,185,255,120)],
            "glow_w":  [16, 9, 2.5],
            "hi":      [_c(255,255,255,200), _c(220,238,255,60), _c(190,220,255,0)],
            "sh":      [_c(0,60,130,0), _c(0,60,130,25), _c(0,60,130,70)],
            "core":    _c(0,160,255,160),
        },
        "qss": r"""
QMainWindow, QWidget {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 rgba(228,238,252,255), stop:0.45 rgba(218,230,248,255), stop:1 rgba(205,222,244,255));
}
QWidget { color: rgba(15,35,75,225); font-size: 13px; }
QFrame, QGroupBox {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(255,255,255,175), stop:0.3 rgba(240,248,255,155),
        stop:0.75 rgba(220,238,255,140), stop:1 rgba(205,228,252,148));
    border:1px solid rgba(0,150,255,55); border-radius:12px;
}
QGroupBox::title { subcontrol-origin:margin; subcontrol-position:top left;
    padding:0 8px; color:rgba(10,50,120,245); font-weight:900; }
QLabel { background:transparent; border:none; color:rgba(15,35,75,225); font-weight:700; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {
    background:rgba(255,255,255,245); border:1px solid rgba(0,150,255,72);
    border-radius:10px; padding:7px 10px; color:rgba(10,30,70,245);
    selection-background-color:rgba(20,20,40,210); selection-color:rgba(255,255,255,255);
}
QLineEdit::placeholder { color:rgba(10,30,70,95); }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
    background:rgba(255,255,255,255); border:1px solid rgba(0,170,255,188);
}
QComboBox QAbstractItemView {
    background:rgba(245,250,255,255); border:1px solid rgba(0,150,255,68);
    color:rgba(10,30,70,245); selection-background-color:rgba(20,20,40,210); selection-color:rgba(255,255,255,255);
}
QPushButton, QToolButton {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(120,195,255,228), stop:0.45 rgba(70,165,248,228), stop:1 rgba(30,138,235,228));
    border:1.5px solid rgba(0,130,220,115); border-radius:10px;
    padding:8px 14px; font-weight:900; color:rgba(255,255,255,248);
}
QPushButton:hover, QToolButton:hover {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(165,218,255,242), stop:0.45 rgba(100,188,255,242), stop:1 rgba(50,158,248,242));
    border:1.5px solid rgba(0,170,255,165); color:rgba(255,255,255,255);
}
QPushButton:pressed, QToolButton:pressed {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(20,115,210,255), stop:0.5 rgba(10,95,188,255), stop:1 rgba(5,75,165,255));
    border:1.5px solid rgba(0,110,195,165);
}
QPushButton:disabled, QToolButton:disabled {
    background:rgba(190,215,240,130); border:1.5px solid rgba(0,120,200,55); color:rgba(80,120,175,105);
}
QScrollBar:vertical { background:transparent; width:10px; margin:4px; }
QScrollBar::handle:vertical { background:rgba(0,150,255,62); border-radius:5px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:rgba(0,180,255,112); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0px; }
QSplitter::handle { background:rgba(0,150,255,30); }
QTreeWidget, QListWidget, QTableWidget, QTextBrowser, QWidget#pdfContent {
    background:rgba(255,255,255,252); color:rgba(10,28,65,255);
    border:1px solid rgba(0,150,255,58); border-radius:10px; padding:8px;
}
QHeaderView::section {
    background:rgba(235,245,255,255); color:rgba(10,60,145,245);
    padding:8px 10px; border:1px solid rgba(0,140,235,50); font-weight:900;
}
""",
    },
]

# Index theme đang active (lưu giữa các lần đổi)
_current_index = 0

def get_current() -> dict:
    return THEMES[_current_index]

def get_index() -> int:
    return _current_index

def set_index(i: int):
    global _current_index
    _current_index = i % len(THEMES)

def next_theme() -> dict:
    global _current_index
    _current_index = (_current_index + 1) % len(THEMES)
    return THEMES[_current_index]
