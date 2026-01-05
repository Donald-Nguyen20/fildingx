# Funtion/learning_vector_store.py
import os, sys
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QProgressBar, QTextEdit, QMessageBox
)

from vector_store_builder import build_vector_store
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



        self.pb = QProgressBar()
        self.pb.setRange(0, 100)
        lay.addWidget(self.pb)

        self.logbox = QTextEdit()
        self.logbox.setReadOnly(True)
        lay.addWidget(self.logbox, 1)

        self.worker = None

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select folder to build vector store")
        if folder:
            self.ed_folder.setText(folder)

    def log(self, s: str):
        self.logbox.append(s)

    def start_build(self):
        folder = self.ed_folder.text().strip()
        name = self.ed_name.text().strip()

        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "Missing", "Please select a valid folder.")
            return
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
