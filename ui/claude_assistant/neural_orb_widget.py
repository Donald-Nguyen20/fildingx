"""ui/claude_assistant/neural_orb_widget.py — Native QPainter port of neural_interface.html.

Same visual language as the former QWebEngineView/canvas orb (organic wavy
dendrites, fluorescence-microscopy glow) but rendered directly with QPainter
inside the existing Qt process — no embedded Chromium page, no
runJavaScript() string bridge. Public API mirrors the old JS functions:
    setS(state)          — was  view.page().runJavaScript(f"setS({state})")
    stream_pulse(intensity) — was view.page().runJavaScript(f"streamPulse({x})")
"""
from __future__ import annotations

import html
import math
import random
from collections import Counter

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMenu, QToolTip, QWidget, QWidgetAction,
)

# ── Canvas-space constants (matches original neural_interface.html) ────────
_CANVAS_W, _CANVAS_H = 620.0, 560.0
_CX, _CY = 310.0, 280.0
_NEURON_COUNT = 320
_BG_COLOR = QColor("#02040b")

# Furthest a neuron is ever placed from the centre. Also the scale the colour
# ramp is measured against, so the outermost neurons are the ones wearing colB.
_NEURON_REACH = 275.0

# Neuron count scales with the real DB document count (sqrt so it grows
# gently instead of exploding on huge DBs), clamped to a safe render range.
_NEURON_COUNT_MIN = 180
_NEURON_COUNT_MAX = 420
_NEURON_SCALE_REF = 4000

# How many folders the legend names before the rest collapse into a single
# "Other" row, so it never grows unreadably long however many folders the DB
# holds.
_FOLDER_LEGEND_MAX = 8

# One colour per folder row, so the counts can be told apart at a glance instead
# of reading as one undifferentiated grey line. These are legend-local: the orb
# clusters folders by ANGLE, not by hue, so the colours separate ROWS from each
# other and nothing more.
#
# Chosen by measurement against the legend's own #06090f background, not picked
# by eye. Every entry clears a 6.7:1 contrast ratio (10px text needs 4.5:1) and
# the closest pair sits at CIEDE2000 20.4. The previous palette failed both:
# mediumvioletred #c71585 managed only 3.68:1 — unreadable at this size, which
# is what made the row hard to scan — and gold/orange collided at dE 17.4.
# Warm and cool alternate down the list so neighbouring rows never share a
# family even before the numbers are considered.
_FOLDER_PALETTE = [
    QColor(255, 99, 71),     # tomato
    QColor(64, 224, 208),    # turquoise
    QColor(240, 230, 120),   # lemon
    QColor(210, 140, 255),   # orchid
    QColor(50, 205, 50),     # limegreen
    QColor(255, 170, 200),   # pink
    QColor(120, 200, 255),   # sky
    QColor(255, 165, 0),     # orange
]

# The "Other" bucket is a leftover, not a folder, so it stays neutral: no hue to
# suggest it belongs in the sequence above, but light enough (8.4:1) to read.
_FOLDER_OTHER_COLOR = QColor(158, 170, 188)

# Search hits. This gold was once replaced by a pale pink on the grounds that it
# fell to a CIEDE2000 of 6.4 against state 4 — but the colour it collided with
# was a colB, and at the time colB was never painted (see _STATES). The
# collision it was rejected for could not happen on screen. It could once the
# ramp started being drawn, which is why those two colB values were changed
# rather than this one.
#
# Re-measured against the colours that do reach the screen — every step of every
# ramp and the firing colour of each — gold held a worst case of 36.7
# where the pink held 35.9, so it is the better separated of the two,
# not the worse. Its one real cost is the citation orange below: 29.5 against
# the pink's 40.5. Still a clear difference, and the two are drawn as different
# shapes (a soft pulsing halo whose brightness carries hit density, against a
# hard filled dot and crisp ring), which is what keeps them apart when the orb
# is in a warm state.
#
# Both markers keep those colours now only because of the halo below. Measured
# against a palette that includes the red->yellow of state 5, the gold clears
# the field by 3.8 and the orange by 2.6 — both far inside the 20 that would
# make them unmistakable, and a sweep of the whole wheel found nothing better
# than a pair of pale near-whites at 25.8 that are hard to tell from each other.
# The halo is what makes the hue distance stop mattering.
_HIGHLIGHT_COLOR = (255, 214, 92)
_HIGHLIGHT_HEX = "#%02x%02x%02x" % _HIGHLIGHT_COLOR

# Orange for the documents an answer actually cited. Held far from the search
# tint above on purpose: the two mean different things (a topic's region vs the
# exact files the answer rests on) and must never be mistaken for each other —
# which is exactly what happened while the search tint was gold and the orb was
# in a warm state.
_SOURCE_COLOR = (255, 126, 46)
_SOURCE_COLOR_HEX = "#%02x%02x%02x" % _SOURCE_COLOR

# The ground colour again, near-opaque, drawn as a band underneath each marker
# before the marker itself goes down.
#
# This is what a map does with a place name that has to sit on any colour the
# terrain happens to be: separate the mark from its background with a gap rather
# than trust the two colours to differ. It is here because the palette ran out
# of room. The states span most of the wheel, and the warm band from hue 15 to
# 65 — every yellow, amber and orange there is — is where these two markers
# live, so a warm state and a hue-separated marker cannot both exist. Measured:
# no colour in that band clears 20 from both markers, the closest being 20.2/4.2.
#
# With the halo the question stops being "can the eye separate these two hues"
# and becomes "can the eye find this edge", which it can against anything. It
# also sharpened the markers on the cool states, where there was no problem to
# solve — the dark band reads as a deliberate outline rather than a fix.
_MARK_HALO = (2, 4, 11, 210)

