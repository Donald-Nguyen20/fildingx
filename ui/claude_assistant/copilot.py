"""ui/claude_assistant/copilot.py — Co-Pilot Sự Cố.

Orchestrator điều phối Claude suy luận đa tầng (multi-hop) trên DB tài liệu VP1:
    triệu chứng → thiết bị → alarm setpoint → interlock → O&M troubleshooting
                → cây nguyên nhân gốc (có bằng chứng trích dẫn) → báo cáo KV-OP.

Module thuần logic, KHÔNG phụ thuộc Qt — dễ test và tái dùng.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from typing import Optional


# ── System prompt: hướng dẫn Claude chạy quy trình chẩn đoán ──────────────

def build_diagnosis_system_prompt(db_path: str, claude_md: str = "") -> str:
    """Tạo system prompt cho chế độ chẩn đoán đa hop."""
    instr = f"""Bạn là KỸ SƯ CHẨN ĐOÁN SỰ CỐ của Nhà máy Nhiệt điện Van Phong 1 BOT.
Nhiệm vụ: từ MỘT triệu chứng vận hành, suy luận ra cây nguyên nhân gốc, mỗi
nguyên nhân phải kèm BẰNG CHỨNG trích dẫn chính xác từ tài liệu trong DB.

File DB tài liệu: "{db_path}"
Truy vấn DB CHỈ bằng lệnh Bash (read-only, chỉ SELECT):
  python db_query.py "{db_path}" "SQL query"

QUY TRÌNH SUY LUẬN — thực hiện tuần tự, mỗi bước 1-2 query:

  ① Xác định THIẾT BỊ + system_code từ triệu chứng:
     python db_query.py "{db_path}" "SELECT DISTINCT system_code,discipline,name,doc_number FROM files WHERE id IN (SELECT rowid FROM files_fts WHERE files_fts MATCH '<từ khóa thiết bị>*') AND name!='BASE_PATH' LIMIT 8"

  ② Lấy ALARM / TRIP SETPOINT (ưu tiên discipline I — I&C):
     python db_query.py "{db_path}" "SELECT f.doc_number,c.heading,c.content FROM chunks c JOIN files f ON f.id=c.file_id WHERE c.id IN (SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'alarm OR trip OR setpoint') AND f.system_code='<code>' ORDER BY rank LIMIT 6"

  ③ Lấy INTERLOCK / LOGIC (cái gì trip cái gì):
     tra chunks_fts MATCH 'interlock OR trip OR protection'

  ④ Lấy mục TROUBLESHOOTING trong O&M Manual:
     tra chunks_fts MATCH '<triệu chứng>*' trên đúng doc_number của O&M

  ⑤ (nếu có) Đối chiếu sự cố cũ tương tự.

NGUYÊN TẮC BẰNG CHỨNG:
- KHÔNG bịa. Mỗi evidence phải lấy từ kết quả query thật: doc_number + heading + 1 đoạn quote ngắn.
- Nếu không tìm được dữ liệu cho 1 nguyên nhân → giảm confidence hoặc bỏ.
- Confidence các nguyên nhân nên cộng lại xấp xỉ 100.

ĐẦU RA — sau khi suy luận xong, viết:
1) Một đoạn tóm tắt ngắn bằng tiếng Việt cho người đọc.
2) MỘT khối JSON đặt trong ```json ... ``` theo ĐÚNG schema sau (không thêm field lạ):

```json
{{
  "symptom": "<triệu chứng người dùng nhập>",
  "equipment": "<tên thiết bị>",
  "system_code": "<vd HNC>",
  "causes": [
    {{
      "title": "<tên nguyên nhân>",
      "confidence": 70,
      "rationale": "<giải thích ngắn vì sao>",
      "evidence": [
        {{
          "doc_number": "<doc_number thật>",
          "section": "<heading thật>",
          "quote": "<đoạn trích ngắn từ content>"
        }}
      ]
    }}
  ]
}}
```

