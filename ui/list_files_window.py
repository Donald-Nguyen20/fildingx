"""
ui/list_files_window.py — Danh sách folder/file dạng cây phân cấp.
"""
import os
import shutil
import webbrowser

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QFileDialog,
    QMessageBox, QLCDNumber, QApplication, QLabel, QMenu,
    QTreeWidgetItemIterator,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
from ui import themes


def _pick_folders_native() -> list[str]:
    """Windows IFileOpenDialog — dialog gốc, chọn nhiều folder (Ctrl/Shift+click)."""
    try:
        import ctypes
        import uuid

        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)

        def _guid(s):
            return (ctypes.c_byte * 16)(*uuid.UUID(s).bytes_le)

        CLSID = _guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")
        IID   = _guid("D57C7288-D4AD-4768-BE02-9D969532D960")

        pDlg = ctypes.c_void_p()
        if ole32.CoCreateInstance(CLSID, None, 1, IID, ctypes.byref(pDlg)) != 0:
            return []

        def vt(p):
            return ctypes.cast(
                ctypes.cast(p, ctypes.POINTER(ctypes.c_void_p))[0],
                ctypes.POINTER(ctypes.c_void_p),
            )

        def fn(p, idx, restype, *argtypes):
            return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vt(p)[idx])

        # GetOptions / SetOptions / Show
        opts = ctypes.c_uint()
        fn(pDlg, 10, ctypes.HRESULT, ctypes.POINTER(ctypes.c_uint))(pDlg, ctypes.byref(opts))
        fn(pDlg,  9, ctypes.HRESULT, ctypes.c_uint)(pDlg, opts.value | 0x20 | 0x200)  # FOS_PICKFOLDERS | FOS_ALLOWMULTISELECT
        hr = fn(pDlg, 3, ctypes.HRESULT, ctypes.c_void_p)(pDlg, None)

        folders = []
        if hr == 0:
            pArr = ctypes.c_void_p()
            fn(pDlg, 27, ctypes.HRESULT, ctypes.POINTER(ctypes.c_void_p))(pDlg, ctypes.byref(pArr))

            count = ctypes.c_uint()
            fn(pArr, 7, ctypes.HRESULT, ctypes.POINTER(ctypes.c_uint))(pArr, ctypes.byref(count))

            for i in range(count.value):
                pItem = ctypes.c_void_p()
                fn(pArr, 8, ctypes.HRESULT, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))(pArr, i, ctypes.byref(pItem))
                name = ctypes.c_wchar_p()
                fn(pItem, 5, ctypes.HRESULT, ctypes.c_int, ctypes.POINTER(ctypes.c_wchar_p))(pItem, 0x80058000, ctypes.byref(name))
                if name.value:
                    folders.append(os.path.normpath(name.value))
                fn(pItem, 2, ctypes.HRESULT)(pItem)

            fn(pArr, 2, ctypes.HRESULT)(pArr)

        fn(pDlg, 2, ctypes.HRESULT)(pDlg)
        return folders
    except Exception:
        return []


def show_list_files_window(parent) -> None:
    """Mở dialog Windows gốc chọn nhiều thư mục rồi hiển thị cây folder/file."""
    folders = _pick_folders_native()
    if not folders:
        return
    _ListFilesWindow(parent, folders).exec()