# Neuron colours, over the black ground above. Each state spans two hues: colA
# at the core, colB at the rim, every neuron holding a fixed place on that ramp
# (see _Neuron.mix). colB used to be carried through _FrameState and
# interpolated on every state change without any paint routine reading it, so
# the orb was one flat hue per state; it is painted now, which is where the
# extra colour comes from.
#
# The colA values are deliberately left alone. They were once brightened to
# answer a complaint that the orb read dark, and the result was worse: measured
# in HSV, (130, 0, 255) already sits at S=100 V=100 -- the corner of the sRGB
# cube, with no direction left that is not paler or darker -- so the extra
# luminance came entirely out of saturation, dropping state 2 from S=100 to
# S=53 and state 1 from S=92 to S=63. On black, a desaturated hue reads as
# washed out rather than as bright, which is the opposite of what was wanted.
#
# The dimness was never in these numbers. It is in the alpha the ink is painted
# at (see _paint_synapses, _paint_dendrites, _paint_cell_bodies) and in the
# radial fade that thins everything away from the centre -- which is where it
# gets fixed, because raising opacity makes the same hue read brighter *and*
# deeper, while the palette can only trade one for the other.
#
# When the ramp was first painted, states 3 and 4 had to give up their amber and
# yellow rims: nothing had ever checked colB against the reserved gold and orange
# below, because nothing checked colours that never reached the screen, and those
# two sat at CIEDE2000 6.4 and 3.0 from the search gold. They stay changed. What
# has changed is why — with _MARK_HALO under the markers the distance is no
# longer what protects them, so the warm band is available again, and state 5
# spends it on one deliberate red->yellow rather than scattering warm rims
# through states that read better cool.
_STATES = [
    {"colA": (0, 200, 215), "colB": (30, 90, 255), "speed": .50, "fire": .18,
     "conn": 55, "axon_spd": .65, "wave_amp": .60, "drift_mul": 1.2},
    {"colA": (20, 120, 255), "colB": (0, 230, 240), "speed": 1.1, "fire": .42,
     "conn": 85, "axon_spd": 1.3, "wave_amp": .78, "drift_mul": 1.8},
    {"colA": (130, 0, 255), "colB": (230, 0, 190), "speed": 2.4, "fire": .72,
     "conn": 118, "axon_spd": 2.2, "wave_amp": 1.08, "drift_mul": 2.8},
    {"colA": (0, 210, 160), "colB": (20, 60, 235), "speed": 1.7, "fire": .58,
     "conn": 98, "axon_spd": 1.7, "wave_amp": .95, "drift_mul": 2.2},
    # Red throughout, hot orange at the rim. This is the error state, and the
    # magenta rim it carried for one revision was only ever a way round the
    # marker collision; with _MARK_HALO doing that job it can be the red it
    # should have been.
    {"colA": (255, 30, 30), "colB": (255, 110, 0), "speed": 4.0, "fire": .98,
     "conn": 150, "axon_spd": 3.8, "wave_amp": 1.50, "drift_mul": 4.0},
    # Amber core out to yellow. The one warm state reachable in normal use —
    # state 4 above is warm too but only an error gets there — so it is wired to
    # Trend Data, which had been drawing state 2 as a copy of Diagnose. Its
    # connection count and drift are near state 3's rather than state 4's: this
    # is a working mode, not an alarm, and the two must not be confused at a
    # glance when both are warm.
    {"colA": (255, 170, 0), "colB": (255, 240, 80), "speed": 2.0, "fire": .62,
     "conn": 105, "axon_spd": 2.0, "wave_amp": 1.00, "drift_mul": 2.4},
]

# How many colours the colA->colB ramp is cut into. A neuron's place on it never
# changes, so the alternative is lerping a colour -- and deriving the brighter
# one it fires in -- for every neuron and every synapse on every frame. Twelve
# steps is finer than the eye separates over a span this short, and costs twelve
# conversions per frame instead of several hundred.
_COL_STEPS = 12


def _radial_fade(dist: float, reach: float) -> float:
    """How much of its ink a neuron keeps at `dist` from the centre.

    The fade used to be linear, which is far steeper than it looks: a neuron
    two-thirds of the way out kept a third of its alpha, so the outer half of
    the orb -- most of its area -- was painted at almost nothing. Raising it to
    a fractional power keeps the falloff shape while lifting the middle of the
    curve, so the rim stays visibly lit instead of dissolving into the ground.
    """
    return max(0.0, min(1.0, 1.0 - dist / reach)) ** 0.45


def _rnd(n: float, s: float = 1.0) -> float:
    x = math.sin(n * 127.1 + s * 311.7) * 43758.5453
    return x - math.floor(x)


def _smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _lerp(a: float, b: float, f: float) -> float:
    return a + (b - a) * f


def _lerp_color(a: tuple, b: tuple, f: float) -> tuple:
    return tuple(a[i] + (b[i] - a[i]) * f for i in range(3))


def _fire_color(col_a: tuple) -> tuple:
    out = []
    for i, v in enumerate(col_a):
        if i == 1:
            target = min(255, col_a[1] + 80)
        elif i == 2:
            target = min(255, col_a[2] + 80)
        else:
            target = min(255, col_a[0] + 60)
        out.append(round(v + (target - v) * .6))
    return tuple(out)


class _SubBranch:
    __slots__ = ("da", "dl", "wav_amp", "wav_phase")

    def __init__(self, da: float, dl: float, wav_amp: float, wav_phase: float):
        self.da, self.dl, self.wav_amp, self.wav_phase = da, dl, wav_amp, wav_phase


class _Dendrite:
    __slots__ = ("a", "len", "subs", "wav_amp", "wav_phase")

    def __init__(self, a: float, length: float, subs: list, wav_amp: float, wav_phase: float):
        self.a, self.len, self.subs = a, length, subs
        self.wav_amp, self.wav_phase = wav_amp, wav_phase


class _Neuron:
    __slots__ = (
        "ox", "oy", "x", "y", "sz", "phase", "fire_spd",
        "firing", "fire_cooldown", "drift_a", "drift_b", "drift_c",
        "drift_spd", "drift_r", "dendrites", "mix",
    )


class _Synapse:
    __slots__ = ("src", "dst", "pulses", "phase", "dist", "curv", "mix")

    def __init__(self, src: int, dst: int, phase: float, dist: float, curv: float,
                 mix: float = 0.0):
        self.src, self.dst = src, dst
        self.pulses: list = []
        self.phase, self.dist, self.curv = phase, dist, curv
        # Halfway between the two neurons it joins, so a connection never wears
        # a colour neither of its ends does.
        self.mix = mix


