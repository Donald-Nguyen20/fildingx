"""
ui/main_window.py — FileSearchApp (main window).

Bugs đã fix so với Finding7.1.py gốc:
  1. load_data_from_file() chỉ gọi 1 lần (gốc gọi 2 lần + reset containers ở giữa)
  2. DATA_FILE / IMAGE_DIR / os.makedirs định nghĩa 2 lần → dùng paths.py
  3. Import trùng lặp đã xoá (hud_widgets x2, os/sys x2, QIcon/QPixmap x2, QTextEdit x2)
  4. add_exe_to_frame_2 định nghĩa 2 lần → giữ phiên bản đúng (create_exe_button)
  5. Dòng lạc `self.main_widget.setStyleSheet(...)` ở cuối IndexSearchWindow.open_file đã xoá
  6. search_duplicates chạy trên QThread → UI không bị đóng băng
  7. display_results dùng statusBar thay vì QMessageBox blocking
"""
import os
import json
import webbrowser
from datetime import datetime
from functools import partial

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QLineEdit, QPushButton, QFileDialog,
    QTreeWidget, QListWidget, QListWidgetItem, QMessageBox,
    QTextEdit, QDialog, QMenu, QLCDNumber, QApplication,
    QStackedWidget, QSplitter, QTabWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QPalette, QColor, QAction, QKeySequence, QBrush

import paths
from ui import themes as _themes
import core.search_engine    as search_engine
import core.container_manager as container_manager
from core.container_manager import get_file_containers
from core.file_stats import record_open
import core.synonym_manager   as synonym_manager
import core.excel_bridge      as excel_bridge
from core.workers import DuplicateSearchWorker

from ui.hud_widgets import qss_hud_metal_header_feel, qss_white_results
from ui.tree_sorter import TreeSortHelper
from ui.help_dialog import HelpDialog
from ui.index_search_window import IndexSearchWindow, IndexSearchWidget
from ui.notebooklm_window import NotebookLMWidget
from ui.list_files_window import show_list_files_window
from ui.pdf_preview import PdfPreviewWidget


