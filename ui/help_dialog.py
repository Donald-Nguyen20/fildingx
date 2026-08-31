# ui/help_dialog.py
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QTextEdit
from PySide6.QtCore import Qt

try:
    # HUD theme (nếu có)
    from ui.hud_widgets import qss_hud_metal_header_feel, qss_white_results
except Exception:
    qss_hud_metal_header_feel = None
    qss_white_results = None


class HelpDialog(QDialog):
    """
    User Guide – mở bằng F1
    Không có button, không có menu
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("User Guide")
        self.setGeometry(520, 160, 980, 680)
        self.setModal(True)

        # Apply HUD theme nếu có
        try:
            if qss_hud_metal_header_feel and qss_white_results:
                self.setStyleSheet(qss_hud_metal_header_feel() + qss_white_results())
        except Exception:
            pass

        layout = QHBoxLayout(self)

        # ===== LEFT: TOC =====
        self.toc = QListWidget()
        self.toc.setFixedWidth(320)
        self.toc.setFocusPolicy(Qt.NoFocus)

        # ===== RIGHT: CONTENT =====
        self.viewer = QTextEdit()
        self.viewer.setReadOnly(True)
        self.viewer.setFocusPolicy(Qt.NoFocus)

        layout.addWidget(self.toc)
        layout.addWidget(self.viewer, 1)

        # ===== CONTENT =====
        self.pages = {
            "Overview": self.page_overview(),
            "Quick Start (5 phút)": self.page_quick_start(),
            "Search by Name": self.page_search_by_name(),
            "Advanced Query (% / * / @ / synonyms)": self.page_advanced_query(),
            "Result Table (cột & thao tác)": self.page_results_table(),
            "Claude Assistant (AI Co-Pilot)": self.page_claude_assistant(),
            "Containers (nhóm công việc)": self.page_containers(),
            "Preview & Notes (PDF + ghi chú AI)": self.page_notes(),
            "Search Duplicates (file trùng)": self.page_duplicates(),
            "Batch Rename (đổi tên hàng loạt)": self.page_batch_rename(),
            "DB Search (Index Search — SQLite)": self.page_index_search(),
            "Tools / EXE Launcher": self.page_tools_exe(),
            "NotebookLM & Dịch thuật": self.page_notebooklm(),
            "Shortcuts & Mouse Actions": self.page_shortcuts(),
            "Workflow Templates (Best practice)": self.page_workflow_templates(),
            "Troubleshooting": self.page_troubleshooting(),
            "Prompt (lệnh ẩn)": self.page_prompt(),
        }

        self.toc.addItems(self.pages.keys())
        self.toc.currentTextChanged.connect(self.on_select)
        self.toc.setCurrentRow(0)

    # ================= EVENTS =================
    def on_select(self, key: str):
        self.viewer.setHtml(self.pages.get(key, "<h3>No content</h3>"))

    # ================= HTML HELPERS =================
    @staticmethod
    def _base_style() -> str:
        # Dùng CSS nhẹ để đọc dễ hơn (QTextEdit HTML support basic)
        return """
        <style>
            body { font-family: Segoe UI, Arial; font-size: 13px; line-height: 1.45; }
            h2 { margin: 12px 0 6px 0; }
            h3 { margin: 10px 0 6px 0; }
            .hint { padding: 8px 10px; border-left: 4px solid #888; background: rgba(128,128,128,0.08); margin: 8px 0; }
            .warn { padding: 8px 10px; border-left: 4px solid #c67; background: rgba(200,80,80,0.08); margin: 8px 0; }
            .ok { padding: 8px 10px; border-left: 4px solid #6a8; background: rgba(80,200,120,0.08); margin: 8px 0; }
            code { background: rgba(0,0,0,0.06); padding: 1px 4px; border-radius: 4px; }
            .kbd { border: 1px solid rgba(0,0,0,0.25); padding: 1px 6px; border-radius: 4px; background: rgba(0,0,0,0.04); }
            table { border-collapse: collapse; width: 100%; margin: 8px 0; }
            th, td { border: 1px solid rgba(0,0,0,0.18); padding: 6px 8px; vertical-align: top; }
            th { background: rgba(0,0,0,0.05); }
            ul { margin: 6px 0 10px 18px; }
            ol { margin: 6px 0 10px 18px; }
        </style>
        """

    # ================= PAGES =================
    def page_overview(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>File Search & Management</h2>
        <p>Ứng dụng hỗ trợ: <b>tìm file kỹ thuật</b>, <b>gom nhóm</b> theo công việc, <b>ghi chú</b> theo file, <b>phát hiện file trùng</b>, và <b>tra cứu chỉ mục SQLite</b>.</p>

        <table>
          <tr><th>Module</th><th>Chức năng chính</th><th>Dùng khi nào?</th></tr>
          <tr>
            <td><b>Search by Name</b></td>
            <td>Tìm theo tên file + query nâng cao</td>
            <td>Khi nhớ "một phần tên", mã KKS, tag, số hiệu bản vẽ…</td>
          </tr>
          <tr>
            <td><b>Containers</b></td>
            <td>Gom file theo dự án/ca/khoản mục</td>
            <td>Tạo "bộ hồ sơ" cho từng công việc (SOP, bản vẽ, báo cáo…)</td>
          </tr>
          <tr>
            <td><b>📄 Preview & Notes</b></td>
            <td>Xem PDF trong app + ghi chú (text/ảnh), tóm tắt & mind map bằng NotebookLM</td>
            <td>Lưu nhanh insight/khuyến nghị khi mở file PDF</td>
          </tr>
          <tr>
            <td><b>Duplicates</b></td>
            <td>Phát hiện file trùng nội dung theo nhóm</td>
            <td>Dọn thư mục rác, tránh trùng bản vẽ/bản scan</td>
          </tr>
          <tr>
            <td><b>Index Search</b></td>
            <td>Tìm theo SQLite database (name/content tùy DB)</td>
            <td>Khi đã có DB index, cần tìm rất nhanh & chính xác</td>
          </tr>
          <tr>
            <td><b>Tools / EXE</b></td>
            <td>Gắn phần mềm/EXE hay dùng vào giao diện</td>
            <td>Mở tool theo workflow (CAD, PDF, DCS viewer, …)</td>
          </tr>
          <tr>
            <td><b>NotebookLM</b></td>
            <td>Chat hỏi tài liệu qua Google NotebookLM, tóm tắt file trong Notes</td>
            <td>Hỏi "theo tài liệu kỹ thuật" có trích nguồn, tóm tắt nhanh PDF</td>
          </tr>
          <tr>
            <td><b>🤖 Claude</b></td>
            <td>AI Co-Pilot: hỏi đáp DB tài liệu, chẩn đoán sự cố (cây nguyên nhân + bằng chứng), sinh báo cáo KV-OP tự động</td>
            <td>Khi cần tra cứu nhanh + phân tích nguyên nhân gốc + soạn báo cáo vận hành</td>
          </tr>
          <tr>
            <td><b>🎨 Studio</b></td>
            <td>Generate Mind Map, Briefing Doc, Flashcards, Quiz, Audio… từ notebook; lưu/xem Notes</td>
            <td>Tạo tài liệu học, sơ đồ tư duy, quiz từ bộ tài liệu kỹ thuật</td>
          </tr>
          <tr>
            <td><b>Vision AI</b></td>
            <td>Phân tích bản vẽ kỹ thuật (P&amp;ID, FBD, sơ đồ) bằng LLM Vision khi Add File</td>
            <td>Khi PDF chứa bản vẽ thuần ảnh, không có text layer</td>
          </tr>
          <tr>
            <td><b>Dịch thuật</b></td>
            <td>Dịch nội dung Notes sang tiếng Việt qua LLM API</td>
            <td>Khi cần đọc hiểu tài liệu kỹ thuật tiếng Anh</td>
          </tr>
        </table>

        <div class="ok"><b>Phím tắt quan trọng:</b> <span class="kbd">F1</span> mở User Guide.</div>
        </body>
        """

    def page_quick_start(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>Quick Start (5 phút)</h2>

        <h3>1) Tìm file nhanh</h3>
        <ol>
          <li><b>Browse folder</b> → chọn thư mục gốc (ví dụ: Documents / SOP / Drawings).</li>
          <li>Nhập keyword → bấm <b>Search</b>.</li>
          <li>Double-click kết quả để mở file.</li>
        </ol>

        <h3>2) Gom file thành 1 bộ hồ sơ (Container)</h3>
        <ol>
          <li>Nhập tên container (VD: <code>UAT Trip 2026-01</code>) → <b>Create</b>.</li>
          <li>Chọn file ở kết quả search → <b>Add File</b> vào container.</li>
          <li>Mở container để xem lại danh sách file bất cứ lúc nào.</li>
        </ol>

        <h3>3) Ghi chú theo file (PDF)</h3>
        <ol>
          <li>Chọn 1 file PDF → bấm <b>📄 Preview</b> ở sidebar phải để mở panel xem trước.</li>
          <li>Chuyển sang tab <b>📝 Notes</b>: ghi text + chèn ảnh (ảnh hiện trường / ảnh đồ thị).</li>
          <li><b>💾 Save</b> để lưu (app cũng tự lưu khi bạn chuyển file khác).</li>
        </ol>

        <h3>4) Dọn trùng</h3>
        <ol>
          <li>Chọn folder → bấm <b>Search Duplicates</b>.</li>
          <li>App hiển thị theo GROUP các file giống nội dung.</li>
          <li>Mở từng file để quyết định giữ/xóa (app không tự xóa).</li>
        </ol>

        <div class="hint">
          <b>Mẹo:</b> Nếu thư mục rất lớn, hãy thử scan theo từng tầng (năm/tháng/dự án) để nhanh hơn.
        </div>
        </body>
        """

    def page_search_by_name(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>Search by Name</h2>

        <h3>Cách dùng cơ bản</h3>
        <ol>
          <li><b>Browse folder</b> để chọn thư mục cần tìm.</li>
          <li>Nhập keyword vào ô tìm kiếm.</li>
          <li>Bấm <b>Search</b> → kết quả hiện trong bảng.</li>
        </ol>

        <h3>Gợi ý keyword hiệu quả (dành cho file kỹ thuật)</h3>
        <ul>
          <li>Mã thiết bị / KKS / tag: <code>21G</code>, <code>87G</code>, <code>GSUT</code>, <code>UAT2A</code>…</li>
          <li>Mã bản vẽ: <code>SLD</code>, <code>Wiring</code>, <code>GA</code>, <code>P&ID</code>…</li>
          <li>Tên hạng mục: <code>Generator</code>, <code>Transformer</code>, <code>Boiler</code>, <code>Turbine</code>…</li>
          <li>Từ khóa ca/kế hoạch: <code>trip</code>, <code>shutdown</code>, <code>commissioning</code>, <code>maintenance</code>…</li>
        </ul>

        <div class="hint">
          <b>Mẹo:</b> Nếu bạn chỉ nhớ "na ná" tên file, hãy dùng <b>fuzzy</b> (xem mục Advanced Query).
        </div>
        </body>
        """

    def page_advanced_query(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>Advanced Query (% / * / @ / synonyms)</h2>

        <h3>1) Wildcard bằng dấu *</h3>
        <p>Dùng <code>*</code> để tìm file chứa nhiều phần theo thứ tự linh hoạt.</p>
        <ul>
          <li><code>UAT*Trip</code> → tên file có "UAT" và sau đó có "Trip".</li>
          <li><code>Trip*UAT</code> → đảo thứ tự.</li>
          <li><b>Gợi ý:</b> dùng khi file có format tên dài: "system_subsystem_topic_date".</li>
        </ul>

        <h3>2) Query kiểu A % B (include/exclude)</h3>
        <p>Dạng này rất mạnh khi bạn muốn <b>chứa A nhưng loại B</b>.</p>
        <div class="ok">
          <b>Ví dụ:</b><br/>
          <code>UAT % drawing</code> → tìm các file có "UAT" nhưng <b>không</b> chứa "drawing".<br/>
          <code>Generator % old</code> → chứa "Generator", loại các file có "old".
        </div>
        <div class="hint">
          <b>Lưu ý:</b> Dấu <code>%</code> là "lọc loại trừ", cực hợp để tránh file backup: <code>report % backup</code>, <code>P&ID % temp</code>.
        </div>

        <h3>3) Fuzzy search bằng tiền tố @</h3>
        <p>Dùng <code>@keyword</code> để tìm "gần đúng" (khi bạn nhớ sai chính tả, hoặc file bị viết tắt).</p>
        <ul>
          <li><code>@deareator</code> → vẫn có thể ra "deaerator".</li>
          <li><code>@vibration</code> → ra cả "vib", "vibra", "vibration".</li>
        </ul>

        <h3>4) Tìm Folder bằng tiền tố folder:</h3>
        <p>Dùng <code>folder:tên</code> để tìm <b>thư mục</b> thay vì file.</p>
        <ul>
          <li><code>folder:boiler</code> → tìm tất cả thư mục có tên chứa "boiler".</li>
          <li><code>folder:UAT*trip</code> → thư mục chứa cả "UAT" và "trip" (kết hợp với <code>*</code>).</li>
          <li>Kết quả hiển thị với icon 📁, cột TYPE = <b>DIR</b>, không có SIZE.</li>
          <li>Double-click → mở thư mục trong Explorer.</li>
        </ul>
        <div class="ok">
          <b>Ví dụ thực tế:</b><br/>
          <code>folder:Commissioning</code> → tìm nhanh tất cả thư mục Commissioning trong folder đang chọn.<br/>
          <code>folder:2024*boiler</code> → thư mục có năm 2024 và chứa "boiler".
        </div>

        <h3>5) Synonyms (từ đồng nghĩa) & chỉnh sửa</h3>
        <p>App có file <code>synonyms.json</code> để mở rộng từ khóa. Bạn có thể chỉnh từ đồng nghĩa trong UI.</p>
        <ul>
          <li>Ví dụ: "UAT" đồng nghĩa "Unit Aux Transformer".</li>
          <li>Ví dụ: "GSU" đồng nghĩa "GSUT", "Generator Step-up Transformer".</li>
        </ul>

        <div class="warn">
          <b>Chú ý:</b> Fuzzy + synonyms mạnh nhưng có thể ra nhiều kết quả. Hãy kết hợp thêm <code>%</code> để loại bớt.
        </div>
        </body>
        """

    def page_results_table(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>Result Table (cột & thao tác)</h2>

        <h3>Các cột trong kết quả</h3>
        <table>
          <tr><th>Cột</th><th>Ý nghĩa</th><th>Dùng để làm gì?</th></tr>
          <tr><td><b>FILE NAME</b></td><td>Tên file</td><td>Nhận dạng nhanh, copy name</td></tr>
          <tr><td><b>DATE MODIFIED</b></td><td>Ngày sửa gần nhất</td><td>Chọn bản mới nhất/đúng phiên bản</td></tr>
          <tr><td><b>TYPE</b></td><td>Định dạng (.pdf/.docx/.dwg…)</td><td>Lọc theo loại tài liệu</td></tr>
          <tr><td><b>SIZE (MB)</b></td><td>Dung lượng</td><td>Phân biệt bản scan nặng vs bản text nhẹ</td></tr>
          <tr><td><b>PATH</b></td><td>Đường dẫn đầy đủ</td><td>Mở folder, copy path, quản lý lưu trữ</td></tr>
        </table>

        <h3>Thao tác phổ biến</h3>
        <ul>
          <li><b>Double-click</b> → mở file.</li>
          <li><b>Right-click</b> (nếu app có menu ngữ cảnh) → mở folder / copy path / thao tác nhanh.</li>
          <li><b>Copy</b> → copy file name hoặc full path để dán sang email/biên bản.</li>
        </ul>

        <h3>🤖 Group — AI tự phân nhóm kết quả</h3>
        <p>Sau khi search ra kết quả, nút <b>🤖 Group</b> (cạnh ô search) sẽ bật lên (enable).
        Bấm để nhờ AI (LLM) tự động <b>phân nhóm kết quả theo loại tài liệu</b>
        (VD: gom riêng bản vẽ, manual, báo cáo, datasheet…) — hữu ích khi kết quả trả về quá nhiều và lẫn lộn nhiều loại.</p>
        <div class="hint">
          <b>Lưu ý:</b> Chức năng này gọi LLM (provider cấu hình ở NotebookLM ⚙ Settings), có thể mất vài giây và tốn 1 lượt gọi API.
        </div>

        <div class="hint">
          <b>Mẹo:</b> Khi có nhiều bản, hãy ưu tiên theo <b>Date Modified</b> và kiểm tra nội dung nhanh trước khi dùng.
        </div>
        </body>
        """

    def page_claude_assistant(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>Claude Assistant (AI Co-Pilot)</h2>
        <p>Tab <b>🤖 Claude</b> là trợ lý AI chạy bằng Claude Code SDK, có thể đọc database tài liệu kỹ thuật
        (schema <code>chunks_fts</code> theo <code>CLAUDE.md</code> — khác với DB đơn giản của tab DB Search),
        chẩn đoán sự cố và tự soạn báo cáo vận hành.</p>

        <h3>Đăng nhập (chỉ cần 1 lần)</h3>
        <ul>
          <li>Bấm <b>🔑 Login</b> → mở cửa sổ console chạy <code>claude login</code>.</li>
          <li>Đăng nhập xong, tab Claude dùng được ngay, không cần lặp lại mỗi lần mở app.</li>
        </ul>

        <h3>Chọn Database tài liệu</h3>
        <ul>
          <li><b>📂 Select DB</b>: chọn file <code>.db/.sqlite</code> chứa tài liệu kỹ thuật đã index (bảng <code>files</code>/<code>chunks</code> + FTS5).</li>
          <li>App tự nhớ đường dẫn DB đã chọn (lưu vào <code>claude_db.json</code>) — mở app lần sau không cần chọn lại.</li>
          <li><b>✕</b>: bỏ chọn DB hiện tại.</li>
          <li><b>System:</b> ô nhập system prompt tùy chỉnh (VD: "Answer in Vietnamese").</li>
        </ul>

        <h3>7 chế độ thao tác (nút bên trái, dưới orb)</h3>
        <table>
          <tr><th>Nút</th><th>Chế độ</th><th>Dùng khi nào?</th></tr>
          <tr><td>💬 <b>Ask</b></td><td>Chat tự do</td><td>Hỏi bất kỳ câu hỏi kỹ thuật nào</td></tr>
          <tr><td>🔍 <b>Find Docs</b></td><td>Tìm trong DB tài liệu</td><td>Cần tra cứu nhanh nội dung/tài liệu liên quan 1 chủ đề</td></tr>
          <tr><td>📝 <b>Make Report</b></td><td>Soạn báo cáo vận hành</td><td>Cần bản nháp báo cáo về 1 chủ đề/sự kiện</td></tr>
          <tr><td>🔬 <b>Diagnose</b></td><td>Chẩn đoán sự cố (Co-Pilot)</td><td>Có triệu chứng bất thường, cần tìm nguyên nhân gốc</td></tr>
          <tr><td>📇 <b>Quick Card</b></td><td>Thẻ tra cứu nhanh thiết bị</td><td>Cần tóm tắt thông số/thông tin 1 thiết bị</td></tr>
          <tr><td>🔧 <b>Work Pack</b></td><td>Gói chuẩn bị công việc</td><td>Sắp làm 1 công việc (VD thay bearing IDF-A), cần gom đủ procedure + drawing + setpoint + safety</td></tr>
          <tr><td>📈 <b>Trend Data</b></td><td>Chẩn đoán kèm số liệu trend/log</td><td>Có bảng số liệu DCS/log sheet, cần phân tích và đối chiếu setpoint trước khi tìm nguyên nhân</td></tr>
        </table>
        <div class="warn">
          <b>Lưu ý:</b> Các chế độ <b>Diagnose</b>, <b>Quick Card</b>, <b>Work Pack</b>, <b>Trend Data</b>
          cần đã chọn DB trước, nếu chưa app sẽ nhắc chọn.
        </div>

        <h3>🔬 Diagnose — Cây chẩn đoán sự cố</h3>
        <ol>
          <li>Bấm <b>🔬 Diagnose</b> → nhập mô tả triệu chứng (VD: "IDF bearing vibration high") → Enter.</li>
          <li>Panel bên phải hiện <b>cây nguyên nhân</b> (Cause) xếp hạng theo <b>% confidence</b>
              (xanh = tin cậy cao, vàng = trung bình, đỏ = thấp).</li>
          <li>Click 1 nguyên nhân → xem <b>bằng chứng</b> (trích đoạn tài liệu, doc number, section) bên phải;
              click bằng chứng để mở file nguồn tương ứng.</li>
          <li>Dropdown lịch sử (góc trên) cho phép mở lại các lần chẩn đoán trước đó.</li>
          <li>Bấm <b>📝 Generate KV-OP Report</b> → app tự soạn báo cáo <code>.docx</code> theo format chuẩn
              (Introduction / Abnormal Status / Analysis / Suggestion / Execution Plan / Conclusion)
              từ chính cây nguyên nhân + bằng chứng đang hiển thị.</li>
        </ol>
        <div class="ok">
          <b>File báo cáo lưu ở đâu?</b> Thư mục <code>reports/</code> nằm <b>cạnh file chạy của app</b>
          (cạnh .exe khi đã đóng gói, hoặc cạnh <code>Finding8.py</code> khi chạy từ source).
        </div>

        <h3>🔧 Work Pack — Gói chuẩn bị công việc</h3>
        <ol>
          <li>Bấm <b>🔧 Work Pack</b> → mô tả công việc (VD: "Replace IDF-A bearing") → Enter.</li>
          <li>Claude tự query DB gom: <b>Safety precautions</b>, <b>Procedures</b> (doc number thật),
              <b>Drawings</b>, <b>Alarm/Trip setpoints</b> cần lưu ý, <b>Tools & Materials</b>,
              <b>Spare parts</b>, trình tự chính và <b>References</b>.</li>
          <li>App tự render file <code>.docx</code> vào thư mục <code>reports/</code> và mở lên —
              dùng ngay cho họp toolbox / chuẩn bị hiện trường.</li>
        </ol>

        <h3>📈 Trend Data — Chẩn đoán kèm số liệu</h3>
        <ol>
          <li>Bấm <b>📈 Trend Data</b> → dialog hiện ra: nhập <b>triệu chứng ngắn gọn</b> +
              <b>dán bảng số liệu</b> (copy từ trend DCS, log sheet Excel — giữ nguyên cột/tab).</li>
          <li>Bấm <b>🔬 Analyze</b>: Claude phân tích chuỗi số liệu (xu hướng, tốc độ thay đổi,
              thời điểm bất thường), <b>đối chiếu giá trị đo với alarm/trip setpoint trong DB</b>,
              rồi chạy tiếp quy trình chẩn đoán như chế độ Diagnose.</li>
          <li>Kết quả hiện trên <b>panel cây nguyên nhân</b> — nhận định số liệu được đưa vào
              rationale của từng nguyên nhân; từ đây bấm <b>Generate KV-OP Report</b> như bình thường
              (số liệu sẽ vào phần Abnormal Status của báo cáo).</li>
        </ol>

        <h3>Orb (JARVIS) — phản ánh trạng thái thật</h3>
        <p>Quả cầu neural bên trái <b>không chỉ để trang trí</b> — nó phản ánh đúng trạng thái xử lý thật của app:</p>
        <ul>
          <li>Nghỉ (REST) khi không có tác vụ.</li>
          <li>Sáng/nhịp nhanh hơn khi đang xử lý hoặc đang stream câu trả lời (cường độ tăng theo tốc độ ký tự trả về).</li>
          <li>Đổi màu cảnh báo khi có lỗi.</li>
        </ul>

        <h3>Chat panel (bên phải)</h3>
        <ul>
          <li><b>📤 Send</b> (hoặc Enter): gửi câu hỏi/yêu cầu.</li>
          <li><b>🗑</b> (nút cạnh Send): xóa toàn bộ nội dung chat hiện tại.</li>
          <li>Câu trả lời hiển thị dạng streaming (chữ chạy dần), có thể kèm trích dẫn <code>Doc:</code>/<code>Section:</code> khi lấy từ DB.</li>
        </ul>
        </body>
        """

    def page_containers(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>Containers (nhóm công việc)</h2>
        <p>Containers giúp bạn gom file thành "bộ hồ sơ" theo công việc – giống playlist nhưng dành cho tài liệu kỹ thuật.</p>

        <h3>Tạo container</h3>
        <ol>
          <li>Nhập tên container (VD: <code>Boiler Metal Temp – Mar 2025</code>).</li>
          <li>Bấm <b>Create</b>.</li>
        </ol>

        <h3>Thêm file vào container</h3>
        <ol>
          <li>Tìm file bằng Search.</li>
          <li>Chọn file trong kết quả.</li>
          <li>Bấm <b>Add File</b> → file được đưa vào container đang chọn.</li>
        </ol>

        <h3>Xem & quản lý container</h3>
        <ul>
          <li>Click container để xem danh sách file trong container.</li>
          <li>Mở file: double-click file trong container.</li>
          <li>Copy nhanh: copy file name / copy full path để share.</li>
        </ul>

        <h3>Thanh công cụ Container (search / layout / fullscreen)</h3>
        <table>
          <tr><th>Điều khiển</th><th>Chức năng</th></tr>
          <tr><td>🔍 <b>Search containers…</b></td><td>Ở chế độ List: lọc danh sách container theo tên. Ở chế độ sơ đồ (TB/LR): <b>highlight</b> container khớp trên sơ đồ</td></tr>
          <tr><td>⛶ <b>Fullscreen</b></td><td>Phóng to/thu nhỏ panel Container để xem dễ hơn</td></tr>
          <tr><td>☰/⇅/⇄ <b>Switch layout</b></td><td>Đổi cách hiển thị container — xem chi tiết bên dưới</td></tr>
        </table>

        <h3>3 chế độ hiển thị container</h3>
        <table>
          <tr><th>Chế độ</th><th>Mô tả</th></tr>
          <tr><td>☰ <b>List</b> (mặc định)</td><td>Danh sách phẳng, gọn, dễ thao tác nhanh (create/rename/right-click)</td></tr>
          <tr><td>⇅ <b>Top → Bottom</b></td><td>Vẽ container dạng <b>sơ đồ tổ chức</b> (org chart) từ trên xuống, thể hiện rõ quan hệ cha–con</td></tr>
          <tr><td>⇄ <b>Left → Right</b></td><td>Sơ đồ tổ chức theo chiều ngang</td></tr>
        </table>
        <div class="hint">
          <b>Mẹo:</b> Ở 2 chế độ sơ đồ (TB/LR), dùng <b>lăn chuột (wheel)</b> để zoom in/out; click vào 1 node để chọn container đó (đồng bộ với danh sách file bên dưới).
        </div>

        <h3>Cây container (phân cấp cha–con)</h3>
        <p>Container có thể lồng nhau thành cây (VD: container mẹ "Boiler" chứa các container con theo từng sự cố).
        Click <b>phải</b> vào 1 container để mở menu:</p>
        <table>
          <tr><th>Mục menu</th><th>Chức năng</th></tr>
          <tr><td>➕ <b>New Sub Container</b></td><td>Tạo container con bên trong container đang chọn</td></tr>
          <tr><td>✏️ <b>Rename</b></td><td>Đổi tên container</td></tr>
          <tr><td>🔗 <b>Set Parent…</b></td><td>Chuyển container vào làm con của 1 container khác</td></tr>
          <tr><td>⬆ <b>Make Root</b></td><td>Đưa container ra khỏi container cha, trở thành container gốc</td></tr>
          <tr><td>🗑 <b>Delete</b></td><td>Xóa container này (và toàn bộ container con bên trong nếu có)</td></tr>
        </table>
        <div class="warn">
          <b>Lưu ý:</b> Xóa container chỉ xóa <b>nhóm</b> (danh sách liên kết đến file), <b>không xóa file gốc trên ổ đĩa</b>.
        </div>

        <h3>Gỡ file khỏi container</h3>
        <ul>
          <li>Chọn 1 file trong danh sách → bấm nút <b>Remove File</b> bên dưới danh sách để gỡ file đó khỏi container đang chọn.</li>
          <li>Thao tác này chỉ gỡ liên kết trong container, <b>không xóa file gốc trên ổ đĩa</b>.</li>
          <li>Nút hình vuông cạnh bên (⛶) <b>mở rộng/thu gọn khung tài liệu</b> (panel file list) khi cần xem nhiều dòng hơn.</li>
        </ul>
        <div class="hint">
          Click phải trên 1 file trong container hiện chỉ có: 📁 Open Folder, 📓 Add to NotebookLM
          (chưa có Delete/Remove trong menu này — dùng nút <b>Remove File</b> thay thế).
        </div>

        <div class="hint">
          <b>Gợi ý đặt tên container chuẩn kỹ thuật:</b><br/>
          <code>[System]-[Topic]-[Date/Shift]-[Case]</code><br/>
          Ví dụ: <code>Generator-Protection-2026-01-Trip</code>
        </div>
        </body>
        """

    def page_notes(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>📄 Preview & Notes (PDF viewer + ghi chú AI)</h2>

        <p>Bấm nút <b>📄 Preview</b> ở sidebar phải để bật/tắt panel xem trước — panel này chỉ hoạt động với
        <b>file PDF</b> (file khác sẽ không load được nội dung xem trước). Panel gồm 2 tab.</p>

        <h3>Tab "📄 Page" — xem PDF</h3>
        <ul>
          <li>Xem PDF trực tiếp trong app (không cần mở app ngoài).</li>
          <li><b>Ctrl+F</b> hoặc chuột phải → <b>Find…</b>: tìm chữ trong PDF (Prev/Next/Close).</li>
          <li>Chuột phải → <b>Copy</b>: copy đoạn text đã bôi đen.</li>
        </ul>

        <h3>Tab "📝 Notes" — ghi chú cho file đang xem</h3>
        <table>
          <tr><th>Nút</th><th>Chức năng</th></tr>
          <tr><td><b>Size / B / I</b></td><td>Cỡ chữ, đậm, nghiêng cho phần đang bôi đen</td></tr>
          <tr><td>🖼 <b>Image</b></td><td>Chèn ảnh minh họa (hiện trường, đồ thị…) vào note</td></tr>
          <tr><td>🌐 <b>VI/EN</b></td><td>Dịch nhanh nội dung note Anh↔Việt (có cache, không gọi API lại nếu đã dịch)</td></tr>
          <tr><td>📓 <b>NbLM</b></td><td>Nhờ NotebookLM tóm tắt file (tự upload → lấy summary → xoá khỏi NotebookLM)</td></tr>
          <tr><td>🗺 <b>Mind Map</b></td><td>Tạo sơ đồ tư duy bằng NotebookLM; có nút 🔄 tạo lại và ⛶ xem toàn màn hình</td></tr>
          <tr><td>💾 <b>Save</b></td><td>Lưu note thủ công (app cũng <b>tự động lưu</b> khi bạn chuyển sang file khác hoặc đóng panel)</td></tr>
        </table>

        <div class="hint">
          Note được lưu theo <b>đường dẫn file PDF</b> (không lưu theo container) — cùng 1 file PDF xuất hiện ở
          nhiều container khác nhau vẫn dùng chung 1 note.
        </div>

        <h4>🗺 Mind Map — cách dùng chi tiết</h4>
        <ol>
          <li>Mở PDF trong Preview → tab Notes → bấm <b>🗺 Mind Map</b>.</li>
          <li>Yêu cầu đã <b>đăng nhập NotebookLM</b> (🔑 Switch Account ở tab NotebookLM) — nếu chưa, app báo "Not Logged In".</li>
          <li>App tạo notebook tạm, upload file, nhờ NotebookLM sinh sơ đồ, rồi <b>xóa notebook tạm ngay sau đó</b> —
          kết quả chỉ được cache local (theo đường dẫn file), <u>không</u> lưu vào tài khoản NotebookLM của bạn.</li>
          <li>Bấm 🗺 lại trên <b>cùng file đang xem</b> → ẩn/hiện lại sơ đồ đã có (không tạo lại, không tốn quota).</li>
          <li>Chuyển sang file PDF khác rồi bấm 🗺 → luôn tạo/hiện sơ đồ <b>của file mới</b>, không bị kẹt ở sơ đồ file cũ.</li>
          <li>🔄 <b>Regenerate</b>: xóa cache và tạo lại từ đầu (dùng khi tài liệu đã cập nhật).</li>
          <li>⛶ <b>Fullscreen</b>: mở sơ đồ toàn màn hình để xem dễ hơn.</li>
          <li>Click vào 1 <b>node</b> trong sơ đồ → app tự chuyển qua tab NotebookLM và hỏi thêm về node đó (cần notebook tương ứng đã được chọn/tự động khớp file).</li>
        </ol>
        <div class="hint">
          Có <b>3 cách</b> tạo mind map trong app, khác nhau ở chỗ có lưu lại hay không — xem so sánh ở trang
          <i>NotebookLM &amp; Studio</i>.
        </div>

        <div class="ok">
          <b>Best practice:</b><br/>
          Mỗi note nên có 3 phần:
          <ol>
            <li><b>Summary</b> – 1-3 dòng kết luận</li>
            <li><b>Evidence</b> – trích dẫn/ảnh/đồ thị</li>
            <li><b>Action</b> – bước cần làm tiếp theo</li>
          </ol>
        </div>
        </body>
        """

    def page_duplicates(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>Search Duplicates (file trùng)</h2>

        <p>Chức năng này tìm các file có <b>nội dung giống nhau</b> và gom thành từng <b>GROUP</b>.</p>

        <h3>Cách dùng</h3>
        <ol>
          <li>Chọn folder cần quét.</li>
          <li>Bấm <b>Search Duplicates</b>.</li>
          <li>Chờ quét xong → kết quả hiển thị theo nhóm.</li>
        </ol>

        <h3>Hiểu kết quả GROUP</h3>
        <ul>
          <li>Mỗi GROUP gồm các file trùng nội dung.</li>
          <li>Trong group thường có: bản gốc, bản copy, bản rename, bản nằm ở folder khác…</li>
          <li>Hãy mở từng file để quyết định giữ cái nào (theo date/đường dẫn/phiên bản).</li>
        </ul>

        <div class="warn">
          <b>Lưu ý hiệu năng:</b> Folder lớn (nhiều file hoặc file dung lượng lớn) sẽ quét lâu.
          Nếu chậm, hãy quét theo từng thư mục con hoặc theo từng loại file.
        </div>

        <h3>Cơ chế phát hiện (mô tả dễ hiểu)</h3>
        <ul>
          <li>App thường dùng <b>size</b> để lọc sơ bộ.</li>
          <li>Sau đó dùng <b>hash nội dung</b> (VD: SHA-256) để xác nhận trùng.</li>
          <li>Vì vậy file cùng tên nhưng khác nội dung sẽ không bị xem là trùng.</li>
        </ul>
        </body>
        """

    def page_batch_rename(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>Batch Rename (đổi tên hàng loạt)</h2>

        <p>Chức năng đổi tên nhiều file theo quy tắc để đồng bộ naming convention.</p>

        <h3>Khi nào nên dùng?</h3>
        <ul>
          <li>Chuẩn hóa tên file theo hệ thống (System-Equipment-DocType-Date).</li>
          <li>Thêm prefix/suffix cho một nhóm file.</li>
          <li>Loại bỏ ký tự thừa, khoảng trắng, "final-final-2" …</li>
        </ul>

        <h3>Quy trình an toàn</h3>
        <ol>
          <li>Chọn danh sách file (từ result hoặc container).</li>
          <li>Mở <b>Batch Rename</b>.</li>
          <li>Preview kết quả trước khi rename.</li>
          <li>Chỉ rename khi chắc chắn không trùng tên.</li>
        </ol>

        <div class="warn">
          <b>Khuyến nghị:</b> Rename xong hãy test mở vài file để chắc chắn đường dẫn & link tham chiếu vẫn đúng.
        </div>
        </body>
        """

    def page_index_search(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>🗄 DB Search (Index Search — SQLite)</h2>

        <p>Tab <b>🗄 DB Search</b> dùng database SQLite (build sẵn bằng script index, VD <code>create_index2.1.py</code>)
        để tìm rất nhanh theo tên/nội dung file đã lập chỉ mục — không cần mở từng file gốc.</p>

        <h3>Cách dùng</h3>
        <ol>
          <li><b>📂 Import DB</b>: chọn 1 hoặc nhiều file <code>.db</code> cùng lúc (multi-select).</li>
          <li>Dropdown chọn DB: mặc định <b>All DBs</b> (tìm trên tất cả DB đã import cùng lúc), hoặc chọn đúng 1 DB cụ thể theo tên.</li>
          <li>Gõ từ khóa vào ô tìm kiếm → Enter hoặc bấm <b>🔍 Search</b>.</li>
          <li>Kết quả hiện dạng bảng <b>File Name | Path</b> — double-click để mở file.</li>
          <li><b>📋 Copy</b>: copy tên file đang chọn trong kết quả.</li>
        </ol>
        <div class="hint">
          Danh sách DB đã import được nhớ lại giữa các lần mở app (lưu ở <code>db_list.json</code>) —
          không cần import lại mỗi lần mở.
        </div>

        <h3>DB có thể chứa gì?</h3>
        <ul>
          <li><b>Name index</b>: tên file, đường dẫn, loại file.</li>
          <li><b>Content index</b> (nếu DB có cột content): nội dung text đã trích từ PDF/Word/Text, tìm bằng <code>LIKE</code>.</li>
        </ul>

        <div class="warn">
          <b>Phân biệt với tab 🤖 Claude:</b> DB dùng ở tab DB Search có schema đơn giản
          (<code>files: id/name/path/type/content</code>). DB dùng ở tab Claude có schema riêng, phức tạp hơn
          (<code>doc_number</code>, <code>lot</code>, <code>discipline</code>, bảng <code>chunks</code> + FTS5) —
          <b>không dùng lẫn hai loại DB này cho nhau.</b> Nếu cần hỏi-đáp/chẩn đoán sâu theo tài liệu kỹ thuật, dùng tab
          <b>🤖 Claude</b> thay vì DB Search.
        </div>
        </body>
        """

    def page_tools_exe(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>Tools / EXE Launcher</h2>

        <h3>Panel "Tools" (sidebar phải)</h3>
        <p>Các tool dựng sẵn trong app:</p>
        <table>
          <tr><th>Nút</th><th>Chức năng</th></tr>
          <tr><td>📋 <b>List Files</b></td><td>Chọn nhiều thư mục cùng lúc (Ctrl/Shift+click), xem dạng cây phân cấp folder/file, tick chọn để thêm vào phạm vi search</td></tr>
          <tr><td>🔄 <b>Sync Folders</b></td><td>Đồng bộ nội dung Folder A → Folder B, xem song song 2 cây thư mục (Source | Target); cấu hình lưu ở <code>sync_config.json</code></td></tr>
          <tr><td>🔍 <b>Duplicates</b></td><td>Quét file trùng nội dung — xem chi tiết ở mục <i>Search Duplicates</i></td></tr>
          <tr><td>📝 <b>Open Notes</b></td><td>Mở/tạo file <code>Notes.xlsm</code> (sổ ghi chú dạng Excel — khác với tab 📝 Notes trong panel <b>Preview</b>, vốn là note HTML gắn theo từng file PDF)</td></tr>
          <tr><td>🔗 <b>Hyperlink Notes</b></td><td>Chọn file đã tick trong cây kết quả → gắn hyperlink các file đó vào 1 ô trong <code>Notes.xlsm</code></td></tr>
          <tr><td>📊 <b>Google Sheet</b></td><td>So sánh nội dung 2 tab trong 1 Google Sheet (diff checker) — hoạt động không cần API key (sheet "Anyone with link"), có API key thì tự load tên tab</td></tr>
        </table>

        <h3>Panel "ADD ON" — gắn EXE ngoài</h3>
        <p>Giúp bạn "gắn" các phần mềm/EXE hay dùng vào giao diện để mở nhanh.</p>
        <h4>Ví dụ tool nên gắn</h4>
        <ul>
          <li>PDF reader</li>
          <li>CAD viewer (DWG/DXF)</li>
          <li>DCS/SCADA viewer (nếu có)</li>
          <li>Notepad++ / VS Code</li>
          <li>Tool nội bộ công ty</li>
        </ul>
        <h4>Cách dùng</h4>
        <ol>
          <li>Bấm <b>ADD ON ➕</b> → chọn file .exe.</li>
          <li>Tool xuất hiện trong danh sách bên dưới nút ADD ON.</li>
          <li>Click để mở tool nhanh.</li>
        </ol>
        <div class="hint">
          <b>Gợi ý:</b> Bạn nên đặt tên tool theo workflow:
          <code>PDF</code>, <code>DWG Viewer</code>, <code>OCR</code>, <code>Log Viewer</code>, <code>Trend Tool</code>…
        </div>
        </body>
        """

    def page_notebooklm(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>NotebookLM &amp; Studio</h2>

        <h3>Đăng nhập lần đầu</h3>
        <ol>
          <li>Bấm <b>🔑 Switch Account</b> → trình duyệt tự mở → đăng nhập Google.</li>
          <li>Sau khi đăng nhập xong, bấm <b>✅ Save Login</b> trong app.</li>
          <li>Các lần sau app tự load danh sách notebook, không cần đăng nhập lại.</li>
        </ol>
        <div class="hint">
          <b>File session:</b> <code>%USERPROFILE%\\.notebooklm\\storage_state.json</code> —
          xóa file này để đăng nhập tài khoản khác.
        </div>

        <h3>Cây Notebooks (panel trái)</h3>
        <ul>
          <li>Danh sách notebook hiển thị dạng <b>cây</b>. Click chọn notebook để load chat.</li>
          <li><b>Double-click</b> (hoặc bấm mũi tên ▶) để <b>expand</b> và xem danh sách source con.</li>
          <li>Mỗi source con có <b>checkbox</b> — tick để chọn file tham gia generate artifact.</li>
          <li>Dòng đầu <b>☑ Select All</b>: tick/bỏ tick toàn bộ source của notebook đó.</li>
          <li>Mặc định tất cả source được tick (dùng tất cả khi generate).</li>
          <li>Click phải source → menu: <i>View Content, Create Mind Map, Delete</i>.</li>
        </ul>

        <div class="ok">
          <b>3 cách tạo Mind Map — khác nhau ở chỗ có lưu lại hay không:</b>
          <table>
            <tr><th>Cách</th><th>Nơi bấm</th><th>Có lưu vĩnh viễn?</th></tr>
            <tr><td>1. Preview panel</td><td>Tab 📝 Notes → nút 🗺 Mind Map</td>
                <td>❌ Không — notebook tạm, xóa ngay sau khi xong, chỉ cache local theo file</td></tr>
            <tr><td>2. Click phải Source</td><td>Cây Notebooks/Sources → <i>Create Mind Map</i></td>
                <td>❌ Không — có file local thì giống Cách 1; không có file local thì tạo online tạm thời (không thành artifact)</td></tr>
            <tr><td>3. Studio panel</td><td>🎨 Studio → nút 🗺 Mind Map</td>
                <td>✅ Có — lưu thành <b>artifact thật</b> trong notebook, hiện trong "Existing Artifacts", mở lại bất cứ lúc nào</td></tr>
          </table>
          Muốn giữ lại mind map lâu dài (chia sẻ, xem lại sau) → luôn dùng <b>Cách 3 (Studio)</b>.
          Muốn xem nhanh không cần lưu → dùng Cách 1 hoặc 2.
        </div>

        <h3>Tab Chat</h3>
        <ul>
          <li>Nhập câu hỏi → <b>Send</b>. Kết quả có trích nguồn bên dưới.</li>
          <li>Click đoạn trích → app tự mở file PDF và nhảy đến trang tương ứng (nếu file có local path).</li>
          <li>Câu trả lời dạng bảng → click link <b>📊 .xlsx</b> để mở file Excel tự động tạo.</li>
          <li><b>📌 Note</b>: lưu nội dung chat hiện tại thành Note trong Studio. App tự mở Studio panel sau khi lưu.</li>
        </ul>

        <h3>Tab Sources</h3>
        <ul>
          <li>Danh sách file đã add vào notebook đang chọn.</li>
          <li>Mỗi file có <b>checkbox</b> — sync 2 chiều với cây Notebooks bên trái.</li>
          <li><b>☐ Select All</b> ở header: chọn/bỏ chọn tất cả.</li>
          <li>Khi có file được tick → nút <b>🗑 Delete Selected</b> hiện ra để xóa hàng loạt.</li>
          <li><b>📄 Add File</b>: thêm file PDF/DOCX/TXT vào notebook.</li>
          <li><b>📡 Phân tích Sơ đồ (Vision AI)</b>: tick trước khi Add File để phân tích bản vẽ kỹ thuật bằng Vision LLM, tạo thêm nguồn mô tả cấu trúc sơ đồ.</li>
        </ul>
        <div class="hint">
          <b>Vision AI — Hybrid mode:</b> App tự detect từng trang PDF.<br>
          • Trang có ≥50 từ text → dùng fitz extract (nhanh, chính xác, 0 chi phí).<br>
          • Trang có ít text (bản vẽ thuần ảnh) → gọi Vision LLM để phân tích.<br>
          Kết quả ghi rõ: <i>[Hybrid: 12 trang fitz, 3 trang Vision via Gemini]</i>
        </div>

        <h3>🎨 Studio Panel</h3>
        <p>Bấm nút <b>🎨 Studio</b> ở thanh sidebar trái (bên dưới Preview) để mở/đóng panel Studio.</p>

        <h4>Generate Artifact</h4>
        <table>
          <tr><th>Nút</th><th>Tạo ra</th></tr>
          <tr><td>🗺 Mind Map</td><td>Sơ đồ tư duy dạng HTML tương tác, có thể zoom/collapse</td></tr>
          <tr><td>📄 Briefing Doc</td><td>Tóm tắt ngắn gọn theo dạng báo cáo</td></tr>
          <tr><td>📚 Study Guide</td><td>Tài liệu học theo cấu trúc câu hỏi–giải đáp</td></tr>
          <tr><td>🃏 Flashcards</td><td>Thẻ ghi nhớ hỏi–đáp</td></tr>
          <tr><td>❓ Quiz</td><td>Bộ câu hỏi trắc nghiệm</td></tr>
          <tr><td>📊 Data Table</td><td>Bảng dữ liệu trích xuất từ tài liệu</td></tr>
          <tr><td>🖼 Infographic</td><td>Infographic tóm tắt</td></tr>
          <tr><td>🎞 Slide Deck</td><td>Bộ slide trình bày</td></tr>
          <tr><td>🎙 Audio</td><td>File audio (podcast style)</td></tr>
        </table>
        <div class="ok">
          <b>Lọc theo source:</b> Tick chọn file ở cây Notebooks hoặc tab Sources trước khi Generate —
          artifact sẽ chỉ dùng những file đã tick. Không tick → dùng toàn bộ notebook.
        </div>

        <h4>Notes (trong Studio)</h4>
        <ul>
          <li>Hiển thị danh sách Note đã lưu trong notebook.</li>
          <li>Double-click Note → xem nội dung. Có thể <b>Convert to Source</b> để thêm vào nguồn.</li>
          <li>Click phải → <i>Delete Note</i>.</li>
        </ul>

        <h4>Existing Artifacts</h4>
        <ul>
          <li>Danh sách artifact đã tạo trước (Mind Map, Report, Audio…).</li>
          <li>Double-click → mở artifact. Click phải → <i>Delete</i>.</li>
        </ul>

        <h3>Tóm tắt PDF trong Notes (NbLM)</h3>
        <p>Mở PDF trong Preview → tab <b>Notes</b> → bấm <b>📓 NbLM</b>:</p>
        <ol>
          <li>App upload file lên notebook → tóm tắt → xóa source → trả kết quả vào ô Notes.</li>
        </ol>
        <div class="warn">Cần đã đăng nhập NotebookLM trước. Nếu chưa có notebook nào, app tự tạo <i>Auto Summary</i>.</div>

        <h3>Dịch thuật (🌐 VI)</h3>
        <ul>
          <li>Tab <b>Notes</b> → bấm <b>🌐 VI</b> để dịch sang tiếng Việt qua LLM API.</li>
          <li>Bấm lại để toggle về bản gốc.</li>
          <li>Provider dịch cấu hình tại <b>⚙ Settings</b> → <i>Translate Provider</i>.</li>
        </ul>

        <h3>Cấu hình LLM (API Keys &amp; Models)</h3>
        <p>Bấm <b>⚙</b> trong tab Notes → <b>LLM Settings</b>. Có thể nhập key và <b>chỉnh model</b> cho từng provider:</p>
        <table>
          <tr><th>Provider</th><th>Model mặc định</th><th>Ghi chú</th></tr>
          <tr><td>Gemini</td><td>gemini-3.6-flash</td><td>Hỗ trợ Vision AI cho bản vẽ — provider Vision chính</td></tr>
          <tr><td>Groq</td><td>openai/gpt-oss-120b</td><td>Nhanh, chỉ text — <b>không</b> nhận ảnh</td></tr>
          <tr><td>OpenRouter</td><td>google/gemma-4-31b-it:free</td><td>Free tier, có Vision — dự phòng</td></tr>
          <tr><td>Ollama</td><td>llama3.1:8b</td><td>Chạy local, không cần key, không cần internet</td></tr>
        </table>
        <div class="hint">Model trên cloud bị nhà cung cấp gỡ bỏ theo thời gian. Nếu gặp lỗi
        <code>404 model not found</code>, mở <b>⚙ LLM Settings</b> và nhập tên model mới.</div>
        <div class="hint">File cấu hình: <code>&lt;thư mục app&gt;\\llm_config.json</code></div>
        </body>
        """

    def page_shortcuts(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>Shortcuts & Mouse Actions</h2>

        <h3>Phím tắt</h3>
        <ul>
          <li><span class="kbd">F1</span> → mở User Guide</li>
          <li>(Nếu có) <span class="kbd">Esc</span> → đóng dialog</li>
        </ul>

        <h3>Chuột</h3>
        <ul>
          <li><b>Double-click</b> kết quả → mở file</li>
          <li><b>Click</b> container → xem danh sách file</li>
          <li><b>Click</b> trích dẫn nguồn trong tab NotebookLM/Claude → mở file nguồn tương ứng</li>
          <li><b>Lăn chuột</b> trên sơ đồ container (chế độ TB/LR) → zoom in/out</li>
        </ul>

        <div class="hint">
          <b>Gợi ý:</b> Nếu bạn muốn thêm shortcut khác (VD: Ctrl+F focus search box, Ctrl+L load store),
          có thể gắn trong <code>keyPressEvent</code> ở app chính.
        </div>
        </body>
        """

    def page_workflow_templates(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>Workflow Templates (Best practice)</h2>

        <h3>Template 1 – Xử lý sự cố (Trip / Alarm)</h3>
        <ol>
          <li>Search theo tag/KKS: <code>87G</code>, <code>40</code>, <code>UAT</code>…</li>
          <li>Tạo container: <code>Trip-YYYY-MM-DD-Shift</code></li>
          <li>Add vào container: SLD, logic trip, SOE/log, SOP, báo cáo cũ</li>
          <li>Notes: ghi "Symptom → Evidence → Hypothesis → Action"</li>
          <li>Tab <b>🤖 Claude</b>: bấm <b>🔬 Diagnose</b>, mô tả triệu chứng → xem cây nguyên nhân + bằng chứng → <b>Generate KV-OP Report</b> để có bản nháp báo cáo ngay</li>
        </ol>

        <h3>Template 2 – Commissioning / Test</h3>
        <ol>
          <li>Container: <code>Commissioning-[System]-[Test]</code></li>
          <li>Nhóm file: procedure, datasheet, ITP, forms, drawings</li>
          <li>Notes: lưu checklist + acceptance criteria</li>
        </ol>

        <h3>Template 3 – Dọn tài liệu (khử trùng)</h3>
        <ol>
          <li>Quét Duplicates theo từng thư mục con</li>
          <li>Giữ bản mới nhất hoặc bản "đúng chuẩn naming"</li>
          <li>Batch rename để đồng bộ tên</li>
        </ol>
        </body>
        """

    def page_troubleshooting(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>Troubleshooting</h2>

        <h3>1) Search không ra kết quả</h3>
        <ul>
          <li>Kiểm tra bạn đã chọn đúng folder gốc chưa.</li>
          <li>Thử keyword ngắn hơn, bỏ ký tự đặc biệt.</li>
          <li>Dùng <code>@keyword</code> để fuzzy.</li>
          <li>Dùng <code>*</code> nếu file có tên dài.</li>
          <li>Dùng <code>%</code> để loại bớt keyword gây nhiễu.</li>
        </ul>

        <h3>2) Duplicates quét lâu</h3>
        <ul>
          <li>Folder quá lớn hoặc nhiều file dung lượng lớn.</li>
          <li>Giải pháp: quét theo từng thư mục con / theo từng loại file.</li>
        </ul>

        <h3>3) Tab Claude không phản hồi / báo lỗi</h3>
        <ul>
          <li>Chưa đăng nhập Claude Code CLI → bấm <b>🔑 Login</b>, đăng nhập trong cửa sổ console hiện ra.</li>
          <li>Nếu vẫn lỗi, kiểm tra máy đã cài <code>claude</code> CLI (Claude Code) chưa.</li>
        </ul>

        <h3>4) Tab Claude — Diagnose / Quick Card / Work Pack / Trend Data không chạy được</h3>
        <ul>
          <li>Chưa chọn DB → bấm <b>📂 Select DB</b>, chọn đúng file <code>.db/.sqlite</code> chứa tài liệu kỹ thuật
              (bảng <code>files</code>/<code>chunks</code> + FTS5 — <b>không phải</b> DB đơn giản của tab DB Search).</li>
          <li>Nếu chọn nhầm DB (thiếu bảng <code>chunks</code>/FTS5), app sẽ không tìm được ngữ cảnh phù hợp.</li>
        </ul>

        <h3>5) NotebookLM báo "Không thể tự làm mới session"</h3>
        <ul>
          <li>Nguyên nhân: session/cookie Google đã hết hạn (thường do lâu ngày không dùng hoặc đổi mật khẩu),
              không phải lỗi code.</li>
          <li>Giải pháp: bấm <b>🔑 Switch Account</b> để đăng nhập Google lại thủ công 1 lần.</li>
        </ul>

        <h3>6) Notes không lưu / không hiện ảnh</h3>
        <ul>
          <li>Kiểm tra quyền ghi file (folder chỉ đọc).</li>
          <li>Ảnh quá lớn: thử resize ảnh trước khi insert.</li>
        </ul>

        <div class="ok">
          <b>Pro tip:</b> Nếu bạn muốn app "không bao giờ đơ", các tác vụ nặng (search folder lớn, duplicates,
          gọi AI) đều nên chạy trong <b>QThread/QRunnable</b> nền — app hiện đã làm vậy cho Duplicates, Group AI, Claude chat.
        </div>
        </body>
        """


    def page_prompt(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>Prompt (lệnh ẩn)</h2>
        <p>Gõ các lệnh đặc biệt vào ô <b>Filename Keyword</b> rồi bấm <b>Search</b> để kích hoạt chức năng ẩn.</p>

        <table>
          <tr><th>Lệnh</th><th>Chức năng</th><th>Ghi chú</th></tr>
          <tr>
            <td><code>$synonym</code></td>
            <td>Mở trình chỉnh sửa từ đồng nghĩa</td>
            <td>Thêm / sửa / xóa từ đồng nghĩa dùng cho tìm kiếm <code>@keyword</code></td>
          </tr>
          <tr>
            <td><code>$stats</code></td>
            <td>Xem thống kê file đã mở</td>
            <td>
              Mở dialog <b>File Open Statistics</b>: lưới nhiệt kiểu GitHub contribution graph (16 tuần gần nhất,
              đậm nhạt theo số lần mở/ngày) + bảng xếp hạng file mở nhiều nhất (🔥 nhiều nhất, 📈/📄/🗒️ theo mức độ).
              Có thể lọc theo <b>Year</b>/<b>Month</b> rồi bấm <b>View</b>.
            </td>
          </tr>
          <tr>
            <td><code>@keyword</code></td>
            <td>Tìm kiếm mờ (fuzzy) + từ đồng nghĩa</td>
            <td>Dùng khi không nhớ chính xác tên file</td>
          </tr>
          <tr>
            <td><code>A % B</code></td>
            <td>Tìm chứa A, loại trừ B</td>
            <td>Ví dụ: <code>report % backup</code></td>
          </tr>
          <tr>
            <td><code>A * B</code></td>
            <td>Tìm chứa cả A và B (thứ tự bất kỳ)</td>
            <td>Ví dụ: <code>UAT * trip</code></td>
          </tr>
          <tr>
            <td><code>folder:name</code></td>
            <td>Tìm <b>thư mục</b> theo tên (thay vì file)</td>
            <td>Ví dụ: <code>folder:boiler</code>, <code>folder:UAT*trip</code> — kết quả hiện icon 📁, double-click mở Explorer</td>
          </tr>
          <tr>
            <td><code>@colour0</code></td>
            <td>Đổi giao diện → <b>Metal Blue</b> (màu gốc)</td>
            <td rowspan="7">Gõ vào ô Keyword rồi bấm Search. Không cần chọn folder.</td>
          </tr>
          <tr>
            <td><code>@colour1</code></td>
            <td>Đổi giao diện → <b>Navy Gold</b></td>
          </tr>
          <tr>
            <td><code>@colour2</code></td>
            <td>Đổi giao diện → <b>Emerald</b></td>
          </tr>
          <tr>
            <td><code>@colour3</code></td>
            <td>Đổi giao diện → <b>Violet</b></td>
          </tr>
          <tr>
            <td><code>@colour4</code></td>
            <td>Đổi giao diện → <b>Rose Gold</b></td>
          </tr>
          <tr>
            <td><code>@colour5</code></td>
            <td>Đổi giao diện → <b>Arctic Frost</b></td>
          </tr>
          <tr>
            <td><code>@colour6</code></td>
            <td>Đổi giao diện → <b>Ghost Purple</b></td>
          </tr>
        </table>

        <div class="hint">
          <b>Lưu ý:</b> Các lệnh <code>$</code> không phân biệt hoa thường.
          Không cần chọn folder trước khi dùng lệnh <code>$</code>.<br>
          Lệnh <code>@colour</code> đổi màu ngay lập tức, không cần folder.
        </div>
        </body>
        """

# (Optional) quick manual test
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    dlg = HelpDialog()
    dlg.show()
    sys.exit(app.exec())