class _FrameState:
    __slots__ = ("col_a", "col_b", "spd", "fire_rate", "conn_c", "axon_spd",
                 "wave_amp", "drift_mul", "ramp")

    def __init__(self, col_a, col_b, spd, fire_rate, conn_c, axon_spd, wave_amp, drift_mul):
        self.col_a, self.col_b = col_a, col_b
        self.spd, self.fire_rate, self.conn_c = spd, fire_rate, conn_c
        self.axon_spd, self.wave_amp, self.drift_mul = axon_spd, wave_amp, drift_mul
        # The whole core-to-rim ramp, resting colour and firing colour together,
        # built once for the frame so the paint routines only ever index it.
        self.ramp = []
        for k in range(_COL_STEPS):
            c = tuple(round(v) for v in _lerp_color(col_a, col_b, k / (_COL_STEPS - 1)))
            self.ramp.append((c, _fire_color(c)))

    def col(self, mix: float) -> tuple[tuple, tuple]:
        """Resting and firing colour for something sitting at `mix` on the ramp."""
        return self.ramp[round(max(0.0, min(1.0, mix)) * (_COL_STEPS - 1))]


def _make_dendrites(ni: int) -> list[_Dendrite]:
    dendrites: list[_Dendrite] = []
    bc = 3 + int(_rnd(ni, 50) * 3)
    for b in range(bc):
        base_angle = (b / bc) * math.tau + (_rnd(ni * 10 + b, 56) - .5) * 1.2
        length = 16 + _rnd(ni * 10 + b, 52) * 42
        wav_amp = 2 + _rnd(ni * 10 + b, 57) * 7
        wav_phase = _rnd(ni * 10 + b, 58) * math.tau
        subs = []
        for s in range(int(_rnd(ni * 10 + b, 53) * 3)):
            key = ni * 100 + b * 10 + s
            subs.append(_SubBranch(
                da=base_angle + (_rnd(key, 54) - .5) * .95,
                dl=length * (.22 + _rnd(key, 55) * .45),
                wav_amp=1.2 + _rnd(key, 59) * 3.5,
                wav_phase=_rnd(key, 60) * math.tau,
            ))
        dendrites.append(_Dendrite(base_angle, length, subs, wav_amp, wav_phase))
    return dendrites


def _make_neuron(i: int, a: float, r: float) -> _Neuron:
    px = _CX + math.cos(a) * r
    py = _CY + math.sin(a) * r * (.88 + _rnd(i, 11) * .24)
    n = _Neuron()
    n.ox, n.oy, n.x, n.y = px, py, px, py
    n.sz = .8 + _rnd(i, 3) * 2.8
    n.phase = _rnd(i, 4) * math.tau
    n.fire_spd = .3 + _rnd(i, 6) * 3.2
    n.firing, n.fire_cooldown = 0.0, 0.0
    n.drift_a = _rnd(i, 7) * math.tau
    n.drift_b = _rnd(i, 12) * math.tau
    n.drift_c = _rnd(i, 13) * math.tau
    n.drift_spd = .2 + _rnd(i, 8) * .9
    n.drift_r = 12 + _rnd(i, 9) * 32
    n.dendrites = _make_dendrites(i)
    # Where this neuron sits on the state's colour ramp: its distance from the
    # centre, so the second hue arrives as a rim wash and the core keeps the
    # colour the centre tint and the core dot are already painted in.
    #
    # Squared, and jittered around that rather than upward from it, because a
    # straight r/reach put the average neuron halfway along the ramp and the
    # second hue simply took the orb over -- the loud state came out pink with a
    # trace of red in the middle instead of red with a pink corona. Neurons are
    # spread evenly along the radius, so the square is what keeps most of them
    # near colA; the jitter is what stops the result reading as a printed
    # gradient, letting hues interleave at every radius the way a stain does.
    n.mix = max(0.0, min(1.0, (r / _NEURON_REACH) ** 2 + (_rnd(i, 14) - .5) * .30))
    return n


def _path_segments(path: str) -> list[str]:
    return [s for s in path.replace("\\", "/").split("/") if s]


def _top_folder(path: str) -> str:
    """First path segment (top-level folder) of a relative file path, or
    '(root)' when the file sits directly under the DB base path with no
    containing folder."""
    segs = _path_segments(path)
    return segs[0] if len(segs) > 1 else "(root)"


def _common_folder_label(paths: list[str]) -> str:
    """Deepest folder shared by every path in the list, e.g. 'Lot 3 AB DWG/sub1'.
    Falls back to 'mixed folders' when the group straddles a folder boundary
    and shares nothing below the root."""
    dir_seg_lists = [_path_segments(p)[:-1] for p in paths]
    if not dir_seg_lists:
        return "mixed folders"
    common = list(dir_seg_lists[0])
    for segs in dir_seg_lists[1:]:
        new_common = []
        for a, b in zip(common, segs):
            if a != b:
                break
            new_common.append(a)
        common = new_common
        if not common:
            break
    return "/".join(common) if common else "mixed folders"


def _scaled_neuron_count(total_docs: int) -> int:
    """Map a real DB document count to a render-safe neuron count so the orb
    still 'feels' proportional to how much is indexed, without ever
    rendering so many neurons the animation lags."""
    if total_docs <= 0:
        return _NEURON_COUNT
    scaled = _NEURON_COUNT * math.sqrt(total_docs / _NEURON_SCALE_REF)
    return int(max(_NEURON_COUNT_MIN, min(_NEURON_COUNT_MAX, round(scaled))))


def _build_neurons(total_docs: int | None = None) -> list[_Neuron]:
    count = _scaled_neuron_count(total_docs) if total_docs else _NEURON_COUNT
    neurons: list[_Neuron] = []
    for i in range(count):
        a = _rnd(i, 1) * math.tau
        r = 10 + _rnd(i, 2) * (_NEURON_REACH - 10)
        neurons.append(_make_neuron(i, a, r))
    return neurons


_MARK_ICONS: dict[tuple[int, int, int], QIcon] = {}


def _mark_icon(color: tuple[int, int, int]) -> QIcon:
    """A diamond in a marker colour, for the file picker.

    Painted rather than typed as a "◆" character so it carries the marker
    colour: in a menu of twenty siblings a plain glyph in the label text is too
    quiet to find. Built lazily and cached per colour -- a QPixmap needs a live
    QGuiApplication, which does not exist at import time."""
    icon = _MARK_ICONS.get(color)
    if icon is None:
        size = 14
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(*color))
        mid, edge = size / 2, size * .12
        diamond = QPainterPath()
        diamond.moveTo(mid, edge)
        diamond.lineTo(size - edge, mid)
        diamond.lineTo(mid, size - edge)
        diamond.lineTo(edge, mid)
        diamond.closeSubpath()
        p.drawPath(diamond)
        p.end()
        icon = QIcon(pm)
        _MARK_ICONS[color] = icon
    return icon


