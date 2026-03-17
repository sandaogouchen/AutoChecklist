from pathlib import Path

from app.graphs.main_workflow import build_workflow


def test_workflow_returns_test_cases(fake_llm_client) -> None:
    workflow = build_workflow(fake_llm_client)

    result = workflow.invoke(
        {
            "file_path": str(Path("tests/fixtures/sample_prd.md")),
            "language": "zh-CN",
        }
    )

    assert result["test_cases"]
    assert result["test_cases"][0].title == "User logs in with SMS code"


def test_workflow_produces_checkpoints(fake_llm_client) -> None:
    """工作流应生成 checkpoints 中间产物。"""
    workflow = build_workflow(fake_llm_client)

    result = workflow.invoke(
        {
            "file_path": str(Path("tests/fixtures/sample_prd.md")),
            "language": "zh-CN",
        }
    )

    assert "checkpoints" in result
    assert len(result["checkpoints"]) > 0
    # 每个 checkpoint 都应有稳定 ID
    for cp in result["checkpoints"]:
        assert cp.checkpoint_id.startswith("CP-")


def test_workflow_produces_checkpoint_coverage(fake_llm_client) -> None:
    """工作流应生成 checkpoint 覆盖状态记录。"""
    workflow = build_workflow(fake_llm_client)

    result = workflow.invoke(
        {
            "file_path": str(Path("tests/fixtures/sample_prd.md")),
            "language": "zh-CN",
        }
    )

    assert "checkpoint_coverage" in result
    coverage = result["checkpoint_coverage"]
    assert len(coverage) > 0


def test_workflow_test_cases_have_checkpoint_id(fake_llm_client) -> None:
    """工作流生成的测试用例应携带 checkpoint_id。"""
    workflow = build_workflow(fake_llm_client)

    result = workflow.invoke(
        {
            "file_path": str(Path("tests/fixtures/sample_prd.md")),
            "language": "zh-CN",
        }
    )

    # 至少部分用例应有 checkpoint_id
    cases_with_cp = [tc for tc in result["test_cases"] if tc.checkpoint_id]
    assert len(cases_with_cp) > 0
