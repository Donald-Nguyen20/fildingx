# Funtion/tree_sorter.py
from __future__ import annotations

import re
from typing import Any, Tuple, Union
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem


def _natural_key(s: str) -> Tuple[Any, ...]:
    """
    Natural sort: "file2" < "file10"
    Trả về tuple so sánh được.
    """
    s = s or ""
    parts = re.split(r"(\d+)", s)
    key = []
    for p in parts:
        if p.isdigit():
            key.append(int(p))
        else:
            key.append(p.lower())
    return tuple(key)


class SortableTreeItem(QTreeWidgetItem):
    """
    QTreeWidgetItem có __lt__ dựa theo "sort key" đã set vào Qt.UserRole.
    Nếu chưa có sort key thì fallback text thường.
    """
    def __lt__(self, other: "QTreeWidgetItem") -> bool:
        tree = self.treeWidget()
        if tree is None:
            return super().__lt__(other)

        col = tree.sortColumn()

        a = self.data(col, Qt.UserRole)
        b = other.data(col, Qt.UserRole)

        # fallback nếu chưa set sort key
        if a is None:
            a = self.text(col)
        if b is None:
            b = other.text(col)

        try:
            return a < b
        except Exception:
            # fallback cuối cùng: so sánh string
            return str(a) < str(b)


class TreeSortHelper:
    """
    Gắn sort behavior cho QTreeWidget.
    - Click header để sort
    - Sort theo sort key (UserRole) nếu có
    """
    def __init__(self, tree: QTreeWidget):
        self.tree = tree
        self.tree.setSortingEnabled(True)

        hdr = self.tree.header()
        hdr.setSectionsClickable(True)
        hdr.setSortIndicatorShown(True)

    def make_item(
        self,
        name: str,
        date_text: str,
        type_text: str,
        size_text: str,
        path: str,
        *,
        mtime_ts: Union[int, float, None] = None,
        size_bytes: Union[int, float, None] = None,
    ) -> SortableTreeItem:
        """
        Tạo item 5 cột (NAME, DATE, TYPE, SIZE, PATH)
        và set sort key chuẩn:
        - NAME: natural key
        - DATE: timestamp
        - TYPE: lowercase text
        - SIZE: bytes/float
        """
        it = SortableTreeItem([name, date_text, type_text, size_text, path])

        # NAME sort key (natural)
        it.setData(0, Qt.UserRole, _natural_key(name))

        # DATE sort key: timestamp (nếu không có thì fallback text)
        if mtime_ts is not None:
            it.setData(1, Qt.UserRole, float(mtime_ts))

        # TYPE sort key
        it.setData(2, Qt.UserRole, (type_text or "").lower())

        # SIZE sort key: bytes (ưu tiên) hoặc float MB
        if size_bytes is not None:
            it.setData(3, Qt.UserRole, float(size_bytes))
        else:
            # nếu bạn chỉ có size_text "12.34" thì vẫn sort được
            try:
                it.setData(3, Qt.UserRole, float(size_text))
            except Exception:
                pass

        # PATH sort key (optional)
        it.setData(4, Qt.UserRole, (path or "").lower())

        return it
