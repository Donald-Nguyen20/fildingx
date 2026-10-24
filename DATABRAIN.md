# DATABRAIN.md

Van Phong 1 BOT Thermal Power Plant — Document Intelligence.

This file describes the *data*, not the app: how to answer a technical question or write an operation report from the indexed documents. The Data Brain tab loads it at runtime as its system prompt (`_load_domain_md()` in `ui/claude_assistant/widget.py`), so it must be copied **next to the `.exe`** — not into `_internal/` — when the app is packaged. For the application codebase, see `CLAUDE.md`.

## Mục tiêu
Project này dùng Cowork/Claude để tra cứu tài liệu kỹ thuật và tạo báo cáo vận hành cho **Nhà máy Nhiệt điện Van Phong 1 BOT**. Toàn bộ tài liệu đã được index vào file SQLite `.db` — Claude chỉ cần query DB để lấy thông tin, không cần đọc file gốc.

---

## File DB

| File | Nội dung |
|------|----------|
| `Databasev3.db` | ~8.000 tài liệu kỹ thuật, bản vẽ, O&M manual, commissioning procedure — khoảng 700.000 chunks |

**BASE_PATH gốc:** `D:/3.VP/6.Library/AB Drawings`
(Đường dẫn tuyệt đối trong DB — dùng để mở file gốc nếu cần)

> Đường dẫn DB thật do tab Data Brain truyền vào từng lệnh `db_query.py`, đọc từ `claude_db.json` — dùng đúng đường dẫn đó, không tự ghép lại. `AB Drawings.db` là DB cũ (create_index2.1: bảng `files`, `LIKE`, không có FTS), schema khác, không dùng ở đây.

