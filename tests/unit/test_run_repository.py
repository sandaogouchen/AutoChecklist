from app.repositories.run_repository import FileRunRepository


def test_file_run_repository_persists_run(tmp_path) -> None:
    repo = FileRunRepository(tmp_path)

    repo.save("run-1", {"status": "succeeded"})

    assert repo.load("run-1")["status"] == "succeeded"
