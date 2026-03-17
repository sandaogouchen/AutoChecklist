"""运行记录持久化仓储。

基于文件系统的运行记录存储实现，每次运行在 ``output/runs/<run_id>/``
目录下创建独立的子目录，保存 JSON 和文本格式的产物。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.utils.filesystem import ensure_directory, read_json, write_json, write_text


class FileRunRepository:
    """基于文件系统的运行记录仓储。

    每个 run_id 对应一个独立目录，目录下存储该次运行的所有产物文件。
    """

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)

    def save(
        self, run_id: str, payload: dict[str, Any], filename: str = "run_result.json"
    ) -> Path:
        """将字典数据序列化为 JSON 并保存到指定运行目录。

        Args:
            run_id: 运行标识。
            payload: 待序列化的数据。
            filename: 目标文件名，默认为 ``run_result.json``。

        Returns:
            写入的文件路径。
        """
        target_path = self._run_dir(run_id) / filename
        write_json(target_path, payload)
        return target_path

    def save_text(self, run_id: str, filename: str, content: str) -> Path:
        """将纯文本内容保存到指定运行目录。

        Args:
            run_id: 运行标识。
            filename: 目标文件名。
            content: 文本内容。

        Returns:
            写入的文件路径。
        """
        target_path = self._run_dir(run_id) / filename
        write_text(target_path, content)
        return target_path

    def load(self, run_id: str, filename: str = "run_result.json") -> dict[str, Any]:
        """从指定运行目录加载 JSON 文件。

        Raises:
            FileNotFoundError: 文件不存在时抛出。
        """
        return read_json(self._run_dir(run_id) / filename)

    def artifact_path(self, run_id: str, filename: str) -> Path:
        """获取指定产物文件的路径（不检查是否存在）。"""
        return self._run_dir(run_id) / filename

    def _run_dir(self, run_id: str) -> Path:
        """获取或创建指定 run_id 的目录。"""
        return ensure_directory(self.root_dir / run_id)
