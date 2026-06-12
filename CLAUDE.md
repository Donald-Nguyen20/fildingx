# Van Phong 1 BOT Thermal Power Plant — Document Intelligence Project

## Mục tiêu
Project này dùng Cowork/Claude để tra cứu tài liệu kỹ thuật và tạo báo cáo vận hành cho **Nhà máy Nhiệt điện Van Phong 1 BOT**. Toàn bộ tài liệu đã được index vào file SQLite `.db` — Claude chỉ cần query DB để lấy thông tin, không cần đọc file gốc.

---

## File DB

| File | Nội dung |
|------|----------|
| `AB Drawings.db` | ~7,500 tài liệu kỹ thuật, bản vẽ, O&M manual, commissioning procedure |

**BASE_PATH gốc:** `D:/3.VP/6.Library/AB Drawings`
(Đường dẫn tuyệt đối trong DB — dùng để mở file gốc nếu cần)

---

## Schema Database

### Bảng `files` — metadata và toàn bộ nội dung file
```sql
CREATE TABLE files (
    id            INTEGER PRIMARY KEY,
    name          TEXT,           -- Tên file (ví dụ: VP1-C-L3-G-HNC-50056-Rev.D.pdf)
    path          TEXT UNIQUE,    -- Đường dẫn tương đối so với BASE_PATH
    type          TEXT,           -- Phần mở rộng: .pdf, .docx, .xlsx ...
    content       TEXT,           -- Toàn bộ text đã extract
    doc_number    TEXT,           -- Ví dụ: VP1-C-L3-G-HNC-50056
    lot           TEXT,           -- L1, L2, L3, L4
    discipline    TEXT,           -- A/C/E/F/G/I/M/P/Q/R (xem bảng bên dưới)
    system_code   TEXT,           -- Ví dụ: HNC, FDF, IDF, BFP ...
    revision      TEXT,           -- Rev.A, Rev.B, D, AB0 ...
    is_scanned    INTEGER,        -- 1 = file scan/OCR, 0 = có text layer
    page_count    INTEGER,
    file_size_kb  INTEGER,
    indexed_date  TEXT
)
```

> **Lưu ý:** Có 1 bản ghi đặc biệt `name = 'BASE_PATH'` lưu thư mục gốc — luôn loại trừ khi đếm hoặc tìm kiếm file thực.

### Bảng `chunks` — nội dung đã chia nhỏ (dùng cho Cowork)
```sql
CREATE TABLE chunks (
    id          INTEGER PRIMARY KEY,
    file_id     INTEGER,    -- FK → files.id
    chunk_index INTEGER,    -- Thứ tự chunk trong file
    heading     TEXT,       -- Tên section/heading (nếu phát hiện được)
    content     TEXT,       -- Nội dung đoạn, tối đa ~1200 ký tự
    char_start  INTEGER,
    char_end    INTEGER
)
```

### Virtual tables (FTS5)
- `files_fts` — FTS index trên `files(name, doc_number, system_code, content)`
- `chunks_fts` — FTS index trên `chunks(heading, content)`

---

## Cách Query

### Tìm file theo tên / doc number / system code
```sql
SELECT name, path, doc_number, lot, discipline, system_code, revision, is_scanned
FROM files
WHERE id IN (SELECT rowid FROM files_fts WHERE files_fts MATCH 'IDF*')
  AND name != 'BASE_PATH'
ORDER BY lot, name
LIMIT 20;
```

### Tìm nội dung liên quan — DÙNG CÁI NÀY KHI LÀM BÁO CÁO
```sql
SELECT f.name, f.doc_number, f.path, c.heading, c.content
FROM chunks c
JOIN files f ON f.id = c.file_id
WHERE c.id IN (SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'lube oil temperature*')
ORDER BY rank
LIMIT 10;
```

### Tìm trong file cụ thể
```sql
SELECT c.heading, c.content
FROM chunks c
JOIN files f ON f.id = c.file_id
WHERE f.doc_number = 'VP1-C-L3-G-HNC-50056'
  AND c.id IN (SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'alarm setpoint*')
ORDER BY c.chunk_index;
```

### Lấy toàn bộ nội dung 1 file (khi cần đọc đầy đủ)
```sql
SELECT content FROM files WHERE doc_number = 'VP1-C-L3-G-HNC-50056';
```

