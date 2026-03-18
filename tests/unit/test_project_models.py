"""Unit tests for app.domain.project_models."""

from app.domain.project_models import (
    ProjectContext,
    ProjectType,
    RegulatoryFramework,
)


class TestProjectContext:

    def test_defaults(self):
        ctx = ProjectContext(name="Acme")
        assert ctx.name == "Acme"
        assert ctx.project_type == ProjectType.OTHER
        assert ctx.regulatory_frameworks == []
        assert ctx.tech_stack == []
        assert ctx.description == ""

    def test_summary_text_minimal(self):
        ctx = ProjectContext(name="Acme")
        summary = ctx.summary_text()
        assert "Acme" in summary

    def test_summary_text_full(self):
        ctx = ProjectContext(
            name="Rocket",
            description="Flight control",
            project_type=ProjectType.EMBEDDED,
            regulatory_frameworks=[RegulatoryFramework.DO_178C],
            tech_stack=["C", "RTOS"],
            custom_standards=["ACME-STD-001"],
        )
        summary = ctx.summary_text()
        assert "Rocket" in summary
        assert "Flight control" in summary
        assert "embedded" in summary
        assert "DO-178C" in summary
        assert "C" in summary
        assert "ACME-STD-001" in summary

    def test_id_uniqueness(self):
        a = ProjectContext(name="A")
        b = ProjectContext(name="B")
        assert a.id != b.id
