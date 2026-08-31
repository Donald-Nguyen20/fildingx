# Đề xuất giao diện — Finding / VP1 Document Intelligence

Thư mục này chứa các hướng giao diện đề xuất. Mỗi hướng gồm file `.html` (mở
được bằng trình duyệt, tự chạy, không cần internet) và ảnh `.png` chụp ở 2x.

Đây là **mockup để bàn bạc**, không phải code sẽ chạy. Chưa có gì trong `ui/`
bị thay đổi. Nếu chọn một hướng để làm thật thì toàn bộ chuỗi hiển thị sẽ viết
bằng tiếng Anh theo quy ước của dự án — ở đây để tiếng Việt cho dễ đọc khi cân nhắc.

---

## F — Giao diện mới cho CẢ APP ★ đang đề xuất

Thư mục `F_app_shell/`. Bốn màn hình, **một** hệ thiết kế, **một** thanh điều hướng.
Bốn công cụ vẫn chạy riêng lẻ y như hiện tại — không gộp tìm kiếm, không gộp DB.

| File | Màn hình | Thay đổi chính so với hiện tại |
|------|----------|-------------------------------|
| `F_app_shell/F1_file_search.png` | File Search | Preview thành panel liền cạnh kết quả (bỏ khỏi rail); cú pháp tìm kiếm hiện thành chip bấm được thay vì nằm trong placeholder; kết quả nhóm theo Lot; cột trạng thái `có text` / `quét OCR` |
| `F_app_shell/F2_db_search.png` | DB Search | Cột lọc trái (Ngành / Lot / Mã hệ thống / Chất lượng); dòng meta `61 đoạn khớp · 23 tài liệu · 25 ms`; panel phải render trang gốc có highlight |
| `F_app_shell/F3_notebooklm.png` | NotebookLM | 7 nút chen chúc góc phải gom còn 2 nút + 1 menu; panel nguồn cho biết nguồn nào **thật sự được trích** |
| `F_app_shell/F4_data_brain.png` | Data Brain | Bố cục của E đưa lên khung chung: `Ask` thành nút chính, 6 nút còn lại nhỏ hơn; chat có chip trích dẫn bấm được; orb + thẻ chứng cứ có `✓ đã đối chiếu với DB` |

Hai file dùng chung:

- `F_app_shell/shell.css` — **một** file token thay cho 163 mã màu / 99 lần
  `setStyleSheet` / 7 giá trị bo góc / 10 cỡ chữ / 49 gradient đang rải rác trong `ui/`.
- `F_app_shell/_nav.html` — **một** thanh điều hướng thay cho rail icon trái
  **cộng** thanh tab trên. Gom 8 điểm đến vào 3 nhóm: Tra cứu / Nghiên cứu / Kho.
  Chân thanh luôn hiện trạng thái kho: `8,052 đã lập chỉ mục · 78% có lớp text ·
  1,771 bản quét OCR`.

### Vấn đề F giải quyết

**App hiện có hai hệ thống điều hướng chồng lên nhau.** Rail icon bên trái
(`Containers / Tools / Add-ons / Preview`) *và* thanh tab trên đầu
(`File Search / DB Search / NotebookLM / Data Brain`). Tám điểm đến, hai kiểu tư
duy khác nhau, người dùng phải học cả hai và không có quy tắc nào nói cái gì nằm
ở đâu. Đây là lỗi cấu trúc, nặng hơn chuyện màu sắc.

### Chi phí thật

Phần lớn công nằm ở `ui/notebooklm_window.py` (5,011 dòng / 15,920 dòng toàn bộ
`ui/`). Ba màn hình còn lại chủ yếu là đổi style + di chuyển widget. Nếu làm,
nên làm theo thứ tự: `shell.css` (token) → nav → F1 → F2 → F4 → F3.

---

## E — Chỉ riêng tab Data Brain

`E_databrain_refresh.png`. Giữ nguyên 4 tab chạy riêng lẻ, giữ 7 nút, giữ chat,
giữ orb. Chỉ sắp xếp lại + thống nhất design token trong phạm vi một tab.
Là phương án nhỏ nhất, rủi ro thấp nhất — vẫn dùng được nếu không muốn động vào
3 tab kia. F4 chính là E đặt lên khung chung của F.

---

## A · B · C · D — Bốn hướng khảo sát ban đầu

| File | Hướng | Ý chính |
|------|-------|---------|
| `A_console.png` | **Unified Console** | Một ô hỏi duy nhất cho cả 4 tab. Trả lời có trích dẫn inline, bên phải là bảng chứng cứ mở được PDF gốc. |
| `B_evidence_desk.png` | **Evidence Desk** | Ba cột: phân tích \| trang tài liệu gốc \| khung dựng báo cáo KV-OP 7 phần. Kéo đoạn văn từ tài liệu sang báo cáo. |
| `C_control_room_light.png` | **Control Room (nền sáng)** | Bộ lọc theo Ngành/Lot/Mã hệ thống, bảng kết quả dày, panel kiểm tra bên phải. Hiện rõ chất lượng chỉ mục (78% có text, 1,771 bản quét OCR). |
| `D_orb_navigator.png` | **Orb as Navigator** | Quả cầu neural làm giao diện chính, không phải trang trí. Ấn tượng nhất về thị giác, yếu nhất về công năng. |

`_orb.png` là ảnh render **thật** từ `NeuralOrbWidget` hiện tại (900×900, 200
tick, 260 kết quả tìm kiếm, 5 nguồn trích dẫn) — dùng làm nền cho hướng D, ô
nguồn ở hướng A và cột phải của E / F4, để mockup không vẽ lại một quả cầu
tưởng tượng.

### Ghi chú thẳng thắn về từng hướng

- **A** — gộp 4 ô tìm kiếm thành 1. **Đã loại** vì trái với yêu cầu giữ 4 công
  cụ chạy riêng lẻ.
- **B** — sát với công việc thật nhất (viết báo cáo KV-OP), nhưng phải làm thêm
  bộ render trang PDF có highlight và khung xuất `.docx` theo 7 mục. Ý tưởng
  "chèn đoạn vào báo cáo" đã được giữ lại trong F2 và F4.
- **C** — nền sáng, dày dữ liệu, hợp phòng điều khiển và in ra giấy. Điểm đáng
  giá nhất là nó **thừa nhận** dữ liệu không hoàn hảo: hiện luôn tỉ lệ OCR để
  không ai tin nhầm một con số đọc sai từ bản quét. Ý này đã được giữ lại trong
  chân thanh nav của F.
- **D** — đẹp nhưng nhãn vùng đè lên chính quả cầu (thấy rõ ở `11_Training` và
  `12_O&M` trong ảnh). Quả cầu hiện không mã hoá cấu trúc tra cứu được: nhìn
  8,052 tài liệu thành một đám xanh không giúp tìm ra một ngưỡng alarm. Nên giữ
  vai trò phụ, đừng làm giao diện chính.
