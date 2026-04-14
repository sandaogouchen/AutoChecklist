"""Prompt 模板加载器。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


class PromptLoader:
    """从仓库 prompts 目录加载模板文件。"""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        if base_dir is None:
            base_dir = Path(__file__).resolve().parents[2] / "prompts"
        self._base_dir = Path(base_dir).resolve()

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @lru_cache(maxsize=256)
    def load(self, relative_path: str) -> str:
        prompt_path = (self._base_dir / relative_path).resolve()
        try:
            prompt_path.relative_to(self._base_dir)
        except ValueError as exc:
            raise ValueError(f"Prompt path is outside prompt root: {relative_path}") from exc

        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {relative_path}")

        return prompt_path.read_text(encoding="utf-8")

    def render(self, relative_path: str, **kwargs: object) -> str:
        return self.load(relative_path).format(**kwargs)


_DEFAULT_PROMPT_LOADER = PromptLoader()


def get_prompt_loader() -> PromptLoader:
    return _DEFAULT_PROMPT_LOADER
