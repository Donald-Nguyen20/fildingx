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

# Neuron count scales with the real DB document count (sqrt so it grows
# gently instead of exploding on huge DBs), clamped to a safe render range.
_NEURON_COUNT_MIN = 180
_NEURON_COUNT_MAX = 420
_NEURON_SCALE_REF = 4000

# Qualitative palette for the folder legend. Folders beyond this many (ranked
# by file count) are lumped into one grey "Other" bucket so the legend never
# grows unreadably long, no matter how many folders the underlying DB has.
_FOLDER_PALETTE = [
    QColor(255, 99, 71),    # tomato
    QColor(255, 215, 0),    # gold
    QColor(50, 205, 50),    # limegreen
    QColor(30, 144, 255),   # dodgerblue
    QColor(238, 130, 238),  # violet
    QColor(255, 165, 0),    # orange
    QColor(64, 224, 208),   # turquoise
    QColor(199, 21, 133),   # mediumvioletred
]
_FOLDER_OTHER_COLOR = QColor(110, 118, 130)

# Warm gold for search hits — every state palette is cool-toned, so this
# stays distinguishable no matter which state the orb is in.
_HIGHLIGHT_COLOR = (255, 214, 92)

# Orange for the documents an answer actually cited. Separate from the search
# gold on purpose: the two mean different things (a topic's region vs the exact
# files the answer rests on) and must never be mistaken for each other.
_SOURCE_COLOR = (255, 126, 46)
_SOURCE_COLOR_HEX = "#%02x%02x%02x" % _SOURCE_COLOR

_STATES = [
    {"colA": (0, 200, 215), "colB": (30, 90, 255), "speed": .50, "fire": .18,
     "conn": 55, "axon_spd": .65, "wave_amp": .60, "drift_mul": 1.2},
    {"colA": (20, 120, 255), "colB": (0, 230, 240), "speed": 1.1, "fire": .42,
     "conn": 85, "axon_spd": 1.3, "wave_amp": .78, "drift_mul": 1.8},
    {"colA": (130, 0, 255), "colB": (230, 0, 190), "speed": 2.4, "fire": .72,
     "conn": 118, "axon_spd": 2.2, "wave_amp": 1.08, "drift_mul": 2.8},
    {"colA": (0, 210, 160), "colB": (240, 175, 0), "speed": 1.7, "fire": .58,
     "conn": 98, "axon_spd": 1.7, "wave_amp": .95, "drift_mul": 2.2},
    {"colA": (255, 30, 30), "colB": (255, 220, 0), "speed": 4.0, "fire": .98,
     "conn": 150, "axon_spd": 3.8, "wave_amp": 1.50, "drift_mul": 4.0},
]


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
        "drift_spd", "drift_r", "dendrites",
    )


class _Synapse:
    __slots__ = ("src", "dst", "pulses", "phase", "dist", "curv")

    def __init__(self, src: int, dst: int, phase: float, dist: float, curv: float):
        self.src, self.dst = src, dst
        self.pulses: list = []
        self.phase, self.dist, self.curv = phase, dist, curv


class _FrameState:
    __slots__ = ("col_a", "col_b", "spd", "fire_rate", "conn_c", "axon_spd", "wave_amp", "drift_mul", "col_fire")

    def __init__(self, col_a, col_b, spd, fire_rate, conn_c, axon_spd, wave_amp, drift_mul):
        self.col_a, self.col_b = col_a, col_b
        self.spd, self.fire_rate, self.conn_c = spd, fire_rate, conn_c
        self.axon_spd, self.wave_amp, self.drift_mul = axon_spd, wave_amp, drift_mul
        self.col_fire = _fire_color(tuple(round(c) for c in col_a))


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
        r = 10 + _rnd(i, 2) * 265
        neurons.append(_make_neuron(i, a, r))
    return neurons


_SOURCE_ICON: QIcon | None = None


def _source_icon() -> QIcon:
    """The orange diamond marking cited files in the picker.

    Painted rather than typed as a "◆" character so it carries the marker
    colour: in a menu of twenty siblings a plain glyph in the label text is too
    quiet to find. Built lazily and cached -- a QPixmap needs a live
    QGuiApplication, which does not exist at import time."""
    global _SOURCE_ICON
    if _SOURCE_ICON is None:
        size = 14
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(*_SOURCE_COLOR))
        mid, edge = size / 2, size * .12
        diamond = QPainterPath()
        diamond.moveTo(mid, edge)
        diamond.lineTo(size - edge, mid)
        diamond.lineTo(mid, size - edge)
        diamond.lineTo(edge, mid)
        diamond.closeSubpath()
        p.drawPath(diamond)
        p.end()
        _SOURCE_ICON = QIcon(pm)
    return _SOURCE_ICON


