"""Coverage-related tests for case generation flow."""

from __future__ import annotations

from types import SimpleNamespace

from app.domain.checkpoint_models import Checkpoint
from app.graphs.case_generation import _coverage_detector_node


def test_coverage_detector_node_uses_checkpoint_id_for_uncovered_checkpoints() -> None:
    state = {
        "xmind_reference_summary": SimpleNamespace(all_leaf_titles=["微信支付成功"]),
        "checkpoints": [
            Checkpoint(checkpoint_id="CP-001", title="微信支付成功"),
            Checkpoint(checkpoint_id="CP-002", title="新增功能测试"),
        ],
    }

    result = _coverage_detector_node(state)

    uncovered_ids = [cp.checkpoint_id for cp in result["uncovered_checkpoints"]]

    assert result["coverage_result"].covered_checkpoint_ids == ["CP-001"]
    assert uncovered_ids == ["CP-002"]
