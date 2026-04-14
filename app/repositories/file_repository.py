"""SQLite-backed 文件存储仓储。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.domain.file_models import StoredFile, StoredFileRecord


class FileRepository:
    """使用 SQLite BLOB 持久化文件。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = self._resolve_db_path(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._initialize()

    def save(self, file_record: StoredFileRecord) -> StoredFile:
        self._conn.execute(
            """
            INSERT INTO files (
                file_id,
                file_name,
                content_type,
                size_bytes,
                sha256,
                created_at,
                content
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_record.file_id,
                file_record.file_name,
                file_record.content_type,
                file_record.size_bytes,
                file_record.sha256,
                file_record.created_at.isoformat(),
                file_record.content,
            ),
        )
        self._conn.commit()
        return self.to_metadata(file_record)

    def get(self, file_id: str) -> StoredFileRecord | None:
        row = self._conn.execute(
            """
            SELECT file_id, file_name, content_type, size_bytes, sha256, created_at, content
            FROM files
            WHERE file_id = ?
            """,
            (file_id,),
        ).fetchone()
        if row is None:
            return None
        return self._deserialize(row)

    def list_all(self) -> list[StoredFile]:
        rows = self._conn.execute(
            """
            SELECT file_id, file_name, content_type, size_bytes, sha256, created_at
            FROM files
            ORDER BY created_at DESC, file_id DESC
            """
        ).fetchall()
        return [
            StoredFile(
                file_id=row["file_id"],
                file_name=row["file_name"],
                content_type=row["content_type"],
                size_bytes=row["size_bytes"],
                sha256=row["sha256"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def delete(self, file_id: str) -> bool:
        cursor = self._conn.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def close(self) -> None:
        self._conn.close()

    def _initialize(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                file_id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                content_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL,
                content BLOB NOT NULL
            )
            """
        )
        self._conn.commit()

    def _resolve_db_path(self, db_path: str | Path | None) -> str:
        if db_path is None:
            return ":memory:"

        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _deserialize(self, row: sqlite3.Row) -> StoredFileRecord:
        return StoredFileRecord(
            file_id=row["file_id"],
            file_name=row["file_name"],
            content_type=row["content_type"],
            size_bytes=row["size_bytes"],
            sha256=row["sha256"],
            created_at=row["created_at"],
            content=row["content"],
        )

    def to_metadata(self, file_record: StoredFileRecord) -> StoredFile:
        return StoredFile(
            file_id=file_record.file_id,
            file_name=file_record.file_name,
            content_type=file_record.content_type,
            size_bytes=file_record.size_bytes,
            sha256=file_record.sha256,
            created_at=file_record.created_at,
        )
