from __future__ import annotations

import json
from pathlib import Path

from app.config.settings import CocoSettings, Settings
from app.domain.api_models import CaseGenerationRequest, CaseGenerationRun, MRRequestConfig
from app.domain.case_models import QualityReport
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


def test_get_llm_client_passes_coco_llm_switch(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    class _FakeClient:
        def __init__(self, config) -> None:
            captured["config"] = config

    monkeypatch.setattr("app.services.workflow_service.OpenAICompatibleLLMClient", _FakeClient)

    service = WorkflowService(
        settings=Settings(
            output_dir=str(tmp_path),
            llm_base_url="http://localhost:8317/v1",
            llm_model="kimi-k2-250711",
            llm_use_coco_as_llm=True,
            llm_timeout_seconds=88,
        ),
        repository=FileRunRepository(tmp_path),
        coco_settings=CocoSettings(
            coco_api_base_url="https://codebase-api.byted.org/v2",
            coco_jwt_token="token",
            coco_agent_name="sandbox",
        ),
    )

    service._get_llm_client()

    config = captured["config"]
    assert config.use_coco_as_llm is True
    assert config.coco_api_base_url == "https://codebase-api.byted.org/v2"
    assert config.coco_jwt_token == "token"
    assert config.coco_agent_name == "sandbox"


def test_get_llm_client_passes_mira_switch_and_analysis_backend(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    class _FakeClient:
        def __init__(self, config) -> None:
            captured["config"] = config

    monkeypatch.setattr("app.services.workflow_service.OpenAICompatibleLLMClient", _FakeClient)

    service = WorkflowService(
        settings=Settings(
            output_dir=str(tmp_path),
            llm_base_url="https://unused.example/v1",
            llm_model="mira-summary-model",
            llm_use_mira_as_llm=True,
            llm_timeout_seconds=90,
            mira_api_base_url="https://mira.example.com",
            mira_jwt_token="mira-token",
            mira_use_for_code_analysis=True,
            timezone="UTC",
        ),
        repository=FileRunRepository(tmp_path),
        coco_settings=CocoSettings(
            coco_api_base_url="https://codebase-api.byted.org/v2",
            coco_jwt_token="legacy-token",
            coco_agent_name="sandbox",
        ),
    )

    service._get_llm_client()

    config = captured["config"]
    assert config.use_mira_as_llm is True
    assert config.mira_api_base_url == "https://mira.example.com"
    assert config.mira_jwt_token == "mira-token"
    assert config.mira_use_for_code_analysis is True
    assert config.timezone == "UTC"


def test_get_llm_client_passes_mira_cookie(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    class _FakeClient:
        def __init__(self, config) -> None:
            captured["config"] = config

    monkeypatch.setattr("app.services.workflow_service.OpenAICompatibleLLMClient", _FakeClient)

    service = WorkflowService(
        settings=Settings(
            output_dir=str(tmp_path),
            llm_base_url="https://unused.example/v1",
            llm_model="gpt-5.4",
            llm_use_mira_as_llm=True,
            mira_api_base_url="https://mira.bytedance.com",
            mira_cookie="locale=zh-CN; mira_session=session-token",
        ),
        repository=FileRunRepository(tmp_path),
        coco_settings=CocoSettings(coco_jwt_token="legacy-token"),
    )

    service._get_llm_client()

    assert captured["config"].mira_cookie == "locale=zh-CN; mira_session=session-token"


def test_build_workflow_input_includes_mr_configs_and_run_output_dir(tmp_path) -> None:
    service = WorkflowService(
        settings=Settings(output_dir=str(tmp_path)),
        repository=FileRunRepository(tmp_path),
        llm_client=object(),
        coco_settings=CocoSettings(coco_jwt_token="token"),
    )
    request = CaseGenerationRequest(
        file_id="0" * 32,
        frontend_mr=[
            MRRequestConfig(
                mr_url="https://example.com/fe/merge_requests/1",
                git_url="https://example.com/fe.git",
                local_path="/tmp/frontend",
                branch="feat/frontend-coco",
                use_coco=True,
            )
        ],
        backend_mr=[
            MRRequestConfig(
                mr_url="https://example.com/be/merge_requests/2",
                git_url="https://example.com/be.git",
                local_path="/tmp/backend",
                branch="feat/backend-coco",
                use_coco=True,
            )
        ],
    )

    workflow_input = service._build_workflow_input(
        run_id="run-001",
        request=request,
        iteration_index=0,
    )

    assert workflow_input["run_output_dir"] == str(tmp_path / "run-001")
    assert workflow_input["frontend_mr_config"][0]["codebase"]["branch"] == "feat/frontend-coco"
    assert workflow_input["backend_mr_config"][0]["codebase"]["branch"] == "feat/backend-coco"


def test_build_workflow_input_normalizes_bits_tree_url_for_coco(tmp_path) -> None:
    service = WorkflowService(
        settings=Settings(output_dir=str(tmp_path)),
        repository=FileRunRepository(tmp_path),
        llm_client=object(),
        coco_settings=CocoSettings(coco_jwt_token="token"),
    )
    request = CaseGenerationRequest(
        file_id="0" * 32,
        frontend_mr=[
            MRRequestConfig(
                mr_url="https://bits.bytedance.net/code/ad/ttam_brand_mono/merge_requests/2142",
                git_url="https://bits.bytedance.net/code/ad/ttam_brand_mono/tree/feat-pulse-lineup",
                branch="",
                use_coco=True,
            )
        ],
    )

    workflow_input = service._build_workflow_input(
        run_id="run-001",
        request=request,
        iteration_index=0,
    )

    assert workflow_input["frontend_mr_config"][0]["codebase"]["git_url"] == (
        "https://code.byted.org/ad/ttam_brand_mono.git"
    )
    assert workflow_input["frontend_mr_config"][0]["codebase"]["branch"] == "feat-pulse-lineup"


def test_build_workflow_input_reuses_matching_historical_coco_cache(tmp_path) -> None:
    service = WorkflowService(
        settings=Settings(
            output_dir=str(tmp_path),
            mira_use_for_code_analysis=False,
        ),
        repository=FileRunRepository(tmp_path),
        llm_client=object(),
        coco_settings=CocoSettings(coco_jwt_token="token"),
    )
    request = CaseGenerationRequest(
        file_id="0" * 32,
        frontend_mr=[
            MRRequestConfig(
                mr_url="https://example.com/fe/merge_requests/1",
                git_url="https://example.com/fe.git",
                branch="feat/frontend-coco",
                use_coco=True,
            )
        ],
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


def test_build_workflow_input_skips_coco_cache_for_mira_code_analysis(tmp_path) -> None:
    service = WorkflowService(
        settings=Settings(
            output_dir=str(tmp_path),
            mira_use_for_code_analysis=True,
        ),
        repository=FileRunRepository(tmp_path),
        llm_client=object(),
        coco_settings=CocoSettings(coco_jwt_token="token"),
    )
    request = CaseGenerationRequest(
        file_id="0" * 32,
        frontend_mr=[
            MRRequestConfig(
                mr_url="https://example.com/fe/merge_requests/1",
                git_url="https://example.com/fe.git",
                branch="feat/frontend-coco",
                use_coco=True,
            )
        ],
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

    assert "coco_cache_run_id" not in workflow_input
    assert "coco_cache_dir" not in workflow_input


def test_persist_run_artifacts_includes_mira_directory(tmp_path) -> None:
    repository = FileRunRepository(tmp_path)
    service = WorkflowService(
        settings=Settings(output_dir=str(tmp_path)),
        repository=repository,
        llm_client=object(),
        coco_settings=CocoSettings(coco_jwt_token="token"),
    )
    run_id = "2026-04-10_03-00-00"
    run_dir = tmp_path / run_id
    (run_dir / "coco").mkdir(parents=True)
    (run_dir / "coco" / "task1_frontend_result.json").write_text("{}", encoding="utf-8")
    (run_dir / "mira").mkdir()
    (run_dir / "mira" / "task2_results.json").write_text("[]", encoding="utf-8")

    run = CaseGenerationRun(
        run_id=run_id,
        status="succeeded",
        input=CaseGenerationRequest(file_id="0" * 32),
        quality_report=QualityReport(),
    )

    final_run = service._persist_run_artifacts(run, {})

    assert "coco::task1_frontend_result.json" in final_run.artifacts
    assert "mira::task2_results.json" in final_run.artifacts
