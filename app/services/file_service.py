"""文件管理应用服务。"""

from __future__ import annotations

import hashlib
import io
import mimetypes
import re
import zipfile
from pathlib import Path

from app.domain.file_models import StoredFile, StoredFilePage, StoredFileRecord, UploadFileTag
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
        tags: list[str] | None = None,
    ) -> StoredFile:
        normalized_name = self._normalize_file_name(file_name)
        media_type = content_type or mimetypes.guess_type(normalized_name)[0] or "application/octet-stream"
        normalized_tags = self._normalize_tags(tags)
        record = StoredFileRecord(
            file_name=normalized_name,
            content_type=media_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            content=content,
            tags=normalized_tags,
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
        return self._repo.list_visible()

    def list_template_files(self, *, page: int, page_size: int) -> StoredFilePage:
        items, total = self._repo.list_templates(page=page, page_size=page_size)
        return StoredFilePage(items=items, page=page, page_size=page_size, total=total)

    def is_template_file(self, file_id: str) -> bool:
        record = self._repo.get(file_id)
        if record is None:
            return False
        return UploadFileTag.TEMPLATE.value in (record.tags or [])

    def list_run_xmind_files(self) -> list[StoredFile]:
        """返回历史 runs 生成的 XMind 文件列表（不走普通列表过滤逻辑）。"""
        items = self._repo.list_generated_xmind()
        # 兼容旧数据：早期生成物可能统一叫 checklist.xmind，这里按 run_id/created_at 归一化为时间戳名称。
        normalized: list[StoredFile] = []
        for item in items:
            expected_name = self._default_generated_xmind_name(item)
            if expected_name and item.file_name != expected_name:
                try:
                    if self._repo.update_file_name(item.file_id, expected_name):
                        item = item.model_copy(update={"file_name": expected_name})
                except Exception:
                    # 列表接口不应因历史数据改名失败而报错
                    pass
            normalized.append(item)
        return normalized

    def create_admin_xmind_file(
        self,
        *,
        file_name: str,
        content: bytes,
        content_type: str | None = None,
    ) -> StoredFile:
        normalized_name = self._normalize_xmind_file_name(file_name)
        if not zipfile.is_zipfile(io.BytesIO(content)):
            raise ValueError("仅支持上传 XMind 压缩文件")

        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if "content.json" not in archive.namelist():
                raise ValueError("上传文件缺少 XMind 所需的 content.json")

        tags = ["generated_artifact", "type:xmind", "admin_uploaded"]
        return self.create_file(
            file_name=normalized_name,
            content=content,
            content_type=content_type,
            tags=tags,
        )

    def rename_file(self, file_id: str, file_name: str) -> StoredFile | None:
        record = self._repo.get(file_id)
        if record is None:
            return None

        normalized_name = self._normalize_file_name(file_name)
        if not normalized_name.lower().endswith(".xmind"):
            normalized_name = f"{normalized_name}.xmind"

        updated = self._repo.update_file_name(file_id, normalized_name)
        if not updated:
            return None

        # 返回最新元信息
        refreshed = self._repo.get(file_id)
        if refreshed is None:
            return None
        return self._repo.to_metadata(refreshed)

    def rename_generic_file(self, file_id: str, file_name: str) -> StoredFile | None:
        """按 file_id 修改文件名（不限制扩展名）。"""
        record = self._repo.get(file_id)
        if record is None:
            return None

        normalized_name = self._normalize_file_name(file_name)
        updated = self._repo.update_file_name(file_id, normalized_name)
        if not updated:
            return None

        refreshed = self._repo.get(file_id)
        if refreshed is None:
            return None
        return self._repo.to_metadata(refreshed)

    def update_file_content(
        self,
        file_id: str,
        *,
        file_name: str,
        content: bytes,
        content_type: str | None = None,
    ) -> StoredFile | None:
        """按 file_id 覆盖文件内容并更新元信息（file_id 保持不变）。"""
        existing = self._repo.get(file_id)
        if existing is None:
            return None

        normalized_name = self._normalize_file_name(file_name)
        media_type = (
            content_type
            or mimetypes.guess_type(normalized_name)[0]
            or existing.content_type
            or "application/octet-stream"
        )
        sha256 = hashlib.sha256(content).hexdigest()
        size_bytes = len(content)

        updated = self._repo.update_file_content(
            file_id,
            file_name=normalized_name,
            content_type=media_type,
            size_bytes=size_bytes,
            sha256=sha256,
            content=content,
        )
        if not updated:
            return None

        refreshed = self._repo.get(file_id)
        if refreshed is None:
            return None
        return self._repo.to_metadata(refreshed)

    @staticmethod
    def _default_generated_xmind_name(file: StoredFile) -> str | None:
        # 已经是时间戳/可读名就不强制改。
        if not file.file_name or file.file_name == "checklist.xmind":
            run_id = ""
            for tag in (file.tags or []):
                if isinstance(tag, str) and tag.startswith("run:"):
                    run_id = tag.split(":", 1)[1].strip()
                    break
            if run_id:
                return f"{run_id}.xmind"

            # fallback：使用 created_at
            try:
                return f"{file.created_at.astimezone().strftime('%Y-%m-%d_%H-%M-%S')}.xmind"
            except Exception:
                return "generated.xmind"

        # 保持现有名称
        if file.file_name.lower().endswith(".xmind"):
            return file.file_name
        return f"{file.file_name}.xmind"

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

    def _normalize_xmind_file_name(self, file_name: str) -> str:
        normalized = self._normalize_file_name(file_name)
        suffix = Path(normalized).suffix.lower()
        if suffix not in {".xmind", ".mind"}:
            raise ValueError("仅支持 .xmind 或 .mind 文件")

        stem = Path(normalized).stem.strip() or "upload"
        return f"{stem}.xmind"

    @staticmethod
    def _normalize_tags(tags: list[str] | None) -> list[str]:
        ordered: list[str] = []
        for tag in tags or []:
            value = str(tag).strip()
            if value and value not in ordered:
                ordered.append(value)
        return ordered
