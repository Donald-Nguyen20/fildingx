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
    QTreeWidget, QListWidget, QMessageBox,
    QTextEdit, QDialog, QMenu, QComboBox, QLCDNumber, QApplication,
    QStackedWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QPalette, QColor, QAction, QKeySequence, QBrush

import paths
import core.search_engine    as search_engine
import core.container_manager as container_manager
from core.container_manager import get_file_containers
from core.file_stats import record_open
import core.synonym_manager   as synonym_manager
import core.excel_bridge      as excel_bridge
from core.workers import DuplicateSearchWorker

from ui.hud_widgets import qss_hud_metal_header_feel, qss_white_results, HudPanel
from ui.tree_sorter import TreeSortHelper
from ui.help_dialog import HelpDialog
from ui.learning_vector_store import VectorStoreDialog

from ui.notes_window import NotesWindow
from ui.index_search_window import IndexSearchWindow
from ui.list_files_window import show_list_files_window


class FileSearchApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Search and Management")
        self.setGeometry(100, 100, 1280, 800)

        self.containers:      dict = {}
        self.exe_addons:      list = []
        self._ai_popup             = None
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

        self.notes_window = NotesWindow(parent=self)
        self.notes_window.main_app = self
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

        lbl_f = QLabel("Folder:")
        lbl_f.setFixedWidth(46)
        h.addWidget(lbl_f)
        self.folder_entry = QLineEdit()
        self.folder_entry.setPlaceholderText("Select folder…")
        h.addWidget(self.folder_entry, 2)
        browse_btn = QPushButton("Browse")
        browse_btn.setMinimumWidth(90)
        browse_btn.setMinimumHeight(40)
        browse_btn.clicked.connect(self.browse_folder)
        h.addWidget(browse_btn)

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

        self.btn_ai = QPushButton("🤖")
        self.btn_ai.setToolTip("Open AI Chat")
        self.btn_ai.setFixedSize(62, 52)
        self.btn_ai.setStyleSheet("""
            QPushButton {
                background: rgba(0,220,255,18);
                border: 1px solid rgba(0,220,255,150);
                border-radius: 8px;
                font-family: "Segoe UI Emoji";
                font-size: 36px;
            }
            QPushButton:hover  { background: rgba(0,220,255,30); }
            QPushButton:pressed{ background: rgba(0,220,255,42); }
        """)
        self.btn_ai.clicked.connect(self.toggle_ai_popup)
        h.addWidget(self.btn_ai)

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
                                 ("🧩","Add-ons",2),("📚","Learning",3)]:
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
        self.tree_widget.setColumnWidth(0, 500)
        self.tree_widget.setColumnWidth(1, 129)
        self.tree_widget.setColumnWidth(2, 80)
        self.tree_widget.setColumnWidth(3, 90)
        self.tree_widget.setColumnWidth(4, 350)
        self.tree_widget.setColumnWidth(5, 200)
        self.tree_widget.itemDoubleClicked.connect(self.open_file)
        self.tree_widget.setSelectionMode(QTreeWidget.MultiSelection)
        self.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_treeview_context_menu)
        body.addWidget(self.tree_widget, 2)

        # ── Right stack ──────────────────────────────────────────
        self._right_stack = QStackedWidget()
        self._right_stack.setVisible(False)
        self._right_stack.setMinimumWidth(380)
        self._right_stack.setMaximumWidth(560)
        self._right_stack.addWidget(self._build_containers_page())  # 0
        self._right_stack.addWidget(self._build_tools_page())       # 1
        self._right_stack.addWidget(self._build_exe_page())         # 2
        body.addWidget(self._right_stack, 1)

        self.root_layout.addLayout(body)

    def _switch_panel(self, index: int, clicked_btn: QPushButton):
        if index == 3:                          # Learning → dialog
            clicked_btn.setChecked(False)
            VectorStoreDialog(self).exec()
            return
        already_visible = self._right_stack.isVisible()
        already_same    = self._right_stack.currentIndex() == index
        if already_visible and already_same:
            self._right_stack.setVisible(False)
            clicked_btn.setChecked(False)
        else:
            self._right_stack.setCurrentIndex(index)
            self._right_stack.setVisible(True)
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
        lay.addWidget(self.containers_list)

        self.container_files_list = QListWidget()
        self.container_files_list.itemClicked.connect(self.show_note_frame)
        self.container_files_list.itemDoubleClicked.connect(self.open_file_from_container)
        self.container_files_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.container_files_list.customContextMenuRequested.connect(
            self.show_context_menu_for_container
        )
        lay.addWidget(self.container_files_list)

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
            (QPushButton("Get Path"),                    self.get_link_from_tree_view),
            (QPushButton("Get Name"),                    self.get_name_from_tree_view),
            (QPushButton("List Files"),                  self.list_files_in_folder),
            (QPushButton("🔍 Contents"),                 self.open_index_interface),
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

    # ══════════════════════════════════════════════════════════════
    #  TOGGLE PANELS
    # ══════════════════════════════════════════════════════════════

    def toggle_hidden_frame(self):
        self._switch_panel(1, self._sidebar_btns[1])

    def toggle_hidden_frame_2(self):
        self._switch_panel(2, self._sidebar_btns[2])

    def open_learning(self):
        VectorStoreDialog(self).exec()

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
        except: mtime_ts  = None
        try:    size_bytes = os.path.getsize(path)
        except: size_bytes = None
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

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.folder_entry.setText(folder)

    def search_files(self):
        folder  = self.folder_entry.text().strip()
        keyword = self.filename_entry.text().strip()
        if not folder or not keyword:
            QMessageBox.warning(self, "Input Error", "Please provide the folder path and keyword.")
            return

        if keyword == "$synonym":
            self.edit_synonyms()
            return

        if keyword == "$stats":
            from ui.stats_dialog import StatsDialog
            StatsDialog(paths.STATS_FILE, self).exec()
            return

        if keyword.startswith("@"):
            synonyms = synonym_manager.load_synonyms(paths.SYNONYMS_FILE)
            results  = search_engine.fuzzy_search(folder, keyword[1:], synonyms)
        else:
            results = search_engine.search_files_by_name(folder, keyword)

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
                item.setToolTip(0, "Đã lưu vào: " + ", ".join(names))
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
        folder = self.folder_entry.text().strip()
        if not folder:
            QMessageBox.warning(self, "Input Error", "Please provide the folder path.")
            return

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
        if item:
            menu = QMenu(self)
            menu.addAction("Open Folder").triggered.connect(
                lambda: self._open_folder_path(os.path.dirname(item.text(4)))
            )
            menu.exec(QCursor.pos())

    def _open_folder_path(self, folder: str):
        if os.path.exists(folder):
            webbrowser.open(f"file:///{folder}")
        else:
            QMessageBox.warning(self, "Error", "Folder not found.")

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
                self.container_files_list.addItem(os.path.basename(fp))

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
                self.notes_window.display_note_for_file(c_item.text(), fp)
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
            menu.exec(QCursor.pos())

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
    #  AI POPUP
    # ══════════════════════════════════════════════════════════════

    def toggle_ai_popup(self):
        if self._ai_popup is None:
            from ui.ai_chat_popup import AIChatPopup
            self._ai_popup = AIChatPopup(main_app=self, parent=self)
        if self._ai_popup.isVisible():
            self._ai_popup.hide()
        else:
            self._ai_popup.show_below_widget(self.btn_ai, gap=8)

    # ══════════════════════════════════════════════════════════════
    #  OTHER DIALOGS
    # ══════════════════════════════════════════════════════════════

    def list_files_in_folder(self):
        show_list_files_window(self)

    def open_index_interface(self):
        IndexSearchWindow(self).exec()
