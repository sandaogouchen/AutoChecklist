"""SQLite-backed 文件存储仓储。"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from app.domain.file_models import StoredFile, StoredFileRecord


class FileRepository:
    """使用 SQLite BLOB 持久化文件。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = self._resolve_db_path(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # sqlite3 connection 在多线程并发下并非完全线程安全；
        # 通过锁串行化同一连接上的 DB 操作，避免偶发的 InterfaceError/OperationalError。
        self._lock = threading.RLock()
        self._initialize()

    def save(self, file_record: StoredFileRecord) -> StoredFile:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO files (
                    file_id,
                    file_name,
                    content_type,
                    size_bytes,
                    sha256,
                    created_at,
                    tags,
                    content
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_record.file_id,
                    file_record.file_name,
                    file_record.content_type,
                    file_record.size_bytes,
                    file_record.sha256,
                    file_record.created_at.isoformat(),
                    json.dumps(file_record.tags or [], ensure_ascii=False),
                    file_record.content,
                ),
            )
            self._conn.commit()
        return self.to_metadata(file_record)

    def get(self, file_id: str) -> StoredFileRecord | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT file_id, file_name, content_type, size_bytes, sha256, created_at, tags, content
                FROM files
                WHERE file_id = ?
                """,
                (file_id,),
            ).fetchone()
        if row is None:
            return None
        return self._deserialize(row)

    def list_all(self) -> list[StoredFile]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT file_id, file_name, content_type, size_bytes, sha256, created_at, tags
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
                tags=self._parse_tags(row["tags"]),
            )
            for row in rows
        ]

    def list_visible(self) -> list[StoredFile]:
        """返回普通文件列表（默认不包含生成产物）。"""
        return self._list_metadata(exclude_tags=["generated_artifact", "template"])

    def list_templates(self, *, page: int, page_size: int) -> tuple[list[StoredFile], int]:
        """返回模板文件分页结果。"""
        offset = max(page - 1, 0) * page_size
        items = self._list_metadata(
            include_tags=["template"],
            exclude_tags=["generated_artifact"],
            limit=page_size,
            offset=offset,
        )
        total = self._count_metadata(
            include_tags=["template"],
            exclude_tags=["generated_artifact"],
        )
        return items, total

    def list_generated_xmind(self) -> list[StoredFile]:
        """返回历史 runs 生成的 XMind 产物列表。"""
        return self._list_metadata(include_tags=["generated_artifact", "type:xmind"])

    def update_file_name(self, file_id: str, file_name: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE files SET file_name = ? WHERE file_id = ?",
                (file_name, file_id),
            )
            self._conn.commit()
        return cursor.rowcount > 0

    def update_file_content(
        self,
        file_id: str,
        *,
        file_name: str,
        content_type: str,
        size_bytes: int,
        sha256: str,
        content: bytes,
    ) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE files
                SET file_name = ?, content_type = ?, size_bytes = ?, sha256 = ?, content = ?
                WHERE file_id = ?
                """,
                (file_name, content_type, size_bytes, sha256, content, file_id),
            )
            self._conn.commit()
        return cursor.rowcount > 0

    def delete(self, file_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
            self._conn.commit()
        return cursor.rowcount > 0

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _initialize(self) -> None:
        with self._lock:
            # 提升并发可用性（尽力设置，失败不影响主流程）。
            try:
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")
                self._conn.execute("PRAGMA busy_timeout=5000")
            except Exception:
                pass

            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    file_id TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    content BLOB NOT NULL
                )
                """
            )

            # 兼容旧库：若缺少 tags 列则进行就地迁移。
            self._ensure_column(
                table="files",
                column="tags",
                ddl="ALTER TABLE files ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'",
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
            tags=self._parse_tags(row["tags"]),
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
            tags=list(file_record.tags or []),
        )

    def _list_metadata(
        self,
        *,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[StoredFile]:
        query = [
            "SELECT file_id, file_name, content_type, size_bytes, sha256, created_at, tags",
            "FROM files",
        ]
        where_sql, params = self._build_tag_filters(
            include_tags=include_tags,
            exclude_tags=exclude_tags,
        )
        if where_sql:
            query.append(where_sql)
        query.append("ORDER BY created_at DESC, file_id DESC")
        if limit is not None:
            query.append("LIMIT ?")
            params.append(limit)
        if offset is not None:
            query.append("OFFSET ?")
            params.append(offset)

        with self._lock:
            rows = self._conn.execute("\n".join(query), tuple(params)).fetchall()
        return [
            StoredFile(
                file_id=row["file_id"],
                file_name=row["file_name"],
                content_type=row["content_type"],
                size_bytes=row["size_bytes"],
                sha256=row["sha256"],
                created_at=row["created_at"],
                tags=self._parse_tags(row["tags"]),
            )
            for row in rows
        ]

    def _count_metadata(
        self,
        *,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
    ) -> int:
        query = ["SELECT COUNT(1) AS total", "FROM files"]
        where_sql, params = self._build_tag_filters(
            include_tags=include_tags,
            exclude_tags=exclude_tags,
        )
        if where_sql:
            query.append(where_sql)
        with self._lock:
            row = self._conn.execute("\n".join(query), tuple(params)).fetchone()
        return int(row["total"] if row is not None else 0)

    @staticmethod
    def _build_tag_filters(
        *,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
    ) -> tuple[str, list[object]]:
        clauses: list[str] = []
        params: list[object] = []

        for tag in include_tags or []:
            clauses.append("tags LIKE ?")
            params.append(FileRepository._tag_like(tag))

        for tag in exclude_tags or []:
            clauses.append("tags NOT LIKE ?")
            params.append(FileRepository._tag_like(tag))

        if not clauses:
            return "", params
        return "WHERE " + " AND ".join(clauses), params

    @staticmethod
    def _tag_like(tag: str) -> str:
        return f'%"{tag}"%'

    def _ensure_column(self, *, table: str, column: str, ddl: str) -> None:
        try:
            rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
            cols = {row["name"] for row in rows}
        except Exception:
            return
        if column not in cols:
            self._conn.execute(ddl)

    @staticmethod
    def _parse_tags(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(x) for x in parsed]
