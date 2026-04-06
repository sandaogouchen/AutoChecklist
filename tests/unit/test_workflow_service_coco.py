from __future__ import annotations

import json
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


def test_build_workflow_input_normalizes_bits_tree_url_for_coco(tmp_path) -> None:
    service = WorkflowService(
        settings=Settings(output_dir=str(tmp_path)),
        repository=FileRunRepository(tmp_path),
        llm_client=object(),
        coco_settings=CocoSettings(coco_jwt_token="token"),
    )
    request = CaseGenerationRequest(
        file_path=str(Path("tests/fixtures/sample_prd.md").resolve()),
        frontend_mr=MRRequestConfig(
            mr_url="https://bits.bytedance.net/code/ad/ttam_brand_mono/merge_requests/2142",
            git_url="https://bits.bytedance.net/code/ad/ttam_brand_mono/tree/feat-pulse-lineup",
            branch="",
            use_coco=True,
        ),
    )

    workflow_input = service._build_workflow_input(
        run_id="run-001",
        request=request,
        iteration_index=0,
    )

    assert workflow_input["frontend_mr_config"]["codebase"]["git_url"] == (
        "https://code.byted.org/ad/ttam_brand_mono.git"
    )
    assert workflow_input["frontend_mr_config"]["codebase"]["branch"] == "feat-pulse-lineup"


def test_build_workflow_input_reuses_matching_historical_coco_cache(tmp_path) -> None:
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
            branch="feat/frontend-coco",
            use_coco=True,
        ),
    )

    historical_run_dir = tmp_path / "2026-04-03_13-01-59"
    historical_run_dir.mkdir(parents=True)
    (historical_run_dir / "coco").mkdir()
    (historical_run_dir / "coco" / "task1_frontend_result.json").write_text("{}", encoding="utf-8")
    (historical_run_dir / "request.json").write_text(
        json.dumps(request.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    workflow_input = service._build_workflow_input(
        run_id="2026-04-03_13-02-00",
        request=request,
        iteration_index=0,
    )

    assert workflow_input["coco_cache_run_id"] == "2026-04-03_13-01-59"
    assert workflow_input["coco_cache_dir"] == str(historical_run_dir / "coco")
