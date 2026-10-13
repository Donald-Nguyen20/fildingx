"""
ui/themes.py — 7 bộ màu cho toàn app.
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
        "light_page": True,   # dark frame, white page
        "ink":  "#0A192D",   # icon colour on buttons, matches this theme's button text
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
        "ink":  "#140F05",   # icon colour on buttons, matches this theme's button text
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
        "ink":  "#05140C",   # icon colour on buttons, matches this theme's button text
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
        "ink":  "#0C061C",   # icon colour on buttons, matches this theme's button text
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
        "ink":  "#1C0C08",   # icon colour on buttons, matches this theme's button text
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
        "light_page": True,   # dark frame, white page
        "light_bar": True,    # ... and a near-white window behind the tabs
        #: The shared rail is a desaturated grey beside this theme's saturated
        #: ice; these two stops sit at hue 209/208, between the window's 214
        #: and the accent's 196-207, so the rail belongs to both. Solid rather
        #: than the shared rgba(...,180), which only let the pale window show
        #: through and washed it out.
        "chrome": {
            "sidebar": """
            QFrame#sidebar {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 rgba(19,57,92,255), stop:1 rgba(11,39,64,255));
                border: none;
                border-radius: 10px;
            }
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 8px;
                color: rgba(220,230,255,200);
                padding-top: 6px;
            }
            QPushButton:hover {
                background: rgba(125,211,252,45);
                border: 1px solid rgba(125,211,252,90);
                color: white;
            }
            QPushButton:checked {
                background: rgba(40,180,110,50);
                border-left: 3px solid rgba(60,210,140,220);
                color: white;
            }
        """,
        },
        "ink":  "#FFFFFF",   # icon colour on buttons, matches this theme's button text
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

    # ── 6) Ghost Purple ───────────────────────────────────────────────────────
    {
        "name": "Ghost Purple",
        "ink":  "#140C22",   # icon colour on buttons, matches this theme's button text
        "hud": {
            "base":    [_c(26,22,38,255), _c(32,27,46,255), _c(21,17,31,255)],
            "sheen":   [_c(190,150,255,24), _c(170,130,245,9), _c(150,110,225,0)],
            "vig_a":   126,
            "vig_dark": True,
            "glow":    [_c(166,111,245,14), _c(185,140,250,40), _c(201,169,245,120)],
            "glow_w":  [16, 9, 2.5],
            "hi":      [_c(215,190,255,60), _c(190,160,250,15), _c(166,120,245,0)],
            "sh":      [_c(0,0,0,0), _c(0,0,0,48), _c(0,0,0,145)],
            "core":    _c(190,150,255,182),
        },
        "qss": r"""
QMainWindow, QWidget {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 rgba(24,20,36,255), stop:0.45 rgba(30,25,46,255), stop:1 rgba(36,30,56,255));
}
QWidget { color: rgba(224,214,250,232); font-size: 13px; }
QFrame, QGroupBox {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(166,111,245,30), stop:0.3 rgba(150,100,235,21),
        stop:0.75 rgba(132,88,215,16), stop:1 rgba(118,78,195,24));
    border:1px solid rgba(190,150,255,50); border-radius:12px;
}
QGroupBox::title { subcontrol-origin:margin; subcontrol-position:top left;
    padding:0 8px; color:rgba(210,185,255,245); font-weight:900; }
