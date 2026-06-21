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
import sqlite3
import webbrowser
from datetime import datetime
from functools import partial

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QLabel, QLineEdit, QPushButton, QFileDialog, QComboBox,
    QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem, QMessageBox,
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
from ui.index_search_window import IndexSearchWindow
from ui.notebooklm_window import NotebookLMWidget
from ui.list_files_window import show_list_files_window
from ui.sync_folder_window import show_sync_folder_window
from ui.google_sheet_window import show_google_sheet_window
from ui.pdf_preview import PdfPreviewWidget
from ui.container_tree import ContainerOrgChartWidget, _fs_icon
from ui.claude_assistant import ClaudeAssistantWidget
from ui.desktop_orb import DesktopOrb
from core.ai_grouper import GroupWorker


def _load_ui_state() -> dict:
    try:
        with open(paths.UI_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_ui_state(state: dict):
    try:
        tmp = paths.UI_STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, paths.UI_STATE_FILE)
    except Exception:
        pass


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

        # Tạo các hàng từ current_folders, hoặc 3 hàng trống nếu chưa có
        init = current_folders if current_folders else ["", "", ""]
        for i, val in enumerate(init):
            self._add_row(val, i + 1)

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
        state = _load_ui_state()
        start_dir = entry.text().strip() or state.get("last_browse_dir", "")
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", start_dir)
        if folder:
            entry.setText(folder)
            state["last_browse_dir"] = folder
            _save_ui_state(state)

    def get_folders(self) -> list[str]:
        return [e.text().strip() for e in self._rows if e.text().strip()]


class FileSearchApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Search and Management")
        self.setGeometry(100, 100, 1280, 800)

        self.containers:         dict = {}
        self.container_parents:  dict = {}
        self.exe_addons:         list = []
        self._dup_worker           = None
        self._group_worker         = None
        self._last_results:   list = []
        self._sidebar_btns:   list = []
        self._right_stack          = None

        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_widget.setStyleSheet(qss_hud_metal_header_feel() + qss_white_results())

        self.root_layout = QVBoxLayout(self.main_widget)
        self.root_layout.setContentsMargins(8, 8, 8, 8)
        self.root_layout.setSpacing(6)

        self._setup_body()
        self._bind_help_f1()

        self.load_data_from_file()
        self.load_exe_addons()
        self._restore_last_folder()

        os.makedirs(paths.IMAGE_DIR, exist_ok=True)

        # Orb được tạo lazy — chỉ khởi tạo lần đầu khi minimize
        self._desktop_orb = None

    def _get_orb(self):
        if self._desktop_orb is None:
            self._desktop_orb = DesktopOrb()
            self._desktop_orb.open_main.connect(self._restore_from_orb)
        return self._desktop_orb

    def changeEvent(self, event):
        from PySide6.QtCore import QEvent as _QEvent
        if event.type() == _QEvent.Type.WindowStateChange:
            if self.isMinimized():
                from PySide6.QtCore import QTimer
                QTimer.singleShot(80, self._show_orb)
        super().changeEvent(event)

    def _show_orb(self) -> None:
        self.hide()
        orb = self._get_orb()
        orb.show()
        orb.raise_()

    def _restore_from_orb(self) -> None:
        if self._desktop_orb:
            self._desktop_orb.hide()
        self.showMaximized()
        self.raise_()
        self.activateWindow()

    def _restore_last_folder(self):
        state = _load_ui_state()
        if self._multi_folder_mode:
            folders = state.get("last_multi_folders", [])
            folders = [f for f in folders if os.path.isdir(f)]
            if folders:
                self._multi_folders = folders
                self.folder_entry.setText(" | ".join(folders))
        else:
            folder = state.get("last_single_folder", "")
            if folder and os.path.isdir(folder):
                self.folder_entry.setText(folder)

    # ══════════════════════════════════════════════════════════════
    #  SETUP HELPERS
    # ══════════════════════════════════════════════════════════════

    def _setup_toolbar(self):
        """Compact toolbar: mode selector + folder/DB controls + keyword + search."""
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

        # ── Mode selector ─────────────────────────────────────────
        self.cmb_search_mode = QComboBox()
        self.cmb_search_mode.addItems(["File local", "DB"])
        self.cmb_search_mode.setFixedHeight(40)
        self.cmb_search_mode.setMinimumWidth(100)
        self.cmb_search_mode.setToolTip("Search mode: local files or indexed database")
        h.addWidget(self.cmb_search_mode)

        sep0 = QFrame(); sep0.setFrameShape(QFrame.VLine)
        sep0.setFixedHeight(28); sep0.setStyleSheet("color: rgba(255,255,255,40);")
        h.addWidget(sep0)

        # ── Folder controls (File local mode) ─────────────────────
        self._folder_controls = QWidget()
        fc_h = QHBoxLayout(self._folder_controls)
        fc_h.setContentsMargins(0, 0, 0, 0)
        fc_h.setSpacing(8)

        self.btn_folder_toggle = QPushButton("Folder:")
        self.btn_folder_toggle.setFixedWidth(82)
        self.btn_folder_toggle.setMinimumHeight(40)
        self.btn_folder_toggle.setToolTip("Click to switch to multi-folder mode")
        self.btn_folder_toggle.clicked.connect(self._toggle_folder_mode)
        fc_h.addWidget(self.btn_folder_toggle)

        self.folder_entry = QLineEdit()
        self.folder_entry.setPlaceholderText("Select folder…")
        fc_h.addWidget(self.folder_entry, 1)

        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setMinimumWidth(90)
        self.browse_btn.setMinimumHeight(40)
        self.browse_btn.clicked.connect(self.browse_folder)
        fc_h.addWidget(self.browse_btn)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.VLine)
        sep1.setFixedHeight(28); sep1.setStyleSheet("color: rgba(255,255,255,40);")
        fc_h.addWidget(sep1)

        h.addWidget(self._folder_controls, 2)

        # ── DB controls (DB mode, hidden by default) ───────────────
        self._db_toolbar_controls = QWidget()
        self._db_toolbar_controls.setVisible(False)
        dbt_h = QHBoxLayout(self._db_toolbar_controls)
        dbt_h.setContentsMargins(0, 0, 0, 0)
        dbt_h.setSpacing(8)

        self.db_import_btn = QPushButton("📂 Import DB")
        self.db_import_btn.setFixedHeight(40)
        self.db_import_btn.setMinimumWidth(110)
        self.db_import_btn.clicked.connect(self._db_import)
        dbt_h.addWidget(self.db_import_btn)

        self.db_selector = QComboBox()
        self.db_selector.setFixedHeight(40)
        self.db_selector.setMinimumWidth(160)
        dbt_h.addWidget(self.db_selector)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.VLine)
        sep2.setFixedHeight(28); sep2.setStyleSheet("color: rgba(255,255,255,40);")
        dbt_h.addWidget(sep2)

        h.addWidget(self._db_toolbar_controls, 2)

        # ── Shared keyword + search ────────────────────────────────
        lbl_k = QLabel("Keyword:")
        lbl_k.setFixedWidth(60)
        h.addWidget(lbl_k)
        self.filename_entry = QLineEdit()
        self.filename_entry.setPlaceholderText("Search by name… ($stats, @fuzzy, A%B, A*B, folder:name)")
        self.filename_entry.returnPressed.connect(self.search_files)
        h.addWidget(self.filename_entry, 3)
        self.search_btn = QPushButton("🔍  Search")
        self.search_btn.setMinimumWidth(120)
        self.search_btn.setMinimumHeight(40)
        self.search_btn.clicked.connect(self.search_files)
        h.addWidget(self.search_btn)

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

        self.btn_group = QPushButton("🤖 Group")
        self.btn_group.setMinimumWidth(100)
        self.btn_group.setMinimumHeight(40)
        self.btn_group.setEnabled(False)
        self.btn_group.setToolTip("Nhờ AI phân nhóm kết quả tìm kiếm theo loại tài liệu")
        self.btn_group.clicked.connect(self._run_group)
        h.addWidget(self.btn_group)

        h.addStretch(1)

        self.cmb_search_mode.currentIndexChanged.connect(self._on_search_mode_changed)
        self._db_refresh_selector()

        return toolbar

    def _setup_body(self):
        """Sidebar (left) + TabWidget (center) + QStackedWidget (right)."""
        toolbar = self._setup_toolbar()

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
        self.tree_widget.installEventFilter(self)

        # ── PDF Preview ───────────────────────────────────────────
        self.pdf_preview = PdfPreviewWidget()
        self.pdf_preview.hide()

        # ── DB result table ───────────────────────────────────────
        self.db_result_table = QTreeWidget()
        self.db_result_table.setObjectName("resultsTree")
        self.db_result_table.setAlternatingRowColors(True)
        self.db_result_table.setUniformRowHeights(True)
        self.db_result_table.setRootIsDecorated(False)
        self.db_result_table.setColumnCount(2)
        self.db_result_table.setHeaderLabels(["File Name", "Path"])
        self.db_result_table.header().setSectionResizeMode(
            0, self.db_result_table.header().ResizeMode.Stretch)
        self.db_result_table.header().setSectionResizeMode(
            1, self.db_result_table.header().ResizeMode.Stretch)
        self.db_result_table.itemDoubleClicked.connect(self._db_open_file)
        self.db_lbl_count = QLabel("")
        self.db_lbl_count.setStyleSheet("color: #888; font-size: 12px; padding: 2px 4px;")

        # ── Tab: Search | NotebookLM | Claude ─────────────────────
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
        # ── Search page: toolbar + stacked results ────────────────
        file_search_page = QWidget()
        fs_lay = QVBoxLayout(file_search_page)
        fs_lay.setContentsMargins(0, 0, 0, 0)
        fs_lay.setSpacing(4)
        fs_lay.addWidget(toolbar)

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.addWidget(self.tree_widget)
        self._splitter.addWidget(self.pdf_preview)
        self._splitter.setSizes([10000, 0])
        self._splitter.setHandleWidth(4)
        self._splitter.setStyleSheet("QSplitter::handle { background: rgba(255,255,255,15); border-radius: 2px; }")

        db_results_page = QWidget()
        db_rp_lay = QVBoxLayout(db_results_page)
        db_rp_lay.setContentsMargins(0, 4, 0, 0)
        db_rp_lay.setSpacing(4)
        db_rp_lay.addWidget(self.db_lbl_count)
        db_rp_lay.addWidget(self.db_result_table, 1)

        self._results_stack = QStackedWidget()
        self._results_stack.addWidget(self._splitter)     # page 0: file
        self._results_stack.addWidget(db_results_page)    # page 1: DB

        fs_lay.addWidget(self._results_stack, 1)

        self._search_tabs.addTab(file_search_page, "🔍 Search")
        self.notebooklm_widget = NotebookLMWidget()
        self._search_tabs.addTab(self.notebooklm_widget, "📓 NotebookLM")
        self.claude_assistant_widget = ClaudeAssistantWidget()
        self._search_tabs.addTab(self.claude_assistant_widget, "🤖 Claude")
        self.notebooklm_widget.open_preview.connect(self._open_preview_from_nlm)
        self.notebooklm_widget.goto_page_signal.connect(self.pdf_preview.goto_page)
        self.notebooklm_widget.request_mindmap.connect(self._mindmap_from_nlm_source)
        self.notebooklm_widget.request_mindmap_online.connect(self._mindmap_online_in_preview)

        # ── Right stack ──────────────────────────────────────────
        self._right_stack = QStackedWidget()
        self._right_stack.setVisible(False)
        self._right_stack.setMinimumWidth(300)
        self._right_stack.addWidget(self._build_containers_page())  # 0
        self._right_stack.addWidget(self._build_tools_page())       # 1
        self._right_stack.addWidget(self._build_exe_page())         # 2

        # Outer splitter: tabs (center) | right stack
        self._outer_splitter = QSplitter(Qt.Horizontal)
        self._outer_splitter.addWidget(self._search_tabs)
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
        lay.setSpacing(4)

        self.org_chart = ContainerOrgChartWidget(page)
        self.org_chart.btn_add_file.clicked.connect(self.add_to_container)
        self.org_chart.containers_changed.connect(self._on_containers_changed)
        self.org_chart.file_open_requested.connect(
            lambda fp: (record_open(fp, paths.STATS_FILE), webbrowser.open(fp))
        )
        self.org_chart.file_clicked.connect(self._on_container_file_clicked)
        self.org_chart.file_context_menu_requested.connect(self._on_container_file_nlm)
        self.org_chart.fullscreen_requested.connect(self._toggle_container_fullscreen)
        lay.addWidget(self.org_chart)
        return page

    def _build_tools_page(self) -> QFrame:
        page = QFrame()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignTop)

        dup_btn = QPushButton("🔍\nDuplicates")
        dup_btn.clicked.connect(self.search_duplicates)
        self.search_duplicates_button = dup_btn

        tools = [
            (QPushButton("📋\nList Files"),         self.list_files_in_folder),
            (QPushButton("🔄\nSync Folders"),        self.sync_folders),
            (dup_btn,                                None),
            (QPushButton("📝\nOpen Notes"),          self.open_or_create_notes),
            (QPushButton("🔗\nHyperlink Notes"),     self.get_hyperlink_from_tree_view),
            (QPushButton("📊\nGoogle Sheet"),        self.check_google_sheet),
        ]

        grid = QGridLayout()
        grid.setSpacing(6)
        for i, (btn, fn) in enumerate(tools):
            if fn:
                btn.clicked.connect(fn)
            btn.setMinimumHeight(68)
            grid.addWidget(btn, i // 2, i % 2)

        lay.addLayout(grid)
        lay.addStretch()
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
                    state = _load_ui_state()
                    state["last_browse_dir"] = self._multi_folders[-1]
                    state["last_multi_folders"] = self._multi_folders
                    _save_ui_state(state)
                else:
                    self.folder_entry.clear()
        else:
            state = _load_ui_state()
            start_dir = self.folder_entry.text().strip() or state.get("last_browse_dir", "")
            folder = QFileDialog.getExistingDirectory(self, "Select Folder", start_dir)
            if folder:
                self.folder_entry.setText(folder)
                state["last_browse_dir"] = folder
                state["last_single_folder"] = folder
                _save_ui_state(state)


    def _get_search_folders(self) -> list[str]:
        """Trả về danh sách folder cần search (1 hoặc nhiều)."""
        if self._multi_folder_mode:
            return [f for f in self._multi_folders if f]
        folder = self.folder_entry.text().strip()
        return [folder] if folder else []

    # ══════════════════════════════════════════════════════════════
    #  SEARCH MODE SWITCH + DB SEARCH
    # ══════════════════════════════════════════════════════════════

    def _on_search_mode_changed(self, idx: int):
        is_db = idx == 1
        self._folder_controls.setVisible(not is_db)
        self._db_toolbar_controls.setVisible(is_db)
        self._results_stack.setCurrentIndex(idx)
        self.lcd_number.setVisible(not is_db)
        self.btn_group.setVisible(not is_db)
        if is_db:
            self.filename_entry.setPlaceholderText("Keyword to search in indexed DB…")
            self.db_lbl_count.setText("")
        else:
            self.filename_entry.setPlaceholderText(
                "Search by name… ($stats, @fuzzy, A%B, A*B, folder:name)")

    def _db_refresh_selector(self):
        from ui.index_search_window import _load_db_list
        db_paths = _load_db_list()
        self.db_selector.clear()
        self.db_selector.addItem("All DBs")
        for p in db_paths:
            self.db_selector.addItem(os.path.basename(p), p)

    def _db_import(self):
        from ui.index_search_window import _load_db_list, _save_db_list
        db_paths = _load_db_list()
        selected, _ = QFileDialog.getOpenFileNames(
            self, "Select SQLite Databases", "", "SQLite Files (*.db *.sqlite)"
        )
        if selected:
            added = [p for p in selected if p not in db_paths]
            db_paths.extend(added)
            _save_db_list(db_paths)
            self._db_refresh_selector()
            self.db_lbl_count.setText(
                f"Imported {len(added)} database(s). Total: {len(db_paths)}")

    def _db_search(self):
        from ui.index_search_window import _load_db_list
        db_paths = _load_db_list()
        if not db_paths:
            QMessageBox.warning(self, "No Database",
                                "Please import a SQLite database first.")
            return
        keyword = self.filename_entry.text().strip()
        if not keyword:
            return

        self.search_btn.setText("⏳  Searching…")
        self.search_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            selected_data = self.db_selector.currentData()
            rows = []
            if selected_data is None:
                for db in db_paths:
                    for row in self._db_search_single(db, keyword):
                        rows.append((*row, db))
            else:
                for row in self._db_search_single(selected_data, keyword):
                    rows.append((*row, selected_data))

            self.db_result_table.clear()
            if rows:
                for name, path, _content, db_path in rows:
                    item = QTreeWidgetItem([name, path])
                    item.setData(0, Qt.UserRole, db_path)
                    self.db_result_table.addTopLevelItem(item)
                self.db_lbl_count.setText(
                    f'Found {len(rows)} result(s) for "{keyword}"')
            else:
                self.db_lbl_count.setText(f'No results for "{keyword}"')
        finally:
            QApplication.restoreOverrideCursor()
            self.search_btn.setEnabled(True)
            self.search_btn.setText("🔍  Search")

    def _db_search_single(self, db_path: str, keyword: str) -> list:
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT name, path, content FROM files "
                "WHERE name LIKE ? OR content LIKE ?",
                (f"%{keyword}%", f"%{keyword}%"),
            )
            rows = cur.fetchall()
            conn.close()
            return rows
        except Exception as e:
            QMessageBox.warning(self, "DB Error", f"Failed to search {db_path}: {e}")
            return []

    def _db_open_file(self, item: QTreeWidgetItem, _column: int):
        try:
            relative_path = item.text(1)
            db_path = item.data(0, Qt.UserRole)
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT path FROM files WHERE name = 'BASE_PATH'")
            row = cur.fetchone()
            conn.close()
            if row:
                abs_path = os.path.join(row[0], relative_path)
                if os.path.exists(abs_path):
                    os.startfile(abs_path)
                else:
                    QMessageBox.warning(self, "Not Found", f"File not found:\n{abs_path}")
            else:
                QMessageBox.warning(self, "Error", "BASE_PATH not found in database.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open file: {e}")

    def search_files(self):
        if self.cmb_search_mode.currentIndex() == 1:
            self._db_search()
            return

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

        self.search_btn.setText("⏳  Searching…")
        self.search_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            if keyword.lower().startswith("folder:"):
                q = keyword[7:].strip()
                if not q:
                    return
                results = []
                for folder in folders:
                    results += search_engine.search_folders_by_name(folder, q)
                self.display_folder_results(results)
            else:
                results = []
                for folder in folders:
                    if keyword.startswith("@"):
                        synonyms = synonym_manager.load_synonyms(paths.SYNONYMS_FILE)
                        results += search_engine.fuzzy_search(folder, keyword[1:], synonyms)
                    else:
                        results += search_engine.search_files_by_name(folder, keyword)
                self.display_results(results)
        finally:
            QApplication.restoreOverrideCursor()
            self.search_btn.setEnabled(True)
            self.search_btn.setText("🔍  Search")

    def display_results(self, results: list):
        self.tree_widget.clear()
        seen: set = set()
        unique = [(n, p) for n, p in results
                  if os.path.normpath(p) not in seen and not seen.add(os.path.normpath(p))]
        self._last_results = unique
        if unique:
            for name, path in unique:
                self.tree_widget.addTopLevelItem(self._make_tree_item(name, path))
            self._mark_saved_items()
            self.lcd_number.display(len(unique))
            self.statusBar().showMessage(f"Found {len(unique)} file(s).")
            self.btn_group.setEnabled(True)
        else:
            self.lcd_number.display(0)
            self.statusBar().showMessage("No files found.")
            self.btn_group.setEnabled(False)
            self.tree_widget.addTopLevelItem(
                self.sort_helper.make_item("No matches found", "", "", "", "",
                                           mtime_ts=None, size_bytes=None)
            )

    # ══════════════════════════════════════════════════════════════
    #  AI GROUP
    # ══════════════════════════════════════════════════════════════

    def _run_group(self):
        if not self._last_results:
            return
        from core.llm_config import load_llm_config
        provider = load_llm_config().get("translate_provider", "gemini")
        self.btn_group.setEnabled(False)
        self.btn_group.setText("⏳ Grouping…")
        self._group_worker = GroupWorker(self._last_results, provider)
        self._group_worker.done.connect(self._on_group_done)
        self._group_worker.error.connect(self._on_group_error)
        self._group_worker.start()

    def _on_group_done(self, result: dict):
        self.btn_group.setText("🤖 Group")
        self.btn_group.setEnabled(True)
        self._display_grouped(result)

    def _on_group_error(self, msg: str):
        self.btn_group.setText("🤖 Group")
        self.btn_group.setEnabled(True)
        QMessageBox.warning(self, "AI Group Error", msg)

    def _display_grouped(self, result: dict):
        pairs  = result.get("pairs", self._last_results)
        groups = result.get("groups", [])
        dupes  = result.get("dupes", [])

        self.tree_widget.clear()
        total = 0

        for grp in groups:
            label = grp["label"]
            files = grp["files"]  # [(filename, original_index), ...]
            header = self.sort_helper.make_item(
                name      = f"📂 {label}  ({len(files)} files)",
                date_text = "", type_text = "GROUP",
                size_text = "", path      = "",
                mtime_ts=None, size_bytes=None,
            )
            header.setExpanded(True)
            for fname, orig_idx in files:
                _, fpath = pairs[orig_idx]
                header.addChild(self._make_tree_item(fname, fpath))
                total += 1
            self.tree_widget.addTopLevelItem(header)

        if dupes:
            dup_header = self.sort_helper.make_item(
                name      = f"⚠️ Multiple Revisions  ({len(dupes)} document(s))",
                date_text = "", type_text = "DUPE",
                size_text = "", path      = "",
                mtime_ts=None, size_bytes=None,
            )
            dup_header.setExpanded(True)
            for dup in dupes:
                sub = self.sort_helper.make_item(
                    name      = f"  📄 {dup['base']}",
                    date_text = "", type_text = "DUPE",
                    size_text = "", path      = "",
                    mtime_ts=None, size_bytes=None,
                )
                sub.setExpanded(True)
                for fname, orig_idx in dup["files"]:
                    _, fpath = pairs[orig_idx]
                    sub.addChild(self._make_tree_item(fname, fpath))
                dup_header.addChild(sub)
            self.tree_widget.addTopLevelItem(dup_header)

        self._mark_saved_items()
        self.lcd_number.display(total)
        self.statusBar().showMessage(
            f"Grouped into {len(groups)} categories. "
            + (f"{len(dupes)} duplicate document(s) detected." if dupes else "")
        )

    def display_folder_results(self, results: list):
        self.tree_widget.clear()
        seen: set = set()
        unique = [(n, p) for n, p in results
                  if os.path.normpath(p) not in seen and not seen.add(os.path.normpath(p))]
        if unique:
            for name, path in unique:
                try:    mtime_ts = os.path.getmtime(path)
                except OSError: mtime_ts = None
                item = self.sort_helper.make_item(
                    name       = f"📁 {name}",
                    date_text  = self.format_mtime(path),
                    type_text  = "DIR",
                    size_text  = "",
                    path       = path,
                    mtime_ts   = mtime_ts,
                    size_bytes = None,
                )
                self.tree_widget.addTopLevelItem(item)
            self.lcd_number.display(len(unique))
            self.statusBar().showMessage(f"Found {len(unique)} folder(s).")
        else:
            self.lcd_number.display(0)
            self.statusBar().showMessage("No folders found.")
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

    def _checked_or_selected_items(self):
        """Trả về items được check (nếu có), ngược lại trả về items được select."""
        checked = []
        root = self.tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            if parent.checkState(0) == Qt.Checked:
                checked.append(parent)
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.checkState(0) == Qt.Checked:
                    checked.append(child)
        return checked if checked else self.tree_widget.selectedItems()

    def show_treeview_context_menu(self, position):
        item = self.tree_widget.itemAt(position)
        if not item:
            return
        file_path = item.text(4)
        is_dir = item.text(2) == "DIR"
        menu = QMenu(self)
        menu.addAction("Open Folder").triggered.connect(
            lambda: self._open_folder_path(file_path if is_dir else os.path.dirname(file_path))
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
        menu.addAction("📋 Copy to folder").triggered.connect(
            lambda: self._copy_files_from_tree(item)
        )
        menu.addAction("📁 Move to folder").triggered.connect(
            lambda: self._move_files_from_tree(item)
        )
        menu.addAction("🗑 Delete file").triggered.connect(
            lambda: self._delete_file_from_tree(item, file_path)
        )

        # ── Folder search actions (chỉ hiện khi kết quả là folder) ──
        if is_dir:
            # Chỉ lấy folder được CHECK bằng checkbox — không dùng selection
            root = self.tree_widget.invisibleRootItem()
            checked_dirs = [
                root.child(i).text(4)
                for i in range(root.childCount())
                if root.child(i).checkState(0) == Qt.Checked
                and root.child(i).text(2) == "DIR"
                and root.child(i).text(4)
            ]
            targets = checked_dirs or [file_path]
            menu.addSeparator()
            menu.addAction("➕ Add to search folders").triggered.connect(
                lambda: self._add_to_search_folders(targets)
            )

        menu.exec(QCursor.pos())

    # ══════════════════════════════════════════════════════════════
    #  FOLDER SEARCH NAVIGATION  (tính năng mới — dùng kết quả folder:
    #  để tiếp tục tìm kiếm bên trong)
    # ══════════════════════════════════════════════════════════════

    def _add_to_search_folders(self, folder_paths: list[str]):
        """Đặt folder(s) được chọn làm danh sách search (thay thế hoàn toàn)."""
        seen: set = set()
        valid = [os.path.normpath(p) for p in folder_paths
                 if p and os.path.isdir(p)
                 and os.path.normpath(p) not in seen and not seen.add(os.path.normpath(p))]
        if not valid:
            self.statusBar().showMessage("No valid folders selected.")
            return
        if not self._multi_folder_mode:
            self._toggle_folder_mode()
        self._multi_folders = valid
        # Tắt ReadOnly tạm để clear + setText luôn áp dụng lên widget
        self.folder_entry.setReadOnly(False)
        self.folder_entry.clear()
        self.folder_entry.setText(" | ".join(valid))
        self.folder_entry.setReadOnly(True)
        state = _load_ui_state()
        state["last_multi_folders"] = valid
        state["last_browse_dir"]    = valid[-1]
        _save_ui_state(state)
        self.statusBar().showMessage(f"Search folders set: {len(valid)} folder(s).")

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
        from PySide6.QtGui import QMouseEvent, QKeyEvent
        if obj is self.tree_widget and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_A and event.modifiers() == Qt.ControlModifier:
                self._check_all_items()
                return True
            if event.key() == Qt.Key_A and event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier):
                self._uncheck_all_items()
                return True
        if obj is self.tree_widget.viewport() and event.type() == QEvent.MouseButtonPress:
            item = self.tree_widget.itemAt(event.pos())
            if item is None:
                self.tree_widget.clearSelection()
        return super().eventFilter(obj, event)

    def _check_all_items(self):
        """Check tất cả items trong tree (Ctrl+A)."""
        root = self.tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            parent.setCheckState(0, Qt.Checked)
            for j in range(parent.childCount()):
                parent.child(j).setCheckState(0, Qt.Checked)

    def _uncheck_all_items(self):
        """Uncheck tất cả items trong tree (Ctrl+Shift+A)."""
        root = self.tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            parent.setCheckState(0, Qt.Unchecked)
            for j in range(parent.childCount()):
                parent.child(j).setCheckState(0, Qt.Unchecked)

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

    def _copy_files_from_tree(self, item):
        """Copy file(s) đã chọn sang thư mục khác."""
        import shutil
        selected = self._checked_or_selected_items()
        targets  = [(i, i.text(4)) for i in (selected if selected else [item])]
        targets  = [(i, p) for i, p in targets if p and os.path.isfile(p)]
        if not targets:
            QMessageBox.warning(self, "File Not Found", "No valid files selected.")
            return
        dest_dir = QFileDialog.getExistingDirectory(self, "Select Destination Folder", "")
        if not dest_dir:
            return
        failed = []
        count  = 0
        for _, path in targets:
            dest = os.path.join(dest_dir, os.path.basename(path))
            if os.path.abspath(path) == os.path.abspath(dest):
                continue
            try:
                shutil.copy2(path, dest)
                count += 1
            except Exception as e:
                failed.append(f"{os.path.basename(path)}: {e}")
        if failed:
            QMessageBox.warning(self, "Error", "Could not copy:\n" + "\n".join(failed))
        if count:
            self.statusBar().showMessage(f"Copied {count} file(s) to {dest_dir}")

    def _move_files_from_tree(self, item):
        """Di chuyển file(s) đã chọn sang thư mục khác."""
        import shutil
        selected = self._checked_or_selected_items()
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
        selected = self._checked_or_selected_items()
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
        selected = self._checked_or_selected_items()
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

    def add_to_container(self):
        selected = self.tree_widget.currentItem()
        if not selected:
            QMessageBox.warning(self, "Select Error", "Please select a file to add.")
            return
        if not self.org_chart.selected_container:
            QMessageBox.warning(self, "Select Error", "Please select a container on the org chart.")
            return
        path = selected.text(4)
        if not self.org_chart.add_file_to_selected(path):
            QMessageBox.warning(self, "File Exists", "This file already exists in the selected container.")

    def _on_containers_changed(self, containers: dict, parents: dict):
        self.containers        = containers
        self.container_parents = parents
        self.save_data_to_file()
        self._mark_saved_items()

    def _toggle_container_fullscreen(self):
        sizes = self._outer_splitter.sizes()
        if sizes[0] > 10:
            self._saved_center_width = sizes[0]
            self._outer_splitter.setSizes([0, sizes[0] + sizes[1]])
            self.org_chart._fs_btn.setIcon(_fs_icon(False))
        else:
            saved = getattr(self, "_saved_center_width", 600)
            total = sum(sizes)
            self._outer_splitter.setSizes([saved, total - saved])
            self.org_chart._fs_btn.setIcon(_fs_icon(True))

    def _on_container_file_clicked(self, fp: str):
        if self.pdf_preview.isVisible():
            if fp.lower().endswith(".pdf"):
                self.pdf_preview.load(fp)
            else:
                self.pdf_preview.clear()

    def _on_container_file_nlm(self, container_name: str, file_path: str, all_files: bool):
        from ui.notebooklm_window import is_nlm_logged_in, NLMNotebookPickerDialog, ListSourcesWorker
        if not is_nlm_logged_in():
            QMessageBox.warning(self, "Not Logged In",
                "Please log in to NotebookLM first.\n\nGo to the 📓 NotebookLM tab and click 🔑 Switch Account.")
            return
        NLM_SUPPORTED = {".pdf", ".txt", ".doc", ".docx", ".pptx", ".md"}
        if all_files:
            all_paths = [fp for fp, _ in self.containers.get(container_name, [])
                         if os.path.isfile(fp) and os.path.splitext(fp)[1].lower() in NLM_SUPPORTED]
        else:
            ext = os.path.splitext(file_path)[1].lower()
            if ext not in NLM_SUPPORTED:
                QMessageBox.warning(self, "Unsupported Format",
                    "NotebookLM only accepts: .pdf .txt .doc .docx .pptx .md")
                return
            all_paths = [file_path] if os.path.isfile(file_path) else []
        if not all_paths:
            return
        nb_id = NLMNotebookPickerDialog.pick(self)
        if not nb_id:
            return
        lw = ListSourcesWorker(nb_id)
        lw.done.connect(lambda sources, nb=nb_id, p=all_paths:
            self._do_add_after_check(nb, p, sources))
        lw.error.connect(lambda _, nb=nb_id, p=all_paths:
            self._do_add_after_check(nb, p, []))
        self._nlm_list_worker = lw
        lw.start()

    # ══════════════════════════════════════════════════════════════
    #  DATA PERSISTENCE
    # ══════════════════════════════════════════════════════════════

    def save_data_to_file(self):
        container_manager.save_containers(self.containers, paths.DATA_FILE)
        container_manager.save_parents(self.container_parents, paths.PARENTS_FILE)

    def load_data_from_file(self):
        self.containers        = container_manager.load_containers(paths.DATA_FILE)
        self.container_parents = container_manager.load_parents(paths.PARENTS_FILE)
        self.org_chart.refresh(self.containers, self.container_parents)

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
        items = self._checked_or_selected_items()
        if items:
            QApplication.clipboard().setText("\n".join(i.text(0) for i in items))
            QMessageBox.information(self, "Copied", "File names copied to clipboard.")
        else:
            QMessageBox.warning(self, "No Selection", "Please select at least one file.")

    def get_link_from_tree_view(self):
        items = self._checked_or_selected_items()
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
        items = self._checked_or_selected_items()
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

    def sync_folders(self):
        show_sync_folder_window(self)

    def check_google_sheet(self):
        show_google_sheet_window(self)

    def open_index_interface(self):
        IndexSearchWindow(self).exec()