### FTS5 — Cú pháp tìm kiếm
| Cú pháp | Ý nghĩa |
|---------|---------|
| `vibration*` | Prefix match: vibration, vibrating, vibrate |
| `"lube oil"` | Cụm từ chính xác |
| `IDF AND bearing` | Phải có cả hai từ |
| `IDF OR FDF` | Có một trong hai |
| `vibration NOT alarm` | Có vibration, không có alarm |

---

## Quy ước Đặt Tên Tài Liệu VP1

**Format:** `VP1-[Unit]-L[Lot]-[Discipline]-[SystemCode]-[DocNo]_Rev[X]`

**Ví dụ:** `VP1-C-L3-G-HNC-50056-Rev.D.pdf`

### Discipline codes
| Code | Ngành |
|------|-------|
| A | Architectural |
| C | Civil / Structural |
| E | Electrical |
| F | Commissioning / Testing |
| G | General (O&M, manuals) |
| I | Instrumentation & Control |
| M | Mechanical |
| P | Piping |
| Q | Quality |
| R | Process / PFD |

### Lot
| Lot | Phạm vi |
|-----|---------|
| L1 | Boiler & Fuel system |
| L2 | Turbine & Generator |
| L3 | Balance of Plant (BOP) |
| L4 | Civil / Common |

### System codes thường gặp
| Code | Thiết bị |
|------|----------|
| HNC | Howden — IDF (Induced Draft Fan) |
| FDF | Forced Draft Fan |
| BFP | Boiler Feed Pump |
| CEP | Condensate Extraction Pump |
| CWP | Circulating Water Pump |
| ACT | Air Cooled Turbine |

---

## Tài liệu Quan Trọng

| Doc Number | Mô tả | Ghi chú |
|------------|-------|---------|
| `VP1-C-L3-G-HNC-50056` | **Howden IDF O&M Manual** | ~654k ký tự, tài liệu chính về IDF |
| Discipline F | Commissioning procedures | Toàn bộ test record và procedure |
| Discipline I | I&C drawings, logic diagram | Alarm setpoints, interlock |

---

## Quy trình Làm Báo Cáo Vận Hành

### Bước 1 — Tìm context liên quan
```sql
-- Tìm các đoạn liên quan đến sự cố
SELECT f.name, f.doc_number, c.heading, c.content
FROM chunks c JOIN files f ON f.id = c.file_id
WHERE c.id IN (
    SELECT rowid FROM chunks_fts
    WHERE chunks_fts MATCH '[từ khóa sự cố]*'
)
ORDER BY rank LIMIT 15;
```

### Bước 2 — Xác nhận thông số kỹ thuật
```sql
-- Tìm alarm setpoint, design value
SELECT c.heading, c.content
FROM chunks c JOIN files f ON f.id = c.file_id
WHERE f.doc_number LIKE 'VP1-%-I-%'   -- Discipline I&C
  AND c.id IN (SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH '[tag name]*');
```

### Bước 3 — Viết báo cáo theo format chuẩn
Báo cáo vận hành VP1 gồm các phần:
1. **Introduction** — Mô tả sự cố, thời điểm, thiết bị liên quan
2. **Abnormal Status** — Diễn biến thực tế (kèm giá trị đo)
3. **Analysis** — Nguyên nhân gốc rễ (Root Cause), tham chiếu tài liệu
4. **Suggestion** — Kiến nghị xử lý
5. **Execution Plan** — Kế hoạch thực hiện (có bảng: Action / Responsible / Target Date)
6. **Conclusion**
7. **Attachment** — Log sheet, trend data

**File name convention:** `KV-OP-YY-XXXX_[Title].docx`

---

## Lưu ý Khi Dùng DB

- Luôn dùng `chunks_fts` thay vì `files_fts` khi cần nội dung để viết báo cáo — chính xác hơn, tiết kiệm token hơn
- File `is_scanned = 1` là bản scan OCR — nội dung có thể có lỗi nhận dạng ký tự
- Khi trích dẫn trong báo cáo, ghi rõ: `Doc: [doc_number], Section: [heading]`
- DB không chứa hình ảnh — nếu cần bản vẽ P&ID thì phải mở file gốc