DB được build bằng **Tools → Create DB** trong app. Bản build từ 2026-10-22 có thêm số trang của chunk, bảng `doc_revisions` và bảng `kks_tags`. Nếu một query báo `no such table: kks_tags`, `no such table: doc_revisions` hoặc `no such column: page_start` thì DB được build trước đó: trả lời bằng `files` / `chunks` như trước (không có số trang, không lọc được revision, không tra được bảng KKS), và nói rõ với người dùng rằng cần build lại DB (ra file mới, hoặc bỏ tick *Incremental*) để có các thông tin đó.

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
    system_code   TEXT,           -- Ví dụ: HNC, HLB, LAC ... (xem mục System codes)
    revision      TEXT,           -- Đã chuẩn hoá, viết hoa: A, B, D, B1, 0, 1, AB0 ...
    is_scanned    INTEGER,        -- 1 = at least half the pages are scans, 0 = mainly text layer
    ocr           INTEGER,        -- how many pages were read by OCR; 0 = none (text layer, or scans NOT OCR'd)
                                  --     (missing in databases built before 2026-10-23)
    page_count    INTEGER,
    file_size_kb  INTEGER,
    indexed_date  TEXT
)
```

> **Lưu ý:** Có 1 bản ghi đặc biệt `name = 'BASE_PATH'` lưu thư mục gốc — luôn loại trừ khi đếm hoặc tìm kiếm file thực.

Một `doc_number` có thể ứng với **nhiều file**: nhiều revision của cùng tài liệu, hoặc cùng revision ở hai định dạng (PDF + DWG). Xem bảng `doc_revisions` để biết file nào là bản mới nhất.

### Bảng `chunks` — nội dung đã chia nhỏ (dùng cho Cowork)
```sql
CREATE TABLE chunks (
    id          INTEGER PRIMARY KEY,
    file_id     INTEGER,    -- FK → files.id
    chunk_index INTEGER,    -- Thứ tự chunk trong file
    heading     TEXT,       -- Tên section/heading (nếu phát hiện được)
    content     TEXT,       -- Nội dung đoạn, tối đa ~1200 ký tự
    char_start  INTEGER,
    char_end    INTEGER,
    page_start  INTEGER,    -- Trang đầu của chunk (slide với PowerPoint)
    page_end    INTEGER     -- Trang cuối; khác page_start khi chunk vắt qua trang
)
```

- PDF, PowerPoint và ảnh được chia **theo từng trang**, nên mỗi chunk biết nó nằm ở trang nào. Trang quá ngắn (bìa, trang chỉ có "Page 3 of 40") được gộp vào trang sau, nên một chunk có thể là `pp. 45–46`.
- Bản vẽ: mỗi sheet là một chunk riêng.
- Word (`.docx`) và Excel (`.xlsx`) không có trang: `page_start` / `page_end` là NULL.
- Bản scan được OCR tối đa 150 trang đầu; bản vẽ scan chỉ OCR khung tên (ghi là trang 1).
- `char_start` / `char_end` là vị trí trong chuỗi các chunk nối lại, **không phải** vị trí trong `files.content` — đừng dùng chúng cho `substr`.

### Bảng `doc_revisions` — file nào là bản mới nhất
```sql
CREATE TABLE doc_revisions (
    file_id     INTEGER PRIMARY KEY,  -- = files.id
    doc_id      TEXT,      -- Mã tài liệu không kèm revision, VIẾT HOA: VP1-C-L3-G-HNC-50056
    revision    TEXT,      -- Revision đọc từ tên file
    rev_rank    INTEGER,   -- Số để so sánh; lớn hơn = mới hơn
    is_latest   INTEGER    -- 1 = bản mới nhất, 0 = đã bị thay thế, NULL = không xác định
)
-- index: idx_docrev_doc ON doc_revisions(doc_id)
```

- Thứ tự revision app đang dùng: chữ cái `A` < `B` < `B1` < … < `Z`, rồi số `0` < `1` < `2` …, rồi as-built `AB0` < `AB1` … Đây là **giả định của bộ index**, chưa đối chiếu với quy trình kiểm soát tài liệu; nếu thứ tự quan trọng cho câu trả lời thì nói rõ điều đó.
- `is_latest = NULL` khi file không có mã tài liệu, hoặc revision không xếp hạng được (vd `AE`). NULL là "không biết", **không** phải "đã cũ" — đừng loại các file này.
- Tài liệu chỉ có một file luôn là `is_latest = 1`. Hai file cùng revision cao nhất (PDF + DWG) đều là 1.

### Bảng `kks_tags` — mã thiết bị KKS tìm thấy trong nội dung
```sql
CREATE TABLE kks_tags (
    id          INTEGER PRIMARY KEY,
    tag         TEXT,      -- Như viết trong tài liệu: "10HAC10 AA001", "20LAB30-CP001"
    tag_norm    TEXT,      -- Bỏ dấu cách và gạch ngang, viết hoa: "10HAC10AA001"
    file_id     INTEGER,   -- FK → files.id
    chunk_id    INTEGER,   -- FK → chunks.id
    page        INTEGER    -- Trang chứa tag (NULL với Word/Excel)
)
-- index: idx_kks_norm ON kks_tags(tag_norm), idx_kks_file ON kks_tags(file_id)
```
Mỗi tag xuất hiện **một dòng cho mỗi chunk** có nó (nhắc nhiều lần trong cùng chunk vẫn một dòng).

### `tag_boxes`
Where a page read by OCR shows each tag: `file_id`, `page`, `tag_norm`, `x0, y0, x1, y1` (fractions 0-1 of the page). It exists so DB Search can show the spot; it holds nothing `kks_tags` does not, so answer tag questions from `kks_tags`. Databases built before it lack the table.

### Virtual tables (FTS5)
- `files_fts` — FTS index trên `files(name, doc_number, system_code, content)`
- `chunks_fts` — FTS index trên `chunks(heading, content)`

---

## Mã KKS

**Format:** `[đơn vị][hệ thống][số]` + tuỳ chọn `[thiết bị]` + tuỳ chọn `[bộ phận]`

| Phần | Dạng | Ví dụ |
|------|------|-------|
| Đơn vị | `00` dùng chung, `10` tổ máy 1, `20` tổ máy 2 | `10` |
| Hệ thống | 3 chữ + 2 số | `HAC10` |
| Thiết bị | 2 chữ + 3 số | `AA001` |
| Bộ phận | 2 chữ + 2 số | `XB01` |

- Chỉ tiền tố `00`, `10`, `20` được nhận là tag. KKS không dùng chữ `I` và `O`, và chỉ chữ in hoa được tính.
- Giữa các phần có thể có dấu cách hoặc gạch ngang. Luôn query trên `tag_norm`: viết hoa, bỏ hết dấu cách và gạch ngang. Ví dụ `10hac10 aa001` → `10HAC10AA001`.
- Tag viết **không có** tiền tố đơn vị (vd `HBK11CP002`) không có trong `kks_tags`.
- `_0LAC30AP010` hay `*0LAB11` là cách vendor viết "cùng tag cho cả hai tổ máy" — **không** phải tag `00`, và không có trong `kks_tags`. Tìm các dạng này bằng `chunks_fts`.
- Phần hệ thống của tag thường trùng với `system_code` của tài liệu: `LAC` là bơm cấp, `HNC` là quạt khói, `HLB` là quạt gió. Nên với tag `10LAC…` có thể tìm thêm tài liệu `system_code = 'LAC'`.

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
SELECT f.name, f.doc_number, f.revision, c.page_start, c.page_end, c.heading, c.content
FROM chunks_fts
JOIN chunks c ON c.id = chunks_fts.rowid
JOIN files f ON f.id = c.file_id
WHERE chunks_fts MATCH 'lube oil temperature*'
ORDER BY rank
LIMIT 10;
```

