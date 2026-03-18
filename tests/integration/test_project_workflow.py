"""Integration tests for project context + workflow integration.

Verifies that:
1. A project created via ProjectContextService is correctly loaded
   by the workflow's project_context_loader node.
2. The workflow functions normally without a project_id (graceful degradation).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.domain.project_models import ProjectContext, ProjectType
from app.nodes.project_context_loader import build_project_context_loader
from app.repositories.project_repository import ProjectRepository
from app.services.project_context_service import ProjectContextService


class TestProjectContextWorkflowIntegration:
    """Integration tests for project context flowing through the workflow."""

    @pytest.fixture
    def project_service(self) -> ProjectContextService:
        """Create a real ProjectContextService with in-memory repo."""
        repo = ProjectRepository()
        return ProjectContextService(repo)

    def test_workflow_with_project_context(self, project_service: ProjectContextService):
        """End-to-end: create project -> build loader -> invoke with state
        -> verify project_context_summary is populated."""
        # Step 1: Create a project via the service
        project = project_service.create_project(
            name="E-Commerce Platform",
            description="An online shopping platform with payment integration.",
            project_type=ProjectType.WEB_APP,
            tech_stack=["Python", "FastAPI", "PostgreSQL"],
            regulatory_frameworks=[],
            custom_standards=["PCI-DSS compliance for payment"],
        )
        project_id = project.id

        # Step 2: Build the loader closure
        loader = build_project_context_loader(project_service)

        # Step 3: Simulate LangGraph passing state dict
        state = {
            "run_id": "test-run-001",
            "file_path": "/tmp/test.md",
            "language": "zh-CN",
            "project_id": project_id,
        }
        result = loader(state)

        # Step 4: Verify the summary is populated
        summary = result["project_context_summary"]
        assert summary != ""
        assert "E-Commerce Platform" in summary
        assert "Python" in summary
        assert "PCI-DSS compliance for payment" in summary

    def test_workflow_without_project_context(self, project_service: ProjectContextService):
        """When no project_id is provided, the loader returns empty summary
        and does not break the workflow."""
        loader = build_project_context_loader(project_service)
        state = {
            "run_id": "test-run-002",
            "file_path": "/tmp/test.md",
            "language": "zh-CN",
            # No project_id
        }
        result = loader(state)
        assert result["project_context_summary"] == ""

    def test_workflow_with_nonexistent_project(self, project_service: ProjectContextService):
        """When project_id refers to a non-existent project, the loader
        returns empty summary without raising."""
        loader = build_project_context_loader(project_service)
        state = {
            "run_id": "test-run-003",
            "file_path": "/tmp/test.md",
            "language": "zh-CN",
            "project_id": "does-not-exist",
        }
        result = loader(state)
        assert result["project_context_summary"] == ""

    def test_service_instance_shared_between_api_and_workflow(self):
        """Verify that API and workflow can share the same service instance
        (same repo -> same data)."""
        # Single repo + single service
        repo = ProjectRepository()
        service = ProjectContextService(repo)

        # Simulate API creating a project
        project = service.create_project(
            name="Shared Instance Test",
            description="Testing shared service instance.",
        )

        # Simulate workflow loading the project
        loader = build_project_context_loader(service)
        result = loader({"project_id": project.id})
        assert "Shared Instance Test" in result["project_context_summary"]

        # Simulate API deleting the project
        service.delete_project(project.id)

        # Workflow should now get empty summary
        result = loader({"project_id": project.id})
        assert result["project_context_summary"] == ""
