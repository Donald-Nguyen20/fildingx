"""ui/container_tree.py — Org-chart container manager widget.

3 dạng hiển thị (chọn qua nút menu):
  TB   — top-to-bottom org chart (mặc định)
  LR   — left-to-right org chart
  LIST — danh sách phẳng (dạng gốc)
"""
from __future__ import annotations
import os
from typing import Dict, List, Optional, Tuple

from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QMenu, QInputDialog, QMessageBox, QSplitter, QStackedWidget,
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QListWidgetItem, QLabel, QLineEdit,
    QTreeWidget, QTreeWidgetItem,
)
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPen, QBrush, QPainter, QFont, QCursor, QPixmap, QIcon

# ── Icon helpers ─────────────────────────────────────────────────────────────

def _panel_icon(expand: bool, size: int = 18) -> QIcon:
    """Icon mở rộng / thu gọn panel dọc."""
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    p   = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor("#374151"), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    cx = size // 2
    m  = 3
    e  = size - m

    if expand:
        # Mũi tên lên (trên) và mũi tên xuống (dưới)
        mid = size // 2
        # Mũi tên lên
        p.drawLine(cx, m, cx, mid - 2)
        p.drawLine(cx, m, cx - 3, m + 4)
        p.drawLine(cx, m, cx + 3, m + 4)
        # Mũi tên xuống
        p.drawLine(cx, e, cx, mid + 2)
        p.drawLine(cx, e, cx - 3, e - 4)
        p.drawLine(cx, e, cx + 3, e - 4)
    else:
        # Mũi tên vào giữa (thu gọn)
        mid = size // 2
        p.drawLine(cx, mid - 2, cx, mid + 2)   # đường giữa nhỏ
        # Mũi tên từ trên xuống giữa
        p.drawLine(cx, m + 4, cx, mid - 2)
        p.drawLine(cx, mid - 2, cx - 3, mid - 6)
        p.drawLine(cx, mid - 2, cx + 3, mid - 6)
        # Mũi tên từ dưới lên giữa
        p.drawLine(cx, e - 4, cx, mid + 2)
        p.drawLine(cx, mid + 2, cx - 3, mid + 6)
        p.drawLine(cx, mid + 2, cx + 3, mid + 6)
    p.end()
    return QIcon(px)


def _fs_icon(expand: bool, size: int = 18) -> QIcon:
    """Vẽ icon fullscreen (expand=True) hoặc restore (expand=False)."""
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    p  = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor("#374151"), 2, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin)
    p.setPen(pen)
    arm = 5          # độ dài cánh tay góc
    m   = 2          # margin từ viền
    e   = size - m   # cạnh phải/dưới

    if expand:
        # 4 góc chữ L hướng ra ngoài
        for cx, cy, dx, dy in [(m,m,1,1),(e,m,-1,1),(m,e,1,-1),(e,e,-1,-1)]:
            p.drawLine(cx, cy, cx + dx*arm, cy)
            p.drawLine(cx, cy, cx, cy + dy*arm)
    else:
        # 4 góc chữ L hướng vào trong
        c = size // 2
        for cx, cy, dx, dy in [(m,m,1,1),(e,m,-1,1),(m,e,1,-1),(e,e,-1,-1)]:
            ix, iy = cx + dx*arm, cy + dy*arm
            p.drawLine(ix, cy, ix, iy)
            p.drawLine(cx, iy, ix, iy)
    p.end()
    return QIcon(px)


# ── Node dimensions ───────────────────────────────────────────────────────────
NODE_W = 160
NODE_H = 46

# ── LR layout constants ───────────────────────────────────────────────────────
LR_H_GAP = 40
LR_V_GAP = 14

# ── TB layout constants ───────────────────────────────────────────────────────
TB_V_GAP = 40
TB_H_GAP = 20

ROOT_X = 20
ROOT_Y = 20


# ── LR layout algorithm ───────────────────────────────────────────────────────

def _lr_subtree_height(name: str, children: Dict[str, List[str]]) -> float:
    kids = children.get(name, [])
    if not kids:
        return NODE_H
    return max(NODE_H,
               sum(_lr_subtree_height(k, children) for k in kids)
               + LR_V_GAP * (len(kids) - 1))