class _CitedFileRow(QWidget):
    """A file-picker row for a cited document, name and all in marker colour.

    A plain QAction cannot carry a text colour and a stylesheet cannot single
    out one menu item, so a cited row has to be a real widget. That costs the
    two things a normal action gives for free -- the hover background and
    click-to-trigger -- which are reimplemented below."""

    activated = Signal()

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 5, 16, 5)
        lay.setSpacing(7)

        mark = QLabel()
        mark.setPixmap(_source_icon().pixmap(11, 11))
        mark.setStyleSheet("background: transparent;")

        label = QLabel(name)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        label.setStyleSheet(
            f"color: {_SOURCE_COLOR_HEX}; background: transparent;"
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
            p.fillRect(self.rect(), QColor(*_SOURCE_COLOR, 46))
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
            synapses.append(_Synapse(i, j, _rnd(i * 10 + c, 35) * math.tau, d, curv))
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
        self._source_paths: set[str] = set()
        self._source_neurons: set[int] = set()
        self.folder_legend: list[tuple[str, QColor, int]] = []
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

        Also computes a legend (self.folder_legend: name, color, file_count)
        so the folder breakdown is readable at a glance instead of only on
        hover.

        Pass total_docs=0, files=[] to fall back to the default decorative
        (no-DB) layout."""
        self._neurons = _build_neurons(total_docs)
        self._synapses = _build_synapses(self._neurons)
        n = len(self._neurons)
        groups: list[list[tuple[str, str]]] = [[] for _ in range(n)]
        self.folder_legend = []
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
            for rank, (name, cnt) in enumerate(folder_counts.most_common()):
                if rank < len(_FOLDER_PALETTE):
                    self.folder_legend.append((name, _FOLDER_PALETTE[rank], cnt))
                else:
                    other_count += cnt
            if other_count:
                self.folder_legend.append(("Other", _FOLDER_OTHER_COLOR, other_count))
        self._neuron_files = groups
        self._path_to_neuron = {
            path: idx for idx, group in enumerate(groups) for _, path in group
        }
        self._highlight = {}
        # Neuron indices are rebuilt above, so any marker pointing at the old
        # layout is now meaningless.
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
        hits = Counter(lookup[p] for p in paths if p in lookup)
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

    def mouseMoveEvent(self, event) -> None:
        idx = self._neuron_at(event.position())
        group = self._neuron_files[idx] if 0 <= idx < len(self._neuron_files) else []
        if group:
            # A neuron can hold dozens of files, so on a marked neuron name the
            # cited ones outright -- otherwise the marker says "the answer came
            # from somewhere in here" and leaves the user to hunt.
            cited = [name for name, path in group if path in self._source_paths]
            if cited:
                # Rich text so the cited names carry the marker colour, the same
                # cue as the orb marker and the picker icon. Names come from the
                # DB and really do contain "&" (folder 12_O&M), so escape them.
                rows = "".join(
                    f'<div style="color:{_SOURCE_COLOR_HEX}">◆ <b>'
                    f"{html.escape(name)}</b></div>"
                    for name in cited[:6]
                )
                if len(cited) > 6:
                    rows += (f'<div style="color:{_SOURCE_COLOR_HEX}">'
                             f"… +{len(cited) - 6} more cited</div>")
                others = len(group) - len(cited)
                if others:
                    rows += f'<div style="color:#9fb3c8">+{others} other file(s) here</div>'
                text = rows
            elif len(group) == 1:
                text = group[0][0]
            else:
                label = _common_folder_label([p for _, p in group])
                text = f"{label} ({len(group)} files)"
            QToolTip.showText(event.globalPosition().toPoint(), text, self)
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
        # Cited files go to the top: clicking a marked neuron is how the user
        # opens the source behind a number in the answer, and burying it in an
        # alphabetical list of twenty siblings would defeat that.
        cited = [f for f in group if f[1] in self._source_paths]
        rest = [f for f in group if f[1] not in self._source_paths]
        for name, rel_path in cited:
            row = _CitedFileRow(name, menu)
            action = QWidgetAction(menu)
            action.setDefaultWidget(row)

            # A widget action is opened by two different routes: the menu never
            # triggers it on a click, so the row reports that itself, but the
            # arrow keys do still land on it, and that path only reaches the
            # action. Both are wired; the latch keeps a platform that happens to
            # deliver both from opening the file twice.
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
        if cited and rest:
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
        ra, ga, ba = (round(c) for c in fr.col_a)
        for s in self._synapses:
            if drawn >= max_drawn:
                break
            na, nb = self._neurons[s.src], self._neurons[s.dst]
            bright = .10 + math.sin(self._t * fr.spd * .5 + s.phase) * fr.wave_amp * .14
            dist_fade = max(0.0, 1 - s.dist / 155)
            alpha = min(.50, bright * dist_fade * 5.0)
            drawn += 1
            if alpha < .018:
                continue

            mx = (na.x + nb.x) / 2 + (na.y - nb.y) * s.curv
            my = (na.y + nb.y) / 2 + (nb.x - na.x) * s.curv

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
                df = max(0.0, 1 - math.hypot(px - _CX, py - _CY) / 285)
                self._glow_dot(p, px, py, 2.2 + fr.wave_amp * .8, fr.col_fire, .90 * df, 8 + fr.wave_amp * 4)

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
        ra, ga, ba = (round(c) for c in fr.col_a)
        pen = QPen()
        for n in self._neurons:
            dist_c = math.hypot(n.x - _CX, n.y - _CY)
            fade = max(0.0, 1 - dist_c / 285)
            if fade < .05:
                continue
            fire_g = math.sin(n.firing * math.pi) if 0 < n.firing < 1 else 0.0
            alpha = max(0.0, min(1.0, (.32 + fire_g * .55) * fade))
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
        ra, ga, ba = (round(c) for c in fr.col_a)
        for n in sorted(self._neurons, key=lambda n: n.firing):
            fade = max(0.0, 1 - math.hypot(n.x - _CX, n.y - _CY) / 280)
            if fade < .05:
                continue
            is_firing = 0 < n.firing < 1
            fire_g = math.sin(n.firing * math.pi) if is_firing else 0.0
            pulse = .28 + math.sin(self._t * fr.spd * n.fire_spd + n.phase) * fr.wave_amp * .28
            sz = n.sz * (.55 + pulse * .50 + fire_g * .90)
            alpha = min(.95, (.48 + pulse * .42 + fire_g * .88) * fade)

            if fire_g > .06:
                self._glow_dot(p, n.x, n.y, max(.4, sz * .80), fr.col_fire, alpha,
                                sz * 12 * (1 + fr.wave_amp * .25) * fire_g)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(ra, ga, ba, round(max(0.0, min(1.0, alpha)) * 255)))
                p.drawEllipse(QPointF(n.x, n.y), max(.4, sz * .80), max(.4, sz * .80))

    def _paint_highlights(self, p: QPainter) -> None:
        """Pulsing warm ring around neurons holding current search hits.
        Warm gold is used because every state palette is cool-toned
        (cyan/blue/violet/green/red), so hits stay readable in any state."""
        if not self._highlight:
            return
        pulse = .5 + .5 * math.sin(self._t * 4.0)
        for idx, weight in self._highlight.items():
            if not 0 <= idx < len(self._neurons):
                continue
            # sqrt so sparse hits stay faintly visible instead of vanishing
            w = math.sqrt(max(0.0, min(1.0, weight)))
            n = self._neurons[idx]
            r = 3.0 + w * 5.0 + pulse * w * 2.5
            self._glow_dot(p, n.x, n.y, .8 + w * 1.4, _HIGHLIGHT_COLOR,
                           (.25 + w * .55) * (.6 + pulse * .4), 4 + w * 8)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(*_HIGHLIGHT_COLOR,
                                 round((60 + w * 170) * (.65 + pulse * .35))), 1.0 + w))
            p.drawEllipse(QPointF(n.x, n.y), r, r)

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
        for idx in self._source_neurons:
            if not 0 <= idx < len(self._neurons):
                continue
            n = self._neurons[idx]
            self._glow_dot(p, n.x, n.y, 2.2, _SOURCE_COLOR, .5 + pulse * .3, 13)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(*_SOURCE_COLOR, 240))
            p.drawEllipse(QPointF(n.x, n.y), 3.0, 3.0)
            # Ring sized to _neuron_at's hit radius so it shows what to click,
            # and large enough to stay findable once the orb panel scales the
            # 620px canvas down to the ~300px it actually gets on screen.
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(*_SOURCE_COLOR, round(175 + pulse * 80)), 2.1))
            r = 9.5 + pulse * 2.0
            p.drawEllipse(QPointF(n.x, n.y), r, r)

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
