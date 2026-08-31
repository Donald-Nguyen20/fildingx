# Cấu trúc UCS.db — ánh xạ để hiển thị đầy đủ như UCS.pdf

File `.db` là SQLite, gồm 25 bảng tiền tố `CAD_`. Dưới đây là toàn bộ cấu trúc và
cách lấy **từng thành phần** trên bản in logic chart.

---

## A. Phân cấp dự án (title block / bộ lọc)

| Bảng | Vai trò | Cột chính |
|------|---------|-----------|
| `CAD_PJ` (1) | Dự án | PROJNO, PROJNAME, PROJNAME1/2 |
| `CAD_PA` (5) | Phân vùng (Plant Area) | PANO, PANAME |
| `CAD_CPU` (1) | CPU | CPUNO, CPUNAME, CPUTYPE, MACROTYPE |
| `CAD_LOOP` (116) | Loop | LOOPNO, LOOPNAME, CPUNO |
| `CAD_DATA` (1822) | **1 dòng / sheet** — bảng chủ | ID, PANO, PASHEETNO, LOOPNO, SHEETNO, SHEETNAME, DRAWNO, EQUIPMENTNO |
| `CAD_SHEET_REV` (492) | Rev thiết kế | DESIGN_NAME, DESIGN_DATE |
| `CAD_IBD_REV` (1701) | Rev + duyệt | DESIGN/CHECK/APPROVE _NAME/_DATE |
| `CAD_TOSMAP` (1822) | Phiên bản xuất | TOSMAP_VERSION, OUTPUTTIME |

**Khung tên góc phải (title block)** = `CAD_DATA` (PANO-SHEETNO, SHEETNAME, DRAWNO)
+ `CAD_IBD_REV`/`CAD_SHEET_REV` (người thiết kế/kiểm/duyệt + ngày).

---

## B. Nội dung 1 sheet (đơn vị = ID trong tất cả bảng con)

Mọi bảng con dùng cột `ID` = mã sheet (vd 620). `IDLINE_ID` = ID*10000 + số dòng.

### B1. Khối logic — `CAD_BLOCK` (44.087)
`BLOCK_ID, EXEORDER, LAYER, SYMBOL, MACROCODE, X, Y, BLK_SUB_NO`
- `X, Y` = toạ độ vẽ khối.
- `MACROCODE` = mã hex khối (→ tra tên/chân qua manual).
- **`EXEORDER`** = **số thứ tự thực thi (số ĐỎ 03/06/09… trên PDF)**.

### B2. Chân khối — `CAD_BLOCK_PIN` (78.298)
`BLOCK_ID, PINNO, PINNAME, SIGNALID, NOT_SIGN, PIN_TYPE`
- Mỗi chân nối tới 1 **net** = `SIGNALID`.
- **Kết nối = các chân CÙNG SIGNALID** (1 nguồn → nhiều đích = fanout).
- `PINNO` 1..n = vào trước, ra sau (map với danh sách chân của manual).
- `NOT_SIGN` = chân có đảo (○) hay không.

### B3. Tham số / nhãn khối — `CAD_BLOCK_PARAM` (61.403)
`BLOCK_ID, PARAMNO, PARAMVALUE`
- **PARAMNO 1** = nhãn nhỏ góc trên-trái khối (vd `35-103`, `A-2`, `21-024`).
- **PARAMNO 2..** = giá trị + đơn vị (vd `A= 50`, `degC`, `R12=99999`, `T=60`).
- → Đây chính là **chú thích dưới/cạnh khối** trong PDF.

### B4. Dây nối — `CAD_LIN` (34.684) + `CAD_LIN_DETAIL` (109.824)
- `CAD_LIN`: `LINE_ID, SIGNALID, REG_TYPE` — mỗi dây mang 1 net.
  (LƯU Ý: `LINE_ID` **KHÔNG** phải block_id — đừng join nhầm.)
- `CAD_LIN_DETAIL`: `LINE_ID, GROUPNO, VERTEXNO, LINETYPE, X, Y`
  - **Toạ độ đỉnh dây CHÍNH XÁC** như bản in.
  - `GROUPNO` = mỗi **nhánh** của dây (fanout → nhiều group).
  - `VERTEXNO` = thứ tự điểm (1,2,…,99 với 99 = điểm cuối).
- Tên net (a0, a1…) hiển thị trên dây = `CAD_LIN.SIGNALID`.