def _lr_place(name: str, x: float, y: float,
              children: Dict[str, List[str]],
              positions: Dict[str, Tuple[float, float]]):
    h = _lr_subtree_height(name, children)
    positions[name] = (x, y + h / 2 - NODE_H / 2)
    kids = children.get(name, [])
    cy = y
    for k in kids:
        kh = _lr_subtree_height(k, children)
        _lr_place(k, x + NODE_W + LR_H_GAP, cy, children, positions)
        cy += kh + LR_V_GAP


def _lr_compute(roots: List[str],
                children: Dict[str, List[str]]) -> Dict[str, Tuple[float, float]]:
    positions: Dict[str, Tuple[float, float]] = {}
    y = ROOT_Y
    for r in roots:
        _lr_place(r, ROOT_X, y, children, positions)
        y += _lr_subtree_height(r, children) + LR_V_GAP * 3
    return positions


# ── TB layout algorithm ───────────────────────────────────────────────────────

def _tb_subtree_width(name: str, children: Dict[str, List[str]]) -> float:
    kids = children.get(name, [])
    if not kids:
        return NODE_W
    return max(NODE_W,
               sum(_tb_subtree_width(k, children) for k in kids)
               + TB_H_GAP * (len(kids) - 1))


def _tb_place(name: str, x: float, y: float,
              children: Dict[str, List[str]],
              positions: Dict[str, Tuple[float, float]]):
    w = _tb_subtree_width(name, children)
    positions[name] = (x + (w - NODE_W) / 2, y)
    kids = children.get(name, [])
    cx = x
    for k in kids:
        kw = _tb_subtree_width(k, children)
        _tb_place(k, cx, y + NODE_H + TB_V_GAP, children, positions)
        cx += kw + TB_H_GAP


def _tb_compute(roots: List[str],
                children: Dict[str, List[str]]) -> Dict[str, Tuple[float, float]]:
    positions: Dict[str, Tuple[float, float]] = {}
    x = ROOT_X
    for r in roots:
        _tb_place(r, x, ROOT_Y, children, positions)
        x += _tb_subtree_width(r, children) + TB_H_GAP * 3
    return positions


# ── Node item ─────────────────────────────────────────────────────────────────

class _ContainerNode(QGraphicsItem):
    def __init__(self, name: str, canvas: "ContainerCanvas", file_count: int = 0):
        super().__init__()
        self.name       = name
        self.canvas     = canvas
        self.file_count = file_count
        self._hovered      = False
        self._dimmed       = False
        self._highlighted  = False
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setAcceptHoverEvents(True)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, NODE_W, NODE_H)

    def paint(self, painter: QPainter, option, widget=None):
        sel, hov, dim, hi = self.isSelected(), self._hovered, self._dimmed, self._highlighted

        if dim:
            bg, border = "#f1f5f9", "#cbd5e1"
            name_color = QColor("#94a3b8")
            badge_bg, badge_txt = "#e2e8f0", QColor("#94a3b8")
        elif sel:
            bg, border = "#3b82f6", "#1d4ed8"
            name_color = QColor("white")
            badge_bg, badge_txt = "#1d4ed8", QColor("white")
        elif hi:
            bg, border = "#fef08a", "#f59e0b"
            name_color = QColor("#78350f")
            badge_bg, badge_txt = "#f59e0b", QColor("white")
        elif hov:
            bg, border = "#dbeafe", "#3b82f6"
            name_color = QColor("#1e3a8a")
            badge_bg, badge_txt = "#3b82f6", QColor("white")
        else:
            bg, border = "#eff6ff", "#93c5fd"
            name_color = QColor("#1e3a8a")
            badge_bg, badge_txt = "#bfdbfe", QColor("#1e40af")

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(border), 2 if sel else 1.5))
        painter.setBrush(QBrush(QColor(bg)))
        painter.drawRoundedRect(self.boundingRect().adjusted(1, 1, -1, -1), 10, 10)

        painter.setPen(QPen(name_color))
        painter.setFont(QFont("Segoe UI", 9, QFont.Medium))
        painter.drawText(QRectF(8, 0, NODE_W - 36, NODE_H),
                         Qt.AlignVCenter | Qt.AlignLeft | Qt.TextWordWrap, self.name)

        BW, BH = 24, 16
        bx, by = NODE_W - BW - 5, (NODE_H - BH) // 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(badge_bg)))
        painter.drawRoundedRect(QRectF(bx, by, BW, BH), BH / 2, BH / 2)
        painter.setPen(QPen(badge_txt))
        painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
        painter.drawText(QRectF(bx, by, BW, BH), Qt.AlignCenter, str(self.file_count))

    def hoverEnterEvent(self, e):
        self._hovered = True;  self.update()

    def hoverLeaveEvent(self, e):
        self._hovered = False; self.update()

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        self.canvas.on_node_clicked(self.name)

    def contextMenuEvent(self, e):
        self.canvas.show_node_menu(self.name)


