"""
core/workers.py — QThread workers cho các tác vụ nặng chạy nền.
"""
from PySide6.QtCore import QThread, Signal

from core.search_engine import find_duplicate_files


class DuplicateSearchWorker(QThread):
    """
    Chạy find_duplicate_files trên background thread.
    Phát signal finished(list) khi xong.
    """
    finished: Signal = Signal(list)

    def __init__(self, folder_path: str, parent=None):
        super().__init__(parent)
        self.folder_path = folder_path

    def run(self) -> None:
        results = find_duplicate_files(self.folder_path)
        self.finished.emit(results)
