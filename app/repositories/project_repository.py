"""Persistence layer for ProjectContext objects.

默认使用进程内 SQLite ``:memory:``，也支持传入文件路径以获得跨实例持久化。
接口保持窄口，便于未来替换为更完整的 DB 实现。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from app.domain.project_models import ProjectContext


class ProjectRepository:
    """SQLite-backed store keyed by ``ProjectContext.id``."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = self._resolve_db_path(db_path)
        self._conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._initialize()

    # -- write -------------------------------------------------------------

    def save(self, project: ProjectContext) -> ProjectContext:
        """Persist (insert or update) a project context."""
        payload = json.dumps(project.model_dump(mode="json"), ensure_ascii=False)
        self._conn.execute(
            """
            INSERT INTO projects (id, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (project.id, payload, project.updated_at.isoformat()),
        )
        self._conn.commit()
        return project

    def delete(self, project_id: str) -> bool:
        """Remove a project context.  Returns *True* if it existed."""
        cursor = self._conn.execute(
            "DELETE FROM projects WHERE id = ?",
            (project_id,),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # -- read --------------------------------------------------------------

    def get(self, project_id: str) -> Optional[ProjectContext]:
        row = self._conn.execute(
            "SELECT payload FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            return None
        return self._deserialize(row["payload"])

    def list_all(self) -> list[ProjectContext]:
        rows = self._conn.execute(
            "SELECT payload FROM projects ORDER BY updated_at DESC, id ASC"
        ).fetchall()
        return [self._deserialize(row["payload"]) for row in rows]

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def _initialize(self) -> None:
        """Create the storage schema if needed."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def _resolve_db_path(self, db_path: str | Path | None) -> str:
        """Resolve the SQLite DB path and ensure parent directories exist."""
        if db_path is None:
            return ":memory:"

        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _deserialize(self, payload: str) -> ProjectContext:
        """Deserialize a row payload back into ProjectContext."""
        return ProjectContext.model_validate(json.loads(payload))
