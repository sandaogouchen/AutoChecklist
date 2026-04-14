"""Regression tests for importing checkpoint outline planner helpers."""

from __future__ import annotations

import importlib
from types import SimpleNamespace


def test_xmind_reference_prompt_section_preserves_mandatory_note() -> None:
    module = importlib.import_module("app.services.checkpoint_outline_planner")

    section = module._build_xmind_reference_prompt_section(
        SimpleNamespace(formatted_summary="- Campaign\n  - Ad group"),
        has_mandatory_skeleton=True,
    )

    assert '标记为"必须保留"的节点是硬约束，不可更改。' in section


def test_module_exports_attach_expected_results_helper() -> None:
    module = importlib.import_module("app.services.checkpoint_outline_planner")

    assert callable(module.attach_expected_results_to_outline)
