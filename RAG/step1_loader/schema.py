from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class RAGDocument:
    """
    Document chuẩn cho toàn bộ pipeline RAG
    """
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadItemResult:
    ok: bool
    doc: Optional[RAGDocument] = None
    error: Optional[str] = None
