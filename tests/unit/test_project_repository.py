"""Unit tests for app.repositories.project_repository."""

from app.domain.project_models import ProjectContext
from app.repositories.project_repository import ProjectRepository


class TestProjectRepository:

    def _make_repo(self) -> ProjectRepository:
        return ProjectRepository()

    def test_save_and_get(self):
        repo = self._make_repo()
        ctx = ProjectContext(name="Test")
        repo.save(ctx)
        assert repo.get(ctx.id) is ctx

    def test_get_missing_returns_none(self):
        repo = self._make_repo()
        assert repo.get("nonexistent") is None

    def test_list_all_empty(self):
        repo = self._make_repo()
        assert repo.list_all() == []

    def test_list_all(self):
        repo = self._make_repo()
        repo.save(ProjectContext(name="A"))
        repo.save(ProjectContext(name="B"))
        assert len(repo.list_all()) == 2

    def test_delete_existing(self):
        repo = self._make_repo()
        ctx = ProjectContext(name="X")
        repo.save(ctx)
        assert repo.delete(ctx.id) is True
        assert repo.get(ctx.id) is None

    def test_delete_missing(self):
        repo = self._make_repo()
        assert repo.delete("nope") is False