### Chỉ lấy bản revision mới nhất
Thêm điều kiện này vào bất kỳ query nào có `files f`. Nó loại các file đã bị thay thế, nhưng giữ lại file `is_latest` NULL:
```sql
  AND f.id NOT IN (SELECT file_id FROM doc_revisions WHERE is_latest = 0)
```
Thông số cài đặt, setpoint và quy trình phải lấy từ bản mới nhất. Nếu buộc phải trích bản cũ thì ghi rõ revision và nói là đã bị thay thế.

### Các revision của 1 tài liệu
```sql
SELECT f.name, dr.revision, dr.rev_rank, dr.is_latest
FROM doc_revisions dr
JOIN files f ON f.id = dr.file_id
WHERE dr.doc_id = 'VP1-C-L3-G-HNC-50056'      -- viết hoa
ORDER BY dr.rev_rank DESC;
```

### Tìm trong file cụ thể
```sql
SELECT f.revision, c.page_start, c.page_end, c.heading, c.content
FROM chunks c
JOIN files f ON f.id = c.file_id
WHERE f.doc_number = 'VP1-C-L3-G-HNC-50056'
  AND f.id NOT IN (SELECT file_id FROM doc_revisions WHERE is_latest = 0)
  AND c.id IN (SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'alarm setpoint*')
ORDER BY c.chunk_index
LIMIT 50;          -- một tài liệu lớn có hàng nghìn chunk
```

### Đọc các trang cụ thể của 1 tài liệu
```sql
SELECT c.page_start, c.page_end, c.heading, c.content
FROM chunks c
JOIN files f ON f.id = c.file_id
WHERE f.doc_number = 'VP1-C-L3-G-HNC-50056'
  AND f.id NOT IN (SELECT file_id FROM doc_revisions WHERE is_latest = 0)
  AND c.page_end >= 45 AND c.page_start <= 46      -- trang 45–46
ORDER BY c.chunk_index;
```

### Tra mã KKS
Tài liệu nào nhắc tới một tag, ở trang nào:
```sql
SELECT f.doc_number, f.name, f.revision, k.tag, k.page, dr.is_latest
FROM kks_tags k
JOIN files f ON f.id = k.file_id
LEFT JOIN doc_revisions dr ON dr.file_id = f.id
WHERE k.tag_norm = '10HAC10AA001'
ORDER BY f.doc_number, k.page
LIMIT 50;
```

Cả một hệ thống — dùng `GLOB` (phân biệt hoa thường, dùng được index) với dấu `*` ở cuối:
```sql
SELECT f.doc_number, f.name, COUNT(*) n, GROUP_CONCAT(DISTINCT k.page) pages
FROM kks_tags k
JOIN files f ON f.id = k.file_id
WHERE k.tag_norm GLOB '10HAC10*'
GROUP BY f.id
ORDER BY n DESC
LIMIT 20;
```

Danh sách thiết bị dưới một hệ thống:
```sql
SELECT tag_norm, COUNT(DISTINCT file_id) n_docs
FROM kks_tags
WHERE tag_norm GLOB '10HAC10*'
GROUP BY tag_norm
ORDER BY tag_norm
LIMIT 100;
```

