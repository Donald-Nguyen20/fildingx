# DATABRAIN.md

Van Phong 1 BOT Thermal Power Plant — Document Intelligence.

This file describes the *data*, not the app: how to answer a technical question or write an operation report from the indexed documents. The Data Brain tab loads it at runtime as its system prompt (`_load_domain_md()` in `ui/claude_assistant/widget.py`), so it must be copied **next to the `.exe`** — not into `_internal/` — when the app is packaged. For the application codebase, see `CLAUDE.md`.

## Mục tiêu
Project này dùng Cowork/Claude để tra cứu tài liệu kỹ thuật và tạo báo cáo vận hành cho **Nhà máy Nhiệt điện Van Phong 1 BOT**. Toàn bộ tài liệu đã được index vào file SQLite `.db` — Claude chỉ cần query DB để lấy thông tin, không cần đọc file gốc.

---

## File DB

| File | Nội dung |
|------|----------|
| `Databasev3.db` | 8,054 tài liệu kỹ thuật, bản vẽ, O&M manual, commissioning procedure — 705,611 chunks |

**BASE_PATH gốc:** `D:/3.VP/6.Library/AB Drawings`
(Đường dẫn tuyệt đối trong DB — dùng để mở file gốc nếu cần)

> Đường dẫn DB thật do tab Data Brain truyền vào từng lệnh `db_query.py`, đọc từ `claude_db.json` — dùng đúng đường dẫn đó, không tự ghép lại. `AB Drawings.db` là DB của tab **DB Search**, schema khác (bảng `files`, `LIKE`, không có FTS), không dùng ở đây.

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
FROM chunks_fts
JOIN chunks c ON c.id = chunks_fts.rowid
JOIN files f ON f.id = c.file_id
WHERE chunks_fts MATCH 'lube oil temperature*'
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
ORDER BY c.chunk_index
LIMIT 50;          -- một tài liệu lớn có hàng nghìn chunk
```

### Đọc nội dung đầy đủ của 1 file
`db_query.py` chặn mỗi ô ở **4.000 ký tự**, nên `SELECT content FROM files`
không bao giờ trả về cả tài liệu: 952 file trong DB dài hơn 100.000 ký tự và
file dài nhất là 20.858.924 ký tự. Khi ô bị cắt, kết quả có `"truncated": true`
— đừng coi phần nhận được là toàn bộ tài liệu.

Đo độ dài trước:
```sql
SELECT doc_number, LENGTH(content) n_chars
FROM files
WHERE doc_number = 'VP1-C-L3-G-HNC-50056';
```

Rồi đọc từng đoạn 4.000 ký tự bằng `substr` (đoạn 1 bắt đầu ở 1, đoạn 2 ở 4001,
đoạn 3 ở 8001...):
```sql
SELECT substr(content, 1, 4000) AS part
FROM files
WHERE doc_number = 'VP1-C-L3-G-HNC-50056';
```

Với tài liệu dài, **đọc theo `chunks` gần như luôn tốt hơn**: chunk đã được cắt
theo heading nên lấy đúng phần cần, thay vì đọc tuần tự hết tài liệu.

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

### System codes

DB có **322 system_code** khác nhau, phủ 6.976/8.054 tài liệu (1.078 file không
có code trong tên). Bảng dưới là các code nhiều tài liệu nhất; nghĩa của từng
code đã được xác nhận bằng cách **đọc tên tài liệu thật trong DB**, không suy ra
từ chữ viết tắt. Số `n` là số file mang code đó.

**Cạm bẫy quan trọng:** code **không phải** là viết tắt tiếng Anh của tên thiết
bị. Boiler Feed Pump là `LAC` chứ không phải `BFP`; FD Fan là `HLB` chứ không
phải `FDF`; không có code nào tên `FDF`, `BFP`, `CEP`, `CWP` hay `ACT`. Luôn tra
code bằng query ở cuối mục này thay vì đoán.

**Lò hơi và phụ trợ**
| Code | n | Thiết bị |
|------|---|----------|
| `HNC` | 36 | ID Fan (quạt khói) |
| `HLB` | 16 | FD Fan (quạt gió chính) |
| `HLV` | 2 | Đường gió FD |
| `HFE` | 16 | PA Fan (quạt gió cấp 1) |
| `HFC` | 35 | Máy nghiền than (pulverizer) |
| `HFV` | 16 | Phụ trợ máy nghiền |
| `UHF` | 6 | Phụ trợ máy nghiền (Lot-4) |
| `HFB` | 7 | Máy cấp than (coal feeder) |
| `HLD` | 20 | Bộ sấy không khí (GAH / air heater) |
| `HCB`, `HCC` | 23 + 26 | Thổi bụi (soot blower) |
| `H` | 141 | **Lò hơi nói chung** — legend P&ID, line list, không phải một thiết bị |

**Khói, tro, FGD**
| Code | n | Thiết bị |
|------|---|----------|
| `HDE` | 43 | Lọc bụi tĩnh điện (ESP) |
| `HDC` | 62 | Hệ thống tro bay (FAHS) |
| `ETA` | 70 | Hệ thống tro xỉ đáy lò |
| `UES` | 26 | Phụ trợ tro xỉ |
| `HT` | 173 | Khử lưu huỳnh nước biển (SWFGD) — line list, P&ID |
| `UEM`, `UQX` | 22 + 10 | Phụ trợ FGD |

**Tuabin, máy phát, nước**
| Code | n | Thiết bị |
|------|---|----------|
| `MAA` | 17 | Tuabin hơi chính (start-up curve, MSV/CV) |
| `MAV` | 29 | Hệ dầu tuabin (oil tank / cooler / conditioner) |
| `MAJ` | 61 | Bình ngưng (condenser) |
| `MKA` | 25 | Máy phát (generator) |
| `LAC` | 34 | **Bơm cấp nước lò (MBFP/TBFP)** |
| `XAA` | 13 | Tuabin dẫn động bơm cấp (BFP turbine) |
| `XAV` | 20 | Đường ống STG / phụ trợ BFPT |
| `XA` | 26 | Thử nghiệm chạy thử bơm cấp |
| `LCB` | 22 | Bơm nước ngưng |
| `LAA` | 8 | Bình khử khí (deaerator) |
| `PAC` | 30 | Hệ nước làm mát tuần hoàn (CW) |
| `GN` | 244 | Modbus list các nhà máy xử lý nước |
| `GCB`, `GCF` | 116 + 82 | Khử muối / nước khử khoáng (DMWT) |

**Điện, điều khiển**
| Code | n | Thiết bị |
|------|---|----------|
| `ABA` | 68 | Trạm 500 kV AIS |
| `ADA` | 73 | Trạm 110 kV AIS |
| `UAG`, `BBT`, `BCT` | 9 + 8 + 7 | Máy biến áp |
| `BOE` | 32 | Tủ phân phối / MCC |
| `CYE`, `BG`, `BLN` | 92 + 78 + 41 | Danh mục và tuyến cáp |
| `BLS` | 210 | Chiếu sáng |
| `QCG` | 45 | **Alarm & Set Point List, IO list, hook-up drawing** — giá trị cao nhất khi tra thông số cài đặt |
| `QJC` | 47 | Danh mục van |
| `QH` | 57 | Dầu mỡ bôi trơn và danh mục van |
| `QFB`, `QE` | 17 + 25 | Khí nén đo lường và khí dịch vụ |
| `LD`, `GTC` | 87 + 85 | Modbus / IO list |

**Than, phụ trợ, công trình**
| Code | n | Thiết bị |
|------|---|----------|
| `SGC`, `EAC`, `EAY`, `ECB` | 73 + 102 + 84 + 128 | Vận chuyển than và máng than |
| `SGA` | 77 | Bơm chữa cháy |
| `SA` | 62 | HVAC |
| `UHN`, `UYC`, `UZR`, `UZD`, `UMA` | 89 + 86 + 85 + 73 + 72 | Nhà và kết cấu (Lot-4) |

**Code chung — không phải một thiết bị cụ thể.** Đừng diễn giải các code này
thành tên thiết bị:
| Code | n | Thực chất là |
|------|---|--------------|
| `GEN` | 607 | Báo cáo chạy thử CCC — nhiều hệ thống khác nhau |
| `MV` | 35 | Báo cáo chạy thử CCC |
| `H` | 141 | Lò hơi nói chung |
| `GM`, `EA`, `SG` | 50 + 60 + 58 | Nhóm hệ thống, không phải thiết bị |

**Tra code khi không nằm trong bảng.** Code → nghĩa, đọc tên tài liệu thật:
```sql
SELECT name, doc_number
FROM files
WHERE system_code = 'HDC'
LIMIT 15;
```

Tên thiết bị → code, xếp theo số tài liệu:
```sql
SELECT system_code, COUNT(*) n
FROM files
WHERE name LIKE '%condenser%'
GROUP BY system_code
ORDER BY n DESC
LIMIT 10;
```
Query thứ hai dễ cho kết quả sai: tên tài liệu có thể chứa `BFP` hay `CWP` chỉ
vì đó là nhãn lô hàng, không phải thiết bị của tài liệu. Luôn chạy query thứ
nhất để đọc tên thật trước khi kết luận.

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
FROM chunks_fts
JOIN chunks c ON c.id = chunks_fts.rowid
JOIN files f ON f.id = c.file_id
WHERE chunks_fts MATCH '[từ khóa sự cố]*'
ORDER BY rank LIMIT 15;
```

### Bước 2 — Xác nhận thông số kỹ thuật
```sql
-- Tìm alarm setpoint, design value
SELECT c.heading, c.content
FROM chunks c JOIN files f ON f.id = c.file_id
WHERE f.doc_number LIKE 'VP1-%-I-%'   -- Discipline I&C
  AND c.id IN (SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH '[tag name]*')
LIMIT 30;
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
