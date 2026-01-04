from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel,
    QTextBrowser, QLineEdit, QPushButton, QHBoxLayout,
    QFileDialog, QMessageBox, QComboBox, QFormLayout
)
from PySide6.QtCore import Qt
import os

# cần 2 file này nằm cùng thư mục:
# - vector_retriever.py
# - llm_client.py
from vector_retriever import VectorRetriever
from llm_client import create_llm_client, PROVIDERS
from llm_config import load_llm_config, save_llm_config
from hud_widgets import HudPanel


class LLMSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM Settings")
        self.setModal(True)
        self.setMinimumWidth(520)

        cfg = load_llm_config()

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.ed_openrouter = QLineEdit(cfg.get("openrouter_api_key",""))
        self.ed_openrouter.setEchoMode(QLineEdit.Password)
        form.addRow("OpenRouter API key:", self.ed_openrouter)

        self.ed_groq = QLineEdit(cfg.get("groq_api_key",""))
        self.ed_groq.setEchoMode(QLineEdit.Password)
        form.addRow("Groq API key:", self.ed_groq)

        self.ed_gemini = QLineEdit(cfg.get("gemini_api_key",""))
        self.ed_gemini.setEchoMode(QLineEdit.Password)
        form.addRow("Gemini API key:", self.ed_gemini)

        self.ed_ollama_host = QLineEdit(cfg.get("ollama_host","http://localhost:11434"))
        form.addRow("Ollama host:", self.ed_ollama_host)

        layout.addLayout(form)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_save = QPushButton("Save")
        btn_cancel = QPushButton("Cancel")
        btn_save.clicked.connect(self.on_save)
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_save)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)
        self.setStyleSheet(self.styleSheet() + """
QComboBox {
    background-color: white;
    color: black;
    border: 1px solid #B0B0B0;
    border-radius: 6px;
    padding: 4px 10px;
}
QComboBox QAbstractItemView {
    background-color: white;
    color: black;
    selection-background-color: #DDEEFF;
    selection-color: black;
}
""")

    def on_save(self):
        cfg = load_llm_config()
        cfg["openrouter_api_key"] = self.ed_openrouter.text().strip()
        cfg["groq_api_key"] = self.ed_groq.text().strip()
        cfg["gemini_api_key"] = self.ed_gemini.text().strip()
        cfg["ollama_host"] = self.ed_ollama_host.text().strip() or "http://localhost:11434"
        save_llm_config(cfg)
        self.accept()

class AIChatPopup(QDialog):
    def __init__(self, main_app=None, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        # trạng thái RAG
        self.store_dir = None
        self.retriever = None
        cfg = load_llm_config()
        self.provider_key = "ollama"
        self.model_name = cfg.get("ollama_model", "llama3.2:3b")
        self.llm = create_llm_client(self.provider_key, self.model_name)



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
        # Provider combobox
        self.cmb_provider = QComboBox()
        for k, label in PROVIDERS:
            self.cmb_provider.addItem(label, userData=k)
        self.cmb_provider.setToolTip("Choose LLM provider")
        top_bar.addWidget(self.cmb_provider)

        # Model combobox (text list)
        self.cmb_model = QComboBox()
        self.cmb_model.setEditable(True)
        self.cmb_model.setToolTip("Choose / type model name")
        top_bar.addWidget(self.cmb_model)

        # Settings button
        self.btn_llm_settings = QPushButton("⚙")
        self.btn_llm_settings.setToolTip("LLM Settings (API keys / defaults)")
        top_bar.addWidget(self.btn_llm_settings)

        self.btn_load_vs = QPushButton("Load Vector Store")
        self.btn_load_vs.clicked.connect(self.load_vector_store)
        top_bar.addWidget(self.btn_load_vs)

        layout.addLayout(top_bar)

        # ===== Chat display =====
        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(False)
        self.chat_display.setOpenLinks(False)
        layout.addWidget(self.chat_display)
        # ===== INIT provider/model mặc định (ĐẶT Ở ĐÂY) =====
        self._fill_models_for_provider("ollama")

        # đặt provider ban đầu = ollama
        for i in range(self.cmb_provider.count()):
            if self.cmb_provider.itemData(i) == "ollama":
                self.cmb_provider.setCurrentIndex(i)
                break

        # khởi tạo LLM theo provider/model đang hiển thị
        self.on_llm_changed()

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
        self.btn_llm_settings.clicked.connect(self.open_llm_settings)
        self.cmb_provider.currentIndexChanged.connect(self.on_llm_changed)
        self.cmb_model.currentIndexChanged.connect(self.on_llm_changed)
        combo_qss = """
        QComboBox {
            background-color: #FFFFFF;
            color: #000000;
            border: 1px solid rgba(180, 180, 180, 220);
            border-radius: 8px;
            padding: 4px 10px;
        }
        QComboBox::drop-down {
            border: none;
            width: 18px;
        }
        QComboBox QAbstractItemView {
            background-color: #FFFFFF;
            color: #000000;
            selection-background-color: #DDEEFF;
            selection-color: #000000;
            outline: 0;
        }
        """

        self.cmb_provider.setStyleSheet(combo_qss)
        self.cmb_model.setStyleSheet(combo_qss)

        # ép Qt “vẽ background” dù widget cha trong suốt (HUD)
        self.cmb_provider.setAttribute(Qt.WA_StyledBackground, True)
        self.cmb_model.setAttribute(Qt.WA_StyledBackground, True)

    def _fill_models_for_provider(self, provider_key: str):
        cfg = load_llm_config()
        self.cmb_model.blockSignals(True)
        self.cmb_model.clear()

        presets = {
            "ollama": [cfg.get("ollama_model","llama3.2:3b"), "llama3.2:3b", "qwen2.5:7b", "deepseek-r1:7b"],
            "openrouter": [cfg.get("openrouter_model","meta-llama/llama-3.3-70b-instruct:free")],
            "groq": [cfg.get("groq_model","llama-3.3-70b-versatile")],
            "gemini": [cfg.get("gemini_model","gemini-1.5-flash"), "gemini-1.5-pro"],
        }
        for m in presets.get(provider_key, []):
            if m:
                self.cmb_model.addItem(m)

        self.cmb_model.setCurrentIndex(0 if self.cmb_model.count() else -1)
        self.cmb_model.blockSignals(False)

    def on_llm_changed(self):
        provider = self.cmb_provider.currentData()
        model = self.cmb_model.currentText().strip()

        # nếu vừa đổi provider, refill models
        if provider != getattr(self, "provider_key", None):
            self.provider_key = provider
            self._fill_models_for_provider(provider)
            model = self.cmb_model.currentText().strip()

        try:
            self.model_name = model
            self.llm = create_llm_client(provider, model)
            self.chat_display.append(f"<i>✅ LLM: {self.cmb_provider.currentText()} | {model}</i>")
        except Exception as e:
            self.chat_display.append(f"<i>⚠️ Cannot init LLM: {e}</i>")
            # fallback
            self.provider_key = "ollama"
            self._fill_models_for_provider("ollama")
            self.llm = create_llm_client("ollama", self.cmb_model.currentText().strip())
            self.chat_display.append("<i>↩ Fallback to Ollama</i>")

    def open_llm_settings(self):
        dlg = LLMSettingsDialog(self)
        if dlg.exec():
            # reload model list + llm after saving settings
            self._fill_models_for_provider(self.cmb_provider.currentData())
            self.on_llm_changed()

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
