from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QLabel,
    QTextBrowser, QLineEdit, QPushButton, QHBoxLayout,
    QFileDialog, QMessageBox, QComboBox, QFormLayout,
    QSplitter, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication

from PySide6.QtCore import QEvent
import os
import json
import sys
import html
import re

# cần 2 file này nằm cùng thư mục:
# - vector_retriever.py
# - llm_client.py
from vector_retriever import VectorRetriever
from llm_client import create_llm_client, PROVIDERS
from llm_config import load_llm_config, save_llm_config, get_config_path
from hud_widgets import HudPanel
from Rag_funtions.clear_history import install_clear_history_button, clear_popup_history
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

        self.ed_gemini = QLineEdit(cfg.get("gemini_api_key",""))
        self.ed_gemini.setEchoMode(QLineEdit.Password)
        self.ed_gemini.setPlaceholderText("AIza...")
        form.addRow("Gemini API key:", self.ed_gemini)

        self.cbo_embed_provider = QComboBox()
        self.cbo_embed_provider.addItem("Local (sentence-transformers)", "local")
        self.cbo_embed_provider.addItem("Gemini text-embedding-004 (cloud)", "gemini")
        current_provider = cfg.get("embedding_provider", "local")
        idx = self.cbo_embed_provider.findData(current_provider)
        if idx >= 0:
            self.cbo_embed_provider.setCurrentIndex(idx)
        form.addRow("Embedding provider:", self.cbo_embed_provider)

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
        cfg["embedding_provider"] = self.cbo_embed_provider.currentData() or "local"
        cfg["ollama_host"] = self.ed_ollama_host.text().strip() or "http://localhost:11434"

        try:
            save_llm_config(cfg)
            QMessageBox.information(self, "Saved", f"Saved to:\n{get_config_path()}")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save failed", f"{type(e).__name__}: {e}\n\nPath:\n{get_config_path()}")
def extract_cited_indices(answer: str, max_k: int) -> list[int]:
    """
    Parse citations like [1], [2]... from LLM answer.
    Return 0-based indices that map to `results`.
    """
    nums = re.findall(r"\[(\d+)\]", answer)
    idx = []
    for s in nums:
        try:
            n = int(s)
        except ValueError:
            continue
        if 1 <= n <= max_k:
            idx.append(n - 1)  # 0-based

    # unique but keep order
    seen = set()
    ordered = []
    for i in idx:
        if i not in seen:
            seen.add(i)
            ordered.append(i)
    return ordered
