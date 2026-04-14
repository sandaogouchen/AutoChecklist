"""文件管理应用服务。"""

from __future__ import annotations

import hashlib
import mimetypes
import re
from pathlib import Path

from app.domain.file_models import StoredFile, StoredFileRecord
from app.repositories.file_repository import FileRepository


class FileService:
    """封装文件上传、查询、删除与运行时落地逻辑。"""

    def __init__(self, repo: FileRepository | None = None) -> None:
        self._repo = repo or FileRepository()

    def create_file(
        self,
        *,
        file_name: str,
        content: bytes,
        content_type: str | None = None,
    ) -> StoredFile:
        normalized_name = self._normalize_file_name(file_name)
        media_type = content_type or mimetypes.guess_type(normalized_name)[0] or "application/octet-stream"
        record = StoredFileRecord(
            file_name=normalized_name,
            content_type=media_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        return self._repo.save(record)

    def get_file(self, file_id: str) -> StoredFile | None:
        record = self._repo.get(file_id)
        if record is None:
            return None
        return self._repo.to_metadata(record)

    def get_file_content(self, file_id: str) -> StoredFileRecord | None:
        return self._repo.get(file_id)

    def list_files(self) -> list[StoredFile]:
        return self._repo.list_all()

    def delete_file(self, file_id: str) -> bool:
        return self._repo.delete(file_id)

    def materialize_to_path(
        self,
        file_id: str,
        *,
        target_dir: str | Path,
        file_name_prefix: str,
    ) -> Path:
        record = self._repo.get(file_id)
        if record is None:
            # 安全边界：仅允许通过上传文件得到的 file_id 访问内容。
            # 禁止将 file_id 作为本地路径回退读取，避免外部请求读取服务端任意本地文件。
            raise FileNotFoundError(f"File not found: {file_id}")

        target_root = Path(target_dir)
        target_root.mkdir(parents=True, exist_ok=True)
        suffix = Path(record.file_name).suffix
        safe_prefix = re.sub(r"[^a-zA-Z0-9_-]+", "_", file_name_prefix).strip("_") or "file"
        output_path = target_root / f"{safe_prefix}_{record.file_id}{suffix}"
        output_path.write_bytes(record.content)
        return output_path.resolve()

    def _normalize_file_name(self, file_name: str) -> str:
        candidate = Path(file_name or "upload.bin").name.strip()
        return candidate or "upload.bin"
