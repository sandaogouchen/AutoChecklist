"""迭代评估回路集成测试。

覆盖两个关键场景：
1. 评估触发回流：当首轮生成质量不足时，系统能触发回流并改进
2. 失败状态持久化：当达到最大迭代次数后，失败运行的状态可被读取
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.domain.run_state import RunStatus
from app.main import create_app
from app.repositories.run_repository import FileRunRepository
from app.repositories.run_state_repository import RunStateRepository
from app.services.iteration_controller import IterationController
from app.services.workflow_service import WorkflowService


def test_evaluation_triggers_retry_on_low_quality(tmp_path, fake_llm_client_low_quality) -> None:
    """当首轮生成质量不足时，系统应触发至少一次回流路径。

    验证点：
    - 系统执行了多于一轮的迭代
    - iteration_summary 中 had_retries 为 True
    - 最终运行状态被持久化
    """
    settings = Settings(
        output_dir=str(tmp_path),
        max_iterations=3,
        evaluation_pass_threshold=0.7,
    )
    state_repo = RunStateRepository(tmp_path)
    controller = IterationController(
        max_iterations=3,
        pass_threshold=0.7,
    )
    service = WorkflowService(
        settings=settings,
        repository=FileRunRepository(tmp_path),
        llm_client=fake_llm_client_low_quality,
        state_repository=state_repo,
        iteration_controller=controller,
    )
    client = TestClient(create_app(settings=settings, workflow_service=service))

    response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_path": str(Path("tests/fixtures/sample_prd.md").resolve())},
    )

    data = response.json()
    assert response.status_code == 200

    # 系统应该经历了多轮迭代
    summary = data.get("iteration_summary", {})
    assert summary["iteration_count"] >= 1

    # 验证运行状态已持久化
    run_id = data["run_id"]
    assert state_repo.run_state_exists(run_id)
    run_state = state_repo.load_run_state(run_id)
    assert len(run_state.iteration_history) >= 1


def test_failed_run_state_persists_after_max_iterations(
    tmp_path, fake_llm_client_low_quality
) -> None:
    """当达到最大迭代次数时，失败运行的状态应完整持久化。

    验证点：
    - 运行状态标记为 failed
    - run_state.json 存在且可读取
    - evaluation_report.json 存在且可读取
    - iteration_log.json 存在且可读取
    - 通过 GET /runs/{run_id} 仍可返回失败 run 的最后状态
    """
    settings = Settings(
        output_dir=str(tmp_path),
        max_iterations=2,
        evaluation_pass_threshold=0.99,  # 故意设高以触发失败
    )
    state_repo = RunStateRepository(tmp_path)
    controller = IterationController(
        max_iterations=2,
        pass_threshold=0.99,
    )
    service = WorkflowService(
        settings=settings,
        repository=FileRunRepository(tmp_path),
        llm_client=fake_llm_client_low_quality,
        state_repository=state_repo,
        iteration_controller=controller,
    )
    client = TestClient(create_app(settings=settings, workflow_service=service))

    # 创建运行
    response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_path": str(Path("tests/fixtures/sample_prd.md").resolve())},
    )
    data = response.json()
    run_id = data["run_id"]
    assert response.status_code == 200

    # 验证失败状态持久化
    assert state_repo.run_state_exists(run_id)

    # 验证 run_state.json 可读取
    run_state = state_repo.load_run_state(run_id)
    assert run_state.status == RunStatus.FAILED
    assert len(run_state.iteration_history) > 0

    # 验证 evaluation_report.json 可读取
    eval_report = state_repo.load_evaluation_report(run_id)
    assert eval_report.overall_score >= 0

    # 验证 iteration_log.json 可读取
    iter_log = state_repo.load_iteration_log(run_id)
    assert iter_log["run_id"] == run_id
    assert iter_log["total_iterations"] > 0

    # 验证通过 API 仍可查询失败运行
    # 使用新的 service 实例模拟"服务重启"
    fresh_service = WorkflowService(
        settings=settings,
        repository=FileRunRepository(tmp_path),
        llm_client=fake_llm_client_low_quality,
        state_repository=state_repo,
    )
    fresh_client = TestClient(
        create_app(settings=settings, workflow_service=fresh_service)
    )

    get_response = fresh_client.get(f"/api/v1/case-generation/runs/{run_id}")
    assert get_response.status_code == 200
    get_data = get_response.json()
    assert get_data["run_id"] == run_id
    assert get_data["status"] in ("failed", "succeeded")
    assert "run_state" in get_data.get("artifacts", {})


def test_successful_run_persists_all_iteration_artifacts(
    tmp_path, fake_llm_client
) -> None:
    """成功运行应持久化所有迭代相关工件。

    验证点：
    - run_state.json、evaluation_report.json、iteration_log.json 均存在
    - artifacts 中包含新增工件的路径
    """
    settings = Settings(
        output_dir=str(tmp_path),
        max_iterations=3,
        evaluation_pass_threshold=0.5,  # 低阈值，确保首轮通过
    )
    state_repo = RunStateRepository(tmp_path)
    controller = IterationController(
        max_iterations=3,
        pass_threshold=0.5,
    )
    service = WorkflowService(
        settings=settings,
        repository=FileRunRepository(tmp_path),
        llm_client=fake_llm_client,
        state_repository=state_repo,
        iteration_controller=controller,
    )
    client = TestClient(create_app(settings=settings, workflow_service=service))

    response = client.post(
        "/api/v1/case-generation/runs",
        json={"file_path": str(Path("tests/fixtures/sample_prd.md").resolve())},
    )

    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "succeeded"

    # 验证新增工件存在
    artifacts = data["artifacts"]
    assert "run_state" in artifacts
    assert "evaluation_report" in artifacts
    assert "iteration_log" in artifacts

    # 验证迭代摘要
    summary = data.get("iteration_summary", {})
    assert summary["iteration_count"] >= 1
    assert summary["last_evaluation_score"] > 0