class _MarkedFileRow(QWidget):
    """A file-picker row for a marked document, name and all in marker colour.

    A plain QAction cannot carry a text colour and a stylesheet cannot single
    out one menu item, so a marked row has to be a real widget. That costs the
    two things a normal action gives for free -- the hover background and
    click-to-trigger -- which are reimplemented below.

    The colour is passed in because a neuron holds two kinds of marked file and
    they must not be confused: orange for a document the answer cited, gold for
    one the current search or folder matched."""

    activated = Signal()

    def __init__(self, name: str, color: tuple[int, int, int], parent=None):
        super().__init__(parent)
        self._color = color
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 5, 16, 5)
        lay.setSpacing(7)

        mark = QLabel()
        mark.setPixmap(_mark_icon(color).pixmap(11, 11))
        mark.setStyleSheet("background: transparent;")

        label = QLabel(name)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        label.setStyleSheet(
            f"color: #{color[0]:02x}{color[1]:02x}{color[2]:02x};"
            f" background: transparent;"
        )

        lay.addWidget(mark)
        lay.addWidget(label)
        lay.addStretch(1)
        self._hover = False

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        if self._hover:
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(*self._color, 46))
        super().paintEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.activated.emit()
        super().mouseReleaseEvent(event)


def _build_synapses(neurons: list[_Neuron]) -> list[_Synapse]:
    synapses: list[_Synapse] = []
    n = len(neurons)
    for i in range(n):
        ni = neurons[i]
        conns = 2 + int(_rnd(i, 30) * 4)
        nearby = sorted(
            ((j, math.hypot(neurons[j].ox - ni.ox, neurons[j].oy - ni.oy)) for j in range(n) if j != i),
            key=lambda t: t[1],
        )
        nearby = [t for t in nearby if t[1] < 150][:14]
        if not nearby:
            continue
        for c in range(conns):
            idx = min(int(_rnd(i * 10 + c, 32) * len(nearby)), len(nearby) - 1)
            j, d = nearby[idx]
            if any(s.src == i and s.dst == j for s in synapses):
                continue
            curv = (_rnd(i * 10 + c, 36) - .5) * .36
            synapses.append(_Synapse(i, j, _rnd(i * 10 + c, 35) * math.tau, d, curv,
                                     (ni.mix + neurons[j].mix) / 2))
    return synapses


