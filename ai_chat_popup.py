from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel,
    QTextBrowser, QLineEdit, QPushButton, QHBoxLayout,
    QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt
import os

# cần 2 file này nằm cùng thư mục:
# - vector_retriever.py
# - llm_client.py
from vector_retriever import VectorRetriever
from llm_client import LLMClient
from hud_widgets import HudPanel

class AIChatPopup(QDialog):
    def __init__(self, main_app=None, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        # trạng thái RAG
        self.store_dir = None
        self.retriever = None
        self.llm = LLMClient(model="llama3.2:3b")  # bạn đã cài model này

        self.setWindowTitle("AI Chat")
        self.setFixedSize(660, 600)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        shell = HudPanel(self, notch=True)
        outer.addWidget(shell)

        layout = QVBoxLayout(shell)
        layout.setContentsMargins(18, 26, 18, 18)  # chừa chỗ notch + padding HUD


        # ===== Top bar: "Chat" + nút Load Vector Store =====
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("💬 Chat:"))
        top_bar.addStretch()

        self.btn_load_vs = QPushButton("Load Vector Store")
        self.btn_load_vs.clicked.connect(self.load_vector_store)
        top_bar.addWidget(self.btn_load_vs)

        layout.addLayout(top_bar)

        # ===== Chat display =====
        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(False)
        self.chat_display.setOpenLinks(False)
        layout.addWidget(self.chat_display)

        # ===== Input row =====
        self.input_line = QLineEdit()
        self.input_line.setPlaceholderText("Nhập tin nhắn...")
        self.input_line.returnPressed.connect(self.handle_user_input)

        send_btn = QPushButton("Gửi")
        send_btn.clicked.connect(self.handle_user_input)

        input_layout = QHBoxLayout()
        input_layout.addWidget(self.input_line)
        input_layout.addWidget(send_btn)
        layout.addLayout(input_layout)

        # Thông báo trạng thái
        self.chat_display.append("🤖 Trợ lý: RAG đang ở chế độ chờ (chưa load Vector Store).")

        # (Tuỳ chọn) nếu main_app đã có last_vector_store_dir thì auto-load
        if self.main_app is not None:
            store = getattr(self.main_app, "last_vector_store_dir", None)
            if store and self._is_valid_store(store):
                self._init_store(store)
                self.chat_display.append(f"✅ Đã auto-load Vector Store:\n{store}")

    def _is_valid_store(self, folder: str) -> bool:
        required = ["index.faiss", "metadata.json", "base_path.txt"]
        return all(os.path.exists(os.path.join(folder, f)) for f in required)

    def _init_store(self, folder: str):
        self.store_dir = folder
        self.retriever = VectorRetriever(folder)
        # lưu lại về main_app để app chính nhớ store đang dùng
        if self.main_app is not None:
            self.main_app.last_vector_store_dir = folder

    def load_vector_store(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Vector Store Folder")
        if not folder:
            return

        if not self._is_valid_store(folder):
            QMessageBox.warning(
                self,
                "Invalid Vector Store",
                "Bạn chọn sai folder.\n\nFolder đúng phải chứa:\n"
                "- index.faiss\n- metadata.json\n- base_path.txt"
            )
            return

        self._init_store(folder)
        self.chat_display.append(f"✅ Vector Store loaded:\n{folder}")

    def handle_user_input(self):
        user_input = self.input_line.text().strip()
        if not user_input:
            return

        self.chat_display.append(f"🧑 Bạn: {user_input}")
        self.input_line.clear()

        # Nếu chưa load store → nhắc user load
        if self.retriever is None:
            self.chat_display.append("🤖 Trợ lý: Bạn hãy bấm 'Load Vector Store' trước nhé.")
            return

        # ==== RAG Retrieve ====
        results = self.retriever.search(user_input, top_k=12)
        if not results:
            self.chat_display.append("🤖 Trợ lý: Mình không tìm thấy đoạn liên quan trong Vector Store.")
            return

        # Ghép CONTEXT (giới hạn để model 3B không ngợp)
        ctx_blocks = []
        for i, r in enumerate(results, start=1):
            ctx_blocks.append(f"[{i}] {r['file_name']} | chunk {r['chunk_id']} | score={r['score']:.3f}\n{r['text']}")
        context = "\n\n".join(ctx_blocks)
        context = context[:8000]

        prompt = (
            "You are a helpful assistant. Use ONLY the context below to answer.\n"
            "If the answer is not in the context, say you don't have enough information.\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"QUESTION:\n{user_input}\n\n"
            "ANSWER:\n"
        )

        try:
            answer = self.llm.generate(prompt)
        except Exception as e:
            answer = f"(LLM error) {e}"

        self.chat_display.append(f"🤖 Trợ lý: {answer}")

        # (Giữ UI như cũ) — chỉ append nguồn tóm tắt vào chat
        src_lines = []
        for i, r in enumerate(results, start=1):
            src_lines.append(f"[{i}] {r['rel_path']} (chunk {r['chunk_id']})")
        self.chat_display.append("📌 Sources:\n" + "\n".join(src_lines))
        self.chat_display.setStyleSheet("""
        QTextBrowser {
            background: rgba(8, 14, 20, 160);
            border: 1px solid rgba(0, 220, 255, 90);
            border-radius: 10px;
            color: #d9ffff;
            padding: 10px;
        }
        """)

        self.input_line.setStyleSheet("""
        QLineEdit {
            background: rgba(8, 14, 20, 180);
            border: 1px solid rgba(0, 220, 255, 110);
            border-radius: 10px;
            color: #d9ffff;
            padding: 8px 10px;
        }
        QLineEdit:focus {
            border: 1px solid rgba(0, 220, 255, 220);
        }
        """)
