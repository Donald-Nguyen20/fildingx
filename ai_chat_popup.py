from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QLabel,
    QTextBrowser, QLineEdit, QPushButton, QHBoxLayout,
    QFileDialog, QMessageBox, QComboBox, QFormLayout,
    QSplitter, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication


import os
import json
import sys
import html

# cần 2 file này nằm cùng thư mục:
# - vector_retriever.py
# - llm_client.py
from vector_retriever import VectorRetriever
from llm_client import create_llm_client, PROVIDERS
from llm_config import load_llm_config, save_llm_config, get_config_path
from hud_widgets import HudPanel

def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def load_prompts_json(filename: str = "promp.json") -> dict:
    path = os.path.join(app_dir(), filename)

    # debug path
    print("[PROMPT] json path =", path)

    if not os.path.exists(path):
        print("[PROMPT] NOT FOUND:", path)
        return {}

    try:
        # ✅ utf-8-sig để ăn BOM của Windows
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        print("[PROMPT] keys =", list(data.keys()))
        return data
    except Exception as e:
        print("[PROMPT] JSON LOAD ERROR:", e)
        print("[PROMPT] PATH:", path)
        return {}


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
        cfg["ollama_host"] = self.ed_ollama_host.text().strip() or "http://localhost:11434"

        try:
            save_llm_config(cfg)
            QMessageBox.information(self, "Saved", f"Saved to:\n{get_config_path()}")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save failed", f"{type(e).__name__}: {e}\n\nPath:\n{get_config_path()}")


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
        self.resize(980, 680)
        self.setMinimumSize(1200, 650)

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        # self.setStyleSheet("""
        # QDialog {
        #     background-color: rgba(0, 0, 0, 235);
        #     border: 1px solid rgba(0, 220, 255, 90);
        #     border-radius: 14px;
        # }
        # QLabel { color: #d9ffff; }
        # QListWidget {
        #     background: rgba(0, 0, 0, 200);
        #     border: 1px solid rgba(0, 220, 255, 70);
        #     border-radius: 10px;
        #     color: #d9ffff;
        # }
        # """)


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
        # 🚫 Không cho Enter/Return kích hoạt nút Settings
        self.btn_llm_settings.setAutoDefault(False)
        self.btn_llm_settings.setDefault(False)
        self.btn_llm_settings.setFocusPolicy(Qt.NoFocus)

        self.btn_load_vs = QPushButton("Load Vector Store")
        self.btn_load_vs.clicked.connect(self.load_vector_store)
        top_bar.addWidget(self.btn_load_vs)
        # 🚫 Không cho Enter/Return kích hoạt Load Vector Store
        self.btn_load_vs.setAutoDefault(False)
        self.btn_load_vs.setDefault(False)
        self.btn_load_vs.setFocusPolicy(Qt.NoFocus)

        layout.addLayout(top_bar)

        # ===== Chat display =====
        # ===== Main area: chat (left) + sources (right) =====
        splitter = QSplitter(Qt.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(True)
        self.chat_display.setOpenLinks(True)
        self.chat_display.setAcceptRichText(True)
        self.chat_display.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard | Qt.LinksAccessibleByMouse
        )
        self.chat_display.setFocusPolicy(Qt.ClickFocus)
        left_layout.addWidget(self.chat_display, 1)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        right_layout.addWidget(QLabel("📌 Sources"))
        self.sources_list = QListWidget()
        self.sources_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.sources_list.setWordWrap(False)
        right_panel.setMinimumWidth(360)

        self.sources_list.itemClicked.connect(self.open_source_item)
        right_layout.addWidget(self.sources_list, 1)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([700, 280])


        layout.addWidget(splitter, 1)

        # keep a handle so we can add input row into the left panel
        self._left_layout = left_layout

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
        # ===== UI: White background + bigger font =====
        font = self.font()
        font.setPointSize(12)  # chữ to hơn: 12-16 tùy bạn
        self.setFont(font)

        self.chat_display.setFont(font)
        self.input_line.setFont(font)

        self.setStyleSheet("""
QDialog {
    background: #FFFFFF;
    color: #111111;
    border: 1px solid rgba(0,0,0,0.18);
    border-radius: 14px;
}

QLabel { color: #111111; }

QTextBrowser {
    background: #FFFFFF;
    color: #111111;
    border: 1px solid rgba(0,0,0,0.12);
    border-radius: 12px;
    padding: 10px;
}

QLineEdit {
    background: #FFFFFF;
    color: #111111;
    border: 1px solid rgba(0,0,0,0.18);
    border-radius: 10px;
    padding: 8px 10px;
}
QLineEdit:focus { border: 1px solid rgba(0,0,0,0.35); }

QListWidget {
    background: #FFFFFF;
    color: #111111;
    border: 1px solid rgba(0,0,0,0.12);
    border-radius: 12px;
    padding: 6px;
}
QListWidget::item {
    padding: 8px 10px;
    border-radius: 8px;
}
QListWidget::item:selected {
    background: rgba(0,0,0,0.08);
    color: #111111;
}

QPushButton {
    background: rgba(0,0,0,0.06);
    color: #111111;
    border: 1px solid rgba(0,0,0,0.14);
    border-radius: 10px;
    padding: 8px 12px;
    font-weight: 600;
}
QPushButton:hover { background: rgba(0,0,0,0.10); }
QPushButton:pressed { background: rgba(0,0,0,0.14); }
""")


        send_btn = QPushButton("Gửi")
        send_btn.clicked.connect(self.handle_user_input)

        input_layout = QHBoxLayout()
        input_layout.addWidget(self.input_line)
        input_layout.addWidget(send_btn)
        self._left_layout.addLayout(input_layout)


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
            if provider == "openrouter":
                self.chat_display.append(
                    f'<i>✅ LLM: {self.cmb_provider.currentText()} | {model} — '
                    f'<a href="https://openrouter.ai/">https://openrouter.ai/</a></i>'
                )
            elif provider == "groq":
                self.chat_display.append(
                    f'<i>✅ LLM: {self.cmb_provider.currentText()} | {model} — '
                    f'<a href="https://console.groq.com/keys">https://console.groq.com/keys</a></i>'
                )
            else:
                self.chat_display.append(
                    f"<i>✅ LLM: {self.cmb_provider.currentText()} | {model}</i>"
                )

        except Exception as e:
            msg = str(e)

            # Default text
            extra = ""

            # Nếu thiếu API key thì gợi ý link theo provider
            if (
                "Missing API key" in msg
                or ("401" in msg and "Unauthorized" in msg)
            ):

                # NOTE: tùy code của anh đang lưu provider ở biến nào
                # Ví dụ: self.provider_key hoặc self.current_provider
                provider = getattr(self, "provider_key", None) or getattr(self, "current_provider", None)

                if provider == "openrouter":
                    extra = ' — Get API key: <a href="https://openrouter.ai/">https://openrouter.ai/</a>'
                elif provider == "groq":
                    extra = ' — Get API key: <a href="https://console.groq.com/keys">https://console.groq.com/keys</a>'
                else:
                    # fallback nếu không xác định provider
                    extra = (
                        ' — Get API key: '
                        '<a href="https://openrouter.ai/">OpenRouter</a> | '
                        '<a href="https://console.groq.com/keys">Groq</a>'
                    )

            self.chat_display.append(f"<i>⚠️ Cannot init LLM: {msg}{extra}</i>")

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
    def open_source_item(self, item: QListWidgetItem):
        """Open the clicked source file in the default application."""
        path = item.data(Qt.UserRole)
        if path and os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            return
        QMessageBox.warning(self, "File not found", f"File not found:\n{path}")

    def show_below_widget(self, anchor_widget, gap: int = 8):
        """Show this popup right below the given widget (e.g., popup button)."""
        if anchor_widget is None:
            self.show()
            return

        # vị trí global của nút
        gpos = anchor_widget.mapToGlobal(anchor_widget.rect().bottomLeft())

        # canh giữa popup theo nút
        btn_center_x = anchor_widget.mapToGlobal(anchor_widget.rect().center()).x()
        x = int(btn_center_x - self.width() / 2)

        y = gpos.y() + gap


        # chống tràn màn hình
        screen = QGuiApplication.screenAt(gpos) or QGuiApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()

            # nếu vượt phải -> kéo sang trái
            if x + self.width() > area.right():
                x = max(area.left(), area.right() - self.width())

            # nếu vượt dưới -> bật lên trên nút
            if y + self.height() > area.bottom():
                top_pos = anchor_widget.mapToGlobal(anchor_widget.rect().topLeft())
                y = max(area.top(), top_pos.y() - self.height() - gap)

        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def handle_user_input(self):
        user_input = self.input_line.text().strip()
        if not user_input:
            return

        safe = html.escape(user_input).replace("\n", "<br>")
        self.chat_display.append(
            f'<span style="color:#d00000; font-weight:700;">🧑 Bạn: {safe}</span>'
        )

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
        # ==== Load prompt template from promp.json ====
        prompts = load_prompts_json("promp.json")
        tpl = prompts.get("sop_prompt")

        if not tpl:
            self.chat_display.append("⚠️ Không đọc được promp.json hoặc thiếu key 'sop_prompt' → dùng prompt mặc định.")
            self.chat_display.append(f"<i>Path: {os.path.join(app_dir(), 'promp.json')}</i>")

            tpl = """You are a thermal power plant operation SOP assistant.

STRICT RULES:
- Answer ONLY using the CONTEXT below. Do NOT use general knowledge.
- If the CONTEXT does not contain the answer, reply exactly: NOT FOUND IN CONTEXT.
- Preserve technical numbers/limits exactly (e.g., 110%, 1 hour, etc.).
- Do NOT mention chunk id, score, retrieval, vector, embeddings, or sources.
- Do NOT write long paragraphs.
- Split multiple points into separate numbered items.
- Each numbered item must contain ONE action or ONE rule only.
- If you need sub-items, use "-" under the numbered item.
- Each numbered item MUST be on its own line.
- Do NOT put multiple numbered items in one paragraph.
- Leave a blank line between sections 1/2/3.
- If the question is Vietnamese, answer in Vietnamese (keep the same level of detail as English). Otherwise, answer in English.

CONTEXT:
<<<
{context}
>>>

QUESTION:
{user_input}

MANDATORY OUTPUT FORMAT:
A) Actions
1. ...

B) Monitoring
1. ...

C) Warnings
1. ...
"""

        prompt = tpl.format(context=context, user_input=user_input)


        try:
            answer = self.llm.generate(prompt)
        except Exception as e:
            answer = f"(LLM error) {e}"

        self.chat_display.append(f"🤖 Trợ lý: {answer}")

        # (Giữ UI như cũ) — chỉ append nguồn tóm tắt vào chat
        # ===== Sources panel (right) =====
        self.sources_list.clear()
        for i, r in enumerate(results, start=1):
            title = f"[{i}] {r.get('rel_path') or r.get('file_name')}"
            item = QListWidgetItem(title)
            item.setToolTip(r.get("abs_path", ""))
            item.setData(Qt.UserRole, r.get("abs_path", ""))
            self.sources_list.addItem(item)

        
