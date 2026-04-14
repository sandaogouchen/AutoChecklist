"""文件存储领域模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class StoredFile(BaseModel):
    """文件元数据。"""

    file_id: str = Field(default_factory=lambda: uuid4().hex)
    file_name: str
    content_type: str = "application/octet-stream"
    size_bytes: int
    sha256: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StoredFileRecord(StoredFile):
    """包含文件原始内容的完整记录。"""

    content: bytes