# ── Canvas ────────────────────────────────────────────────────────────────────

class ContainerCanvas(QGraphicsView):
    def __init__(self, widget: "ContainerOrgChartWidget"):
        super().__init__()
        self.widget       = widget
        self._scene       = QGraphicsScene(self)
        self._search_text = ""
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor("#f8fafc")))
        self.setMinimumHeight(160)
        self._nodes: Dict[str, _ContainerNode] = {}

    def rebuild(self, containers: Dict, parents: Dict[str, str],
                selected: Optional[str], direction: str = "TB"):
        self._scene.clear()
        self._nodes = {}
        if not containers:
            return

        all_names = list(containers.keys())
        children: Dict[str, List[str]] = {n: [] for n in all_names}
        roots: List[str] = []
        for name in all_names:
            p = parents.get(name)
            if p and p in children:
                children[p].append(name)
            else:
                roots.append(name)

        positions = _tb_compute(roots, children) if direction == "TB" \
                    else _lr_compute(roots, children)

        edge_pen = QPen(QColor("#93c5fd"), 1.5)
        for name, (x, y) in positions.items():
            kids = children.get(name, [])
            if not kids:
                continue
            if direction == "TB":
                px_c  = x + NODE_W / 2
                py_b  = y + NODE_H
                mid_y = py_b + TB_V_GAP / 2
                self._scene.addLine(px_c, py_b, px_c, mid_y, edge_pen).setZValue(-1)
                cx_list = [positions[k][0] + NODE_W / 2 for k in kids]
                self._scene.addLine(min(cx_list), mid_y, max(cx_list), mid_y, edge_pen).setZValue(-1)
                for k in kids:
                    ckx = positions[k][0] + NODE_W / 2
                    self._scene.addLine(ckx, mid_y, ckx, positions[k][1], edge_pen).setZValue(-1)
            else:
                px    = x + NODE_W
                py_c  = y + NODE_H / 2
                mid_x = px + LR_H_GAP / 2
                self._scene.addLine(px, py_c, mid_x, py_c, edge_pen).setZValue(-1)
                cy_list = [positions[k][1] + NODE_H / 2 for k in kids]
                self._scene.addLine(mid_x, min(cy_list), mid_x, max(cy_list), edge_pen).setZValue(-1)
                for k in kids:
                    cky = positions[k][1] + NODE_H / 2
                    self._scene.addLine(mid_x, cky, positions[k][0], cky, edge_pen).setZValue(-1)

        for name, (x, y) in positions.items():
            count = len(containers.get(name, []))
            node  = _ContainerNode(name, self, file_count=count)
            node.setPos(x, y)
            node.setSelected(name == selected)
            self._scene.addItem(node)
            self._nodes[name] = node

        self._scene.setSceneRect(
            self._scene.itemsBoundingRect().adjusted(-20, -20, 20, 20)
        )
        self._apply_highlight()

    def highlight(self, text: str):
        self._search_text = text.strip().lower()
        self._apply_highlight()

    def _apply_highlight(self):
        q = self._search_text
        for name, node in self._nodes.items():
            node._dimmed      = bool(q) and q not in name.lower()
            node._highlighted = bool(q) and q in name.lower()
            node.update()

    def fit_all(self):
        if self._scene.items():
            self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
            self.scale(0.95, 0.95)

    def on_node_clicked(self, name: str):
        self.widget.on_container_selected(name)

    def show_node_menu(self, name: str):
        menu = QMenu()
        menu.addAction("➕ New Sub Container").triggered.connect(
            lambda: self.widget.create_sub_container(name)
        )
        menu.addAction("✏️ Rename").triggered.connect(
            lambda: self.widget.rename_container(name)
        )
        menu.addSeparator()
        menu.addAction("🔗 Set Parent…").triggered.connect(
            lambda: self.widget.set_parent_for(name)
        )
        menu.addAction("⬆ Make Root").triggered.connect(
            lambda: self.widget.make_root(name)
        )
        menu.addSeparator()
        menu.addAction("🗑 Delete").triggered.connect(
            lambda: self.widget.delete_container(name)
        )
        menu.exec(QCursor.pos())

    def contextMenuEvent(self, event):
        if self.itemAt(event.pos()) is None:
            menu = QMenu()
            menu.addAction("➕ New Container").triggered.connect(
                self.widget.create_root_container
            )
            menu.exec(event.globalPos())
        else:
            super().contextMenuEvent(event)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)


