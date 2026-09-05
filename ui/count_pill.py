"""
ui/count_pill.py — the small "how many did we find" readout on a result toolbar.

Replaces the QLCDNumber both result windows used to carry.

Unlike the rest of the chrome this pill keeps a dark face and fixed colours
instead of following the theme, for the same reason a real instrument does: one
bright reading has to stay legible on every ground, and no single accent can do
that over a face that comes out near-black in six themes and pale blue in the
seventh. Giving the pill its own face settles that once.

Green rather than a colour of its own: the app already reads that green as
"there is something live here", on the open sidebar panel and the selected tab.
The figure lights up only when there is something to report; until then the
readout sits dark behind a muted dash.

    self.count = count_pill.make("Files in the list")
    count_pill.set_count(self.count, len(rows))
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

_INK_ON  = "#3CD28C"   # the app's "active" green — the figure, once there is one
_INK_OFF = "#8CA3B8"   # the dash shown before anything has been counted

_QSS = """
    QLabel#countPill {
        background: rgba(12,18,30,225);
        border: 1px solid rgba(60,210,140,60);
        border-radius: 8px;
        padding: 0 10px;
    }
"""


def make(tooltip: str, height: int = 40, width: int = 76) -> QLabel:
    """A counter reading a dash until set_count() is called.

    height should match the buttons beside it, or the pill sits off their line.
    The tooltip is where the noun lives, since the face shows the figure alone.
    """
    lbl = QLabel()
    lbl.setObjectName("countPill")
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setMinimumWidth(width)
    lbl.setFixedHeight(height)
    lbl.setToolTip(tooltip)
    lbl.setStyleSheet(_QSS)
    set_count(lbl, None)
    return lbl


def set_count(lbl: QLabel, n) -> None:
    """Write the figure. n is an int, or None for "nothing counted yet"."""
    number, ink = ("\u2014", _INK_OFF) if n is None else (f"{n:,}", _INK_ON)
    lbl.setText(
        f'<span style="font-size:18px; font-weight:700; color:{ink};">{number}</span>'
    )