class _ListFilesWindow(QDialog):

    def __init__(self, parent, folder_paths: list[str]):
        super().__init__(parent)
        if len(folder_paths) == 1:
            self.setWindowTitle(f"📂  {os.path.basename(folder_paths[0])}")
        else:
            self.setWindowTitle(f"📂  {len(folder_paths)} folders")
        self.setGeometry(150, 80, 1200, 720)

        self._folder_paths = folder_paths
        self._ext_set: set = set()
        self._total_files = 0
        self._blocking = False          # chặn itemChanged khi set checkbox hàng loạt

        self.setStyleSheet(themes.get_current()["qss"])
        layout = QVBoxLayout(self)

        # ── Filter / action bar ───────────────────────────────────
        bar = QHBoxLayout()

        self.lcd = QLCDNumber()
        self.lcd.setDigitCount(6)
        self.lcd.setFixedSize(80, 30)
        pal = self.lcd.palette()
        pal.setColor(QPalette.WindowText, QColor("black"))
        pal.setColor(QPalette.Light,      QColor("blue"))
        pal.setColor(QPalette.Dark,       QColor("black"))
        self.lcd.setPalette(pal)

        self.format_combo = QComboBox()
        self.format_combo.addItem("All types")
        self.format_combo.setMinimumWidth(120)

        self.min_size = QLineEdit()
        self.min_size.setPlaceholderText("Min MB")
        self.min_size.setFixedWidth(75)
        self.max_size = QLineEdit()
        self.max_size.setPlaceholderText("Max MB")
        self.max_size.setFixedWidth(75)

        btn_size       = QPushButton("Filter Size")
        btn_expand     = QPushButton("Expand All")
        btn_collapse   = QPushButton("Collapse All")
        btn_delete     = QPushButton("🗑 Delete")
        btn_copy       = QPushButton("📋 Copy Paths")
        btn_rename     = QPushButton("✏ Batch Rename")
        btn_add_search = QPushButton("➕ Add to Search")

        for w in [self.lcd,
                  QLabel("Type:"), self.format_combo,
                  QLabel("Size:"), self.min_size, self.max_size, btn_size,
                  btn_expand, btn_collapse,
                  btn_delete, btn_copy, btn_rename, btn_add_search]:
            bar.addWidget(w)
        bar.addStretch()
        layout.addLayout(bar)

        # ── Tree ─────────────────────────────────────────────────
        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Name", "Type", "Size (MB)", "Full Path"])
        self.tree.setColumnWidth(0, 480)
        self.tree.setColumnWidth(1, 80)
        self.tree.setColumnWidth(2, 90)
        self.tree.header().setStretchLastSection(True)
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree.itemDoubleClicked.connect(self._open_item)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree)

        # Signals
        btn_size.clicked.connect(self._filter_by_size)
        btn_expand.clicked.connect(self.tree.expandAll)
        btn_collapse.clicked.connect(self.tree.collapseAll)
        btn_delete.clicked.connect(self._delete_checked)
        btn_copy.clicked.connect(self._copy_paths)
        btn_rename.clicked.connect(self._open_batch_rename)
        btn_add_search.clicked.connect(lambda: self._add_to_search())
        self.format_combo.currentTextChanged.connect(self._reapply_filters)

        # Build
        for fp in folder_paths:
            self._build_root(fp)
        self.format_combo.addItems(sorted(self._ext_set))
        self.lcd.display(self._total_files)

    # ══════════════════════════════════════════════════════════════
    #  BUILD TREE
    # ══════════════════════════════════════════════════════════════

    def _build_root(self, folder: str):
        """Tạo top-level item cho folder được chọn, rồi build con bên trong."""
        name = os.path.basename(folder) or folder
        item = self._make_item(f"📁 {name}", "DIR", "", folder)
        self.tree.addTopLevelItem(item)
        self._build_tree(folder, item)

    def _build_tree(self, folder: str, parent):
        try:
            entries = sorted(
                os.scandir(folder),
                key=lambda e: (not e.is_dir(), e.name.lower()),
            )
        except PermissionError:
            return

        for e in entries:
            if e.is_dir():
                item = self._make_item(f"📁 {e.name}", "DIR", "", e.path)
                self._attach(item, parent)
                self._build_tree(e.path, item)
            else:
                ext = os.path.splitext(e.name)[1].lower() or "—"
                self._ext_set.add(ext)
                try:
                    sz = e.stat().st_size / (1024 * 1024)
                except Exception:
                    sz = 0.0
                item = self._make_item(e.name, ext, f"{sz:.2f}", e.path)
                item.setData(2, Qt.UserRole, sz)
                self._attach(item, parent)
                self._total_files += 1

    def _make_item(self, name: str, type_: str, size: str, path: str) -> QTreeWidgetItem:
        it = QTreeWidgetItem([name, type_, size, path])
        it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        it.setCheckState(0, Qt.Checked)
        return it

    def _attach(self, item: QTreeWidgetItem, parent):
        if parent:
            parent.addChild(item)
        else:
            self.tree.addTopLevelItem(item)

    # ══════════════════════════════════════════════════════════════
    #  CHECKBOX PROPAGATION
    # ══════════════════════════════════════════════════════════════

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        if column != 0 or self._blocking:
            return
        self._blocking = True
        try:
            self._propagate(item, item.checkState(0))
        finally:
            self._blocking = False

    def _propagate(self, item: QTreeWidgetItem, state):
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._propagate(child, state)

    # ══════════════════════════════════════════════════════════════
    #  FILTERS
    # ══════════════════════════════════════════════════════════════

    def _reapply_filters(self):
        ext = self.format_combo.currentText()
        try:
            lo = float(self.min_size.text()) if self.min_size.text() else None
            hi = float(self.max_size.text()) if self.max_size.text() else None
        except ValueError:
            lo = hi = None
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            vis = self._apply_filter(root.child(i), ext, lo, hi)
            root.child(i).setHidden(not vis)

    def _filter_by_size(self):
        try:
            lo = float(self.min_size.text()) if self.min_size.text() else None
            hi = float(self.max_size.text()) if self.max_size.text() else None
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Enter valid numbers.")
            return
        if lo is None and hi is None:
            QMessageBox.warning(self, "Input Error", "Enter at least one size value.")
            return
        self._reapply_filters()

    def _apply_filter(self, item: QTreeWidgetItem, ext_filter: str,
                      min_mb, max_mb) -> bool:
        """Trả True nếu item nên hiện. Ẩn/hiện con đệ quy."""
        if item.text(1) == "DIR":
            any_vis = False
            for i in range(item.childCount()):
                child = item.child(i)
                vis = self._apply_filter(child, ext_filter, min_mb, max_mb)
                child.setHidden(not vis)
                if vis:
                    any_vis = True
            return any_vis
        else:
            if ext_filter and ext_filter != "All types":
                if item.text(1) != ext_filter:
                    return False
            if min_mb is not None or max_mb is not None:
                sz = item.data(2, Qt.UserRole) or 0.0
                if min_mb is not None and sz < min_mb:
                    return False
                if max_mb is not None and sz > max_mb:
                    return False
            return True

    # ══════════════════════════════════════════════════════════════
    #  COLLECT CHECKED ITEMS
    # ══════════════════════════════════════════════════════════════

    def _collect_checked(self, include_dirs: bool = False) -> list[str]:
        result: list[str] = []
        self._walk_checked(self.tree.invisibleRootItem(), result, include_dirs)
        return result

    def _walk_checked(self, node: QTreeWidgetItem, result: list, include_dirs: bool):
        for i in range(node.childCount()):
            child = node.child(i)
            if int(child.checkState(0)) == 2:   # Qt.Checked == 2
                if child.text(1) == "DIR":
                    if include_dirs:
                        result.append(child.text(3))
                    # Không đệ quy vào con — cả folder được xử lý như 1 đơn vị
                else:
                    result.append(child.text(3))
            else:
                self._walk_checked(child, result, include_dirs)

    def _collect_checked_dirs(self) -> list[str]:
        """Lấy top-level DIR không bị Unchecked để add to search."""
        result: list[str] = []
        self._walk_checked_dirs(self.tree.invisibleRootItem(), result, set())
        return result

    def _walk_checked_dirs(self, node: QTreeWidgetItem, result: list, added: set):
        for i in range(node.childCount()):
            child = node.child(i)
            if child.text(1) != "DIR":
                continue
            path = child.text(3)
            cs = child.checkState(0)
            if cs != Qt.Unchecked:
                if path and path not in added:
                    result.append(path)
                    added.add(path)
                # Cha đã check → không đệ quy vào con
            else:
                # Cha unchecked → tìm trong con
                self._walk_checked_dirs(child, result, added)

    # ══════════════════════════════════════════════════════════════
    #  ACTIONS
    # ══════════════════════════════════════════════════════════════

    def _open_item(self, item: QTreeWidgetItem, _col: int):
        path = item.text(3)
        if os.path.exists(path):
            webbrowser.open(path)

    def _add_to_search(self, paths: list[str] | None = None):
        if paths is None:
            paths = self._collect_checked_dirs()
        if not paths:
            QMessageBox.information(self, "Notice", "No folder checked.")
            return
        main_win = self.parent()
        if hasattr(main_win, "_add_to_search_folders"):
            main_win._add_to_search_folders(paths)
        names = "\n".join(f"• {os.path.basename(p)}" for p in paths)
        QMessageBox.information(
            self, "Added to Search",
            f"Added {len(paths)} folder(s) to search:\n\n{names}",
        )

    def _delete_checked(self):
        paths = self._collect_checked(include_dirs=True)
        if not paths:
            QMessageBox.information(self, "Notice", "No items checked.")
            return
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(paths)} item(s)?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        failed = []
        for path in paths:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except Exception as e:
                failed.append(f"{os.path.basename(path)}: {e}")
        if failed:
            QMessageBox.warning(self, "Errors", "\n".join(failed))
        else:
            QMessageBox.information(self, "Done", "Deleted successfully.")
        self._rebuild()

    def _copy_paths(self):
        paths = self._collect_checked(include_dirs=True)
        if not paths:
            QMessageBox.information(self, "Notice", "No items checked.")
            return
        QApplication.clipboard().setText("\n".join(paths))
        QMessageBox.information(self, "Copied", f"{len(paths)} path(s) copied to clipboard.")

    def _open_batch_rename(self):
        paths = self._collect_checked(include_dirs=False)
        if not paths:
            QMessageBox.warning(self, "No Selection", "Check at least one file.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Batch Rename")
        dlg.setGeometry(500, 300, 420, 180)
        lay = QVBoxLayout(dlg)

        prefix_in  = QLineEdit(); prefix_in.setPlaceholderText("Prefix")
        suffix_in  = QLineEdit(); suffix_in.setPlaceholderText("Suffix (before extension)")
        replace_in = QLineEdit(); replace_in.setPlaceholderText("Text to replace → leave empty to skip")

        for w in [prefix_in, suffix_in, replace_in]:
            lay.addWidget(w)

        ok_btn = QPushButton("Rename")
        ok_btn.clicked.connect(
            lambda: self._do_rename(
                paths, prefix_in.text(), suffix_in.text(), replace_in.text(), dlg
            )
        )
        lay.addWidget(ok_btn)
        dlg.exec()

    def _do_rename(self, paths: list, prefix: str, suffix: str,
                   replace_text: str, dialog: QDialog):
        failed = []
        for path in paths:
            folder   = os.path.dirname(path)
            old_name = os.path.basename(path)
            stem, ext = os.path.splitext(old_name)
            new_stem = stem.replace(replace_text, "") if replace_text else stem
            new_name = f"{prefix}{new_stem}{suffix}{ext}"
            new_path = os.path.join(folder, new_name)
            try:
                os.rename(path, new_path)
            except Exception as e:
                failed.append(f"{old_name}: {e}")
        if failed:
            QMessageBox.warning(self, "Errors", "\n".join(failed))
        else:
            QMessageBox.information(self, "Done", "Batch rename complete.")
        dialog.accept()
        self._rebuild()

    # ══════════════════════════════════════════════════════════════
    #  REBUILD
    # ══════════════════════════════════════════════════════════════

    def _rebuild(self):
        self.tree.clear()
        self._ext_set.clear()
        self._total_files = 0
        for fp in self._folder_paths:
            self._build_root(fp)
        new_items = sorted(self._ext_set)
        current = [self.format_combo.itemText(i)
                   for i in range(1, self.format_combo.count())]
        for ext in new_items:
            if ext not in current:
                self.format_combo.addItem(ext)
        self.lcd.display(self._total_files)