def safe_braces(s: str) -> str:
    return s.replace("{", "{{").replace("}", "}}")


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

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint )


        
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
        top_bar.addWidget(QLabel("💬:"))
        top_bar.addStretch()
        # Provider combobox
        self.cmb_provider = QComboBox()
        # Nút Clear ngay cạnh chữ Chat
        btn_clear = install_clear_history_button(self, top_bar, insert_at=1, confirm=False)

        # (Tuỳ chọn) sau khi clear thì hiện lại dòng trạng thái
        def _after_clear():
            clear_popup_history(self, ask_confirm=False)
            self.chat_display.append("🤖 Chat bot: Cleared history. ")
        btn_clear.clicked.disconnect()
        btn_clear.clicked.connect(_after_clear)
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
        self.chat_display.append("🤖 Chat bot: RAG đang ở chế độ chờ (chưa load Vector Store).")

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


    def event(self, e):
        # ✅ Mở tác vụ khác / mất focus: KHÔNG minimize, KHÔNG hide
        if e.type() == QEvent.WindowDeactivate:
            return False  # để Qt xử lý bình thường, popup vẫn giữ nguyên trạng thái
        return super().event(e)


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
        # TOGGLE: nếu đang hiện (kể cả minimized) thì ẩn; nếu đang ẩn thì hiện
        if self.isVisible() and not self.isMinimized():
            self.hide()
            return

        # nếu đang minimized mà bấm nút -> restore lên lại
        if self.isMinimized():
            self.showNormal()

        if anchor_widget is None:
            self.show()
            self.raise_()
            self.activateWindow()
            return

        gpos = anchor_widget.mapToGlobal(anchor_widget.rect().bottomLeft())
        btn_center_x = anchor_widget.mapToGlobal(anchor_widget.rect().center()).x()
        x = int(btn_center_x - self.width() / 2)
        y = gpos.y() + gap

        screen = QGuiApplication.screenAt(gpos) or QGuiApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            if x + self.width() > area.right():
                x = max(area.left(), area.right() - self.width())
            if y + self.height() > area.bottom():
                top_pos = anchor_widget.mapToGlobal(anchor_widget.rect().topLeft())
                y = max(area.top(), top_pos.y() - self.height() - gap)

        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input_line.setFocus(Qt.ActiveWindowFocusReason)


    def handle_user_input(self):
        user_input = self.input_line.text().strip()
        if not user_input:
            return

        safe = html.escape(user_input).replace("\n", "<br>")
        self.chat_display.append(
            f'<span style="color:#d00000; font-weight:700;">🧑 You: {safe}</span>'
        )

        self.input_line.clear()

        # Nếu chưa load store → nhắc user load
        if self.retriever is None:
            self.chat_display.append("🤖 Chat bot: Please click 'Load Vector Store' before that.")
            return

        # ==== RAG Retrieve ====
        results = self.retriever.search(user_input, top_k=12)
        if not results:
            self.chat_display.append("🤖 Chat bot: I don't research any things related in Vector Store.")
            return

        # Ghép CONTEXT (chunk-based: KHÔNG cắt ngang chunk)
        MAX_CTX_CHARS = 8000  # giữ ngưỡng cũ cho model 3B
        PER_CHUNK_CAP = 1600  # (tuỳ chọn) giới hạn mỗi chunk để không 1 chunk nuốt hết budget

        ctx_blocks = []
        total = 0

        for i, r in enumerate(results, start=1):
            text = r["text"]
            if len(text) > PER_CHUNK_CAP:
                text = text[:PER_CHUNK_CAP] + " ..."

            block = f"[{i}] {r['file_name']} | chunk {r['chunk_id']} | score={r['score']:.3f}\n{text}\n"
            blen = len(block)

            # nếu block đầu tiên quá dài thì cắt nhẹ (hiếm)
            if not ctx_blocks and blen > MAX_CTX_CHARS:
                ctx_blocks.append(block[:MAX_CTX_CHARS])
                break

            # nếu thêm block sẽ vượt ngưỡng -> dừng (không cắt ngang chunk)
            if total + blen > MAX_CTX_CHARS:
                break

            ctx_blocks.append(block)
            total += blen

        context = "\n\n".join(ctx_blocks)

        # ==== Load prompt template from promp.json ====
        prompts = load_prompts_json("promp.json")
        tpl = prompts.get("sop_prompt")

        if not tpl:
            self.chat_display.append("⚠️ Không đọc được promp.json hoặc thiếu key 'sop_prompt' → dùng prompt mặc định.")
            self.chat_display.append(f"<i>Path: {os.path.join(app_dir(), 'promp.json')}</i>")

            tpl = r"""You are a Thermal Power Plant Operation SOP Assistant.

YOUR ROLE:
- You act strictly as a SOP reader and SOP executor.
- You do NOT act as an engineer, advisor, or instructor.
- You are NOT allowed to use engineering judgment, experience, or general knowledge.

ABSOLUTE RULES (NO EXCEPTIONS):
1. Answer ONLY using the CONTENT explicitly written in the CONTEXT section.
2. Do NOT use any external knowledge, assumptions, logic inference, or intuition.
3. Do NOT infer missing steps, implied actions, or unstated conditions.
4. If ANY required information is missing, incomplete, or unclear, reply EXACTLY:
   NOT FOUND IN CONTEXT.
5. If the CONTEXT contains conflicting instructions, limits, values, or steps, reply EXACTLY:
   CONFLICT IN CONTEXT.

SOP PRESERVATION RULES:
- Preserve ALL technical wording exactly as written in the CONTEXT.
- Preserve equipment names, tags, abbreviations, symbols, and units exactly.
- Preserve all numerical values, limits, durations, percentages, and setpoints exactly.
- Do NOT paraphrase, simplify, summarize, or reword SOP instructions.
- Do NOT translate technical terms unless the CONTEXT already contains the translation.

REASONING RESTRICTIONS:
- Do NOT explain background theory.
- Do NOT justify actions.
- Do NOT add causes, effects, notes, or explanations unless explicitly written in the CONTEXT.

FORMAT RULES (MANDATORY):
- Answer ONLY with a numbered list.
- Each numbered item MUST contain ONLY ONE action OR ONE rule.
- Each numbered item MUST be on its own line.
- If sub-actions are explicitly written in the CONTEXT, use '-' under the same numbered item.
- Do NOT combine multiple actions into one numbered item.
- Do NOT write introductory or concluding sentences.

LANGUAGE RULE:
- If the QUESTION is written in Vietnamese, answer in Vietnamese.
- Otherwise, answer in English.
- Keep the same technical level and wording style as the CONTEXT.

EXHAUSTIVE LISTING RULES (ADDITIONAL):
- When the QUESTION asks to "talk about", "describe", "list", or "explain" a subject,
  you MUST extract ALL distinct points explicitly written in the CONTEXT related to that subject.
- Do NOT stop after listing a few representative items.
- Continue listing numbered items until ALL relevant statements in the CONTEXT are exhausted.
- Each sentence or clause in the CONTEXT that describes a different aspect MUST be written as a separate numbered item.
- Do NOT merge multiple aspects into a single numbered item.

CITATION RULES (MANDATORY):
- Every numbered item MUST end with at least one citation in the format [n].
- [n] refers to the chunk number shown in the CONTEXT section.
- Use ONLY citation numbers that exist in the CONTEXT.
- Do NOT invent, guess, or reuse citation numbers incorrectly.
- If a numbered item cannot be supported by any chunk in the CONTEXT, reply EXACTLY:
  NOT FOUND IN CONTEXT.

CONTEXT:
<<<
{context}
>>>

QUESTION:
{user_input}

MANDATORY OUTPUT FORMAT:
1. ... [n]
2. ... [n]
3. ... [n]
"""


        prompt = tpl.format(
    context=safe_braces(context),
    user_input=safe_braces(user_input),
)



        try:
            answer = self.llm.generate(prompt)
        except Exception as e:
            answer = f"(LLM error) {e}"

        safe_ans = html.escape(answer).replace("\n", "<br>")
        self.chat_display.append(
            f'<span style="color:#111111; font-weight:400;">🤖 Chat bot: {safe_ans}</span>'
        )


        # (Giữ UI như cũ) — chỉ append nguồn tóm tắt vào chat
        # ===== Sources panel (right) =====
        # ===== Sources panel (right) =====
        # Show ONLY sources that are actually cited in the answer.
        cited_idx = extract_cited_indices(answer, max_k=len(results))

        self.sources_list.clear()

        if cited_idx:
            # Keep original numbers so they match citations in the answer: [n]
            for idx in cited_idx:
                r = results[idx]
                n = idx + 1  # original chunk number
                title = f"[{n}] {r.get('rel_path') or r.get('file_name')}"
                item = QListWidgetItem(title)
                item.setToolTip(r.get("abs_path", ""))
                item.setData(Qt.UserRole, r.get("abs_path", ""))
                self.sources_list.addItem(item)
        else:
            # Fallback: if the model forgot to cite, show a small retrieved set (debug-friendly)
            for i, r in enumerate(results[:5], start=1):
                title = f"[{i}] {r.get('rel_path') or r.get('file_name')}"
                item = QListWidgetItem(title)
                item.setToolTip(r.get("abs_path", ""))
                item.setData(Qt.UserRole, r.get("abs_path", ""))
                self.sources_list.addItem(item)


