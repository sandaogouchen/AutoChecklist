"""Checkpoint 相关单元测试。

测试检查点模型、生成节点和评估节点的核心逻辑。
"""

from app.domain.checkpoint_models import (
    Checkpoint,
    CheckpointCoverage,
    generate_checkpoint_id,
)
from app.domain.research_models import EvidenceRef, ResearchFact, ResearchOutput
from app.nodes.checkpoint_evaluator import checkpoint_evaluator_node
from app.nodes.checkpoint_generator import (
    _build_checkpoint_prompt,
    _synthesize_facts_from_legacy,
)


def test_generate_checkpoint_id_is_stable() -> None:
    """相同输入应生成相同的 checkpoint ID。"""
    id1 = generate_checkpoint_id(["FACT-001"], "Verify login flow")
    id2 = generate_checkpoint_id(["FACT-001"], "Verify login flow")
    assert id1 == id2
    assert id1.startswith("CP-")


def test_generate_checkpoint_id_differs_for_different_input() -> None:
    """不同输入应生成不同的 checkpoint ID。"""
    id1 = generate_checkpoint_id(["FACT-001"], "Verify login flow")
    id2 = generate_checkpoint_id(["FACT-002"], "Verify logout flow")
    assert id1 != id2


def test_generate_checkpoint_id_case_insensitive() -> None:
    """标题大小写不同但内容相同时应生成相同 ID。"""
    id1 = generate_checkpoint_id(["FACT-001"], "Verify Login Flow")
    id2 = generate_checkpoint_id(["FACT-001"], "verify login flow")
    assert id1 == id2


def test_checkpoint_model_defaults() -> None:
    """Checkpoint 模型的默认值应正确设置。"""
    cp = Checkpoint(title="Test checkpoint")
    assert cp.checkpoint_id == ""
    assert cp.category == "functional"
    assert cp.risk == "medium"
    assert cp.coverage_status == "uncovered"
    assert cp.fact_ids == []
    assert cp.evidence_refs == []


def test_checkpoint_coverage_model() -> None:
    """CheckpointCoverage 模型应正确记录覆盖状态。"""
    cc = CheckpointCoverage(
        checkpoint_id="CP-abc",
        covered_by_test_ids=["TC-001", "TC-002"],
        coverage_status="covered",
    )
    assert cc.checkpoint_id == "CP-abc"
    assert len(cc.covered_by_test_ids) == 2
    assert cc.coverage_status == "covered"


def test_synthesize_facts_from_legacy() -> None:
    """从旧版 ResearchOutput 字段合成 facts 应正确工作。"""
    research = ResearchOutput(
        feature_topics=["Login"],
        user_scenarios=["User logs in with SMS code"],
        constraints=["SMS code expires in 5 minutes"],
    )
    facts = _synthesize_facts_from_legacy(research)

    assert len(facts) == 3
    assert facts[0].fact_id == "FACT-001"
    assert facts[0].category == "behavior"
    assert facts[1].fact_id == "FACT-002"
    assert facts[1].category == "requirement"
    assert facts[2].fact_id == "FACT-003"
    assert facts[2].category == "constraint"


def test_checkpoint_evaluator_deduplicates() -> None:
    """checkpoint_evaluator 应按标题去重。"""
    cp1 = Checkpoint(checkpoint_id="CP-001", title="Verify login")
    cp2 = Checkpoint(checkpoint_id="CP-002", title="Verify Login")  # 重复（大小写不同）
    cp3 = Checkpoint(checkpoint_id="CP-003", title="Verify logout")

    state = {"checkpoints": [cp1, cp2, cp3]}
    result = checkpoint_evaluator_node(state)

    assert len(result["checkpoints"]) == 2
    assert result["checkpoints"][0].checkpoint_id == "CP-001"
    assert result["checkpoints"][1].checkpoint_id == "CP-003"


def test_checkpoint_evaluator_initializes_coverage() -> None:
    """checkpoint_evaluator 应为每个 checkpoint 初始化覆盖记录。"""
    cp1 = Checkpoint(checkpoint_id="CP-001", title="Verify login")
    cp2 = Checkpoint(checkpoint_id="CP-002", title="Verify logout")

    state = {"checkpoints": [cp1, cp2]}
    result = checkpoint_evaluator_node(state)

    coverage = result["checkpoint_coverage"]
    assert len(coverage) == 2
    assert all(cc.coverage_status == "uncovered" for cc in coverage)
    assert coverage[0].checkpoint_id == "CP-001"


def test_research_fact_model() -> None:
    """ResearchFact 模型应正确创建。"""
    fact = ResearchFact(
        fact_id="FACT-001",
        description="User can log in",
        source_section="Login",
        category="behavior",
        evidence_refs=[
            EvidenceRef(
                section_title="Login",
                excerpt="Login flow",
                line_start=1,
                line_end=5,
                confidence=0.9,
            )
        ],
    )
    assert fact.fact_id == "FACT-001"
    assert len(fact.evidence_refs) == 1


def test_checkpoint_prompt_includes_fact_level_code_todo() -> None:
    fact = ResearchFact(
        fact_id="FACT-001",
        description="Pulse Custom Lineups 的默认 frequency cap 调整为 4 impressions per day",
        requirement="默认 frequency cap 必须展示并提交为 4 impressions per 1 day",
        branch_hint="默认与自定义切换分支",
        code_todo="代码当前仍保留 3 impressions per 7 days，生成 checklist 时需要覆盖该偏差",
        code_actual_implementation="当前默认值来自 default，展示为 3 impressions per 7 days",
    )

    prompt = _build_checkpoint_prompt([fact], "zh-CN")

    assert "Code TODO" in prompt
    assert "3 impressions per 7 days" in prompt
    assert "默认与自定义切换分支" in prompt


def test_research_output_backward_compatible() -> None:
    """ResearchOutput 新增的 facts 字段默认为空列表，不影响旧代码。"""
    output = ResearchOutput(
        feature_topics=["Login"],
        user_scenarios=["User logs in"],
    )
    assert output.facts == []
