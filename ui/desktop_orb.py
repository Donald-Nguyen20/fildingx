"""ui/desktop_orb.py — Floating desktop widget hiển thị Neural Orb.

Không có thanh tiêu đề — chỉ hiện canvas neural trong suốt.
- Kéo bất kỳ đâu để di chuyển.
- Double-click để restore full app.
- Right-click → menu "Mở App" / "Đóng Orb".
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QPoint, QUrl, Signal
from PySide6.QtGui import QColor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMenu, QVBoxLayout, QWidget

_ORB_W = 460
_ORB_H = 420


class _Overlay(QWidget):
    """Widget trong suốt phủ toàn bộ orb — bắt mọi mouse event."""

    def __init__(self, orb: "DesktopOrb"):
        super().__init__(orb)
        self._orb = orb
        self._drag_pos: QPoint | None = None
        self.setGeometry(0, 0, _ORB_W, _ORB_H)
        # Trong suốt về hình ảnh nhưng vẫn nhận chuột
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx_menu)

    def _ctx_menu(self, pos) -> None:
        m = QMenu(self)
        m.setStyleSheet("""
            QMenu { background:#101520; border:1px solid #1e2d45; color:#8ab4d4; }
            QMenu::item:selected { background:#1e3050; }
        """)
        m.addAction("⬡  Mở App", self._orb.open_main.emit)
        m.addSeparator()
        m.addAction("✕  Đóng Orb", self._orb.hide)
        m.exec(self.mapToGlobal(pos))

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self._orb.frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:
        if e.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self._orb.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _) -> None:
        self._drag_pos = None

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._orb.open_main.emit()


class DesktopOrb(QWidget):
    open_main = Signal()

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._loaded = False
        self._view: QWebEngineView | None = None
        self._setup_geometry()
        self._build_ui()

    def _setup_geometry(self) -> None:
        self.setFixedSize(_ORB_W, _ORB_H)
        screen = QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            self.move(g.right() - _ORB_W - 20, g.bottom() - _ORB_H - 40)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._view = QWebEngineView()
        self._view.page().setBackgroundColor(QColor(Qt.GlobalColor.transparent))
        self._view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        root.addWidget(self._view, 1)

        html = Path(__file__).parent / "claude_assistant" / "neural_interface.html"
        self._view.load(QUrl.fromLocalFile(str(html)))
        self._view.loadFinished.connect(self._on_loaded)

        # Overlay phải raise sau khi view được add
        self._overlay = _Overlay(self)
        self._overlay.raise_()

    def _on_loaded(self, _: bool) -> None:
        self._loaded = True
        self._view.setZoomFactor(_ORB_W / 620)
        self._view.page().runJavaScript("""
            (function(){
                var lbl  = document.getElementById('lbl');
                var ctrl = document.querySelector('.ctrl');
                if (lbl)  lbl.style.display  = 'none';
                if (ctrl) ctrl.style.display = 'none';
                document.body.style.overflow = 'hidden';
                document.body.style.margin   = '0';
                setS(0);
                startAutoCycle(8000);
            })();
        """)

    def set_state(self, state: int) -> None:
        if self._loaded:
            self._view.page().runJavaScript(f"setS({state})")