class MultiFolderDialog(QDialog):
    """Dialog chọn nhiều folder để search cùng lúc."""

    def __init__(self, current_folders: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Folders")
        self.setMinimumWidth(560)
        self.setModal(True)

        from PySide6.QtWidgets import QScrollArea, QDialogButtonBox

        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        # Scroll area chứa các hàng folder
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumHeight(120)
        scroll.setMaximumHeight(400)
        inner_widget = QWidget()
        self._rows_lay = QVBoxLayout(inner_widget)
        self._rows_lay.setSpacing(6)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(inner_widget)
        outer.addWidget(scroll)

        self._rows: list[QLineEdit] = []

        # Tạo 3 hàng mặc định
        init = current_folders if current_folders else ["", "", ""]
        for i, val in enumerate(init):
            self._add_row(val, i + 1)
        # Nếu current_folders > 3, thêm thêm
        for i in range(3, len(current_folders)):
            self._add_row(current_folders[i], i + 1)

        # Nút Add source
        btn_add = QPushButton("＋ Add source")
        btn_add.setFixedHeight(32)
        btn_add.clicked.connect(self._add_empty_row)
        outer.addWidget(btn_add)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        outer.addWidget(btns)

    def _add_row(self, value: str = "", index: int | None = None):
        n = index if index is not None else len(self._rows) + 1
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        entry = QLineEdit()
        entry.setPlaceholderText(f"Folder {n} (leave empty to skip)")
        entry.setFixedHeight(34)
        entry.setText(value)
        btn_browse = QPushButton("📂")
        btn_browse.setFixedSize(34, 34)
        btn_browse.setToolTip("Browse")
        btn_browse.clicked.connect(lambda _=False, e=entry: self._browse(e))
        btn_remove = QPushButton("✕")
        btn_remove.setFixedSize(28, 34)
        btn_remove.setToolTip("Remove")
        btn_remove.clicked.connect(lambda _=False, w=row_widget, e=entry: self._remove_row(w, e))
        row.addWidget(entry, 1)
        row.addWidget(btn_browse)
        row.addWidget(btn_remove)
        self._rows_lay.addWidget(row_widget)
        self._rows.append(entry)

    def _add_empty_row(self):
        self._add_row("", len(self._rows) + 1)

    def _remove_row(self, row_widget: QWidget, entry: QLineEdit):
        if len(self._rows) <= 1:
            return  # giữ ít nhất 1 hàng
        self._rows.remove(entry)
        row_widget.setParent(None)
        row_widget.deleteLater()

    def _browse(self, entry: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            entry.setText(folder)

    def get_folders(self) -> list[str]:
        return [e.text().strip() for e in self._rows if e.text().strip()]


class FileSearchApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Search and Management")
        self.setGeometry(100, 100, 1280, 800)

        self.containers:      dict = {}
        self.exe_addons:      list = []
        self._dup_worker           = None
        self._sidebar_btns:   list = []
        self._right_stack          = None

        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_widget.setStyleSheet(qss_hud_metal_header_feel() + qss_white_results())

        self.root_layout = QVBoxLayout(self.main_widget)
        self.root_layout.setContentsMargins(8, 8, 8, 8)
        self.root_layout.setSpacing(6)

        self._setup_toolbar()
        self._setup_body()
        self._bind_help_f1()

        self.load_data_from_file()
        self.load_exe_addons()


        os.makedirs(paths.IMAGE_DIR, exist_ok=True)

    # ══════════════════════════════════════════════════════════════
    #  SETUP HELPERS
    # ══════════════════════════════════════════════════════════════

    def _setup_toolbar(self):
        """Compact toolbar: folder + keyword + search + AI button."""
        toolbar = QFrame()
        toolbar.setObjectName("toolbarFrame")
        toolbar.setFixedHeight(62)
        toolbar.setStyleSheet("""
            QFrame#toolbarFrame {
                background: rgba(255,255,255,8);
                border: 1px solid rgba(255,255,255,15);
                border-radius: 8px;
            }
        """)
        h = QHBoxLayout(toolbar)
        h.setContentsMargins(14, 0, 14, 0)
        h.setSpacing(8)

        self._multi_folder_mode = False
        self._multi_folders: list[str] = []

        self.btn_folder_toggle = QPushButton("Folder:")
        self.btn_folder_toggle.setFixedWidth(82)
        self.btn_folder_toggle.setMinimumHeight(40)
        self.btn_folder_toggle.setToolTip("Click to switch to multi-folder mode")
        self.btn_folder_toggle.clicked.connect(self._toggle_folder_mode)
        h.addWidget(self.btn_folder_toggle)

        self.folder_entry = QLineEdit()
        self.folder_entry.setPlaceholderText("Select folder…")
        h.addWidget(self.folder_entry, 2)

        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setMinimumWidth(90)
        self.browse_btn.setMinimumHeight(40)
        self.browse_btn.clicked.connect(self.browse_folder)
        h.addWidget(self.browse_btn)

        sep = QFrame(); sep.setFrameShape(QFrame.VLine)
        sep.setFixedHeight(28)
        sep.setStyleSheet("color: rgba(255,255,255,40);")
        h.addWidget(sep)

        lbl_k = QLabel("Keyword:")
        lbl_k.setFixedWidth(60)
        h.addWidget(lbl_k)
        self.filename_entry = QLineEdit()
        self.filename_entry.setPlaceholderText("Search by name… ($stats, @fuzzy, A%B, A*B)")
        self.filename_entry.returnPressed.connect(self.search_files)
        h.addWidget(self.filename_entry, 3)
        search_btn = QPushButton("🔍  Search")
        search_btn.setMinimumWidth(120)
        search_btn.setMinimumHeight(40)
        search_btn.clicked.connect(self.search_files)
        h.addWidget(search_btn)

        self.lcd_number = QLCDNumber()
        self.lcd_number.setDigitCount(6)
        self.lcd_number.setFixedSize(96, 36)
        self.lcd_number.display(0)
        pal = self.lcd_number.palette()
        pal.setColor(QPalette.WindowText, QColor("black"))
        pal.setColor(QPalette.Light,      QColor("#4a5d23"))
        pal.setColor(QPalette.Dark,       QColor("black"))
        self.lcd_number.setPalette(pal)
        h.addWidget(self.lcd_number)

        h.addStretch(1)

        self.root_layout.addWidget(toolbar)

    def _setup_body(self):
        """Sidebar (left) + Tree (center) + QStackedWidget (right)."""
        body = QHBoxLayout()
        body.setSpacing(6)

        # ── Sidebar ──────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(80)
        sidebar.setStyleSheet("""
            QFrame#sidebar {
                background: rgba(30,40,60,180);
                border-radius: 8px;
            }
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 8px;
                font-family: "Segoe UI Emoji";
                font-size: 28px;
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
        """)
        sb_lay = QVBoxLayout(sidebar)
        sb_lay.setContentsMargins(4, 16, 4, 8)
        sb_lay.setSpacing(4)
        sb_lay.setAlignment(Qt.AlignTop)

        from PySide6.QtGui import QFont as _QFont

        for emoji, tip, idx in [("🗂️","Containers",0),("🛠️","Tools",1),
                                 ("🧩","Add-ons",2),("📄","Preview",3)]:
            btn = QPushButton()
            btn.setFixedSize(72, 72)
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    border-radius: 8px;
                }
                QPushButton:hover {
                    background: rgba(255,255,255,30);
                    border: 1px solid rgba(255,255,255,70);
                }
                QPushButton:checked {
                    background: rgba(40,180,110,50);
                    border-left: 3px solid rgba(60,210,140,220);
                }
            """)

            # Layout bên trong button: emoji lớn + label nhỏ
            v = QVBoxLayout(btn)
            v.setContentsMargins(0, 6, 0, 4)
            v.setSpacing(1)

            lbl_icon = QLabel(emoji)
            lbl_icon.setAlignment(Qt.AlignCenter)
            lbl_icon.setFont(_QFont("Segoe UI Emoji", 22))
            lbl_icon.setAttribute(Qt.WA_TransparentForMouseEvents)

            lbl_text = QLabel(tip)
            lbl_text.setAlignment(Qt.AlignCenter)
            lbl_text.setFont(_QFont("Segoe UI", 7))
            lbl_text.setStyleSheet("color: rgba(200,220,255,200);")
            lbl_text.setAttribute(Qt.WA_TransparentForMouseEvents)

            v.addWidget(lbl_icon)
            v.addWidget(lbl_text)

            btn.clicked.connect(lambda _, i=idx, b=btn: self._switch_panel(i, b))
            self._sidebar_btns.append(btn)
            sb_lay.addWidget(btn)

        sb_lay.addStretch()
        body.addWidget(sidebar)

        # ── Tree ─────────────────────────────────────────────────
        self.tree_widget = QTreeWidget()
        self.sort_helper = TreeSortHelper(self.tree_widget)
        self.tree_widget.setStyleSheet("""
            QTreeWidget { outline:0; selection-background-color: transparent; }
            QTreeWidget::item:hover                   { background: rgba(0,120,215,25); }
            QTreeWidget::item:selected:active,
            QTreeWidget::item:selected:focus          { background: rgba(0,120,215,170); color:white; }
            QTreeWidget::item:selected:!active        { background: rgba(0,120,215,80);  color:black; }
            QTreeWidget::item:focus                   { outline: none; }
        """)
        self.tree_widget.setFocusPolicy(Qt.StrongFocus)
        self.tree_widget.itemPressed.connect(lambda *_: self.tree_widget.setFocus())
        self.tree_widget.itemClicked.connect(lambda *_: self.tree_widget.setFocus())
        self.tree_widget.setColumnCount(6)
        self.tree_widget.setHeaderLabels(["FILE NAME","DATE MODIFIED","TYPE","SIZE (MB)","PATH","IN CONTAINERS"])
        self.tree_widget.setColumnWidth(0, 700)
        self.tree_widget.setColumnWidth(1, 129)
        self.tree_widget.setColumnWidth(2, 80)
        self.tree_widget.setColumnWidth(3, 90)
        self.tree_widget.setColumnWidth(4, 350)
        self.tree_widget.setColumnWidth(5, 200)
        self.tree_widget.itemDoubleClicked.connect(self.open_file)
        self.tree_widget.itemClicked.connect(self._on_tree_item_clicked)
        self.tree_widget.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_treeview_context_menu)
        self.tree_widget.viewport().installEventFilter(self)

        # ── PDF Preview ───────────────────────────────────────────
        self.pdf_preview = PdfPreviewWidget()
        self.pdf_preview.hide()

        # ── Tab: File Search | DB Search ─────────────────────────
        self._search_tabs = QTabWidget()
        self._search_tabs.setStyleSheet("""
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
        """)
        self._search_tabs.addTab(self.tree_widget, "🔍 File Search")
        self.db_search_widget = IndexSearchWidget()
        self._search_tabs.addTab(self.db_search_widget, "🗄 DB Search")
        self.notebooklm_widget = NotebookLMWidget()
        self._search_tabs.addTab(self.notebooklm_widget, "📓 NotebookLM")
        self.notebooklm_widget.open_preview.connect(self._open_preview_from_nlm)
        self.notebooklm_widget.goto_page_signal.connect(self.pdf_preview.goto_page)
        self.notebooklm_widget.request_mindmap.connect(self._mindmap_from_nlm_source)
        self.notebooklm_widget.request_mindmap_online.connect(self._mindmap_online_in_preview)

        # Splitter: tabs (trái) | pdf preview (phải)
        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.addWidget(self._search_tabs)
        self._splitter.addWidget(self.pdf_preview)
        self._splitter.setSizes([10000, 0])
        self._splitter.setHandleWidth(4)
        self._splitter.setStyleSheet("QSplitter::handle { background: rgba(255,255,255,15); border-radius: 2px; }")

        # ── Right stack ──────────────────────────────────────────
        self._right_stack = QStackedWidget()
        self._right_stack.setVisible(False)
        self._right_stack.setMinimumWidth(300)
        self._right_stack.addWidget(self._build_containers_page())  # 0
        self._right_stack.addWidget(self._build_tools_page())       # 1
        self._right_stack.addWidget(self._build_exe_page())         # 2

        # Outer splitter: center (tabs+preview) | right stack — kéo ngang được
        self._outer_splitter = QSplitter(Qt.Horizontal)
        self._outer_splitter.addWidget(self._splitter)
        self._outer_splitter.addWidget(self._right_stack)
        self._outer_splitter.setHandleWidth(5)
        self._outer_splitter.setStyleSheet("QSplitter::handle { background: rgba(255,255,255,15); border-radius: 2px; }")
        self._outer_splitter.setSizes([10000, 0])
        body.addWidget(self._outer_splitter, 1)

        self.root_layout.addLayout(body)

    def _switch_panel(self, index: int, clicked_btn: QPushButton):
        if index == 3:                          # Preview → toggle splitter
            is_on = self.pdf_preview.isVisible()
            if is_on:
                self.pdf_preview.hide()
                self._splitter.setSizes([10000, 0])
                clicked_btn.setChecked(False)
            else:
                total = self._splitter.width()
                self._splitter.setSizes([total // 2, total // 2])
                self.pdf_preview.show()
                clicked_btn.setChecked(True)
            return

        already_visible = self._right_stack.isVisible()
        already_same    = self._right_stack.currentIndex() == index
        if already_visible and already_same:
            # Lưu kích thước hiện tại rồi collapse
            sizes = self._outer_splitter.sizes()
            self._right_stack_saved_width = sizes[1]
            self._outer_splitter.setSizes([sizes[0] + sizes[1], 0])
            self._right_stack.setVisible(False)
            clicked_btn.setChecked(False)
        else:
            self._right_stack.setCurrentIndex(index)
            if not already_visible:
                self._right_stack.setVisible(True)
                saved = getattr(self, "_right_stack_saved_width", 420)
                total = self._outer_splitter.width()
                self._outer_splitter.setSizes([max(total - saved, 200), saved])
            for btn in self._sidebar_btns:
                btn.setChecked(False)
            clicked_btn.setChecked(True)

    def _build_containers_page(self) -> QFrame:
        page = QFrame()
        page.setObjectName("rightFrame")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        self.container_search_bar = QLineEdit()
        self.container_search_bar.setPlaceholderText("Search containers…")
        self.container_search_bar.textChanged.connect(self.filter_containers)
        lay.addWidget(self.container_search_bar)

        crud_row = QHBoxLayout()
        del_btn = QPushButton("Delete")
        del_btn.setMinimumHeight(36)
        del_btn.clicked.connect(self.delete_container)
        self.container_entry = QLineEdit()
        self.container_entry.setMinimumHeight(36)
        create_btn = QPushButton("Create")
        create_btn.setMinimumHeight(36)
        create_btn.clicked.connect(self.create_container)
        crud_row.addWidget(del_btn)
        crud_row.addWidget(self.container_entry)
        crud_row.addWidget(create_btn)
        lay.addLayout(crud_row)

        self.containers_list = QListWidget()
        self.containers_list.itemClicked.connect(self.display_container_files)

        self.container_files_list = QListWidget()
        self.container_files_list.itemClicked.connect(self.show_note_frame)
        self.container_files_list.itemDoubleClicked.connect(self.open_file_from_container)
        self.container_files_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.container_files_list.customContextMenuRequested.connect(
            self.show_context_menu_for_container
        )

        list_splitter = QSplitter(Qt.Vertical)
        list_splitter.addWidget(self.containers_list)
        list_splitter.addWidget(self.container_files_list)
        list_splitter.setStretchFactor(0, 1)
        list_splitter.setStretchFactor(1, 1)
        list_splitter.setHandleWidth(6)
        lay.addWidget(list_splitter)

        file_row = QHBoxLayout()
        add_btn = QPushButton("Add File")
        add_btn.setMinimumHeight(36)
        add_btn.clicked.connect(self.add_to_container)
        del_file_btn = QPushButton("Delete File")
        del_file_btn.setMinimumHeight(36)
        del_file_btn.clicked.connect(self.delete_file_from_container)
        file_row.addWidget(add_btn)
        file_row.addWidget(del_file_btn)
        lay.addLayout(file_row)
        return page

    def _build_tools_page(self) -> QFrame:
        page = QFrame()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)
        lay.setAlignment(Qt.AlignTop)

        dup_btn = QPushButton("Search Duplicates")
        dup_btn.clicked.connect(self.search_duplicates)
        self.search_duplicates_button = dup_btn

        for btn, fn in [
            (dup_btn,                                    None),
            (QPushButton("Open Notes"),                  self.open_or_create_notes),
            (QPushButton("Get Hyperlink for Notes"),     self.get_hyperlink_from_tree_view),
            (QPushButton("List Files"),                  self.list_files_in_folder),
        ]:
            if fn:
                btn.clicked.connect(fn)
            btn.setMinimumHeight(38)
            lay.addWidget(btn)
        return page

    def _build_exe_page(self) -> QFrame:
        page = QFrame()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        add_exe_btn = QPushButton("ADD ON ➕")
        f = add_exe_btn.font(); f.setPointSize(12); add_exe_btn.setFont(f)
        add_exe_btn.setStyleSheet("""
            QPushButton { background:#4CAF50; color:white; border-radius:8px; padding:5px; }
            QPushButton:hover { background:#45a049; }
        """)
        add_exe_btn.clicked.connect(self.add_exe_to_frame_2)
        lay.addWidget(add_exe_btn)

        self.exe_list_layout = QVBoxLayout()
        lay.addLayout(self.exe_list_layout)
        lay.addStretch()
        return page

    def _bind_help_f1(self):
        act = QAction(self)
        act.setShortcut(QKeySequence("F1"))
        act.triggered.connect(lambda: HelpDialog(self).exec())
        self.addAction(act)

    def _apply_theme(self, index: int):
        _themes.set_index(index)
        t = _themes.get_current()
        self.main_widget.setStyleSheet(t["qss"])
        self.main_widget.repaint()
        from ui.hud_widgets import HudPanel
        for panel in self.findChildren(HudPanel):
            panel.repaint()
        self.statusBar().showMessage(f"Theme: {t['name']}", 3000)

    # ══════════════════════════════════════════════════════════════
    #  TOGGLE PANELS
    # ══════════════════════════════════════════════════════════════

    def toggle_hidden_frame(self):
        self._switch_panel(1, self._sidebar_btns[1])

    def toggle_hidden_frame_2(self):
        self._switch_panel(2, self._sidebar_btns[2])

    # ══════════════════════════════════════════════════════════════
    #  FILE UTILS
    # ══════════════════════════════════════════════════════════════

    def format_mtime(self, path: str) -> str:
        try:
            return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return ""

    def get_file_type(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        return ext[1:].upper() if ext else "FILE"

    def get_file_size_mb(self, path: str) -> str:
        try:
            return f"{os.path.getsize(path) / (1024 * 1024):.2f}"
        except Exception:
            return ""

    def _make_tree_item(self, name: str, path: str):
        try:    mtime_ts  = os.path.getmtime(path)
        except OSError: mtime_ts  = None
        try:    size_bytes = os.path.getsize(path)
        except OSError: size_bytes = None
        return self.sort_helper.make_item(
            name       = name,
            date_text  = self.format_mtime(path),
            type_text  = self.get_file_type(path),
            size_text  = self.get_file_size_mb(path),
            path       = path,
            mtime_ts   = mtime_ts,
            size_bytes = size_bytes,
        )

    # ══════════════════════════════════════════════════════════════
    #  SEARCH
    # ══════════════════════════════════════════════════════════════

    def _toggle_folder_mode(self):
        self._multi_folder_mode = not self._multi_folder_mode
        if self._multi_folder_mode:
            self.btn_folder_toggle.setText("Folders:")
            self.btn_folder_toggle.setToolTip("Click to switch back to single folder mode")
            self.btn_folder_toggle.setStyleSheet(
                "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                "stop:0 rgba(251,146,60,230),stop:1 rgba(234,88,12,230));"
                "color: white; border: 1.5px solid rgba(194,65,12,160);"
                "border-radius: 10px; font-weight: 900;"
            )
            self.folder_entry.setPlaceholderText(
                " | ".join(self._multi_folders) if self._multi_folders
                else "Multiple folders — click Browse to select…"
            )
            self.folder_entry.setReadOnly(True)
        else:
            self.btn_folder_toggle.setText("Folder:")
            self.btn_folder_toggle.setToolTip("Click to switch to multi-folder mode")
            self.btn_folder_toggle.setStyleSheet("")  # reset về theme mặc định
            self.folder_entry.setReadOnly(False)
            self.folder_entry.setPlaceholderText("Select folder…")

    def browse_folder(self):
        if self._multi_folder_mode:
            dlg = MultiFolderDialog(self._multi_folders, self)
            if dlg.exec() == QDialog.Accepted:
                self._multi_folders = dlg.get_folders()
                if self._multi_folders:
                    self.folder_entry.setText(" | ".join(self._multi_folders))
                else:
                    self.folder_entry.clear()
        else:
            folder = QFileDialog.getExistingDirectory(self, "Select Folder")
            if folder:
                self.folder_entry.setText(folder)


    def _get_search_folders(self) -> list[str]:
        """Trả về danh sách folder cần search (1 hoặc nhiều)."""
        if self._multi_folder_mode:
            return [f for f in self._multi_folders if f]
        folder = self.folder_entry.text().strip()
        return [folder] if folder else []

    def search_files(self):
        folders = self._get_search_folders()
        keyword = self.filename_entry.text().strip()
        if not folders or not keyword:
            QMessageBox.warning(self, "Input Error", "Please provide the folder path and keyword.")
            return

        if keyword == "$synonym":
            self.edit_synonyms()
            return

        if keyword == "$stats":
            from ui.stats_dialog import StatsDialog
            StatsDialog(paths.STATS_FILE, self).exec()
            return

        import re as _re
        _cm = _re.fullmatch(r"@colour(\d)", keyword, _re.IGNORECASE)
        if _cm:
            self._apply_theme(int(_cm.group(1)))
            return

        results = []
        for folder in folders:
            if keyword.startswith("@"):
                synonyms = synonym_manager.load_synonyms(paths.SYNONYMS_FILE)
                results += search_engine.fuzzy_search(folder, keyword[1:], synonyms)
            else:
                results += search_engine.search_files_by_name(folder, keyword)

        self.display_results(results)

    def display_results(self, results: list):
        self.tree_widget.clear()
        if results:
            for name, path in results:
                self.tree_widget.addTopLevelItem(self._make_tree_item(name, path))
            self._mark_saved_items()
            self.lcd_number.display(len(results))
            self.statusBar().showMessage(f"Found {len(results)} file(s).")
        else:
            self.lcd_number.display(0)
            self.statusBar().showMessage("No files found.")
            self.tree_widget.addTopLevelItem(
                self.sort_helper.make_item("No matches found", "", "", "", "",
                                           mtime_ts=None, size_bytes=None)
            )

    def _mark_saved_items(self):
        """Tô màu vàng nhạt và hiện tên container ở cột 5 cho file đã lưu."""
        highlight = QBrush(QColor(255, 248, 200))   # vàng nhạt
        normal    = QBrush(QColor(Qt.transparent))

        def _mark(item):
            path = item.text(4)   # cột PATH — không thay đổi
            names = get_file_containers(path, self.containers)
            if names:
                for col in range(self.tree_widget.columnCount()):
                    item.setBackground(col, highlight)
                name0 = item.text(0)
                if not name0.startswith("📌"):
                    item.setText(0, f"📌 {name0}")
                item.setToolTip(0, "Saved to: " + ", ".join(names))
                item.setText(5, ", ".join(names))   # cột riêng, không đụng PATH
            else:
                for col in range(self.tree_widget.columnCount()):
                    item.setBackground(col, normal)
                item.setText(5, "")

        root = self.tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            _mark(parent)
            for j in range(parent.childCount()):   # group duplicate
                _mark(parent.child(j))

    # ── Duplicate search (background thread) ─────────────────────

    def search_duplicates(self):
        folders = self._get_search_folders()
        if not folders:
            QMessageBox.warning(self, "Input Error", "Please provide the folder path.")
            return
        # DuplicateSearchWorker nhận 1 folder — dùng folder đầu tiên
        folder = folders[0]

        self.search_duplicates_button.setEnabled(False)
        self.search_duplicates_button.setText("Searching…")
        self.tree_widget.clear()
        self.statusBar().showMessage("Searching for duplicates…")

        self._dup_worker = DuplicateSearchWorker(folder)
        self._dup_worker.finished.connect(self._on_duplicates_found)
        self._dup_worker.start()

    def _on_duplicates_found(self, groups: list):
        self.search_duplicates_button.setEnabled(True)
        self.search_duplicates_button.setText("Search Duplicates")

        if not groups:
            self.lcd_number.display(0)
            self.statusBar().showMessage("No duplicates found.")
            self.tree_widget.addTopLevelItem(
                self.sort_helper.make_item("No duplicates found", "", "", "", "",
                                           mtime_ts=None, size_bytes=None)
            )
            return

        total = 0
        for idx, g in enumerate(groups, start=1):
            total += len(g["files"])
            parent = self.sort_helper.make_item(
                name=f"GROUP {idx}  •  {len(g['files'])} files",
                date_text="", type_text="DUP", size_text="", path="",
                mtime_ts=None, size_bytes=None,
            )
            self.tree_widget.addTopLevelItem(parent)
            parent.setExpanded(True)
            for name, path in g["files"]:
                parent.addChild(self._make_tree_item(name, path))

        self._mark_saved_items()
        self.lcd_number.display(total)
        self.statusBar().showMessage(
            f"Found {len(groups)} duplicate group(s), {total} files total."
        )

    # ══════════════════════════════════════════════════════════════
    #  TREE CONTEXT MENU / OPEN FILE
    # ══════════════════════════════════════════════════════════════

    def show_treeview_context_menu(self, position):
        item = self.tree_widget.itemAt(position)
        if not item:
            return
        file_path = item.text(4)
        menu = QMenu(self)
        menu.addAction("Open Folder").triggered.connect(
            lambda: self._open_folder_path(os.path.dirname(file_path))
        )
        menu.addAction("📋 Copy Path").triggered.connect(
            lambda: self.get_link_from_tree_view()
        )
        menu.addAction("📋 Copy Name").triggered.connect(
            lambda: self.get_name_from_tree_view()
        )
        menu.addSeparator()
        menu.addAction("📓 Add to NotebookLM").triggered.connect(
            self._add_selected_to_notebooklm
        )
        menu.addAction("💬 Ask NbLM about this file").triggered.connect(
            lambda: self._ask_nlm_about_file(file_path)
        )
        menu.addSeparator()
        menu.addAction("📁 Move to folder").triggered.connect(
            lambda: self._move_files_from_tree(item)
        )
        menu.addAction("🗑 Delete file").triggered.connect(
            lambda: self._delete_file_from_tree(item, file_path)
        )
        menu.exec(QCursor.pos())

    def _ask_nlm_about_file(self, file_path: str):
        """Tạo notebook tạm, upload file, switch sang NbLM tab để chat."""
        from ui.notebooklm_window import is_nlm_logged_in, NotebookLMWidget, TempChatWorker
        if not is_nlm_logged_in():
            QMessageBox.warning(self, "Not Logged In",
                "Please log in to NotebookLM first.\n\nGo to the 📓 NotebookLM tab and click 🔑 Switch Account.")
            return
        NLM_SUPPORTED = {".pdf", ".txt", ".doc", ".docx", ".pptx", ".md"}
        if os.path.splitext(file_path)[1].lower() not in NLM_SUPPORTED:
            QMessageBox.warning(self, "Unsupported Format",
                "NotebookLM chỉ hỗ trợ: .pdf .txt .doc .docx .pptx .md")
            return
        # Switch to NbLM tab
        for i in range(self._search_tabs.count()):
            if isinstance(self._search_tabs.widget(i), NotebookLMWidget):
                self._search_tabs.setCurrentIndex(i)
                break
        fname = os.path.basename(file_path)
        self.statusBar().showMessage(f"⏳ Uploading {fname} to NbLM…")
        self.notebooklm_widget.lbl_nb_name.setText(f"⏳ Uploading {fname}…")
        w = TempChatWorker(file_path)
        w.done.connect(self._on_temp_chat_ready)
        w.error.connect(lambda e: (
            self.statusBar().showMessage(f"NbLM upload error: {e}"),
            QMessageBox.critical(self, "Error", e),
        ))
        if not hasattr(self, "_temp_chat_workers"):
            self._temp_chat_workers = []
        self._temp_chat_workers.append(w)
        w.finished.connect(lambda: self._temp_chat_workers.remove(w) if w in self._temp_chat_workers else None)
        w.finished.connect(w.deleteLater)
        w.start()

    def _on_temp_chat_ready(self, nb_id: str, nb_title: str):
        self.statusBar().showMessage(f"✅ Ready — '{nb_title}' (will be deleted on close)")
        if not hasattr(self, "_temp_nb_ids"):
            self._temp_nb_ids = []
        self._temp_nb_ids.append(nb_id)
        self.notebooklm_widget.open_temp_chat_notebook(nb_id, nb_title)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QMouseEvent
        if obj is self.tree_widget.viewport() and event.type() == QEvent.MouseButtonPress:
            item = self.tree_widget.itemAt(event.pos())
            if item is None:
                self.tree_widget.clearSelection()
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        self._cleanup_temp_notebooks()
        event.accept()

    def _cleanup_temp_notebooks(self):
        ids = getattr(self, "_temp_nb_ids", [])
        if not ids:
            return
        import asyncio
        from notebooklm import NotebookLMClient
        async def _delete_all():
            async with await NotebookLMClient.from_storage() as client:
                for nb_id in ids:
                    try:
                        await client.notebooks.delete(nb_id)
                    except Exception:
                        pass
        try:
            asyncio.run(_delete_all())
        except Exception:
            pass
        self._temp_nb_ids = []

    def _move_files_from_tree(self, item):
        """Di chuyển file(s) đã chọn sang thư mục khác."""
        import shutil
        selected = self.tree_widget.selectedItems()
        targets = [(i, i.text(4)) for i in (selected if selected else [item])]
        targets = [(i, p) for i, p in targets if p and os.path.isfile(p)]
        if not targets:
            QMessageBox.warning(self, "File Not Found", "No valid files selected.")
            return
        dest_dir = QFileDialog.getExistingDirectory(self, "Select Destination Folder", "")
        if not dest_dir:
            return
        failed = []
        moved_items = []
        for it, path in targets:
            dest = os.path.join(dest_dir, os.path.basename(path))
            if os.path.abspath(path) == os.path.abspath(dest):
                continue
            try:
                shutil.move(path, dest)
                moved_items.append(it)
            except Exception as e:
                failed.append(f"{os.path.basename(path)}: {e}")
        for it in moved_items:
            parent = it.parent()
            if parent:
                parent.removeChild(it)
            else:
                idx = self.tree_widget.indexOfTopLevelItem(it)
                if idx >= 0:
                    self.tree_widget.takeTopLevelItem(idx)
        if failed:
            QMessageBox.warning(self, "Error", "Could not move:\n" + "\n".join(failed))
        if moved_items:
            self.statusBar().showMessage(f'Moved {len(moved_items)} file(s) to {dest_dir}')

    def _delete_file_from_tree(self, item, file_path: str):
        """Xác nhận rồi xóa file(s) khỏi disk và khỏi tree."""
        selected = self.tree_widget.selectedItems()
        # Nếu không có multi-select, dùng item được click
        targets = [(i, i.text(4)) for i in (selected if selected else [item])]
        targets = [(i, p) for i, p in targets if p and os.path.isfile(p)]
        if not targets:
            QMessageBox.warning(self, "File Not Found", "No valid files selected.")
            return
        if len(targets) == 1:
            msg = f'Delete this file from disk?\n\n"{os.path.basename(targets[0][1])}"'
        else:
            names = "\n".join(f'  • {os.path.basename(p)}' for _, p in targets[:10])
            more = f"\n  … and {len(targets)-10} more" if len(targets) > 10 else ""
            msg = f"Delete {len(targets)} files from disk?\n\n{names}{more}"
        reply = QMessageBox.question(self, "Delete Files", msg, QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        failed = []
        deleted_items = []
        for it, path in targets:
            try:
                os.remove(path)
                deleted_items.append(it)
            except Exception as e:
                failed.append(f"{os.path.basename(path)}: {e}")
        # Remove from tree
        for it in deleted_items:
            parent = it.parent()
            if parent:
                parent.removeChild(it)
            else:
                idx = self.tree_widget.indexOfTopLevelItem(it)
                if idx >= 0:
                    self.tree_widget.takeTopLevelItem(idx)
        if failed:
            QMessageBox.warning(self, "Error", "Could not delete:\n" + "\n".join(failed))
        self.statusBar().showMessage(f'Deleted {len(deleted_items)} file(s)')

    def _add_selected_to_notebooklm(self):
        from ui.notebooklm_window import is_nlm_logged_in, NLMNotebookPickerDialog, AddSourceWorker, ListSourcesWorker
        if not is_nlm_logged_in():
            QMessageBox.warning(self, "Not Logged In",
                "Please log in to NotebookLM first.\n\nGo to the 📓 NotebookLM tab and click 🔑 Switch Account.")
            return
        selected = self.tree_widget.selectedItems()
        if not selected:
            return
        nb_id = NLMNotebookPickerDialog.pick(self)
        if not nb_id:
            return
        NLM_SUPPORTED = {".pdf", ".txt", ".doc", ".docx", ".pptx", ".md"}
        all_paths = [it.text(4) for it in selected if os.path.isfile(it.text(4))]
        paths_to_add = [p for p in all_paths if os.path.splitext(p)[1].lower() in NLM_SUPPORTED]
        unsupported = [os.path.basename(p) for p in all_paths if p not in paths_to_add]
        if unsupported:
            QMessageBox.warning(self, "Unsupported Format",
                "NotebookLM only accepts: .pdf, .txt, .doc, .docx, .pptx, .md\n\n"
                "Skipping the following files:\n" + "\n".join(f"  • {n}" for n in unsupported))
        if not paths_to_add:
            return

        # Fetch existing sources trước để kiểm tra trùng
        lw = ListSourcesWorker(nb_id)
        lw.done.connect(lambda sources, nb=nb_id, paths=paths_to_add:
            self._do_add_after_check(nb, paths, sources))
        lw.error.connect(lambda e, nb=nb_id, paths=paths_to_add:
            self._do_add_after_check(nb, paths, []))  # nếu lấy list lỗi thì add luôn
        self._nlm_list_worker = lw
        lw.start()

    def _do_add_after_check(self, nb_id: str, paths_to_add: list, existing_sources: list):
        from ui.notebooklm_window import AddSourceWorker
        existing_titles = set()
        for s in existing_sources:
            t = getattr(s, "title", None) or getattr(s, "name", None) or ""
            if t:
                existing_titles.add(t.strip().lower())

        skipped, to_upload = [], []
        for p in paths_to_add:
            fname = os.path.basename(p)
            if fname.strip().lower() in existing_titles:
                skipped.append(fname)
            else:
                to_upload.append(p)

        if skipped:
            QMessageBox.warning(self, "Duplicate Files",
                "The following files already exist in the notebook and will be skipped:\n" +
                "\n".join(f"  • {n}" for n in skipped))
        if not to_upload:
            return

        # Extract configurations from NotebookLM widget if instantiated
        use_vision_val = False
        main_win = self.window()
        if hasattr(main_win, "notebooklm_widget") and main_win.notebooklm_widget:
            try:
                use_vision_val = main_win.notebooklm_widget.chk_vision.isChecked()
            except AttributeError:
                pass # Fallback in case checkbox is removed

        self._nlm_add_workers = []
        for file_path in to_upload:
            w = AddSourceWorker(nb_id, file_path, use_vision=use_vision_val)
            w.error.connect(lambda e, p=file_path: QMessageBox.warning(
                self, "NotebookLM Error", f"{os.path.basename(p)}:\n{e}"
            ))
            self._nlm_add_workers.append(w)
            w.finished.connect(lambda _w=w: self._nlm_add_workers.remove(_w) if _w in self._nlm_add_workers else None)
            w.finished.connect(w.deleteLater)
            w.start()
        
        msg = f"Adding {len(to_upload)} file(s) to NotebookLM in the background…"
        if use_vision_val:
            msg += "\n\nApplying: [Vision AI]"
            
        QMessageBox.information(self, "NotebookLM", msg)

    def _open_preview_from_nlm(self, file_path: str, page_num):
        if not self.pdf_preview.isVisible():
            self.pdf_preview.show()
            self._splitter.setSizes([6000, 4000])
        self.pdf_preview.load(file_path)
        if page_num is not None and page_num > 0:
            self.pdf_preview.goto_page(page_num)

    def _mindmap_from_nlm_source(self, file_path: str):
        """Mở PDF preview và tạo mind map từ source được chọn trong NbLM."""
        if not self.pdf_preview.isVisible():
            self.pdf_preview.show()
            self._splitter.setSizes([6000, 4000])
        self.pdf_preview.load(file_path)
        self.pdf_preview._nlm_mind_map()

    def _mindmap_online_in_preview(self, notebook_id: str, source_id: str, title: str):
        """Tạo mind map online, hiển thị trong panel Notes của pdf_preview."""
        if not self.pdf_preview.isVisible():
            self.pdf_preview.show()
            self._splitter.setSizes([6000, 4000])
        self.pdf_preview.show_mindmap_online(notebook_id, source_id, title)

    def _open_folder_path(self, folder: str):
        if os.path.exists(folder):
            webbrowser.open(f"file:///{folder}")
        else:
            QMessageBox.warning(self, "Error", "Folder not found.")

    def _on_tree_item_clicked(self, item):
        if not self.pdf_preview.isVisible():
            return
        path = item.text(4)
        if path.lower().endswith(".pdf"):
            self.pdf_preview.load(path)
        else:
            self.pdf_preview.clear()

    def open_file(self, item):
        path = item.text(4)
        if os.path.exists(path):
            record_open(path, paths.STATS_FILE)
            webbrowser.open(path)
        else:
            QMessageBox.warning(self, "File Not Found", "The selected file does not exist.")

    # ══════════════════════════════════════════════════════════════
    #  CONTAINER MANAGEMENT
    # ══════════════════════════════════════════════════════════════

    def create_container(self):
        name = self.container_entry.text().strip()
        if not name:
            QMessageBox.warning(self, "Empty", "Please enter container name.")
            return
        if name in self.containers:
            QMessageBox.warning(self, "Exists", "Container already exists.")
            return
        self.containers[name] = []
        self.save_data_to_file()
        self.container_search_bar.blockSignals(True)
        self.container_search_bar.setText("")
        self.container_search_bar.blockSignals(False)
        self.filter_containers("")
        for i in range(self.containers_list.count()):
            if self.containers_list.item(i).text() == name:
                self.containers_list.setCurrentRow(i)
                self.display_container_files(self.containers_list.item(i))
                break
        self.container_entry.clear()
        QMessageBox.information(self, "Created", f"Created container: {name}")

    def delete_container(self):
        item = self.containers_list.currentItem()
        if item:
            del self.containers[item.text()]
            self.containers_list.takeItem(self.containers_list.row(item))
            self.container_files_list.clear()
            self.save_data_to_file()

    def add_to_container(self):
        selected = self.tree_widget.currentItem()
        if not selected:
            QMessageBox.warning(self, "Select Error", "Please select a file to add.")
            return
        c_item = self.containers_list.currentItem()
        if not c_item:
            QMessageBox.warning(self, "Select Error", "Please select a container.")
            return
        path = selected.text(4)
        name = c_item.text()
        if path not in [f[0] for f in self.containers[name]]:
            self.containers[name].append((path, {"text": ""}))
            self.save_data_to_file()
            self.display_container_files(c_item)
        else:
            QMessageBox.warning(self, "File Exists", "This file already exists in the selected container.")

    def delete_file_from_container(self):
        f_item = self.container_files_list.currentItem()
        c_item = self.containers_list.currentItem()
        if not f_item or not c_item:
            QMessageBox.warning(self, "Selection Error", "Please select a file and a container.")
            return
        file_name      = f_item.text()
        container_name = c_item.text()
        for i, (fp, _) in enumerate(self.containers[container_name]):
            if os.path.basename(fp) == file_name:
                del self.containers[container_name][i]
                self.save_data_to_file()
                self.display_container_files(c_item)
                QMessageBox.information(self, "Success", f"'{file_name}' removed from container.")
                break
        else:
            QMessageBox.warning(self, "Not Found", "File not found in container.")

    def display_container_files(self, item):
        self.container_files_list.clear()
        name = item.text()
        if name in self.containers:
            for fp, _ in self.containers[name]:
                list_item = QListWidgetItem(os.path.basename(fp))
                if not os.path.exists(fp):
                    list_item.setForeground(QBrush(QColor("#f85149")))
                    list_item.setToolTip(f"File no longer exists:\n{fp}")
                else:
                    list_item.setToolTip(fp)
                self.container_files_list.addItem(list_item)

    def open_file_from_container(self, item):
        c_item = self.containers_list.currentItem()
        if not c_item:
            return
        for fp, _ in self.containers[c_item.text()]:
            if os.path.basename(fp) == item.text():
                if os.path.exists(fp):
                    record_open(fp, paths.STATS_FILE)
                    webbrowser.open(fp)
                else:
                    QMessageBox.warning(self, "Not Found", "The file does not exist.")
                break

    def show_note_frame(self, item):
        c_item = self.containers_list.currentItem()
        if not c_item:
            QMessageBox.warning(self, "No Container", "Please select a container first.")
            return
        for fp, _ in self.containers.get(c_item.text(), []):
            if os.path.basename(fp) == item.text():
                # Trigger PDF preview nếu đang bật
                if self.pdf_preview.isVisible():
                    if fp.lower().endswith(".pdf"):
                        self.pdf_preview.load(fp)
                    else:
                        self.pdf_preview.clear()
                return

    def show_context_menu_for_container(self, pos):
        item = self.container_files_list.itemAt(
            self.container_files_list.viewport().mapFromGlobal(QCursor.pos())
        )
        if item:
            menu = QMenu(self)
            menu.addAction("Open Folder").triggered.connect(
                lambda: self._open_folder_for_container_item(item)
            )
            menu.addSeparator()
            menu.addAction("📓 Add this file to NotebookLM").triggered.connect(
                lambda: self._add_container_file_to_nlm(item, all_files=False)
            )
            menu.addAction("📓 Add all files in container to NotebookLM").triggered.connect(
                lambda: self._add_container_file_to_nlm(item, all_files=True)
            )
            menu.exec(QCursor.pos())

    def _add_container_file_to_nlm(self, item, all_files: bool):
        from ui.notebooklm_window import is_nlm_logged_in, NLMNotebookPickerDialog, ListSourcesWorker
        if not is_nlm_logged_in():
            QMessageBox.warning(self, "Not Logged In",
                "Please log in to NotebookLM first.\n\nGo to the 📓 NotebookLM tab and click 🔑 Switch Account.")
            return
        c_item = self.containers_list.currentItem()
        if not c_item:
            return
        NLM_SUPPORTED = {".pdf", ".txt", ".doc", ".docx", ".pptx", ".md"}
        if all_files:
            all_paths = [fp for fp, _ in self.containers[c_item.text()]
                         if os.path.isfile(fp) and os.path.splitext(fp)[1].lower() in NLM_SUPPORTED]
        else:
            # find path for clicked item
            all_paths = []
            for fp, _ in self.containers[c_item.text()]:
                if os.path.basename(fp) == item.text() and os.path.isfile(fp):
                    if os.path.splitext(fp)[1].lower() in NLM_SUPPORTED:
                        all_paths = [fp]
                    else:
                        QMessageBox.warning(self, "Unsupported Format",
                            f"NotebookLM only accepts: .pdf .txt .doc .docx .pptx .md")
                    break
        if not all_paths:
            return
        nb_id = NLMNotebookPickerDialog.pick(self)
        if not nb_id:
            return
        lw = ListSourcesWorker(nb_id)
        lw.done.connect(lambda sources, nb=nb_id, paths=all_paths:
            self._do_add_after_check(nb, paths, sources))
        lw.error.connect(lambda _, nb=nb_id, paths=all_paths:
            self._do_add_after_check(nb, paths, []))
        self._nlm_list_worker = lw
        lw.start()

    def _open_folder_for_container_item(self, item):
        c_item = self.containers_list.currentItem()
        if not c_item:
            return
        for fp, _ in self.containers[c_item.text()]:
            if os.path.basename(fp) == item.text():
                self._open_folder_path(os.path.dirname(fp))
                break

    def filter_containers(self, text: str):
        self.containers_list.clear()
        for name in self.containers:
            if text.lower() in name.lower():
                self.containers_list.addItem(name)

    # ══════════════════════════════════════════════════════════════
    #  DATA PERSISTENCE
    # ══════════════════════════════════════════════════════════════

    def save_data_to_file(self):
        container_manager.save_containers(self.containers, paths.DATA_FILE)

    def load_data_from_file(self):
        self.containers = container_manager.load_containers(paths.DATA_FILE)
        self.filter_containers("")
        if self.containers_list.count() > 0 and self.containers_list.currentItem() is None:
            self.containers_list.setCurrentRow(0)
            self.display_container_files(self.containers_list.currentItem())

    # ══════════════════════════════════════════════════════════════
    #  SYNONYMS
    # ══════════════════════════════════════════════════════════════

    def edit_synonyms(self):
        syns = synonym_manager.load_synonyms(paths.SYNONYMS_FILE)
        text = "\n".join(f"{k} == {', '.join(v)}" for k, v in syns.items())
        dlg = QDialog(self)
        dlg.setWindowTitle("Edit Synonyms")
        dlg.setGeometry(500, 300, 600, 400)
        layout = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setPlainText(text)
        layout.addWidget(te)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(lambda: self._save_synonyms(dlg, te))
        layout.addWidget(save_btn)
        dlg.exec()

    def _save_synonyms(self, dialog: QDialog, te: QTextEdit):
        try:
            syns = {}
            for line in te.toPlainText().strip().splitlines():
                if "==" in line:
                    k, v = map(str.strip, line.split("==", 1))
                    syns[k] = [x.strip() for x in v.split(",")]
            synonym_manager.save_synonyms(syns, paths.SYNONYMS_FILE)
            QMessageBox.information(self, "Success", "Synonyms updated successfully!")
            dialog.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save synonyms: {e}")

    # ══════════════════════════════════════════════════════════════
    #  CLIPBOARD / TREE ACTIONS
    # ══════════════════════════════════════════════════════════════

    def get_name_from_tree_view(self):
        items = self.tree_widget.selectedItems()
        if items:
            QApplication.clipboard().setText("\n".join(i.text(0) for i in items))
            QMessageBox.information(self, "Copied", "File names copied to clipboard.")
        else:
            QMessageBox.warning(self, "No Selection", "Please select at least one file.")

    def get_link_from_tree_view(self):
        items = self.tree_widget.selectedItems()
        if items:
            QApplication.clipboard().setText("\n".join(i.text(4) for i in items))
            QMessageBox.information(self, "Copied", "File paths copied to clipboard.")
        else:
            QMessageBox.warning(self, "No Selection", "Please select at least one file.")

    # ══════════════════════════════════════════════════════════════
    #  EXCEL INTEGRATION
    # ══════════════════════════════════════════════════════════════


    def open_or_create_notes(self):
        try:
            excel_bridge.open_or_create_notes(paths.NOTES_FILE)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open Notes: {e}")

    def get_hyperlink_from_tree_view(self):
        items = self.tree_widget.selectedItems()
        if not items:
            QMessageBox.warning(self, "No Selection", "Please select at least one file.")
            return
        if not os.path.exists(paths.NOTES_FILE):
            QMessageBox.warning(self, "Not Found", "Notes.xlsm not found. Create it first.")
            return
        address = self._ask_cell_address()
        if not address:
            QMessageBox.warning(self, "No Address", "Please enter a valid cell address.")
            return
        try:
            excel_bridge.add_hyperlinks(paths.NOTES_FILE, [i.text(4) for i in items], address)
            QMessageBox.information(self, "Success", "Hyperlinks added to Notes.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add hyperlink: {e}")

    def _ask_cell_address(self) -> str:
        dlg = QDialog(self)
        dlg.setWindowTitle("Enter Cell Address")
        dlg.setGeometry(300, 300, 220, 100)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Enter the Excel cell address (e.g., A1):"))
        cell_input = QLineEdit()
        layout.addWidget(cell_input)
        ok = QPushButton("OK")
        ok.clicked.connect(dlg.accept)
        layout.addWidget(ok)
        return cell_input.text() if dlg.exec() else ""

    # ══════════════════════════════════════════════════════════════
    #  EXE ADD-ONS
    # ══════════════════════════════════════════════════════════════

    def add_exe_to_frame_2(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Executable", "", "Executable Files (*.exe)"
        )
        for path in files:
            if path not in self.exe_addons:
                self.exe_addons.append(path)
                self.save_exe_addons()
            self.create_exe_button(path)

    def create_exe_button(self, exe_path: str):
        btn = QPushButton(f"Open {os.path.basename(exe_path)}")
        btn.setContextMenuPolicy(Qt.CustomContextMenu)
        btn.customContextMenuRequested.connect(partial(self._exe_context_menu, btn, exe_path))
        btn.clicked.connect(partial(self.open_exe_file, exe_path))
        self.exe_list_layout.addWidget(btn)

    def _exe_context_menu(self, button, exe_path, _pos):
        menu = QMenu(self)
        menu.addAction("Release").triggered.connect(partial(self._release_exe, button, exe_path))
        menu.exec(QCursor.pos())

    def _release_exe(self, button, exe_path):
        button.setParent(None)
        button.deleteLater()
        if exe_path in self.exe_addons:
            self.exe_addons.remove(exe_path)
            self.save_exe_addons()

    def save_exe_addons(self):
        with open(paths.EXE_ADDON_FILE, "w", encoding="utf-8") as f:
            json.dump(self.exe_addons, f)

    def load_exe_addons(self):
        if os.path.exists(paths.EXE_ADDON_FILE):
            try:
                with open(paths.EXE_ADDON_FILE, "r", encoding="utf-8") as f:
                    self.exe_addons = json.load(f)
                for p in self.exe_addons:
                    self.create_exe_button(p)
            except Exception:
                pass

    def open_exe_file(self, path: str):
        if os.path.exists(path):
            try:
                os.startfile(path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open {path}: {e}")
        else:
            QMessageBox.warning(self, "Not Found", f"{path} does not exist.")

    # ══════════════════════════════════════════════════════════════
    #  OTHER DIALOGS
    # ══════════════════════════════════════════════════════════════

    def list_files_in_folder(self):
        show_list_files_window(self)

    def open_index_interface(self):
        IndexSearchWindow(self).exec()
