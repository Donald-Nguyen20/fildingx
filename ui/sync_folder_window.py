"""
ui/sync_folder_window.py — Đồng bộ nội dung Folder A → Folder B.
Layout: 2 panel tree song song (Source | Target).
Lưu/load cấu hình src+dst vào sync_config.json.
"""
import json
import os
import shutil

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QTreeWidget, QTreeWidgetItem, QFileDialog, QMessageBox,
    QLabel, QSplitter, QFrame,
)
from PySide6.QtCore import Qt

from ui import themes
import paths


_CONFIG_FILE = paths.SYNC_CONFIG_FILE


def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_config(src: str, dst: str, unchecked: list[str] | None = None) -> None:
    data: dict = {"source": src, "target": dst}
    if unchecked is not None:
        data["unchecked"] = unchecked
    try:
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def show_sync_folder_window(parent) -> None:
    _SyncFolderWindow(parent).exec()


class _SyncFolderWindow(QDialog):

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Synchronize Folders")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self.setGeometry(100, 60, 1300, 740)
        self.setStyleSheet(themes.get_current()["qss"])

        self._src      = ""
        self._dst      = ""
        self._blocking = False

        cfg = _load_config()
        self._src = cfg.get("source", "")
        self._dst = cfg.get("target", "")

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Folder selectors (2 cột) ──────────────────────────────
        sel_row = QHBoxLayout()

        # Source
        src_col = QVBoxLayout()
        src_label = QLabel("📂  Folder A — Source")
        src_label.setStyleSheet("font-weight:bold;")
        src_bar = QHBoxLayout()
        self.src_edit = QLineEdit()
        self.src_edit.setPlaceholderText("Select source folder…")
        self.src_edit.setReadOnly(True)
        btn_src = QPushButton("Browse")
        btn_src.clicked.connect(self._pick_src)
        src_bar.addWidget(self.src_edit, 1)
        src_bar.addWidget(btn_src)
        src_col.addWidget(src_label)
        src_col.addLayout(src_bar)

        # Target
        dst_col = QVBoxLayout()
        dst_label = QLabel("📂  Folder B — Target")
        dst_label.setStyleSheet("font-weight:bold;")
        dst_bar = QHBoxLayout()
        self.dst_edit = QLineEdit()
        self.dst_edit.setPlaceholderText("Select target folder…")
        self.dst_edit.setReadOnly(True)
        btn_dst = QPushButton("Browse")
        btn_dst.clicked.connect(self._pick_dst)
        dst_bar.addWidget(self.dst_edit, 1)
        dst_bar.addWidget(btn_dst)
        dst_col.addWidget(dst_label)
        dst_col.addLayout(dst_bar)

        sel_row.addLayout(src_col, 1)
        sel_row.addSpacing(12)
        sel_row.addLayout(dst_col, 1)
        layout.addLayout(sel_row)

        # ── Action bar ────────────────────────────────────────────
        act = QHBoxLayout()
        btn_check    = QPushButton("Check All")
        btn_uncheck  = QPushButton("Uncheck All")
        btn_expand   = QPushButton("Expand All")
        btn_collapse = QPushButton("Collapse All")
        self.btn_sync = QPushButton("🔄  Synchronize →")
        self.btn_sync.setEnabled(False)

        for w in [btn_check, btn_uncheck, btn_expand, btn_collapse]:
            act.addWidget(w)
        act.addStretch()
        act.addWidget(self.btn_sync)
        layout.addLayout(act)

        # ── Splitter: Source tree | Target tree ───────────────────
        splitter = QSplitter(Qt.Horizontal)

        self.src_tree = self._make_tree()
        self.dst_tree = self._make_tree(checkable=False)

        src_frame = self._wrap(self.src_tree, "Source")
        dst_frame = self._wrap(self.dst_tree, "Target")

        splitter.addWidget(src_frame)
        splitter.addWidget(dst_frame)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setHandleWidth(6)
        layout.addWidget(splitter, 1)

        # ── Restore saved paths ───────────────────────────────────
        if self._src and os.path.isdir(self._src):
            self.src_edit.setReadOnly(False)
            self.src_edit.setText(self._src)
            self.src_edit.setReadOnly(True)
            self._build_tree(self.src_tree, self._src, checkable=True)
            self._restore_check_state(set(cfg.get("unchecked", [])))
        if self._dst and os.path.isdir(self._dst):
            self.dst_edit.setReadOnly(False)
            self.dst_edit.setText(self._dst)
            self.dst_edit.setReadOnly(True)
            self._build_tree(self.dst_tree, self._dst, checkable=False)
        self._refresh_sync_btn()

        # Signals
        btn_check.clicked.connect(lambda: self._set_all(Qt.Checked))
        btn_uncheck.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        btn_expand.clicked.connect(self._expand_all)
        btn_collapse.clicked.connect(self._collapse_all)
        self.btn_sync.clicked.connect(lambda: self._run_sync())
        self.src_tree.itemChanged.connect(self._on_item_changed)

    # ── Helpers ───────────────────────────────────────────────────

    def _make_tree(self, checkable: bool = True) -> QTreeWidget:
        t = QTreeWidget()
        t.setColumnCount(3)
        t.setHeaderLabels(["Name", "Type", "Size (MB)"])
        t.setColumnWidth(0, 320)
        t.setColumnWidth(1, 70)
        t.header().setStretchLastSection(True)
        t.setSelectionMode(QTreeWidget.ExtendedSelection)
        return t

    def _wrap(self, tree: QTreeWidget, title: str) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        lbl = QLabel(title)
        lbl.setStyleSheet("font-weight:bold; padding:2px;")
        lay.addWidget(lbl)
        lay.addWidget(tree)
        return frame

    def _expand_all(self):
        self.src_tree.expandAll()
        self.dst_tree.expandAll()

    def _collapse_all(self):
        self.src_tree.collapseAll()
        self.dst_tree.collapseAll()

    # ══════════════════════════════════════════════════════════════
    #  FOLDER PICKING
    # ══════════════════════════════════════════════════════════════

    def _pick_src(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Source Folder (A)")
        if not folder:
            return
        self._src = os.path.normpath(folder)
        self.src_edit.setReadOnly(False)
        self.src_edit.setText(self._src)
        self.src_edit.setReadOnly(True)
        self._build_tree(self.src_tree, self._src, checkable=True)
        self._refresh_sync_btn()
        _save_config(self._src, self._dst, self._collect_unchecked())

    def _pick_dst(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Target Folder (B)")
        if not folder:
            return
        self._dst = os.path.normpath(folder)
        self.dst_edit.setReadOnly(False)
        self.dst_edit.setText(self._dst)
        self.dst_edit.setReadOnly(True)
        self._build_tree(self.dst_tree, self._dst, checkable=False)
        self._refresh_sync_btn()
        _save_config(self._src, self._dst, self._collect_unchecked())

    def _refresh_sync_btn(self):
        self.btn_sync.setEnabled(bool(self._src and self._dst))

    # ══════════════════════════════════════════════════════════════
    #  BUILD TREE
    # ══════════════════════════════════════════════════════════════

    def _build_tree(self, tree: QTreeWidget, folder: str, checkable: bool):
        tree.clear()
        self._scan(tree, folder, None, "", checkable)

    def _scan(self, tree: QTreeWidget, folder: str, parent, rel_prefix: str, checkable: bool):
        try:
            entries = sorted(
                os.scandir(folder),
                key=lambda e: (not e.is_dir(), e.name.lower()),
            )
        except PermissionError:
            return

        for e in entries:
            rel = os.path.join(rel_prefix, e.name) if rel_prefix else e.name
            if e.is_dir():
                item = self._make_item(f"📁 {e.name}", "DIR", "", rel, checkable)
                self._attach(tree, item, parent)
                self._scan(tree, e.path, item, rel, checkable)
            else:
                ext = os.path.splitext(e.name)[1].lower() or "—"
                try:
                    sz = f"{e.stat().st_size / (1024 * 1024):.2f}"
                except Exception:
                    sz = "0.00"
                item = self._make_item(e.name, ext, sz, rel, checkable)
                self._attach(tree, item, parent)

    def _make_item(self, name: str, type_: str, size: str,
                   rel: str, checkable: bool) -> QTreeWidgetItem:
        it = QTreeWidgetItem([name, type_, size])
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if checkable:
            flags |= Qt.ItemIsUserCheckable
        it.setFlags(flags)
        it.setData(0, Qt.UserRole, rel)
        if checkable:
            it.setCheckState(0, Qt.Checked)
        return it

    def _attach(self, tree: QTreeWidget, item: QTreeWidgetItem, parent):
        if parent:
            parent.addChild(item)
        else:
            tree.addTopLevelItem(item)

    # ══════════════════════════════════════════════════════════════
    #  CHECKBOX PROPAGATION (chỉ Source tree)
    # ══════════════════════════════════════════════════════════════

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        if column != 0 or self._blocking:
            return
        self._blocking = True
        try:
            self._propagate(item, item.checkState(0))
        finally:
            self._blocking = False
        _save_config(self._src, self._dst, self._collect_unchecked())

    def _propagate(self, item: QTreeWidgetItem, state):
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._propagate(child, state)

    def _set_all(self, state):
        self._blocking = True
        try:
            root = self.src_tree.invisibleRootItem()
            for i in range(root.childCount()):
                item = root.child(i)
                item.setCheckState(0, state)
                self._propagate(item, state)
        finally:
            self._blocking = False
        _save_config(self._src, self._dst, self._collect_unchecked())

    # ══════════════════════════════════════════════════════════════
    #  CHECK STATE PERSISTENCE
    # ══════════════════════════════════════════════════════════════

    def _collect_unchecked(self) -> list[str]:
        result: list[str] = []
        self._walk_unchecked(self.src_tree.invisibleRootItem(), result)
        return result

    def _walk_unchecked(self, node: QTreeWidgetItem, result: list[str]) -> None:
        for i in range(node.childCount()):
            child = node.child(i)
            if child.checkState(0) == Qt.Unchecked:
                result.append(child.data(0, Qt.UserRole))
            self._walk_unchecked(child, result)

    def _restore_check_state(self, unchecked: set[str]) -> None:
        if not unchecked:
            return
        self._blocking = True
        try:
            self._apply_check_state(self.src_tree.invisibleRootItem(), unchecked)
        finally:
            self._blocking = False

    def _apply_check_state(self, node: QTreeWidgetItem, unchecked: set[str]) -> None:
        for i in range(node.childCount()):
            child = node.child(i)
            if child.data(0, Qt.UserRole) in unchecked:
                child.setCheckState(0, Qt.Unchecked)
            self._apply_check_state(child, unchecked)

    # ══════════════════════════════════════════════════════════════
    #  COLLECT CHECKED
    # ══════════════════════════════════════════════════════════════

    def _collect_checked(self) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        self._walk(self.src_tree.invisibleRootItem(), result)
        return result

    def _walk(self, node: QTreeWidgetItem, result: list):
        for i in range(node.childCount()):
            child = node.child(i)
            cs = child.checkState(0)
            if cs == Qt.Checked:
                result.append((child.data(0, Qt.UserRole), child.text(1)))
            elif cs != Qt.Unchecked:
                self._walk(child, result)

    # ══════════════════════════════════════════════════════════════
    #  SYNC
    # ══════════════════════════════════════════════════════════════

    def _run_sync(self):
        if not self._src or not self._dst:
            return
        if os.path.normpath(self._src) == os.path.normpath(self._dst):
            QMessageBox.warning(self, "Error", "Source and target must be different folders.")
            return

        items = self._collect_checked()
        if not items:
            QMessageBox.information(self, "Notice", "No items selected.")
            return

        reply = QMessageBox.question(
            self, "Confirm Sync",
            f"Sync {len(items)} item(s)\n"
            f"From: {self._src}\n"
            f"To:   {self._dst}\n\n"
            f"Existing files will be overwritten. Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        ok: list[str] = []
        failed: list[str] = []

        for rel, type_ in items:
            src_path = os.path.join(self._src, rel)
            dst_path = os.path.join(self._dst, rel)
            try:
                if type_ == "DIR":
                    shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    shutil.copy2(src_path, dst_path)
                ok.append(rel)
            except Exception as e:
                failed.append(f"• {rel}: {e}")

        msg = f"Synced {len(ok)} item(s) successfully."
        if failed:
            msg += f"\n\nFailed ({len(failed)}):\n" + "\n".join(failed)
        QMessageBox.information(self, "Sync Complete", msg)

        # Refresh target tree sau khi sync
        self._build_tree(self.dst_tree, self._dst, checkable=False)
