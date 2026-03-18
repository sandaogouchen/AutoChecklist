"""Unit tests for app.services.project_context_service."""

import pytest

from app.domain.project_models import ProjectType
from app.services.project_context_service import ProjectContextService


class TestProjectContextService:

    def _svc(self) -> ProjectContextService:
        return ProjectContextService()

    def test_create_and_get(self):
        svc = self._svc()
        p = svc.create_project(name="Demo", project_type=ProjectType.WEB_APP)
        assert p.name == "Demo"
        assert svc.get_project(p.id) is not None

    def test_list_projects(self):
        svc = self._svc()
        svc.create_project(name="A")
        svc.create_project(name="B")
        assert len(svc.list_projects()) == 2

    def test_update_project(self):
        svc = self._svc()
        p = svc.create_project(name="Old")
        updated = svc.update_project(p.id, name="New")
        assert updated.name == "New"

    def test_update_missing_raises(self):
        svc = self._svc()
        with pytest.raises(KeyError):
            svc.update_project("bad-id", name="X")

    def test_delete_project(self):
        svc = self._svc()
        p = svc.create_project(name="Bye")
        assert svc.delete_project(p.id) is True
        assert svc.get_project(p.id) is None

    def test_delete_missing(self):
        svc = self._svc()
        assert svc.delete_project("nope") is False
