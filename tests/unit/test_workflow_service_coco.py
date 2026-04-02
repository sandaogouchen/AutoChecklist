from __future__ import annotations

from pathlib import Path

from app.config.settings import CocoSettings, Settings
from app.domain.api_models import CaseGenerationRequest, MRRequestConfig
from app.repositories.run_repository import FileRunRepository
from app.services.workflow_service import WorkflowService
from app.utils.timing import NodeTimer


def test_build_timed_workflow_passes_coco_settings(monkeypatch, tmp_path) -> None:
    captured: dict = {}

    def _fake_build_workflow(*args, **kwargs):
        captured["kwargs"] = kwargs

        class _Workflow:
            def invoke(self, _state):
                return {}

        return _Workflow()

    monkeypatch.setattr("app.services.workflow_service.build_workflow", _fake_build_workflow)

    service = WorkflowService(
        settings=Settings(output_dir=str(tmp_path)),
        repository=FileRunRepository(tmp_path),
        llm_client=object(),
        coco_settings=CocoSettings(coco_jwt_token="token"),
    )

    service._build_timed_workflow(NodeTimer(), 0)

    assert captured["kwargs"]["coco_settings"].coco_jwt_token == "token"


def test_build_workflow_input_includes_mr_configs_and_run_output_dir(tmp_path) -> None:
    service = WorkflowService(
        settings=Settings(output_dir=str(tmp_path)),
        repository=FileRunRepository(tmp_path),
        llm_client=object(),
        coco_settings=CocoSettings(coco_jwt_token="token"),
    )
    request = CaseGenerationRequest(
        file_path=str(Path("tests/fixtures/sample_prd.md").resolve()),
        frontend_mr=MRRequestConfig(
            mr_url="https://example.com/fe/merge_requests/1",
            git_url="https://example.com/fe.git",
            local_path="/tmp/frontend",
            branch="feat/frontend-coco",
            use_coco=True,
        ),
        backend_mr=MRRequestConfig(
            mr_url="https://example.com/be/merge_requests/2",
            git_url="https://example.com/be.git",
            local_path="/tmp/backend",
            branch="feat/backend-coco",
            use_coco=True,
        ),
    )

    workflow_input = service._build_workflow_input(
        run_id="run-001",
        request=request,
        iteration_index=0,
    )

    assert workflow_input["run_output_dir"] == str(tmp_path / "run-001")
    assert workflow_input["frontend_mr_config"]["codebase"]["branch"] == "feat/frontend-coco"
    assert workflow_input["backend_mr_config"]["codebase"]["branch"] == "feat/backend-coco"
