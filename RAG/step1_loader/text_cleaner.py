import re
import unicodedata


def clean_vietnamese_text(text: str) -> str:
    """
    Chuẩn hóa text cho RAG:
    - Unicode NFC
    - Bỏ ký tự control
    - Gom whitespace
    """
    if not text:
        return ""

    text = unicodedata.normalize("NFC", text)

    text = "".join(
        ch for ch in text
        if ch in ("\n", "\t") or unicodedata.category(ch)[0] != "C"
    )

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