QLabel { background:transparent; border:none; color:rgba(224,214,250,232); font-weight:700; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {
    background:rgba(18,14,28,238); border:1px solid rgba(190,150,255,64);
    border-radius:10px; padding:7px 10px; color:rgba(224,214,250,246);
    selection-background-color:rgba(20,20,40,230); selection-color:rgba(255,255,255,255);
}
QLineEdit::placeholder { color:rgba(224,214,250,92); }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
    background:rgba(22,17,34,252); border:1px solid rgba(201,169,245,190);
}
QComboBox QAbstractItemView {
    background:rgba(22,17,34,255); border:1px solid rgba(190,150,255,62);
    color:rgba(224,214,250,246); selection-background-color:rgba(20,20,40,230); selection-color:rgba(255,255,255,255);
}
QPushButton, QToolButton {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(201,169,245,224), stop:0.45 rgba(178,138,240,224), stop:1 rgba(150,108,225,224));
    border:1.5px solid rgba(160,115,235,118); border-radius:10px;
    padding:8px 14px; font-weight:900; color:rgba(20,12,34,246);
}
QPushButton:hover, QToolButton:hover {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(224,200,255,244), stop:0.45 rgba(196,160,255,244), stop:1 rgba(166,120,248,244));
    border:1.5px solid rgba(201,169,245,170); color:rgba(14,8,26,246);
}
QPushButton:pressed, QToolButton:pressed {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(140,96,228,255), stop:0.5 rgba(120,74,205,255), stop:1 rgba(109,40,217,255));
    border:1.5px solid rgba(125,82,215,170);
}
QPushButton:disabled, QToolButton:disabled {
    background:rgba(44,32,64,112); border:1.5px solid rgba(100,68,160,52); color:rgba(160,135,210,92);
}
QScrollBar:vertical { background:transparent; width:10px; margin:4px; }
QScrollBar::handle:vertical { background:rgba(190,150,255,62); border-radius:5px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:rgba(201,169,245,112); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0px; }
QSplitter::handle { background:rgba(190,150,255,28); }
QTreeWidget, QListWidget, QTableWidget, QTextBrowser, QWidget#pdfContent {
    background:rgba(18,14,28,246); color:rgba(224,214,250,255);
    border:1px solid rgba(190,150,255,56); border-radius:10px; padding:8px;
}
QHeaderView::section {
    background:rgba(24,19,36,255); color:rgba(201,169,245,245);
    padding:8px 10px; border:1px solid rgba(190,150,255,46); font-weight:900;
}
""",
    },

    # -- 7) Daylight: white canvas, emerald actions, sky navigation ------------
    {
        "name": "Daylight",
        "light": True,
        "light_page": True,
        "ink":  "#13263D",   # icon colour on buttons, matches this theme's button text
        "hud": {
            "base":    [_c(255,255,255,250), _c(248,251,254,250), _c(238,245,252,252)],
            "sheen":   None,
            "vig_a":   55,
            "vig_dark": False,
            "glow":    [_c(16,185,129,16), _c(16,185,129,40), _c(16,185,129,100)],
            "glow_w":  [14, 9, 2.7],
            "hi":      [_c(255,255,255,70), _c(255,255,255,16), _c(255,255,255,0)],
            "sh":      [_c(0,0,0,0), _c(30,50,75,28), _c(30,50,75,90)],
            "core":    _c(190,250,225,195),
        },
        "qss": r"""
QMainWindow, QWidget {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 rgba(248,251,254,255), stop:0.5 rgba(241,246,252,255), stop:1 rgba(232,240,249,255));
}
QWidget { color: rgba(17,32,51,235); font-size: 13px; }
QFrame, QGroupBox {
    background: rgba(255,255,255,255);
    border: 1px solid rgba(206,220,236,255); border-radius: 12px;
}
QGroupBox::title { subcontrol-origin:margin; subcontrol-position:top left;
    padding:0 8px; color:rgba(17,32,51,235); font-weight:900; }
