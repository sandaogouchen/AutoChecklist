from __future__ import annotations

from pathlib import Path

import pytest

from app.services.prompt_loader import PromptLoader


def test_prompt_loader_reads_prompt_file(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "sample.md").write_text("hello {name}", encoding="utf-8")

    loader = PromptLoader(base_dir=prompts_dir)

    assert loader.load("sample.md") == "hello {name}"


def test_prompt_loader_formats_prompt_with_variables(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "sample.md").write_text("hello {name}", encoding="utf-8")

    loader = PromptLoader(base_dir=prompts_dir)

    assert loader.render("sample.md", name="mira") == "hello mira"


def test_prompt_loader_caches_file_contents(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    prompt_path = prompts_dir / "sample.md"
    prompt_path.write_text("v1", encoding="utf-8")

    loader = PromptLoader(base_dir=prompts_dir)
    assert loader.load("sample.md") == "v1"

    prompt_path.write_text("v2", encoding="utf-8")
    assert loader.load("sample.md") == "v1"


def test_prompt_loader_rejects_missing_prompt(tmp_path) -> None:
    loader = PromptLoader(base_dir=tmp_path / "prompts")

    with pytest.raises(FileNotFoundError, match="missing.md"):
        loader.load("missing.md")


def test_prompt_loader_rejects_paths_outside_prompt_root(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    loader = PromptLoader(base_dir=prompts_dir)

    with pytest.raises(ValueError, match="outside prompt root"):
        loader.load("../escape.md")
