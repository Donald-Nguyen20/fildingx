# Funtion/help_dialog.py
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QTextEdit
from PySide6.QtCore import Qt

try:
    # HUD theme (nếu có)
    from hud_widgets import qss_hud_metal_header_feel, qss_white_results
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
            "Containers (nhóm công việc)": self.page_containers(),
            "Notes (ghi chú theo file)": self.page_notes(),
            "Search Duplicates (file trùng)": self.page_duplicates(),
            "Batch Rename (đổi tên hàng loạt)": self.page_batch_rename(),
            "Index Search (SQLite DB)": self.page_index_search(),
            "Tools / EXE Launcher": self.page_tools_exe(),
            "AI Popup (RAG Chat / Jarvis)": self.page_ai_popup(),
            "Shortcuts & Mouse Actions": self.page_shortcuts(),
            "Workflow Templates (Best practice)": self.page_workflow_templates(),
            "Troubleshooting": self.page_troubleshooting(),
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
            <td>Khi nhớ “một phần tên”, mã KKS, tag, số hiệu bản vẽ…</td>
          </tr>
          <tr>
            <td><b>Containers</b></td>
            <td>Gom file theo dự án/ca/khoản mục</td>
            <td>Tạo “bộ hồ sơ” cho từng công việc (SOP, bản vẽ, báo cáo…)</td>
          </tr>
          <tr>
            <td><b>Notes</b></td>
            <td>Ghi chú theo file (text + ảnh), lưu HTML</td>
            <td>Lưu nhanh insight/khuyến nghị khi mở file</td>
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
            <td><b>AI Popup (RAG)</b></td>
            <td>Chat hỏi tài liệu SOP/notes/bộ hồ sơ vector store</td>
            <td>Hỏi “theo tài liệu nội bộ” và có nguồn trích dẫn</td>
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

        <h3>3) Ghi chú theo file</h3>
        <ol>
          <li>Trong container, click file → mở <b>Notes</b>.</li>
          <li>Ghi text + chèn ảnh (ảnh hiện trường / ảnh đồ thị).</li>
          <li><b>Save</b> để lưu dạng HTML.</li>
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
          <b>Mẹo:</b> Nếu bạn chỉ nhớ “na ná” tên file, hãy dùng <b>fuzzy</b> (xem mục Advanced Query).
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
          <li><code>UAT*Trip</code> → tên file có “UAT” và sau đó có “Trip”.</li>
          <li><code>Trip*UAT</code> → đảo thứ tự.</li>
          <li><b>Gợi ý:</b> dùng khi file có format tên dài: “system_subsystem_topic_date”.</li>
        </ul>

        <h3>2) Query kiểu A % B (include/exclude)</h3>
        <p>Dạng này rất mạnh khi bạn muốn <b>chứa A nhưng loại B</b>.</p>
        <div class="ok">
          <b>Ví dụ:</b><br/>
          <code>UAT % drawing</code> → tìm các file có “UAT” nhưng <b>không</b> chứa “drawing”.<br/>
          <code>Generator % old</code> → chứa “Generator”, loại các file có “old”.
        </div>
        <div class="hint">
          <b>Lưu ý:</b> Dấu <code>%</code> là “lọc loại trừ”, cực hợp để tránh file backup: <code>report % backup</code>, <code>P&ID % temp</code>.
        </div>

        <h3>3) Fuzzy search bằng tiền tố @</h3>
        <p>Dùng <code>@keyword</code> để tìm “gần đúng” (khi bạn nhớ sai chính tả, hoặc file bị viết tắt).</p>
        <ul>
          <li><code>@deareator</code> → vẫn có thể ra “deaerator”.</li>
          <li><code>@vibration</code> → ra cả “vib”, “vibra”, “vibration”.</li>
        </ul>

        <h3>4) Synonyms (từ đồng nghĩa) & chỉnh sửa</h3>
        <p>App có file <code>synonyms.json</code> để mở rộng từ khóa. Bạn có thể chỉnh từ đồng nghĩa trong UI.</p>
        <ul>
          <li>Ví dụ: “UAT” đồng nghĩa “Unit Aux Transformer”.</li>
          <li>Ví dụ: “GSU” đồng nghĩa “GSUT”, “Generator Step-up Transformer”.</li>
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

        <div class="hint">
          <b>Mẹo:</b> Khi có nhiều bản, hãy ưu tiên theo <b>Date Modified</b> và kiểm tra nội dung nhanh trước khi dùng.
        </div>
        </body>
        """

    def page_containers(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>Containers (nhóm công việc)</h2>
        <p>Containers giúp bạn gom file thành “bộ hồ sơ” theo công việc – giống playlist nhưng dành cho tài liệu kỹ thuật.</p>

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
          <li>Xóa file khỏi container: remove item (không xóa file gốc nếu app thiết kế đúng theo “remove from list”).</li>
          <li>Xóa container: delete container (chỉ xóa nhóm, không xóa file gốc).</li>
        </ul>

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
        <h2>Notes (ghi chú theo file)</h2>

        <p>Notes giúp bạn lưu “tri thức cá nhân” ngay cạnh tài liệu: nhận xét, kết luận, checklist, ảnh chụp hiện trường/đồ thị.</p>

        <h3>Mở Notes</h3>
        <ul>
          <li>Chọn file trong container → mở Notes.</li>
          <li>Hoặc dùng chức năng Notes panel (nếu có nút/khung Notes).</li>
        </ul>

        <h3>Những gì Notes hỗ trợ</h3>
        <ul>
          <li><b>Text</b> (rich text) – bôi đen, xuống dòng, bullet…</li>
          <li><b>Insert Image</b> – chèn ảnh minh họa</li>
          <li><b>Save</b> – lưu dạng HTML (dễ mở lại và giữ format)</li>
          <li><b>Font size</b> – tăng/giảm để đọc dễ</li>
        </ul>

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
          <li>Loại bỏ ký tự thừa, khoảng trắng, “final-final-2” …</li>
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
        <h2>Index Search (SQLite DB)</h2>

        <p>Index Search dùng database SQLite để tìm rất nhanh trong một “chỉ mục” đã xây sẵn.</p>

        <h3>Cách dùng</h3>
        <ol>
          <li>Mở <b>Index Search</b> (thường là nút/khung riêng).</li>
          <li><b>Import DB (*.db)</b> để nạp database.</li>
          <li>Nhập keyword → Search.</li>
          <li>Mở file từ kết quả.</li>
        </ol>

        <h3>DB có thể chứa gì?</h3>
        <ul>
          <li><b>Name index</b>: tên file, đường dẫn, metadata.</li>
          <li><b>Content index</b> (nếu DB có): nội dung text đã trích từ PDF/Word/Text.</li>
        </ul>

        <div class="hint">
          <b>Mẹo:</b> Nếu bạn đã có DB index content, đây là cách tìm “từ trong nội dung” nhanh hơn RAG.
          RAG phù hợp hơn cho hỏi-đáp, tóm tắt, giải thích theo tài liệu.
        </div>
        </body>
        """

    def page_tools_exe(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>Tools / EXE Launcher</h2>

        <p>Tính năng này giúp bạn “gắn” các phần mềm/EXE hay dùng vào giao diện để mở nhanh.</p>

        <h3>Ví dụ tool nên gắn</h3>
        <ul>
          <li>PDF reader</li>
          <li>CAD viewer (DWG/DXF)</li>
          <li>DCS/SCADA viewer (nếu có)</li>
          <li>Notepad++ / VS Code</li>
          <li>Tool nội bộ công ty</li>
        </ul>

        <h3>Cách dùng</h3>
        <ol>
          <li>Thêm tool (Add EXE) → chọn file .exe.</li>
          <li>Tool xuất hiện ở khu vực Tools.</li>
          <li>Click để mở tool nhanh.</li>
        </ol>

        <div class="hint">
          <b>Gợi ý:</b> Bạn nên đặt tên tool theo workflow:
          <code>PDF</code>, <code>DWG Viewer</code>, <code>OCR</code>, <code>Log Viewer</code>, <code>Trend Tool</code>…
        </div>
        </body>
        """

    def page_ai_popup(self) -> str:
        return f"""
        {self._base_style()}
        <body>
        <h2>AI Popup (RAG Chat / Jarvis)</h2>

        <p>AI Popup cho phép bạn hỏi đáp dựa trên <b>Vector Store</b> (FAISS + metadata). Nó trả lời theo tài liệu và có <b>Sources</b>.</p>

        <h3>Khái niệm nhanh</h3>
        <ul>
          <li><b>Vector Store</b>: thư mục chứa <code>index.faiss</code> + <code>metadata.json</code> + <code>base_path.txt</code>.</li>
          <li><b>Retriever</b>: tìm top-k đoạn liên quan.</li>
          <li><b>LLM</b>: viết câu trả lời dựa trên context + prompt SOP.</li>
        </ul>

        <h3>Cách dùng</h3>
        <ol>
          <li>Bật AI Popup (toggle) từ app chính.</li>
          <li>Bấm <b>Load Vector Store</b> → chọn folder vector store.</li>
          <li>Nhập câu hỏi → Send.</li>
          <li>Xem <b>Sources</b> bên phải → click để mở file nguồn.</li>
        </ol>

        <h3>Hỏi gì hiệu quả?</h3>
        <ul>
          <li><b>Tóm tắt</b>: “Tóm tắt SOP shutdown cho hệ …”</li>
          <li><b>Checklist</b>: “Checklist trước khi restart …”</li>
          <li><b>Giải thích</b>: “Vì sao cần …, trích theo tài liệu?”</li>
          <li><b>So sánh</b>: “So sánh 2 procedure … có khác gì?”</li>
        </ul>

        <div class="warn">
          <b>Lưu ý:</b> AI Popup trả lời tốt khi vector store được build sạch (ít rác, dedup tốt, chunk hợp lý).
          Nếu kết quả lạ, hãy rebuild store hoặc bổ sung tài liệu.
        </div>
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
          <li><b>Click</b> source trong AI Popup → mở file nguồn</li>
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
          <li>Notes: ghi “Symptom → Evidence → Hypothesis → Action”</li>
          <li>(Nếu có vector store) hỏi AI: checklist & trích SOP</li>
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
          <li>Giữ bản mới nhất hoặc bản “đúng chuẩn naming”</li>
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

        <h3>3) AI Popup báo thiếu vector store</h3>
        <ul>
          <li>Folder vector store phải có: <code>index.faiss</code>, <code>metadata.json</code>, <code>base_path.txt</code>.</li>
          <li>Nếu thiếu: hãy rebuild vector store bằng tool build/append.</li>
        </ul>

        <h3>4) Sources trong AI Popup click không mở</h3>
        <ul>
          <li>Đường dẫn gốc trong <code>base_path.txt</code> sai hoặc đã di chuyển folder tài liệu.</li>
          <li>Giải pháp: rebuild store hoặc sửa base_path đúng thư mục tài liệu.</li>
        </ul>

        <h3>5) Notes không lưu / không hiện ảnh</h3>
        <ul>
          <li>Kiểm tra quyền ghi file (folder chỉ đọc).</li>
          <li>Ảnh quá lớn: thử resize ảnh trước khi insert.</li>
        </ul>

        <div class="ok">
          <b>Pro tip:</b> Nếu bạn muốn app “không bao giờ đơ”, hãy chuyển các tác vụ nặng
          (search folder lớn, duplicates, build store) sang <b>QThread/QRunnable</b>.
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