### B5. Tín hiệu vào/ra sheet (cột Line Name / From / To / LID)
- **Đầu ra sheet** — `CAD_ID` (6.984): `SIGNALID, LINENAME, IDLINE_ID` (LID = số cục bộ 11/12…, LINENAME = tên).
- **Đầu vào sheet** — chân E0B1 mang tag ngoài (vd `HA212-18`); tên lấy bằng
  giải mã tag: PA+PASHEETNO → sheet (qua `CAD_DATA`) → `CAD_ID[sheet,sig]`.
- `CAD_INP` (371): danh sách input dạng bảng (ít dùng trong file này).
- **From / To** = LOOPNO+SHEETNO của sheet nguồn/đích, tra qua
  `CAD_ID_CRS` (IDLINE_ID → PANO+PASHEETNO) → `CAD_DATA`.
- `CAD_SIGNAL` (5.633): tín hiệu hệ thống toàn cục (SYSTEMLINE → LINENAME).

### B6. Tag thiết bị (KKS) — `CAD_TAG_FID` (46.435) + `CAD_TAG_PARAM` (1.244)
`BLOCK_ID, FID, FIDSUFFIX, FIDVALUE`
- `FIDSUFFIX='Ttag'` = mã tag KKS (vd `10HFE61EZ001`).
- `TID`, `STN`, `TDes1` = Tag ID, station, mô tả.
- **`ISTD`/`OSTD`** = **mô tả từng chân vào/ra của riêng instance** (vd
  "PULV A PAFL CTRL MAN", "PULV A PAFL CTRL AUTO"…) — quý hơn tên chân chung.
- `CAD_TAG_PARAM`: BLOCK_ID → TAGTYPE, TAGCODE.

### B7. Đồ thị / bảng / chữ tự do
- `CAD_GRAPH` (912): đồ thị hàm F(x) (giới hạn X/Y) gắn vào khối F(x).
- `CAD_GRAPH_ASSIST` (27.360): đường phụ trợ của đồ thị.
- `CAD_TABLE` (911): bảng dữ liệu nhúng trên sheet.
- `CAD_TEXT` (46): chữ chú thích tự do (vd "(NOT USED)", "(U2: To JI446)").

---

## C. Thuật toán dựng lại 1 sheet (đầy đủ)

```
1. Header: CAD_DATA[ID] + CAD_IBD_REV[ID]  → khung tên.
2. Khối:   CAD_BLOCK[ID]  → vị trí X/Y, macro, EXEORDER.
3. Chân:   CAD_BLOCK_PIN  → net mỗi chân; map PINNO ↔ tên chân (manual).
4. Tham số:CAD_BLOCK_PARAM → nhãn góc + giá trị/đơn vị dưới khối.
5. Dây:    CAD_LIN + CAD_LIN_DETAIL → vẽ polyline chính xác theo vertex;
           tên net = CAD_LIN.SIGNALID (hiện trên dây).
6. Vào/Ra: E0B1 trái = input (giải mã tag → Line Name/From/LID),
           CAD_ID = output (LINENAME/LID); To qua CAD_ID_CRS.
7. Tag:    CAD_TAG_FID (Ttag/TID/TDes1 + ISTD/OSTD cho từng chân).
8. Phụ:    CAD_GRAPH/TABLE/TEXT nếu sheet có.
```

## D. Trạng thái hiện tại của app (T-Designer Lite)

| Thành phần | Bảng nguồn | App đã có? |
|---|---|---|
| Khối + vị trí | CAD_BLOCK | ✅ |
| Tên/số chân | manual + CAD_BLOCK_PIN | ✅ |
| Kết nối (fanout) | CAD_BLOCK_PIN theo SIGNALID | ✅ |
| Line Name / From / LID / To | CAD_ID(_CRS)/CAD_DATA | ✅ |
| Tag KKS + mô tả | CAD_TAG_FID | ✅ |
| **Số thực thi (đỏ)** | CAD_BLOCK.EXEORDER | ⬜ chưa |
| **Nhãn + tham số khối** | CAD_BLOCK_PARAM | ⬜ chưa |
| **Tên net trên dây** | CAD_LIN.SIGNALID | ⬜ chưa |
| **Dây vẽ đúng toạ độ** | CAD_LIN_DETAIL | ⬜ (đang vẽ vuông tự tính) |
| **Mô tả chân theo instance** | CAD_TAG_FID ISTD/OSTD | ⬜ chưa |
| Khung tên / rev | CAD_DATA/CAD_IBD_REV | ⬜ chưa |
| Đồ thị / bảng / text | CAD_GRAPH/TABLE/TEXT | ⬜ chưa |