# ── Main widget ───────────────────────────────────────────────────────────────

class ContainerOrgChartWidget(QWidget):
    containers_changed          = Signal(dict, dict)
    file_open_requested         = Signal(str)
    file_clicked                = Signal(str)
    file_context_menu_requested = Signal(str, str, bool)
    fullscreen_requested        = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._containers: Dict           = {}
        self._parents:    Dict[str, str] = {}
        self._selected:   Optional[str]  = None
        self._direction:  str            = "LIST"
        self._setup_ui()

    # ── UI setup ──────────────────────────────────────────────────────────────

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        self.canvas = ContainerCanvas(self)

        # ── Toolbar ───────────────────────────────────────────────
        toolbar = QWidget()
        tb_lay  = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(0, 0, 0, 0)
        tb_lay.setSpacing(4)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍  Search containers…")
        self.search_bar.setFixedHeight(28)
        self.search_bar.textChanged.connect(self._on_search_changed)

        self._fs_btn = QPushButton()
        self._fs_btn.setIcon(_fs_icon(expand=True))
        self._fs_btn.setFixedSize(32, 28)
        self._fs_btn.setToolTip("Fullscreen / thu nhỏ panel container")
        self._fs_btn.clicked.connect(self.fullscreen_requested.emit)

        self._btn_dir = QPushButton("☰ List")
        self._btn_dir.setFixedSize(68, 28)
        self._btn_dir.setToolTip("Switch layout")
        self._btn_dir.clicked.connect(self._show_direction_menu)

        tb_lay.addWidget(self.search_bar, 1)
        tb_lay.addWidget(self._fs_btn)
        tb_lay.addWidget(self._btn_dir)
        lay.addWidget(toolbar)

        # ── List panel (dạng danh sách phẳng) ────────────────────
        self._list_panel = self._build_list_panel()

        # ── Stacked: canvas | list panel ─────────────────────────
        self._top_stack = QStackedWidget()
        self._top_stack.addWidget(self.canvas)       # 0
        self._top_stack.addWidget(self._list_panel)  # 1

        # ── Bottom: file list ─────────────────────────────────────
        bottom     = QWidget()
        bottom_lay = QVBoxLayout(bottom)
        bottom_lay.setContentsMargins(0, 0, 0, 0)
        bottom_lay.setSpacing(4)

        self.file_list = QListWidget()
        self.file_list.itemClicked.connect(self._on_file_clicked)
        self.file_list.itemDoubleClicked.connect(self._on_file_double_clicked)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._show_file_context_menu)

        btn_row = QHBoxLayout()
        self.btn_add_file = QPushButton("Add File")
        self.btn_add_file.setMinimumHeight(32)
        self.btn_del_file = QPushButton("Remove File")
        self.btn_del_file.setMinimumHeight(32)
        self.btn_del_file.clicked.connect(self.remove_selected_file)
        self._btn_expand_panel = QPushButton()
        self._btn_expand_panel.setIcon(_panel_icon(expand=True))
        self._btn_expand_panel.setFixedSize(32, 32)
        self._btn_expand_panel.setToolTip("Mở rộng / thu gọn khung tài liệu")
        self._btn_expand_panel.clicked.connect(self._toggle_file_panel)
        btn_row.addWidget(self.btn_add_file)
        btn_row.addWidget(self.btn_del_file)
        btn_row.addWidget(self._btn_expand_panel)

        bottom_lay.addWidget(self.file_list)
        bottom_lay.addLayout(btn_row)

        self._inner_splitter = QSplitter(Qt.Vertical)
        self._inner_splitter.addWidget(self._top_stack)
        self._inner_splitter.addWidget(bottom)
        self._inner_splitter.setStretchFactor(0, 3)
        self._inner_splitter.setStretchFactor(1, 2)
        self._inner_splitter.setHandleWidth(6)
        lay.addWidget(self._inner_splitter)
        self._initial_sizes_set = False
        self._top_stack.setCurrentIndex(1)  # mặc định List mode

    def _build_list_panel(self) -> QWidget:
        panel = QWidget()
        lay   = QVBoxLayout(panel)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(4)

        # Hàng tạo container (xóa dùng click-phải trên item)
        crud = QHBoxLayout()
        self._list_entry = QLineEdit()
        self._list_entry.setPlaceholderText("New container name…")
        self._list_entry.setFixedHeight(28)
        self._list_entry.returnPressed.connect(self._list_create_container)

        create_btn = QPushButton("➕")
        create_btn.setFixedSize(28, 28)
        create_btn.setToolTip("Create")
        # padding:0 để glyph không bị QSS toàn cục (padding:8px 14px) cắt mất
        create_btn.setStyleSheet("QPushButton { padding: 0px; font-size: 15px; }")
        create_btn.clicked.connect(self._list_create_container)

        crud.addWidget(self._list_entry, 1)
        crud.addWidget(create_btn)
        lay.addLayout(crud)

        self._containers_list = QTreeWidget()
        self._containers_list.setHeaderHidden(True)
        self._containers_list.setIndentation(18)
        self._containers_list.setRootIsDecorated(True)
        self._containers_list.setStyleSheet("""
            QTreeWidget { outline: 0; }
            QTreeWidget::branch:has-siblings:!adjoins-item {
                border-left: 1px solid #93c5fd; }
            QTreeWidget::branch:has-siblings:adjoins-item {
                border-left: 1px solid #93c5fd;
                border-bottom: 1px solid #93c5fd; }
            QTreeWidget::branch:!has-children:!has-siblings:adjoins-item {
                border-bottom: 1px solid #93c5fd; }
        """)
        self._containers_list.itemClicked.connect(
            lambda item, _col: self._on_list_item_clicked(item)
        )
        self._containers_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._containers_list.customContextMenuRequested.connect(
            self._show_list_context_menu
        )
        lay.addWidget(self._containers_list)
        return panel

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initial_sizes_set:
            self._initial_sizes_set = True
            h = self._inner_splitter.height()
            if h > 0:
                self._inner_splitter.setSizes([h * 13 // 20, h * 7 // 20])

    # ── Direction / mode ──────────────────────────────────────────────────────

    def _show_direction_menu(self):
        menu = QMenu(self)
        for label, mode in [
            ("☰  List",          "LIST"),
            ("⇅  Top → Bottom", "TB"),
            ("⇄  Left → Right", "LR"),
        ]:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self._direction == mode)
            action.triggered.connect(lambda _, m=mode: self._set_direction(m))
        menu.exec(self._btn_dir.mapToGlobal(self._btn_dir.rect().bottomLeft()))

    def _set_direction(self, direction: str):
        self._direction = direction
        labels = {"TB": "⇅ TB", "LR": "⇄ LR", "LIST": "☰ List"}
        self._btn_dir.setText(labels[direction])

        is_chart = direction in ("TB", "LR")
        self._top_stack.setCurrentIndex(0 if is_chart else 1)

        if is_chart:
            self.canvas.rebuild(self._containers, self._parents,
                                self._selected, direction)
        else:
            self._refresh_containers_list()

    def _on_search_changed(self, text: str):
        if self._direction == "LIST":
            self._filter_containers_list(text)
        else:
            self.canvas.highlight(text)

    # ── List-mode helpers ─────────────────────────────────────────────────────

    def _refresh_containers_list(self):
        self._containers_list.clear()

        all_names = list(self._containers.keys())
        children: Dict[str, List[str]] = {n: [] for n in all_names}
        roots: List[str] = []
        for name in all_names:
            p = self._parents.get(name)
            if p and p in children:
                children[p].append(name)
            else:
                roots.append(name)

        def _make(name: str) -> QTreeWidgetItem:
            count = len(self._containers.get(name, []))
            it    = QTreeWidgetItem([f"{name}  ({count})"])
            it.setData(0, Qt.UserRole, name)
            for kid in children.get(name, []):
                it.addChild(_make(kid))
            return it

        for root in roots:
            self._containers_list.addTopLevelItem(_make(root))

        self._containers_list.expandAll()
        self._sync_list_selection()

    def _sync_list_selection(self):
        """Highlight item khớp với _selected trong QTreeWidget."""
        def _find(item: QTreeWidgetItem) -> bool:
            if item.data(0, Qt.UserRole) == self._selected:
                self._containers_list.setCurrentItem(item)
                return True
            for i in range(item.childCount()):
                if _find(item.child(i)):
                    return True
            return False
        root = self._containers_list.invisibleRootItem()
        for i in range(root.childCount()):
            if _find(root.child(i)):
                break

    def _filter_containers_list(self, text: str):
        q = text.strip().lower()

        def _matches(item: QTreeWidgetItem) -> bool:
            name = item.data(0, Qt.UserRole) or ""
            if q in name.lower():
                return True
            return any(_matches(item.child(i)) for i in range(item.childCount()))

        def _apply(item: QTreeWidgetItem):
            visible = not q or _matches(item)
            item.setHidden(not visible)
            for i in range(item.childCount()):
                _apply(item.child(i))

        root = self._containers_list.invisibleRootItem()
        for i in range(root.childCount()):
            _apply(root.child(i))

    def _on_list_item_clicked(self, item: QTreeWidgetItem):
        self.on_container_selected(item.data(0, Qt.UserRole))

    def _list_create_container(self):
        name = self._list_entry.text().strip()
        if not name:
            return
        if name in self._containers:
            QMessageBox.warning(self, "Exists", "Container already exists.")
            return
        self._containers[name] = []
        self._list_entry.clear()
        self._emit_changed()
        self.on_container_selected(name)

    def _show_list_context_menu(self, pos):
        item = self._containers_list.itemAt(pos)
        if not item:
            return
        name = item.data(0, Qt.UserRole)
        menu = QMenu(self)
        menu.addAction("✏️ Rename").triggered.connect(
            lambda: self.rename_container(name)
        )
        menu.addSeparator()
        menu.addAction("🔗 Set Parent…").triggered.connect(
            lambda: self.set_parent_for(name)
        )
        menu.addAction("⬆ Make Root").triggered.connect(
            lambda: self.make_root(name)
        )
        menu.addSeparator()
        menu.addAction("🗑 Delete").triggered.connect(
            lambda: self.delete_container(name)
        )
        menu.exec(QCursor.pos())

    def _toggle_file_panel(self):
        sizes = self._inner_splitter.sizes()
        total = sum(sizes)
        if total == 0:
            return
        target = total // 2
        if abs(sizes[1] - target) < 30:          # đang ở ~50% → restore
            saved = getattr(self, "_saved_panel_sizes", None)
            if saved and sum(saved) > 0:
                self._inner_splitter.setSizes(saved)
            else:
                self._inner_splitter.setSizes([total * 3 // 5, total * 2 // 5])
            self._btn_expand_panel.setIcon(_panel_icon(expand=True))
        else:                                     # chưa ở 50% → mở rộng lên 50%
            self._saved_panel_sizes = list(sizes)
            self._inner_splitter.setSizes([target, target])
            self._btn_expand_panel.setIcon(_panel_icon(expand=False))

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, containers: Dict, parents: Dict[str, str]):
        self._containers = containers
        self._parents    = parents
        if self._selected and self._selected not in containers:
            self._selected = None
        if self._direction in ("TB", "LR"):
            self.canvas.rebuild(containers, parents, self._selected, self._direction)
        else:
            self._refresh_containers_list()
        self._refresh_file_list()

    @property
    def selected_container(self) -> Optional[str]:
        return self._selected

    def add_file_to_selected(self, file_path: str) -> bool:
        if not self._selected:
            return False
        files = self._containers.setdefault(self._selected, [])
        if file_path in [f[0] for f in files]:
            return False
        files.append((file_path, {"text": ""}))
        self._emit_changed()
        return True

    # ── Container CRUD ────────────────────────────────────────────────────────

    def create_root_container(self):
        name, ok = QInputDialog.getText(self, "New Container", "Container name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self._containers:
            QMessageBox.warning(self, "Exists", "Container already exists.")
            return
        self._containers[name] = []
        self._emit_changed()
        self.on_container_selected(name)

    def create_sub_container(self, parent_name: str):
        name, ok = QInputDialog.getText(
            self, "New Sub Container",
            f"Sub container name (under '{parent_name}'):"
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self._containers:
            QMessageBox.warning(self, "Exists", "Container already exists.")
            return
        self._containers[name] = []
        self._parents[name]    = parent_name
        self._emit_changed()
        self.on_container_selected(name)

    def rename_container(self, old_name: str):
        name, ok = QInputDialog.getText(
            self, "Rename Container", "New name:", text=old_name
        )
        if not ok or not name.strip() or name.strip() == old_name:
            return
        name = name.strip()
        if name in self._containers:
            QMessageBox.warning(self, "Exists", "Name already exists.")
            return
        self._containers[name] = self._containers.pop(old_name)
        if old_name in self._parents:
            self._parents[name] = self._parents.pop(old_name)
        for k, v in list(self._parents.items()):
            if v == old_name:
                self._parents[k] = name
        if self._selected == old_name:
            self._selected = name
        self._emit_changed()

    def delete_container(self, name: str):
        descendants = self._collect_descendants(name)
        msg = (
            f"Delete '{name}' and {len(descendants)-1} sub-container(s)?"
            if len(descendants) > 1
            else f"Delete container '{name}'?"
        )
        if QMessageBox.question(
            self, "Confirm Delete", msg,
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return
        for n in descendants:
            self._containers.pop(n, None)
            self._parents.pop(n, None)
        if self._selected in descendants:
            self._selected = None
        self._emit_changed()

    def set_parent_for(self, name: str):
        invalid    = set(self._collect_descendants(name))
        candidates = [n for n in self._containers if n not in invalid]
        if not candidates:
            QMessageBox.information(self, "No Candidates",
                "No other containers available to set as parent.")
            return
        current = self._parents.get(name, "")
        if current in candidates:
            candidates.remove(current)
            candidates.insert(0, current)
        chosen, ok = QInputDialog.getItem(
            self, "Set Parent", f"Choose parent for '{name}':",
            candidates, 0, False
        )
        if not ok or not chosen:
            return
        self._parents[name] = chosen
        self._emit_changed()

    def make_root(self, name: str):
        if name in self._parents:
            self._parents.pop(name)
            self._emit_changed()

    def remove_selected_file(self):
        if not self._selected:
            return
        item = self.file_list.currentItem()
        if not item:
            return
        fp    = item.toolTip()
        files = self._containers.get(self._selected, [])
        for i, (f, _) in enumerate(files):
            if f == fp:
                del files[i]
                self._emit_changed()
                self._refresh_file_list()
                break

    # ── Internal ──────────────────────────────────────────────────────────────

    def on_container_selected(self, name: str):
        self._selected = name
        # Sync selection trong canvas
        for n, node in self.canvas._nodes.items():
            node.setSelected(n == name)
            node.update()
        # Sync selection trong list
        self._sync_list_selection()
        self._refresh_file_list()

    def _collect_descendants(self, name: str) -> List[str]:
        result = [name]
        for k, v in self._parents.items():
            if v == name:
                result.extend(self._collect_descendants(k))
        return result

    def _refresh_file_list(self):
        self.file_list.clear()
        if not self._selected or self._selected not in self._containers:
            return
        for fp, _ in self._containers.get(self._selected, []):
            item = QListWidgetItem(os.path.basename(fp))
            item.setToolTip(fp)
            if not os.path.exists(fp):
                item.setForeground(QBrush(QColor("#f85149")))
            self.file_list.addItem(item)

    def _emit_changed(self):
        self.containers_changed.emit(self._containers, self._parents)
        if self._direction in ("TB", "LR"):
            self.canvas.rebuild(self._containers, self._parents,
                                self._selected, self._direction)
        else:
            self._refresh_containers_list()
        self._refresh_file_list()

    def _on_file_clicked(self, item: QListWidgetItem):
        self.file_clicked.emit(item.toolTip())

    def _on_file_double_clicked(self, item: QListWidgetItem):
        fp = item.toolTip()
        if os.path.exists(fp):
            self.file_open_requested.emit(fp)

    def _show_file_context_menu(self, pos):
        item = self.file_list.itemAt(pos)
        if not item or not self._selected:
            return
        fp   = item.toolTip()
        menu = QMenu()
        menu.addAction("📁 Open Folder").triggered.connect(
            lambda: os.startfile(os.path.dirname(fp))
        )
        menu.addSeparator()
        menu.addAction("📓 Add this file to NotebookLM").triggered.connect(
            lambda: self.file_context_menu_requested.emit(self._selected, fp, False)
        )
        menu.addAction("📓 Add all files in container to NotebookLM").triggered.connect(
            lambda: self.file_context_menu_requested.emit(self._selected, fp, True)
        )
        menu.exec(QCursor.pos())
