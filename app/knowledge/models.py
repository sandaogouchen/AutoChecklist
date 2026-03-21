"""知识检索领域模型。

定义知识文档、检索结果等数据结构。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class KnowledgeDocument(BaseModel):
    """已索引的知识文档元数据。"""

    doc_id: str
    file_name: str
    file_path: str
    file_size_bytes: int = 0
    md5_hash: str = ""
    indexed_at: Optional[datetime] = None
    entity_count: int = 0


class RetrievalResult(BaseModel):
    """知识检索结果。"""

    content: str = ""
    sources: list[str] = Field(default_factory=list)
    mode: str = "hybrid"
    success: bool = True
    error_message: str = ""


class KnowledgeStatus(BaseModel):
    """知识库状态信息。"""

    enabled: bool = False
    ready: bool = False
    document_count: int = 0
    last_indexed_at: Optional[datetime] = None
    working_dir: str = ""
