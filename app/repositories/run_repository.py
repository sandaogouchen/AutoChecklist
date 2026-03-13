from __future__ import annotations

from pathlib import Path
from typing import Any

from app.domain.output_models import OutputBundle
from app.utils.filesystem import ensure_directory, read_json, write_json, write_text


class FileRunRepository:
    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)

    def save(self, run_id: str, payload: Any, filename: str = "run_result.json") -> Path:
        run_dir = self._run_dir(run_id)
        target_path = run_dir / filename
        write_json(target_path, payload)
        return target_path

    def save_text(self, run_id: str, filename: str, content: str) -> Path:
        run_dir = self._run_dir(run_id)
        target_path = run_dir / filename
        write_text(target_path, content)
        return target_path

    def load(self, run_id: str, filename: str = "run_result.json") -> dict[str, Any]:
        return read_json(self._run_dir(run_id) / filename)

    def artifact_path(self, run_id: str, filename: str) -> Path:
        return self._run_dir(run_id) / filename

    def save_bundle(self, run_id: str, bundle: OutputBundle) -> dict[str, str]:
        artifacts: dict[str, str] = {}
        for filename, payload in bundle.file_payloads.items():
            if payload.format == "markdown":
                target_path = self.save_text(run_id, filename, str(payload.content))
            else:
                target_path = self.save(run_id, payload.content, filename)
            artifacts[payload.key] = str(target_path)
        return artifacts

    def _run_dir(self, run_id: str) -> Path:
        return ensure_directory(self.root_dir / run_id)