QLabel { background:transparent; border:none; color:rgba(17,32,51,235); font-weight:700; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {
    background:rgba(255,255,255,255); border:1px solid rgba(206,220,236,255);
    border-radius:10px; padding:7px 10px; color:rgba(13,26,43,255);
    selection-background-color:rgba(16,185,129,215); selection-color:rgba(255,255,255,255);
}
QLineEdit::placeholder { color:rgba(109,128,150,190); }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
    background:rgba(255,255,255,255); border:1px solid rgba(16,185,129,230);
}
QComboBox QAbstractItemView {
    background:rgba(255,255,255,255); border:1px solid rgba(206,220,236,255);
    color:rgba(13,26,43,255); selection-background-color:rgba(16,185,129,215); selection-color:rgba(255,255,255,255);
}
QPushButton, QToolButton {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(255,255,255,255), stop:1 rgba(238,244,251,255));
    border:1.5px solid rgba(201,216,233,255); border-radius:10px;
    padding:8px 14px; font-weight:900; color:rgba(19,38,61,255);
}
QPushButton:hover, QToolButton:hover {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(226,252,241,255), stop:1 rgba(190,242,220,255));
    border:1.5px solid rgba(16,185,129,200); color:rgba(6,78,59,255);
}
QPushButton:pressed, QToolButton:pressed {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(167,235,208,255), stop:1 rgba(110,219,180,255));
    border:1.5px solid rgba(5,150,105,230); color:rgba(5,60,45,255);
}
QPushButton:disabled, QToolButton:disabled {
    background:rgba(241,245,250,255); border:1.5px solid rgba(217,227,238,255); color:rgba(148,163,184,255);
}
QScrollBar:vertical { background:transparent; width:10px; margin:4px; }
QScrollBar::handle:vertical { background:rgba(148,172,198,110); border-radius:5px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:rgba(16,185,129,190); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0px; }
QSplitter::handle { background:rgba(210,224,239,255); }
QTreeWidget, QListWidget, QTableWidget, QTextBrowser, QWidget#pdfContent {
    background:rgba(255,255,255,255); color:rgba(15,23,42,255);
    border:1px solid rgba(214,226,240,255); border-radius:10px; padding:8px;
}
QHeaderView::section {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(250,252,255,255), stop:1 rgba(240,246,252,255));
    color:rgba(30,58,92,255); padding:8px 10px;
    border:none; border-right:1px solid rgba(226,235,245,255);
    border-bottom:2px solid rgba(14,165,233,160); font-weight:900;
}
""",
    },
]

# Index theme đang active (lưu giữa các lần đổi)
# Arctic: a near-white window framing a white page, its own deep glacier rail,
# and tab inks measured against that window rather than inherited from the dark
# chrome. Metal Blue is still here at @colour0 and Daylight at @colour7.
_current_index = 5

def get_current() -> dict:
    return THEMES[_current_index]

def ink() -> str:
    """Icon colour for the active theme — see ui/icons.py."""
    return THEMES[_current_index]["ink"]


def get_index() -> int:
    return _current_index

def set_index(i: int):
    global _current_index
    _current_index = i % len(THEMES)

def next_theme() -> dict:
    global _current_index
    _current_index = (_current_index + 1) % len(THEMES)
    return THEMES[_current_index]


# -- Chrome ------------------------------------------------------------------
# Six surfaces the theme QSS cannot reach. Each sets its own stylesheet when it
# is built, and a widget's own stylesheet beats the one on main_widget, so a
# rule in "qss" above loses to it. They were all written against a dark window
# -- white at 3-6% alpha, pale blue captions -- which is invisible on a light
# one, so a light theme has to supply its own set.
#
# _CHROME_DARK repeats, character for character, what those six widgets have
# always carried. Themes 0-6 therefore render exactly as before; only a theme
# marked "light": True gets the other set.

_CHROME_DARK = {
    "toolbar": """
            QFrame#toolbarFrame {
                background: rgba(255,255,255,8);
                border: 1px solid rgba(255,255,255,15);
                border-radius: 8px;
            }
        """,
    "sidebar": """
            QFrame#sidebar {
                background: rgba(30,40,60,180);
                border-radius: 8px;
            }
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 8px;
                color: rgba(220,230,255,200);
                padding-top: 6px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,25);
                border: 1px solid rgba(255,255,255,60);
                color: white;
            }
            QPushButton:checked {
                background: rgba(40,180,110,50);
                border-left: 3px solid rgba(60,210,140,220);
                color: white;
            }
        """,
    "tabs": """
            QTabWidget::pane { border: none; }
            QTabBar::tab {
                background: rgba(255,255,255,10);
                color: rgba(220,230,255,180);
                padding: 6px 18px;
                border-radius: 4px;
                margin-right: 2px;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background: rgba(40,180,110,50);
                color: white;
                border-bottom: 2px solid rgba(60,210,140,220);
            }
            QTabBar::tab:hover { background: rgba(255,255,255,20); }
        """,
    "splitter": "QSplitter::handle { background: rgba(255,255,255,15); border-radius: 2px; }",
    "tree": """
            QTreeWidget { outline:0; selection-background-color: transparent; }
            QTreeWidget::item:hover                   { background: rgba(0,120,215,25); }
            QTreeWidget::item:selected:active,
            QTreeWidget::item:selected:focus          { background: rgba(0,120,215,170); color:white; }
            QTreeWidget::item:selected:!active        { background: rgba(0,120,215,80);  color:black; }
            QTreeWidget::item:focus                   { outline: none; }
        """,
    "separator": "color: rgba(255,255,255,40);",
    "sidebar_caption": "color: rgba(200,220,255,200);",
    "nb_check_all": """
            QPushButton {
                background: #1e3a5f; color: #93c5fd;
                border: 1px solid #3b82f6; border-radius: 6px;
                font-size: 12px; padding: 0 10px;
            }
            QPushButton:hover   { background: #2a4f80; color: #bfdbfe; }
            QPushButton:pressed { background: #1a3050; }
            QPushButton:disabled { background: #1a2535; color: #4a6080; border-color: #2a3a4a; }
        """,
    #: The NotebookLM tab's own labels -- they sit on the panel, not on the
    #: white page inside it, so they follow the frame like the rest of this dict.
    "nb_label":       "#89b4fa",
    "nb_label_muted": "#a6adc8",
    "tab_ink": ("#DCE6FF", "#FFFFFF"),
}

#: The rail stays dark on the light theme too. It is the one surface that reads
#: as navigation rather than content, and its active state is already the
#: emerald this palette builds on. Only the translucency goes: 180/255 of a dark
#: blue over a near-white window washes out to grey.
_CHROME_LIGHT = {
    "toolbar": """
            QFrame#toolbarFrame {
                background: rgba(255,255,255,255);
                border: 1px solid rgba(206,220,236,255);
                border-radius: 10px;
            }
        """,
    "sidebar": """
            QFrame#sidebar {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 rgba(26,38,56,255), stop:1 rgba(19,29,45,255));
                border: none;
                border-radius: 10px;
            }
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 8px;
                color: rgba(220,230,255,200);
                padding-top: 6px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,28);
                border: 1px solid rgba(255,255,255,65);
                color: white;
            }
            QPushButton:checked {
                background: rgba(16,185,129,60);
                border-left: 3px solid rgba(52,211,153,235);
                color: white;
            }
        """,
    "tabs": """
            QTabWidget::pane { border: none; }
            QTabBar::tab {
                background: rgba(255,255,255,0);
                color: rgba(88,106,130,255);
                padding: 6px 18px;
                border-radius: 4px;
                margin-right: 2px;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background: rgba(255,255,255,255);
                color: rgba(12,74,110,255);
                border-bottom: 2px solid rgba(14,165,233,230);
            }
            QTabBar::tab:hover { background: rgba(14,165,233,28); }
        """,
    "splitter": "QSplitter::handle { background: rgba(203,219,236,255); border-radius: 2px; }",
    "tree": """
            QTreeWidget { outline:0; selection-background-color: transparent; }
            QTreeWidget::item:hover                   { background: rgba(14,165,233,28); }
            QTreeWidget::item:selected:active,
            QTreeWidget::item:selected:focus          { background: rgba(16,185,129,185); color:white; }
            QTreeWidget::item:selected:!active        { background: rgba(16,185,129,70);  color:rgba(6,60,45,255); }
            QTreeWidget::item:focus                   { outline: none; }
        """,
    "separator": "color: rgba(17,32,51,55);",
    "sidebar_caption": "color: rgba(200,220,255,200);",
    "nb_check_all": """
            QPushButton {
                background: #E0F2FE; color: #075985;
                border: 1px solid #7DD3FC; border-radius: 6px;
                font-size: 12px; padding: 0 10px;
            }
            QPushButton:hover   { background: #BAE6FD; color: #0C4A6E; }
            QPushButton:pressed { background: #7DD3FC; }
            QPushButton:disabled { background: #F1F5F9; color: #94A3B8; border-color: #E2E8F0; }
        """,
    "nb_label":       "#1D4ED8",
    "nb_label_muted": "#64748B",
    "tab_ink": ("#5A6A82", "#0C4A6E"),
}



# -- The content page -------------------------------------------------------
# A theme's frame and its content page are coloured independently: Metal Blue
# and Arctic both draw a dark-ish gradient around a white QTextEdit and a white
# tree. The chat transcript writes its colours straight into HTML, so they have
# to follow the page the text lands on rather than the frame around it --
# measured per theme from the QLineEdit/QTextEdit rule in "qss".

_PAGE_DARK = {
    "nb_list": """
            QTreeWidget { font-size: 15px; }
            QTreeWidget::item { padding: 4px 2px; }
            QTreeWidget::item:selected { background: #313244; }
        """,
    "nb_blue":  "#89b4fa",
    "nb_green": "#a6e3a1",
    "nb_red":   "#f38ba8",
    "nb_muted": "#a6adc8",
}

_PAGE_LIGHT = {
    "nb_list": """
            QTreeWidget { font-size: 15px; }
            QTreeWidget::item { padding: 4px 2px; }
            QTreeWidget::item:selected { background: rgba(16,185,129,185); color: white; }
        """,
    #: Role inks for the chat transcript, picked for a white page: every one
    #: clears 4.5:1 on #FFFFFF, where the dark set above sits near 2:1.
    "nb_blue":  "#1D4ED8",
    "nb_green": "#047857",
    "nb_red":   "#BE123C",
    "nb_muted": "#64748B",
}


# -- The tab bar ------------------------------------------------------------
# A third surface, and not answered by either of the other two: Arctic frames a
# white page in a near-white window while claiming to be a dark theme, so the
# strip its tab labels are read against is light even though is_light() says
# the frame is not. The inks below are measured from that window, rgb(228,238,
# 252): the idle one reads at 9.8:1 on it, where the dark chrome's pale blue
# reads at 1.05.

_BAR_LIGHT = {
    #: The deep navy keeps the tabs inside Arctic's own blue family rather than
    #: dropping a neutral slate into it. Selected gains a solid white face, so
    #: its ink is measured against white, not against the window. The base rule
    #: carries a transparent border so that gaining one on hover or on select
    #: does not change the tab's height and nudge the bar.
    "tabs": """
            QTabWidget::pane { border: none; }
            QTabBar::tab {
                background: rgba(255,255,255,0);
                color: rgba(30,58,95,255);
                padding: 6px 18px;
                border-radius: 4px;
                border-bottom: 2px solid transparent;
                margin-right: 2px;
                font-size: 12px;
            }
            QTabBar::tab:hover {
                background: rgba(14,165,233,70);
                border-bottom: 2px solid rgba(14,165,233,120);
            }
            QTabBar::tab:selected {
                background: rgba(255,255,255,255);
                color: rgba(12,74,110,255);
                border-bottom: 2px solid rgba(14,165,233,230);
            }
        """,
    "tab_ink": ("#1E3A5F", "#0C4A6E"),
}


def is_light(index: int = None) -> bool:
    """True when the theme paints on a light window rather than a dark one."""
    i = _current_index if index is None else index % len(THEMES)
    return bool(THEMES[i].get("light"))


def light_page(index: int = None) -> bool:
    """True when text views and trees sit on a light surface in this theme.

    Not the same question as is_light(): Metal Blue and Arctic frame a white
    page in a dark gradient, so they answer True here and False there.
    """
    i = _current_index if index is None else index % len(THEMES)
    return bool(THEMES[i].get("light_page"))


def light_bar(index: int = None) -> bool:
    """True when the window behind the tab bar is a light surface.

    A third question again, and not answered by either of the others: Arctic
    paints a near-white window without claiming to be a light theme. Themes
    that are light all the way through need no flag -- is_light() already sends
    them to the light chrome.
    """
    i = _current_index if index is None else index % len(THEMES)
    return bool(THEMES[i].get("light_bar"))


def chrome(index: int = None) -> dict:
    """Stylesheets for the widgets that carry their own, outside the theme QSS.

    Three surfaces, three questions: frame-bound keys follow is_light(),
    page-bound ones light_page(), and the tab bar light_bar(). A theme's own
    "chrome" dict, if it has one, wins over all three.
    """
    i = _current_index if index is None else index % len(THEMES)
    frame = _CHROME_LIGHT if is_light(i) else _CHROME_DARK
    page = _PAGE_LIGHT if light_page(i) else _PAGE_DARK
    out = {**frame, **page}
    if light_bar(i):
        out = {**out, **_BAR_LIGHT}
    #: A theme may override any chrome key for itself, and does so last.
    return {**out, **THEMES[i].get("chrome", {})}
