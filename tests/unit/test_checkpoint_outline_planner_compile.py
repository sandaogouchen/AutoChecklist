"""Regression tests for checkpoint outline planner module syntax."""

from __future__ import annotations

import py_compile
from pathlib import Path


def test_checkpoint_outline_planner_module_compiles() -> None:
    module_path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "checkpoint_outline_planner.py"
    )

    py_compile.compile(str(module_path), doraise=True)
