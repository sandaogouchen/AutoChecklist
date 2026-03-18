"""Checklist 模板文件持久化仓储。

基于文件系统存储模板，每个模板保存为独立的 YAML 文件。
支持内置模板（只读）和用户自定义模板（可读写）两类存储区域。

存储结构：
    templates/
    ├── builtin/          # 内置模板（只读）
    │   ├── web-app-general.yaml
    │   └── ...
    └── custom/           # 自定义模板（可读写）
        ├── {template_id}.yaml
        └── ...
"""

from __future__ import annotations

import fcntl
import logging
import tempfile
from pathlib import Path
from typing import Optional

import yaml

from app.domain.template_models import ChecklistTemplate

logger = logging.getLogger(__name__)


class TemplateRepository:
    """基于文件系统的模板仓储。

    启动时扫描 builtin 和 custom 目录，加载所有模板到内存索引。
    所有写操作仅针对 custom 目录。
    """

    def __init__(
        self,
        builtin_dir: str | Path = "templates/builtin",
        custom_dir: str | Path = "templates/custom",
    ) -> None:
        self.builtin_dir = Path(builtin_dir)
        self.custom_dir = Path(custom_dir)
        self._index: dict[str, ChecklistTemplate] = {}
        self._ensure_dirs()
        self._load_all()

    def _ensure_dirs(self) -> None:
        """确保存储目录存在。"""
        self.builtin_dir.mkdir(parents=True, exist_ok=True)
        self.custom_dir.mkdir(parents=True, exist_ok=True)

    def _load_all(self) -> None:
        """扫描内置和自定义目录，加载所有模板到内存索引。"""
        # 加载内置模板
        for yaml_file in sorted(self.builtin_dir.glob("*.yaml")):
            try:
                template = self._read_yaml(yaml_file, source="builtin")
                if template:
                    self._index[template.id] = template
                    logger.info("加载内置模板: %s (%s)", template.metadata.name, template.id)
            except Exception:
                logger.exception("加载内置模板失败: %s", yaml_file)

        # 加载自定义模板
        for yaml_file in sorted(self.custom_dir.glob("*.yaml")):
            try:
                template = self._read_yaml(yaml_file, source="custom")
                if template:
                    self._index[template.id] = template
                    logger.info("加载自定义模板: %s (%s)", template.metadata.name, template.id)
            except Exception:
                logger.exception("加载自定义模板失败: %s", yaml_file)

        logger.info(
            "模板索引加载完成: %d 个内置, %d 个自定义",
            sum(1 for t in self._index.values() if t.source == "builtin"),
            sum(1 for t in self._index.values() if t.source == "custom"),
        )

    def _read_yaml(self, path: Path, source: str) -> Optional[ChecklistTemplate]:
        """从 YAML 文件读取并解析为模板对象。"""
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            logger.warning("YAML 文件内容不是 dict: %s", path)
            return None

        # 如果文件中没有 id 字段，使用文件名（去除扩展名）作为 id
        if "id" not in data:
            data["id"] = path.stem

        data["source"] = source
        return ChecklistTemplate.model_validate(data)

    def get(self, template_id: str) -> Optional[ChecklistTemplate]:
        """根据 ID 获取模板。"""
        return self._index.get(template_id)

    def list_all(
        self,
        *,
        source: Optional[str] = None,
        tag: Optional[str] = None,
        project_type: Optional[str] = None,
    ) -> list[ChecklistTemplate]:
        """列出所有模板，支持过滤。

        Args:
            source: 按来源过滤 ("builtin" / "custom")。
            tag: 按标签过滤。
            project_type: 按适用项目类型过滤。

        Returns:
            符合条件的模板列表。
        """
        templates = list(self._index.values())

        if source:
            templates = [t for t in templates if t.source == source]

        if tag:
            templates = [t for t in templates if tag in t.metadata.tags]

        if project_type:
            templates = [
                t for t in templates
                if project_type in t.metadata.applicable_project_types
            ]

        return templates

    def save(self, template: ChecklistTemplate) -> ChecklistTemplate:
        """保存模板到自定义目录。

        使用原子写入（先写临时文件再 rename）防止写入中断导致损坏。
        使用文件锁防止并发写入冲突。

        Args:
            template: 待保存的模板。

        Returns:
            保存后的模板。

        Raises:
            PermissionError: 尝试保存内置模板。
        """
        if template.source == "builtin":
            raise PermissionError("内置模板不可修改")

        target_path = self.custom_dir / f"{template.id}.yaml"
        data = template.model_dump(mode="json")

        # 序列化为 YAML
        yaml_content = yaml.safe_dump(
            data,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

        # 原子写入：先写临时文件，再 rename
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self.custom_dir),
                suffix=".yaml.tmp",
            )
            tmp_file = Path(tmp_path)
            try:
                with open(fd, "w", encoding="utf-8") as f:
                    # 文件锁
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    try:
                        f.write(yaml_content)
                        f.flush()
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                # 原子 rename
                tmp_file.rename(target_path)
            except Exception:
                # 清理临时文件
                if tmp_file.exists():
                    tmp_file.unlink()
                raise
        except OSError as e:
            logger.error("写入模板文件失败: %s, 错误: %s", target_path, e)
            raise

        # 更新内存索引
        self._index[template.id] = template
        logger.info("保存模板: %s (%s)", template.metadata.name, template.id)
        return template

    def delete(self, template_id: str) -> bool:
        """删除自定义模板。

        Args:
            template_id: 模板 ID。

        Returns:
            是否成功删除。

        Raises:
            PermissionError: 尝试删除内置模板。
        """
        template = self._index.get(template_id)
        if template is None:
            return False

        if template.source == "builtin":
            raise PermissionError("内置模板不可删除")

        # 删除文件
        target_path = self.custom_dir / f"{template_id}.yaml"
        if target_path.exists():
            target_path.unlink()

        # 移除内存索引
        self._index.pop(template_id, None)
        logger.info("删除模板: %s", template_id)
        return True

    def exists(self, template_id: str) -> bool:
        """检查模板是否存在。"""
        return template_id in self._index

    def name_exists(self, name: str, exclude_id: Optional[str] = None) -> bool:
        """检查模板名称是否已被使用。

        Args:
            name: 待检查的名称。
            exclude_id: 排除的模板 ID（用于更新时允许保留原名）。

        Returns:
            名称是否已存在。
        """
        for tid, template in self._index.items():
            if template.metadata.name == name and tid != exclude_id:
                return True
        return False

    def count(self, *, source: Optional[str] = None) -> int:
        """统计模板数量。"""
        if source:
            return sum(1 for t in self._index.values() if t.source == source)
        return len(self._index)

    def reload(self) -> None:
        """重新加载所有模板（从文件系统刷新）。"""
        self._index.clear()
        self._load_all()
