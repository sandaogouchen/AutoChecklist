"""Unit tests for the project_context_loader node factory.

Covers:
- Factory returns a callable
- No project_id in state -> empty summary
- Empty-string project_id -> empty summary
- Project not found -> empty summary + warning
- Project found -> summary_text() written to state
- Service exception -> graceful degradation (empty summary)
- summary_text() exception -> graceful degradation (empty summary)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.domain.project_models import ProjectContext, ProjectType
from app.nodes.project_context_loader import build_project_context_loader
from app.services.project_context_service import ProjectContextService


@pytest.fixture
def mock_service() -> MagicMock:
    """A mock ProjectContextService."""
    return MagicMock(spec=ProjectContextService)


@pytest.fixture
def sample_project() -> ProjectContext:
    """A sample project context for testing."""
    return ProjectContext(
        id="proj-001",
        name="TestProject",
        description="A test project for unit testing.",
        project_type=ProjectType.WEB_APP,
        regulatory_frameworks=[],
        tech_stack=["Python", "FastAPI"],
        custom_standards=[],
    )


class TestBuildProjectContextLoader:
    """Tests for the build_project_context_loader factory function."""

    def test_factory_returns_callable(self, mock_service: MagicMock):
        """build_project_context_loader should return a callable."""
        loader = build_project_context_loader(mock_service)
        assert callable(loader)

    def test_no_project_id_in_state(self, mock_service: MagicMock):
        """When state has no project_id, return empty summary."""
        loader = build_project_context_loader(mock_service)
        result = loader({})
        assert result["project_context_summary"] == ""
        mock_service.get_project.assert_not_called()

    def test_project_id_empty_string(self, mock_service: MagicMock):
        """When project_id is an empty string, return empty summary."""
        loader = build_project_context_loader(mock_service)
        result = loader({"project_id": ""})
        assert result["project_context_summary"] == ""
        mock_service.get_project.assert_not_called()

    def test_project_id_none(self, mock_service: MagicMock):
        """When project_id is None, return empty summary."""
        loader = build_project_context_loader(mock_service)
        result = loader({"project_id": None})
        assert result["project_context_summary"] == ""
        mock_service.get_project.assert_not_called()

    def test_project_not_found(self, mock_service: MagicMock):
        """When project doesn't exist, return empty summary with warning."""
        mock_service.get_project.return_value = None
        loader = build_project_context_loader(mock_service)
        result = loader({"project_id": "nonexistent"})
        assert result["project_context_summary"] == ""
        mock_service.get_project.assert_called_once_with("nonexistent")

    def test_project_found_returns_summary(
        self, mock_service: MagicMock, sample_project: ProjectContext
    ):
        """When project is found, return its summary_text() as context."""
        mock_service.get_project.return_value = sample_project
        loader = build_project_context_loader(mock_service)
        result = loader({"project_id": "proj-001"})

        assert result["project_context_summary"] != ""
        assert "TestProject" in result["project_context_summary"]
        mock_service.get_project.assert_called_once_with("proj-001")

    def test_service_exception_graceful(self, mock_service: MagicMock):
        """When service raises an exception, return empty summary gracefully."""
        mock_service.get_project.side_effect = RuntimeError("DB connection lost")
        loader = build_project_context_loader(mock_service)
        # Should NOT raise
        result = loader({"project_id": "proj-001"})
        assert result["project_context_summary"] == ""

    def test_summary_text_exception_graceful(self, mock_service: MagicMock):
        """When summary_text() raises, return empty summary gracefully."""
        broken_project = MagicMock(spec=ProjectContext)
        broken_project.summary_text.side_effect = ValueError("bad data")
        broken_project.name = "BrokenProject"
        mock_service.get_project.return_value = broken_project

        loader = build_project_context_loader(mock_service)
        result = loader({"project_id": "proj-broken"})
        assert result["project_context_summary"] == ""

    def test_returns_dict_not_mutated_state(self, mock_service: MagicMock):
        """The loader should return a new dict (LangGraph incremental update),
        not mutate the input state dict."""
        mock_service.get_project.return_value = None
        loader = build_project_context_loader(mock_service)
        state = {"project_id": "x"}
        result = loader(state)
        # The result is a new dict with only the updated key
        assert "project_context_summary" in result
        # Original state should NOT be mutated
        assert "project_context_summary" not in state
