"""Unit tests for app.repositories.project_repository."""

from pathlib import Path

from app.domain.project_models import ProjectContext
from app.repositories.project_repository import ProjectRepository


class TestProjectRepository:

    def _make_repo(self, db_path: Path | None = None) -> ProjectRepository:
        return ProjectRepository(db_path=db_path)

    def test_save_and_get(self):
        repo = self._make_repo()
        ctx = ProjectContext(name="Test")
        repo.save(ctx)
        loaded = repo.get(ctx.id)
        assert loaded is not None
        assert loaded.id == ctx.id
        assert loaded.name == ctx.name

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

    def test_persists_across_repository_instances(self, tmp_path):
        db_path = tmp_path / "projects.sqlite3"

        repo_a = self._make_repo(db_path)
        ctx = ProjectContext(name="Persistent")
        repo_a.save(ctx)

        repo_b = self._make_repo(db_path)
        loaded = repo_b.get(ctx.id)

        assert loaded is not None
        assert loaded.id == ctx.id
        assert loaded.name == "Persistent"
