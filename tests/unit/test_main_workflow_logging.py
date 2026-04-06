"""Workflow bridge logging tests."""

from __future__ import annotations

import logging

import pytest

from app.domain.research_models import ResearchOutput
from app.graphs.main_workflow import _build_case_generation_bridge


def _reset_app_logging_for_caplog() -> None:
    app_logger = logging.getLogger("app")
    app_logger.handlers.clear()
    app_logger.setLevel(logging.NOTSET)
    app_logger.propagate = True


def test_case_generation_bridge_logs_subgraph_failure_context(caplog) -> None:
    _reset_app_logging_for_caplog()

    class _FailingSubgraph:
        def invoke(self, _state):
            raise RuntimeError("boom")

    bridge = _build_case_generation_bridge(_FailingSubgraph())
    state = {
        "language": "zh-CN",
        "parsed_document": {"title": "doc"},
        "research_output": ResearchOutput(),
        "frontend_mr_config": {"mr_url": "https://example.com/fe"},
    }

    with caplog.at_level(logging.ERROR, logger="app.graphs.main_workflow"):
        with pytest.raises(RuntimeError, match="boom"):
            bridge(state)

    assert "case_generation subgraph failed" in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert "has_frontend_mr=True" in caplog.text
    assert "has_backend_mr=False" in caplog.text
    assert "has_mr_input=False" in caplog.text