Khối JSON là BẮT BUỘC và phải nằm ở CUỐI câu trả lời. CHỈ dùng SELECT, không chạy lệnh shell khác."""
    if claude_md:
        return claude_md.strip() + "\n\n" + instr
    return instr


def build_diagnosis_prompt(symptom: str) -> str:
    """Prompt người dùng cho 1 lượt chẩn đoán."""
    return (
        f"Triệu chứng sự cố cần chẩn đoán:\n\"{symptom.strip()}\"\n\n"
        "Hãy chạy quy trình suy luận đa tầng rồi trả về tóm tắt + khối JSON cây nguyên nhân."
    )


# ── Parse khối JSON kết quả từ stream text của Claude ─────────────────────

_JSON_FENCE_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def extract_diagnosis_json(full_text: str) -> Optional[dict]:
    """Trích khối ```json``` cuối cùng trong câu trả lời. None nếu không có / lỗi."""
    if not full_text:
        return None

    candidates = _JSON_FENCE_RE.findall(full_text)
    if not candidates:
        # fallback: thử tìm object JSON cuối có "causes"
        brace = _last_balanced_object(full_text)
        candidates = [brace] if brace else []

    for raw in reversed(candidates):
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "causes" in data:
                return _normalize(data)
        except Exception:
            continue
    return None


def _last_balanced_object(text: str) -> Optional[str]:
    """Tìm object {...} cân bằng ngoặc cuối cùng chứa chuỗi 'causes'."""
    idx = text.rfind('"causes"')
    if idx == -1:
        return None
    start = text.rfind("{", 0, idx)
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _normalize(data: dict) -> dict:
    """Chuẩn hoá kiểu dữ liệu để panel render an toàn."""
    out = {
        "symptom": str(data.get("symptom", "")),
        "equipment": str(data.get("equipment", "")),
        "system_code": str(data.get("system_code", "")),
        "causes": [],
    }
    for c in (data.get("causes") or []):
        if not isinstance(c, dict):
            continue
        try:
            conf = int(round(float(c.get("confidence", 0))))
        except Exception:
            conf = 0
        evidence = []
        for e in (c.get("evidence") or []):
            if not isinstance(e, dict):
                continue
            evidence.append({
                "doc_number": str(e.get("doc_number", "")),
                "section": str(e.get("section", "")),
                "quote": str(e.get("quote", "")),
            })
        out["causes"].append({
            "title": str(c.get("title", "Nguyên nhân")),
            "confidence": max(0, min(100, conf)),
            "rationale": str(c.get("rationale", "")),
            "evidence": evidence,
        })
    # xếp hạng giảm dần theo confidence
    out["causes"].sort(key=lambda x: x["confidence"], reverse=True)
    return out


# ── Sinh báo cáo KV-OP từ kết quả chẩn đoán ──────────────────────────────

def build_report_prompt(diagnosis: dict, db_path: str) -> str:
    """Prompt yêu cầu Claude sinh file .docx KV-OP từ cây nguyên nhân."""
    diag_json = json.dumps(diagnosis, ensure_ascii=False, indent=2)
    return (
        "Từ kết quả chẩn đoán dưới đây, hãy SINH BÁO CÁO VẬN HÀNH KV-OP (.docx).\n\n"
        "Dùng module có sẵn `report_helper.py` bằng cách viết 1 script Python rồi chạy qua Bash:\n"
        "  from report_helper import new_doc, add_title_block, add_section, add_para, \\\n"
        "      add_bullet, add_data_table, add_sign_off, add_attachment_list, save_report\n\n"
        "Báo cáo gồm đủ 7 phần: Introduction, Abnormal Status, Analysis (Root Cause), "
        "Suggestion, Execution Plan (bảng Action/Responsible/Target Date), Conclusion, Attachment.\n"
        "Phần Analysis phải liệt kê các nguyên nhân theo confidence và GHI RÕ trích dẫn "
        "'Doc: <doc_number>, Section: <heading>' cho mỗi luận điểm.\n"
        f"DB tham chiếu nếu cần tra thêm: \"{db_path}\"\n\n"
        "Sau khi save, in ra đường dẫn file. Kết quả chẩn đoán (JSON):\n"
        f"```json\n{diag_json}\n```"
    )


# ── Mở file gốc theo doc_number (dùng cho nút 'Mở file' ở panel) ──────────

def resolve_source_path(
    db_path: str,
    doc_number: str = "",
    rel_path: str = "",
) -> Optional[str]:
    """Trả về đường dẫn tuyệt đối của file gốc, hoặc None."""
    if not db_path or not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()

        cur.execute("SELECT path FROM files WHERE name='BASE_PATH' LIMIT 1")
        row = cur.fetchone()
        base = row[0] if row else ""

        rp = rel_path
        if not rp and doc_number:
            cur.execute(
                "SELECT path FROM files WHERE doc_number=? AND name!='BASE_PATH' LIMIT 1",
                (doc_number,),
            )
            r = cur.fetchone()
            rp = r[0] if r else ""
        conn.close()

        if not rp:
            return None
        return os.path.join(base, rp) if base else rp
    except Exception:
        return None
