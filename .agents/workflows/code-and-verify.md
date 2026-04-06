---
description: Gemini-Claude Collaboration
---

Step 1 (Gemini): Phân tích yêu cầu của người dùng và viết code hoàn chỉnh. Lưu kết quả vào file tạm hoặc Artifact.

Step 2 (Claude): Chuyển ngữ cảnh sang Claude Code. Yêu cầu Claude rà soát code của Gemini ở bước 1.

Step 3: Nếu Claude phản hồi "PASS", hãy merge code. Nếu "FAIL", yêu cầu Gemini sửa lại theo ý kiến của Claude.