Đọc đoạn văn quanh tag:
```sql
SELECT f.doc_number, c.page_start, c.page_end, c.heading, c.content
FROM kks_tags k
JOIN chunks c ON c.id = k.chunk_id
JOIN files f ON f.id = k.file_id
WHERE k.tag_norm = '10HAC10AA001'
  AND f.id NOT IN (SELECT file_id FROM doc_revisions WHERE is_latest = 0)
LIMIT 10;
```

Luôn tra tag bằng `kks_tags` trước. `chunks_fts` tách `10HAC10 AA001` thành hai từ, nên `MATCH` một tag chỉ tìm được đúng một cách viết.

### Đọc nội dung đầy đủ của 1 file
`db_query.py` chặn mỗi ô ở **4.000 ký tự**, nên `SELECT content FROM files`
không bao giờ trả về cả tài liệu: 952 file trong DB dài hơn 100.000 ký tự và
file dài nhất là 20.858.924 ký tự. Mỗi câu trả lời cũng chỉ có tối đa 200 dòng
và khoảng 120.000 ký tự. Khi bị cắt, kết quả có `"truncated": true` — đừng coi
phần nhận được là toàn bộ.

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
theo trang và heading nên lấy đúng phần cần, có số trang để trích dẫn, thay vì
đọc tuần tự hết tài liệu.

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
từ chữ viết tắt. Số `n` là số file mang code đó, đếm trên bản build trước
2026-10-22 — DB build lại có thể chênh vài file.

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
Tìm các đoạn liên quan đến sự cố. `db_query.py` chỉ nhận câu lệnh bắt đầu bằng `SELECT`, nên đừng đặt dòng chú thích `--` ở đầu query:
```sql
SELECT f.name, f.doc_number, f.revision, c.page_start, c.page_end, c.heading, c.content
FROM chunks_fts
JOIN chunks c ON c.id = chunks_fts.rowid
JOIN files f ON f.id = c.file_id
WHERE chunks_fts MATCH '[từ khóa sự cố]*'
ORDER BY rank LIMIT 15;
```
Nếu sự cố gắn với một thiết bị có mã KKS, tra `kks_tags` trước (mục *Tra mã KKS*): nó chỉ thẳng tới tài liệu và trang nhắc tới thiết bị đó.

### Bước 2 — Xác nhận thông số kỹ thuật
Tìm alarm setpoint, design value — chỉ bản mới nhất:
```sql
SELECT f.doc_number, f.revision, c.page_start, c.page_end, c.heading, c.content
FROM chunks c JOIN files f ON f.id = c.file_id
WHERE f.doc_number LIKE 'VP1-%-I-%'   -- Discipline I&C
  AND f.id NOT IN (SELECT file_id FROM doc_revisions WHERE is_latest = 0)
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
- Tra thiết bị theo mã KKS bằng `kks_tags`, không bằng `MATCH`
- Lấy thông số từ bản revision mới nhất; khi trích bản đã bị thay thế thì nói rõ
- File `ocr > 0` có trang đọc bằng OCR (`ocr` = số trang) — nội dung các trang đó có thể có lỗi nhận dạng ký tự. `is_scanned = 1 AND ocr = 0` là bản scan **chưa** OCR: chỉ tên file tìm được, nội dung trống — đừng kết luận "tài liệu không nhắc tới X". Database cũ chưa có cột `ocr`: khi đó dùng `is_scanned`
- A drawing sheet OCR'd with Create DB's "OCR drawings" (P&IDs whose labels are AutoCAD SHX strokes, scanned drawings) ends its page text with a `[KKS] 10MAW85 AA001 | 10MAW65 AA001 | ...` line: the tags read off the drawing, two-line labels (system part over or beside the equipment part) put back together by position. These tags are in `kks_tags` with the page, so a tag lookup finds the sheet; a tag can still be missing if OCR could not read its label
- Khi trích dẫn trong báo cáo, ghi rõ: `Doc: [doc_number] Rev [revision], p. [page], Section: [heading]`. Lấy trang từ `page_start`–`page_end` của chunk, hoặc `kks_tags.page`; bỏ phần trang khi nó là NULL (Word/Excel), đừng tự đoán
- DB không chứa hình ảnh — nếu cần bản vẽ P&ID thì phải mở file gốc
