# Funtion/learning_vector_store.py
import os, sys
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QProgressBar, QTextEdit, QMessageBox,
    QComboBox, QFrame
)


from vector_store_builder import build_vector_store, build_vector_store_from_files, append_vector_store
from Funtion.rag_extract import extract_content


def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)      # thư mục chứa .exe
    return os.path.dirname(os.path.abspath(__file__))  # Funtion/.. (sẽ chỉnh dưới)


def get_root_dir():
    # root = nơi chứa Finding7.1.py hoặc .exe
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # __file__ = Funtion/learning_vector_store.py => lên 1 cấp
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class DropZone(QFrame):
    filesDropped = Signal(list)  # list[str]

    def __init__(self, text="pull and drop file/folder to append", parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame{
                border:2px dashed rgba(180,180,180,160);
                border-radius:12px;
                padding:16px;
                background: rgba(255,255,255,18);
            }
        """)
        lay = QVBoxLayout(self)
        self.lbl = QLabel(text)
        self.lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.lbl)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        paths = []
        for u in urls:
            p = u.toLocalFile()
            if p:
                paths.append(p)

        # Expand folder -> files
        expanded = []
        for p in paths:
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for fn in files:
                        expanded.append(os.path.join(root, fn))
            else:
                expanded.append(p)

        self.filesDropped.emit(expanded)
        e.acceptProposedAction()

class BuildStoreWorker(QThread):
    progress = Signal(int)
    log = Signal(str)
    done = Signal(str)
    error = Signal(str)

    def __init__(self, folder_path: str, output_dir: str):
        super().__init__()
        self.folder_path = folder_path
        self.output_dir = output_dir

    def run(self):
        try:
            self.log.emit(f"Source: {self.folder_path}")
            self.log.emit(f"Output: {self.output_dir}")

            out = build_vector_store(
                folder_path=self.folder_path,
                extract_content_fn=extract_content,
                output_dir=self.output_dir,
                progress_cb=lambda p: self.progress.emit(int(p)),
            )
            self.done.emit(out)
        except Exception as e:
            self.error.emit(str(e))
class BuildStoreWorkerFiles(QThread):
    progress = Signal(int)
    log = Signal(str)
    done = Signal(str)
    error = Signal(str)

    def __init__(self, file_paths: list, output_dir: str):
        super().__init__()
        self.file_paths = file_paths or []
        self.output_dir = output_dir

    def run(self):
        try:
            self.log.emit(f"Selected files: {len(self.file_paths)}")
            self.log.emit(f"Output: {self.output_dir}")

            out = build_vector_store_from_files(
                file_paths=self.file_paths,
                extract_content_fn=extract_content,
                output_dir=self.output_dir,
                progress_cb=lambda p: self.progress.emit(int(p)),
            )
            self.done.emit(out)
        except Exception as e:
            self.error.emit(str(e))

class AppendStoreWorker(QThread):
    progress = Signal(int)
    log = Signal(str)
    done = Signal(int)     # số chunk added
    error = Signal(str)

    def __init__(self, store_dir: str, file_paths: list):
        super().__init__()
        self.store_dir = store_dir
        self.file_paths = file_paths

    def run(self):
        try:
            self.log.emit(f"Store: {self.store_dir}")
            self.log.emit(f"Incoming files: {len(self.file_paths)}")

            added = append_vector_store(
                store_dir=self.store_dir,
                file_paths=self.file_paths,
                extract_content_fn=extract_content,
                progress_cb=lambda p: self.progress.emit(int(p)),
            )
            self.done.emit(int(added))
        except Exception as e:
            self.error.emit(str(e))


class VectorStoreDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        from hud_widgets import qss_hud_metal_header_feel
        self.setStyleSheet(qss_hud_metal_header_feel())

        self.setWindowTitle("Learning • Build Vector Store")
        self.resize(720, 440)

        lay = QVBoxLayout(self)

        row1 = QHBoxLayout()
        self.ed_folder = QLineEdit()
        self._picked_files = []
        btn_browse = QPushButton("Browse Folder…")
        btn_browse.clicked.connect(self.pick_folder)
        row1.addWidget(QLabel("Source folder:"))
        row1.addWidget(self.ed_folder, 1)
        row1.addWidget(btn_browse)
        lay.addLayout(row1)

        row2 = QHBoxLayout()

        self.ed_name = QLineEdit("my_store")
        row2.addWidget(QLabel("Store name:"))
        row2.addWidget(self.ed_name, 1)

        self.btn_build = QPushButton("Build Vector Store")
        self.btn_build.clicked.connect(self.start_build)
        row2.addWidget(self.btn_build)

        lay.addLayout(row2)

        # ---- Row: select existing store ----
        row3 = QHBoxLayout()
        self.cbo_store = QComboBox()
        self.btn_reload = QPushButton("Reload")
        self.btn_reload.clicked.connect(self.reload_store_list)
        row3.addWidget(QLabel("Existing store:"))
        row3.addWidget(self.cbo_store, 1)
        row3.addWidget(self.btn_reload)
        lay.addLayout(row3)

        # ---- Drop zone + append button ----
        self.drop_zone = DropZone()
        self.drop_zone.filesDropped.connect(self.on_files_dropped)
        lay.addWidget(self.drop_zone)

        row4 = QHBoxLayout()
        self.btn_append = QPushButton("Append Dropped Files")
        self.btn_append.clicked.connect(self.start_append_from_drop)
        row4.addWidget(self.btn_append)
        lay.addLayout(row4)

        # internal buffer
        self._dropped_paths = []
        self.reload_store_list()


        self.pb = QProgressBar()
        self.pb.setRange(0, 100)
        lay.addWidget(self.pb)

        self.logbox = QTextEdit()
        self.logbox.setReadOnly(True)
        lay.addWidget(self.logbox, 1)

        self.worker = None

    def pick_folder(self):
        # 1) Chọn NHIỀU FILE trước
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select files (multi-select with Ctrl/Shift) OR Cancel to choose folder",
            "",
            "Documents (*.pdf *.docx *.xlsx *.pptx *.txt *.csv *.md *.html *.json *.xml);;All files (*.*)"
        )
        if files:
            self._picked_files = files
            self.ed_folder.setText(f"[{len(files)} files selected]")
            return

        # 2) Nếu Cancel -> chọn FOLDER
        folder = QFileDialog.getExistingDirectory(self, "Select folder to build vector store")
        if folder:
            self._picked_files = []
            self.ed_folder.setText(folder)

    def log(self, s: str):
        self.logbox.append(s)

    def start_build(self):
        name = self.ed_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing", "Please enter store name.")
            return

        root_dir = get_root_dir()
        vs_root = os.path.join(root_dir, "VectorStore")
        os.makedirs(vs_root, exist_ok=True)

        out_dir = os.path.join(vs_root, name)
        os.makedirs(out_dir, exist_ok=True)

        self.btn_build.setEnabled(False)
        self.pb.setValue(0)
        self.log(f"Output folder created: {out_dir}")

        # --- MODE 1: build từ NHIỀU FILE ---
        if self._picked_files:

            self.worker = BuildStoreWorkerFiles(self._picked_files, out_dir)

        # --- MODE 2: build từ FOLDER ---
        else:
            folder = self.ed_folder.text().strip()
            if not folder or not os.path.isdir(folder):
                QMessageBox.warning(self, "Missing", "Please select a valid folder OR select files.")
                self.btn_build.setEnabled(True)
                return
            self.worker = BuildStoreWorker(folder, out_dir)

        self.worker.progress.connect(self.pb.setValue)
        self.worker.log.connect(self.log)
        self.worker.done.connect(self.on_done)
        self.worker.error.connect(self.on_error)
        self.worker.start()


    def on_done(self, out_dir: str):
        self.log(f"✅ Done: {out_dir}")
        self.btn_build.setEnabled(True)
        QMessageBox.information(self, "Done", f"Vector store created:\n{out_dir}")

    def on_error(self, msg: str):
        self.log(f"❌ Error: {msg}")
        self.btn_build.setEnabled(True)
        QMessageBox.critical(self, "Error", msg)
    def reload_store_list(self):
        self.cbo_store.clear()
        root_dir = get_root_dir()
        vs_root = os.path.join(root_dir, "VectorStore")
        if not os.path.isdir(vs_root):
            return

        for name in sorted(os.listdir(vs_root)):
            store_dir = os.path.join(vs_root, name)
            if not os.path.isdir(store_dir):
                continue

            # store hợp lệ (đủ file để load/append/validate)
            idx  = os.path.join(store_dir, "index.faiss")
            meta = os.path.join(store_dir, "metadata.json")
            base = os.path.join(store_dir, "base_path.txt")
            cfg  = os.path.join(store_dir, "index_config.json")

            if os.path.exists(idx) and os.path.exists(meta) and os.path.exists(base) and os.path.exists(cfg):
                self.cbo_store.addItem(name, userData=store_dir)


    def on_files_dropped(self, paths: list):
        self._dropped_paths = paths or []
        self.log(f"📥 Dropped: {len(self._dropped_paths)} file(s).")
        # auto start append luôn cũng được; ở đây mình để bạn bấm nút Append.

    def start_append_from_drop(self):
        store_dir = self.cbo_store.currentData()
        if not store_dir:
            QMessageBox.warning(self, "Missing", "Please select an existing store.")
            return
        if not self._dropped_paths:
            QMessageBox.warning(self, "Missing", "Please drag & drop some files/folders first.")
            return

        self.btn_append.setEnabled(False)
        self.pb.setValue(0)
        self.log("▶️ Start append...")

        self.worker = AppendStoreWorker(store_dir, self._dropped_paths)
        self.worker.progress.connect(self.pb.setValue)
        self.worker.log.connect(self.log)
        self.worker.done.connect(self.on_append_done)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_append_done(self, added_chunks: int):
        self.log(f"✅ Append done: +{added_chunks} chunks")
        self.btn_append.setEnabled(True)
        QMessageBox.information(self, "Done", f"Append completed.\nAdded chunks: {added_chunks}")
