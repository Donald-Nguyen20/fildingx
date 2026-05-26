# CODEBASE — Finding8 (File Search App)

## Tổng quan

Ứng dụng tìm kiếm file/folder trên Windows, viết bằng Python + PySide6.
Entry point: `Finding8.py` → khởi tạo `QApplication` → tạo `FileSearchApp`.

---

## Cấu trúc thư mục

```
Finding8.py              # Entry point + pyinstaller build command
paths.py                 # Hằng số đường dẫn toàn app (DATA_FILE, IMAGE_DIR…)
vector_store_builder.py  # CLI script build vector store (RAG)

core/                    # Business logic, không phụ thuộc UI
ui/                      # Tất cả widget và dialog PySide6

# Data files (runtime)
containers_data.json     # Dữ liệu containers
container_parents.json   # Quan hệ cha-con container
db_list.json             # Danh sách SQLite index databases
file_stats.json          # Thống kê mở file
llm_config.json          # Cấu hình LLM (model, api key…)
summaries.json           # Tóm tắt AI đã generate
ui_state.json            # Trạng thái UI (theme, search folders…)
nlm_source_map.json      # NotebookLM source mapping
```

---

## core/ — Business Logic

| File | Vai trò |
|------|---------|
| `search_engine.py` | Tìm file theo tên (`search_files_by_name`), tìm folder (`search_folders_by_name`), fuzzy search, tìm file trùng lặp (`find_duplicate_files`), hash file |
| `workers.py` | QThread workers chạy nền — hiện có `DuplicateSearchWorker` (dùng `find_duplicate_files`) |
| `container_manager.py` | Load/save container data từ JSON; `get_file_containers(path)` tra cứu container của 1 file |
| `synonym_manager.py` | Load/save `synonyms.json`; mở rộng keyword tìm kiếm bằng từ đồng nghĩa |
| `excel_bridge.py` | Tích hợp Excel qua `win32com` — mở file, điều hướng, copy path |
| `file_stats.py` | Ghi log lần mở file (`record_open`), thống kê theo ngày/tuần/tháng |
| `llm_client.py` | HTTP client gọi LLM API (Ollama/OpenAI-compatible); dùng config từ `llm_config.py` |
| `llm_config.py` | Load/save `llm_config.json`; `DEFAULT_CONFIG` với model mặc định |
| `percent_exclude_search.py` | Syntax `A%B` — tìm A nhưng loại trừ B khỏi kết quả |
| `rag/` | RAG pipeline: `vector_store_builder.py` → `vector_retriever.py`; `rag_extract.py` trích nội dung; `rag_dedup.py` loại trùng |

---

## ui/ — Giao diện

### Cửa sổ chính

**`main_window.py`** — `FileSearchApp(QMainWindow)` — trung tâm toàn app.

Import từ: `paths`, `themes`, `search_engine`, `container_manager`, `file_stats`,
`synonym_manager`, `excel_bridge`, `workers`, `hud_widgets`, `tree_sorter`,
`help_dialog`, `index_search_window`, `notebooklm_window`, `list_files_window`,
`sync_folder_window`, `pdf_preview`, `container_tree`.

Các method quan trọng:
- `search_files()` — tìm file theo keyword, gọi `search_engine`
- `search_duplicates()` — khởi động `DuplicateSearchWorker`
- `_add_to_search_folders(paths)` — thêm folder vào danh sách search
- `list_files_in_folder()` → `show_list_files_window(self)`
- `sync_folders()` → `show_sync_folder_window(self)`
- `open_or_create_notes()` — mở `NotesWindow`
- `load_data_from_file()` / `save_data_to_file()` — persist state

### Dialog / Tool windows

| File | Class / Function | Vai trò |
|------|-----------------|---------|
| `list_files_window.py` | `show_list_files_window(parent)` → `_ListFilesWindow` | Chọn nhiều folder (Windows IFileOpenDialog native), hiển thị cây file/folder có checkbox, nút "Add to Search Folders" |
| `sync_folder_window.py` | `show_sync_folder_window(parent)` → `_SyncFolderWindow` | Sync Folder A → B; layout 2 panel QSplitter (Source có checkbox, Target read-only); dùng `shutil.copytree/copy2` |
| `notes_window.py` | `NotesWindow`, `RichTextEdit` | Rich text editor + ảnh, lưu/load note theo file |
| `pdf_preview.py` | `PdfPreviewWidget` | Preview PDF inline trong app |
| `index_search_window.py` | `IndexSearchWindow`, `IndexSearchWidget` | Tìm kiếm nội dung trong SQLite index databases |
| `notebooklm_window.py` | `NotebookLMWidget` | Tích hợp NotebookLM (async subprocess) |
| `help_dialog.py` | `HelpDialog` | Cửa sổ trợ giúp |
| `stats_dialog.py` | — | Thống kê mở file (dùng `file_stats.py`) |
| `clear_history.py` | — | Xóa lịch sử tìm kiếm |

### Widgets & Utilities

| File | Vai trò |
|------|---------|
| `themes.py` | 6 bộ màu; `get_current()` → `{"name", "hud", "qss"}`; `qss` apply cho toàn app qua `setStyleSheet` |
| `container_tree.py` | `ContainerOrgChartWidget` — hiển thị container 3 chế độ: LIST (mặc định), TB (top-bottom), LR (left-right) |
| `tree_sorter.py` | `TreeSortHelper` — sort QTreeWidget theo cột, hỗ trợ natural sort (1, 2, 10 thay vì 1, 10, 2) |
| `hud_widgets.py` | HUD panel vẽ bằng QPainter/QPainterPath; `qss_hud_metal_header_feel`, `qss_white_results` |

---

## Luồng dữ liệu chính

```
Finding8.py
  └─ FileSearchApp (main_window.py)
       ├─ search_engine.py      ← tìm kiếm
       ├─ container_manager.py  ← quản lý container (lưu JSON)
       ├─ synonym_manager.py    ← từ đồng nghĩa
       ├─ excel_bridge.py       ← tương tác Excel
       ├─ workers.py            ← background threads
       ├─ themes.py             ← stylesheet toàn app
       ├─ container_tree.py     ← widget container (nhúng vào main)
       ├─ pdf_preview.py        ← widget PDF (nhúng vào main)
       ├─ index_search_window.py ← dialog SQLite search
       ├─ notebooklm_window.py  ← widget NotebookLM (nhúng vào main)
       ├─ list_files_window.py  ← dialog độc lập
       └─ sync_folder_window.py ← dialog độc lập
```

---

## Ghi chú kỹ thuật

- **PySide6 CheckState**: dùng `item.checkState(0) == Qt.Checked` (không dùng `int()`)
- **Checkbox propagation**: dùng `self._blocking` flag để tránh signal loop khi set check state
- **QPushButton.clicked** truyền `bool checked` — dùng `lambda:` khi connect tới method có param
- **Theme**: tất cả dialog mở bằng `self.setStyleSheet(themes.get_current()["qss"])`
- **Đường dẫn**: import `paths.py` thay vì hardcode, đặc biệt khi build pyinstaller
- **Container data**: `containers_data.json` + `container_parents.json` — 2 file riêng, load/save qua `container_manager.py`
- **Branch hiện tại**: `new-layout` (feature branch, chưa merge vào `main`)