class NeuralOrbWidget(QWidget):
    """Drop-in native replacement for the QWebEngineView-based neural orb."""

    # Emitted on left-click over a neuron that has a real file attached:
    # (name, relative_path).
    neuron_clicked = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setMouseTracking(True)
        self._neurons = _build_neurons()
        self._synapses = _build_synapses(self._neurons)
        self._neuron_files: list[list[tuple[str, str]]] = []
        self._path_to_neuron: dict[str, int] = {}
        self._highlight: dict[int, float] = {}
        # The individual files behind the highlight. _highlight is per-neuron and
        # a neuron holds dozens of files, so without this the orb could say a
        # region matched but never which document in it did.
        self._highlight_paths: set[str] = set()
        self._source_paths: set[str] = set()
        self._source_neurons: set[int] = set()
        self.folder_legend: list[tuple[str, QColor, int]] = []
        self._folder_paths: dict[str, list[str]] = {}
        self._cur = 0
        self._nxt = 0
        self._bl = 1.0
        self._t = 0.0
        self._fire_timer = 0.0
        self._stream_boost = 0.0
        self._frame: _FrameState | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._tick()

    def sizeHint(self) -> QSize:
        return QSize(320, 320)

    # ── Public API (mirrors old setS()/streamPulse() JS calls) ─────────
    def setS(self, state: int) -> None:
        if not 0 <= state < len(_STATES):
            return
        self._cur, self._nxt = self._nxt, state
        self._bl = 0.0

    def stream_pulse(self, intensity: float) -> None:
        intensity = max(0.0, min(1.0, intensity))
        self._stream_boost = max(self._stream_boost, intensity)
        eligible = [i for i, n in enumerate(self._neurons) if n.firing == 0 and n.fire_cooldown <= 0]
        random.shuffle(eligible)
        for idx in eligible[: int(intensity * 6)]:
            self._trigger_fire(idx)

    def set_documents(self, total_docs: int, files: list[tuple[str, str]]) -> None:
        """Rebuild the neuron/synapse map with density scaled to the real DB
        document count, and distribute ALL given (name, relative_path)
        records across the neurons so every file stays reachable via click
        regardless of the neuron render budget (many files can share one
        neuron when there are more files than neurons).

        Files are grouped by folder proximity: sorting by path puts files
        that share a folder/subfolder next to each other in the list, and
        walking the neurons in angular order (instead of raw build index)
        means consecutive chunks of that sorted list land on spatially
        adjacent neurons. Net effect: files from the same folder cluster
        together on the orb instead of being scattered uniformly.

        Also computes a legend (self.folder_legend: name, colour, file_count) so
        the folder breakdown is readable at a glance instead of only on hover.

        Pass total_docs=0, files=[] to fall back to the default decorative
        (no-DB) layout."""
        self._neurons = _build_neurons(total_docs)
        self._synapses = _build_synapses(self._neurons)
        n = len(self._neurons)
        groups: list[list[tuple[str, str]]] = [[] for _ in range(n)]
        self.folder_legend = []
        self._folder_paths = {}
        if n and files:
            angular_order = sorted(
                range(n),
                key=lambda i: math.atan2(self._neurons[i].oy - _CY, self._neurons[i].ox - _CX),
            )
            sorted_files = sorted(files, key=lambda f: f[1].lower())
            base, extra = divmod(len(sorted_files), n)
            pos = 0
            for slot, neuron_idx in enumerate(angular_order):
                size = base + (1 if slot < extra else 0)
                groups[neuron_idx] = sorted_files[pos:pos + size]
                pos += size

            folder_counts = Counter(_top_folder(p) for _, p in files)
            other_count = 0
            named: set[str] = set()
            for rank, (name, cnt) in enumerate(folder_counts.most_common()):
                if rank < _FOLDER_LEGEND_MAX:
                    self.folder_legend.append((name, _FOLDER_PALETTE[rank], cnt))
                    named.add(name)
                else:
                    other_count += cnt
            if other_count:
                self.folder_legend.append(("Other", _FOLDER_OTHER_COLOR, other_count))

            # Keyed by the name the legend shows, not by the folder on disk, so
            # a click on a legend row can be answered with the exact set of
            # files that row counted -- including "Other", which is not a folder
            # at all but every folder past _FOLDER_LEGEND_MAX collapsed into one.
            for _, p in files:
                key = _top_folder(p)
                self._folder_paths.setdefault(
                    key if key in named else "Other", []).append(p)
        self._neuron_files = groups
        self._path_to_neuron = {
            path: idx for idx, group in enumerate(groups) for _, path in group
        }
        self._highlight = {}
        # Neuron indices are rebuilt above, so any marker pointing at the old
        # layout is now meaningless.
        self._highlight_paths = set()
        self._source_paths = set()
        self._source_neurons = set()

    # ── Search highlight ────────────────────────────────────────────────
    def highlight_files(self, paths) -> None:
        """Light up neurons holding the given file paths so search results
        read as regions of the orb rather than a flat text list.

        Weight is how many times a neuron's hit density exceeds the query's own
        overall hit rate, log-scaled and normalised so the most concentrated
        neuron always reaches full brightness. Raw density fails at both ends:
        a broad query ("lube oil temperature high alarm" matches half the
        library) would wash ~90% of the orb, while a narrow one ("gearbox",
        3%) never gets dense enough to show up. Scoring against the query's own
        baseline keeps the reading the same at any breadth -- lit means "denser
        here than this query's average", not "matched at all"."""
        lookup = self._path_to_neuron
        # Kept file by file as well as counted per neuron. Lighting a region
        # answers "where does this live"; the set answers the question that comes
        # straight after it -- which of the files in here is the one -- when a
        # neuron is hovered or clicked. Every match is kept, including ones in
        # neurons too sparse to light: the file matched either way, and a match
        # the user can never reach is worse than one whose neuron is dim.
        self._highlight_paths = {p for p in paths if p in lookup}
        hits = Counter(lookup[p] for p in self._highlight_paths)
        total_files = len(lookup)
        matched = sum(hits.values())
        if not (hits and total_files and matched):
            self._highlight = {}
            return

        baseline = matched / total_files
        scores: dict[int, float] = {}
        for idx, cnt in hits.items():
            group = self._neuron_files[idx]
            if not group:
                continue
            lift = (cnt / len(group)) / baseline
            if lift > 1.0:
                scores[idx] = math.log(lift)

        top = max(scores.values(), default=0.0)
        if top <= 0.0:
            # Hits spread perfectly evenly: no concentration worth pointing at.
            self._highlight = {}
            return
        self._highlight = {idx: s / top for idx, s in scores.items()}

    def clear_highlight(self) -> None:
        self._highlight = {}
        self._highlight_paths = set()

    def highlight_hits(self) -> set[str]:
        """The file paths behind the current highlight."""
        return set(self._highlight_paths)

    def folder_files(self, name: str) -> list[str]:
        """Every file path the legend counts under one of its folder names.

        Answered here rather than recomputed by the caller because this is the
        end that built the legend: which folders were named and which fell into
        "Other" is decided above and nowhere else.
        """
        return list(self._folder_paths.get(name, ()))

    # ── Answer sources (provenance) ─────────────────────────────────────
    def set_source_files(self, paths) -> list[str]:
        """Mark the neurons holding the documents an answer cited.

        Unlike the search highlight there is no weighting here: a document was
        either cited or it was not, so every marker is drawn at full strength.
        Returns the paths that actually exist in this DB, so the caller can
        report how many citations were verifiable rather than how many were
        merely mentioned."""
        lookup = self._path_to_neuron
        resolved = [p for p in paths if p in lookup]
        self._source_paths = set(resolved)
        self._source_neurons = {lookup[p] for p in resolved}
        return resolved

    def clear_sources(self) -> None:
        self._source_paths = set()
        self._source_neurons = set()

    # ── Hit-testing (hover tooltip / click-to-open) ─────────────────────
    def _neuron_at(self, pos: QPointF) -> int:
        """Map a widget-local mouse position to the nearest neuron index
        (inverting the same translate+scale paintEvent uses), or -1 if none
        is within the hit radius."""
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return -1
        scale = min(w / _CANVAS_W, h / _CANVAS_H)
        if scale <= 0:
            return -1
        tx = (w - _CANVAS_W * scale) / 2
        ty = (h - _CANVAS_H * scale) / 2
        cx = (pos.x() - tx) / scale
        cy = (pos.y() - ty) / scale
        best_idx, best_d = -1, 12.0
        for i, n in enumerate(self._neurons):
            d = math.hypot(n.x - cx, n.y - cy)
            if d < best_d:
                best_d = d
                best_idx = i
        return best_idx

    @staticmethod
    def _marked_rows(names: list[str], color_hex: str, more: str) -> str:
        """Name the marked files in a neuron, in the colour they were marked in.

        Rich text so the names carry the marker colour, the same cue as the orb
        and the picker icon. Names come from the DB and really do contain "&"
        (folder 12_O&M), so escape them. Capped at six: past that the tooltip is
        taller than it is useful, and the picker is the place to read the rest.
        """
        rows = "".join(
            f'<div style="color:{color_hex}">◆ <b>{html.escape(n)}</b></div>'
            for n in names[:6]
        )
        if len(names) > 6:
            rows += (f'<div style="color:{color_hex}">'
                     f"… +{len(names) - 6} {more}</div>")
        return rows

    def _neuron_tooltip(self, group: list[tuple[str, str]]) -> str:
        """What a neuron says when hovered.

        A neuron holds dozens of files, so a marked one names the files behind
        the mark outright -- otherwise the orb says "it is somewhere in here"
        and leaves the user to hunt through the picker for it.
        """
        cited = [n for n, p in group if p in self._source_paths]
        hits = [n for n, p in group if p in self._highlight_paths
                and p not in self._source_paths]
        if cited or hits:
            rows = self._marked_rows(cited, _SOURCE_COLOR_HEX, "more cited")
            rows += self._marked_rows(hits, _HIGHLIGHT_HEX, "more matching")
            others = len(group) - len(cited) - len(hits)
            if others:
                rows += (f'<div style="color:#9fb3c8">'
                         f"+{others} other file(s) here</div>")
            return rows
        if len(group) == 1:
            return group[0][0]
        label = _common_folder_label([p for _, p in group])
        return f"{label} ({len(group)} files)"

    def mouseMoveEvent(self, event) -> None:
        idx = self._neuron_at(event.position())
        group = self._neuron_files[idx] if 0 <= idx < len(self._neuron_files) else []
        if group:
            QToolTip.showText(event.globalPosition().toPoint(),
                              self._neuron_tooltip(group), self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            idx = self._neuron_at(event.position())
            group = self._neuron_files[idx] if 0 <= idx < len(self._neuron_files) else []
            if len(group) == 1:
                name, rel_path = group[0]
                self.neuron_clicked.emit(name, rel_path)
            elif len(group) > 1:
                self._show_file_picker(group, event.globalPosition().toPoint())
        super().mousePressEvent(event)

    def _show_file_picker(self, group: list[tuple[str, str]], global_pos) -> None:
        menu = QMenu(self)
        # The panel sets "QWidget { background: #02040b }", which cascades into
        # this popup while the text stays the default black -- unreadable. Style
        # the menu explicitly, in the same colours as the legend below the orb.
        menu.setStyleSheet(
            "QMenu { background: #06090f; color: #9fb3c8;"
            " border: 1px solid #1a2535; padding: 4px; }"
            "QMenu::item { padding: 5px 16px; background: transparent; }"
            "QMenu::item:selected { background: #16283c; color: #d7e6f5; }"
            "QMenu::separator { height: 1px; background: #1a2535;"
            " margin: 4px 10px; }"
        )
        # Marked files go to the top: clicking a lit neuron is how the user gets
        # from "the answer came from around here" or "the phrase is in this
        # region" to the actual document, and burying it in an alphabetical list
        # of twenty siblings would defeat that. Cited outranks matched -- a
        # citation is what the answer rested on, a match is only where a word
        # occurs -- and a file that is both is listed once, as cited.
        cited = [f for f in group if f[1] in self._source_paths]
        hits = [f for f in group if f[1] in self._highlight_paths
                and f[1] not in self._source_paths]
        marked = {f[1] for f in cited} | {f[1] for f in hits}
        rest = [f for f in group if f[1] not in marked]

        for bucket, color in ((cited, _SOURCE_COLOR), (hits, _HIGHLIGHT_COLOR)):
            for name, rel_path in bucket:
                row = _MarkedFileRow(name, color, menu)
                action = QWidgetAction(menu)
                action.setDefaultWidget(row)

                # A widget action is opened by two different routes: the menu
                # never triggers it on a click, so the row reports that itself,
                # but the arrow keys do still land on it, and that path only
                # reaches the action. Both are wired; the latch keeps a platform
                # that happens to deliver both from opening the file twice.
                opened: list[bool] = []

                def _open(_checked=False, n=name, p=rel_path, m=menu, once=opened):
                    if once:
                        return
                    once.append(True)
                    m.close()
                    self.neuron_clicked.emit(n, p)

                row.activated.connect(_open)
                action.triggered.connect(_open)
                menu.addAction(action)

        if marked and rest:
            menu.addSeparator()
        for name, rel_path in rest:
            action = menu.addAction(name)
            action.triggered.connect(
                lambda checked=False, n=name, p=rel_path: self.neuron_clicked.emit(n, p)
            )
        menu.exec(global_pos)

    # ── Simulation step ──────────────────────────────────────────────
    def _trigger_fire(self, idx: int) -> None:
        n = self._neurons[idx]
        if n.firing > 0 or n.fire_cooldown > 0:
            return
        n.firing = .01
        n.fire_cooldown = 18 + random.random() * 45
        for s in self._synapses:
            if s.src == idx:
                s.pulses.append({"prog": 0.0, "spd": .012 + random.random() * .026})

    def _tick(self) -> None:
        self._t += .016
        if self._bl < 1:
            self._bl = min(1.0, self._bl + .008)
        if self._stream_boost > 0:
            self._stream_boost = max(0.0, self._stream_boost - .012)

        f = _smoothstep(self._bl)
        sa, sb = _STATES[self._cur], _STATES[self._nxt]
        spd = _lerp(sa["speed"], sb["speed"], f)
        fire_rate = _lerp(sa["fire"], sb["fire"], f)
        drift_mul = _lerp(sa["drift_mul"], sb["drift_mul"], f)

        self._frame = _FrameState(
            col_a=_lerp_color(sa["colA"], sb["colA"], f),
            col_b=_lerp_color(sa["colB"], sb["colB"], f),
            spd=spd,
            fire_rate=fire_rate,
            conn_c=round(_lerp(sa["conn"], sb["conn"], f)),
            axon_spd=_lerp(sa["axon_spd"], sb["axon_spd"], f),
            wave_amp=_lerp(sa["wave_amp"], sb["wave_amp"], f),
            drift_mul=drift_mul,
        )

        for n in self._neurons:
            if n.firing > 0:
                n.firing = min(1.0, n.firing + .05 * spd)
            if n.fire_cooldown > 0:
                n.fire_cooldown -= spd
            n.drift_a += n.drift_spd * .016 * spd
            n.drift_b += n.drift_spd * .010 * spd * 1.3
            n.drift_c += n.drift_spd * .006 * spd * 1.7
            dr = n.drift_r * drift_mul * .012
            ox = (math.cos(n.drift_a) * dr * n.drift_r
                  + math.cos(n.drift_b) * dr * n.drift_r * .55
                  + math.cos(n.drift_c) * dr * n.drift_r * .30)
            oy = (math.sin(n.drift_a) * dr * n.drift_r
                  + math.sin(n.drift_b) * dr * n.drift_r * .55
                  + math.sin(n.drift_c) * dr * n.drift_r * .30)
            n.x += (n.ox + ox - n.x) * .04
            n.y += (n.oy + oy - n.y) * .04

        self._fire_timer -= spd
        if self._fire_timer <= 0:
            self._fire_timer = .8 + random.random() * (4 / fire_rate)
            eligible = [i for i, n in enumerate(self._neurons) if n.firing == 0 and n.fire_cooldown <= 0]
            random.shuffle(eligible)
            for idx in eligible[: 1 + int(fire_rate * 3)]:
                self._trigger_fire(idx)

        for s in self._synapses:
            alive = []
            for p in s.pulses:
                p["prog"] += p["spd"] * self._frame.axon_spd
                if p["prog"] >= 1:
                    self._trigger_fire(s.dst)
                else:
                    alive.append(p)
            s.pulses = alive

        self.update()

    # ── Painting ─────────────────────────────────────────────────────
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), _BG_COLOR)

        w, h = self.width(), self.height()
        fr = self._frame
        if w <= 0 or h <= 0 or fr is None:
            return
        scale = min(w / _CANVAS_W, h / _CANVAS_H)
        painter.translate((w - _CANVAS_W * scale) / 2, (h - _CANVAS_H * scale) / 2)
        painter.scale(scale, scale)

        self._paint_center_tint(painter, fr)
        self._paint_synapses(painter, fr)
        self._paint_dendrites(painter, fr)
        self._paint_cell_bodies(painter, fr)
        self._paint_highlights(painter)
        self._paint_sources(painter)
        self._paint_core(painter, fr)

    @staticmethod
    def _glow_dot(p: QPainter, cx: float, cy: float, radius: float, color: tuple, alpha: float, blur: float) -> None:
        """Approximates canvas shadowBlur with a soft radial-gradient halo + solid core."""
        r, g, b = (round(c) for c in color)
        alpha = max(0.0, min(1.0, alpha))
        outer = radius + blur
        grad = None
        if outer > 0:
            from PySide6.QtGui import QRadialGradient
            grad = QRadialGradient(QPointF(cx, cy), outer)
            grad.setColorAt(0.0, QColor(r, g, b, round(255 * alpha)))
            grad.setColorAt(min(1.0, radius / outer) if outer else 0, QColor(r, g, b, round(255 * alpha * .6)))
            grad.setColorAt(1.0, QColor(r, g, b, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(cx, cy), outer, outer)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(r, g, b, round(255 * alpha)))
        p.drawEllipse(QPointF(cx, cy), max(.1, radius), max(.1, radius))

    def _paint_center_tint(self, p: QPainter, fr: _FrameState) -> None:
        from PySide6.QtGui import QRadialGradient
        r, g, b = (round(c) for c in fr.col_a)
        grad = QRadialGradient(QPointF(_CX, _CY), 260)
        grad.setColorAt(0, QColor(r, g, b, round(255 * .028)))
        grad.setColorAt(1, QColor(r, g, b, 0))
        p.fillRect(QRectF(0, 0, _CANVAS_W, _CANVAS_H), QBrush(grad))

    def _paint_synapses(self, p: QPainter, fr: _FrameState) -> None:
        drawn = 0
        max_drawn = fr.conn_c * 3
        for s in self._synapses:
            if drawn >= max_drawn:
                break
            na, nb = self._neurons[s.src], self._neurons[s.dst]
            bright = .17 + math.sin(self._t * fr.spd * .5 + s.phase) * fr.wave_amp * .14
            dist_fade = _radial_fade(s.dist, 175)
            alpha = min(.62, bright * dist_fade * 5.0)
            drawn += 1
            if alpha < .018:
                continue

            mx = (na.x + nb.x) / 2 + (na.y - nb.y) * s.curv
            my = (na.y + nb.y) / 2 + (nb.x - na.x) * s.curv

            (ra, ga, ba), col_fire = fr.col(s.mix)
            pen = QPen(QColor(ra, ga, ba, round(max(0.0, alpha) * 255)))
            pen.setWidthF(1.1)
            p.setPen(pen)
            path = QPainterPath(QPointF(na.x, na.y))
            path.quadTo(QPointF(mx, my), QPointF(nb.x, nb.y))
            p.drawPath(path)

            for pulse in s.pulses:
                mt = pulse["prog"]
                px = na.x * (1 - mt) ** 2 + mx * 2 * mt * (1 - mt) + nb.x * mt * mt
                py = na.y * (1 - mt) ** 2 + my * 2 * mt * (1 - mt) + nb.y * mt * mt
                df = _radial_fade(math.hypot(px - _CX, py - _CY), 285)
                self._glow_dot(p, px, py, 2.2 + fr.wave_amp * .8, col_fire, .90 * df, 8 + fr.wave_amp * 4)

    def _wavy_path(self, x1: float, y1: float, x2: float, y2: float, amp: float, phase: float) -> QPainterPath | None:
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1:
            return None
        nx, ny = -dy / length, dx / length
        steps = max(3, int(length / 9))
        path = None
        for i in range(steps + 1):
            s = i / steps
            env = math.sin(s * math.pi)
            wv = math.sin(s * math.pi * 2.5 + phase) * amp * env
            px, py = x1 + dx * s + nx * wv, y1 + dy * s + ny * wv
            if path is None:
                path = QPainterPath(QPointF(px, py))
            else:
                path.lineTo(QPointF(px, py))
        return path

    def _paint_dendrites(self, p: QPainter, fr: _FrameState) -> None:
        pen = QPen()
        for n in self._neurons:
            dist_c = math.hypot(n.x - _CX, n.y - _CY)
            fade = _radial_fade(dist_c, 285)
            if fade < .05:
                continue
            fire_g = math.sin(n.firing * math.pi) if 0 < n.firing < 1 else 0.0
            alpha = max(0.0, min(1.0, (.46 + fire_g * .48) * fade))
            (ra, ga, ba), _ = fr.col(n.mix)
            pen.setColor(QColor(ra, ga, ba, round(alpha * 255)))

            for d in n.dendrites:
                wobble = math.sin(self._t * fr.spd * .7 + n.phase + d.a) * fr.wave_amp * .8
                ex = n.x + math.cos(d.a + wobble * .035) * d.len
                ey = n.y + math.sin(d.a + wobble * .035) * d.len
                pen.setWidthF(1.3)
                p.setPen(pen)
                path = self._wavy_path(n.x, n.y, ex, ey, d.wav_amp * (.5 + fr.wave_amp * .55),
                                        d.wav_phase + self._t * fr.spd * .25)
                if path:
                    p.drawPath(path)

                smx, smy = n.x + math.cos(d.a) * d.len * .45, n.y + math.sin(d.a) * d.len * .45
                pen.setWidthF(.7)
                p.setPen(pen)
                for sb in d.subs:
                    sub_path = self._wavy_path(
                        smx, smy, smx + math.cos(sb.da) * sb.dl, smy + math.sin(sb.da) * sb.dl,
                        sb.wav_amp * (.4 + fr.wave_amp * .45), sb.wav_phase + self._t * fr.spd * .18,
                    )
                    if sub_path:
                        p.drawPath(sub_path)

    def _paint_cell_bodies(self, p: QPainter, fr: _FrameState) -> None:
        for n in sorted(self._neurons, key=lambda n: n.firing):
            fade = _radial_fade(math.hypot(n.x - _CX, n.y - _CY), 280)
            if fade < .05:
                continue
            is_firing = 0 < n.firing < 1
            fire_g = math.sin(n.firing * math.pi) if is_firing else 0.0
            pulse = .28 + math.sin(self._t * fr.spd * n.fire_spd + n.phase) * fr.wave_amp * .28
            sz = n.sz * (.55 + pulse * .50 + fire_g * .90)
            alpha = min(.98, (.60 + pulse * .40 + fire_g * .88) * fade)
            (ra, ga, ba), col_fire = fr.col(n.mix)

            if fire_g > .06:
                self._glow_dot(p, n.x, n.y, max(.4, sz * .80), col_fire, alpha,
                                sz * 12 * (1 + fr.wave_amp * .25) * fire_g)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(ra, ga, ba, round(max(0.0, min(1.0, alpha)) * 255)))
                p.drawEllipse(QPointF(n.x, n.y), max(.4, sz * .80), max(.4, sz * .80))

    def _paint_highlights(self, p: QPainter) -> None:
        """Pulsing gold ring around neurons holding current search hits.

        Warm on purpose, and it no longer has to apologise for it: the ring is
        laid on a band of _MARK_HALO, so it reads against the cool states and
        against the red->yellow of state 5 alike. The halo goes down at the same
        radius and slightly thicker, which puts a dark edge on both sides of the
        gold rather than only outside it."""
        if not self._highlight:
            return
        pulse = .5 + .5 * math.sin(self._t * 4.0)
        # Built once rather than per neuron: a broad query lights ~80 of them and
        # this runs every frame, so the colours that do not vary should not be
        # rebuilt 80 times for each one that does.
        halo, gold = QColor(*_MARK_HALO), QColor(*_HIGHLIGHT_COLOR)
        for idx, weight in self._highlight.items():
            if not 0 <= idx < len(self._neurons):
                continue
            # sqrt so sparse hits stay faintly visible instead of vanishing
            w = math.sqrt(max(0.0, min(1.0, weight)))
            n = self._neurons[idx]
            r = 3.0 + w * 5.0 + pulse * w * 2.5
            self._glow_dot(p, n.x, n.y, .8 + w * 1.4, _HIGHLIGHT_COLOR,
                           (.25 + w * .55) * (.6 + pulse * .4), 4 + w * 8)
            centre = QPointF(n.x, n.y)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(halo, 2.4 + w * 1.6))
            p.drawEllipse(centre, r, r)
            gold.setAlpha(round((60 + w * 170) * (.65 + pulse * .35)))
            p.setPen(QPen(gold, 1.0 + w))
            p.drawEllipse(centre, r, r)

    def _paint_sources(self, p: QPainter) -> None:
        """Solid orange markers on the neurons holding the documents the last
        answer cited.

        Drawn deliberately unlike the search highlight: that one is a soft halo
        whose brightness carries a meaning (hit density), while a citation is
        binary, so these get a hard filled dot and a crisp ring — something to
        aim a click at when checking where a number in the answer came from."""
        if not self._source_neurons:
            return
        pulse = .5 + .5 * math.sin(self._t * 2.2)
        # Ring sized to _neuron_at's hit radius so it shows what to click, and
        # large enough to stay findable once the orb panel scales the 620px
        # canvas down to the ~300px it actually gets on screen.
        r = 9.5 + pulse * 2.0
        # Nothing here varies between citations -- they are a binary mark, and
        # the pulse is the same for all of them -- so every pen and brush is
        # built once for the frame instead of once per citation.
        halo = QColor(*_MARK_HALO)
        halo_pen = QPen(halo, 3.4)
        ring_pen = QPen(QColor(*_SOURCE_COLOR, round(175 + pulse * 80)), 2.1)
        dot = QColor(*_SOURCE_COLOR, 240)
        for idx in self._source_neurons:
            if not 0 <= idx < len(self._neurons):
                continue
            n = self._neurons[idx]
            self._glow_dot(p, n.x, n.y, 2.2, _SOURCE_COLOR, .5 + pulse * .3, 13)
            centre = QPointF(n.x, n.y)
            # Halo under both parts, so the gap the eye reads is the whole mark
            # -- ring and dot together -- rather than the ring alone.
            p.setBrush(Qt.NoBrush)
            p.setPen(halo_pen)
            p.drawEllipse(centre, r, r)
            p.setPen(Qt.NoPen)
            p.setBrush(halo)
            p.drawEllipse(centre, 4.6, 4.6)
            p.setBrush(dot)
            p.drawEllipse(centre, 3.0, 3.0)
            p.setBrush(Qt.NoBrush)
            p.setPen(ring_pen)
            p.drawEllipse(centre, r, r)

    def _paint_core(self, p: QPainter, fr: _FrameState) -> None:
        from PySide6.QtGui import QRadialGradient
        ra, ga, ba = (round(c) for c in fr.col_a)
        cp = (.68 + self._stream_boost * .22) + math.sin(self._t * 3.2) * fr.wave_amp * .38
        for radius, a in ((88, .022), (58, .048), (32, .110), (16, .240), (7, .460), (3, .800)):
            rr = radius * cp
            if rr <= 0:
                continue
            grad = QRadialGradient(QPointF(_CX, _CY), rr)
            grad.setColorAt(0, QColor(ra, ga, ba, round(min(1.0, a * 1.7 * cp) * 255)))
            grad.setColorAt(1, QColor(ra, ga, ba, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(_CX, _CY), rr, rr)

        self._glow_dot(p, _CX, _CY, 2.6, fr.col_a, min(1.0, .90 + math.sin(self._t * 4.5) * .10), 9)
