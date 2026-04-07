"""回归评估器测试类。

覆盖 Phase 1 结构对比和 Phase 2 双盲评估的完整流程。
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Type, TypeVar

import pytest
from pydantic import BaseModel

from app.domain.regression_models import (
    BlindEvalResponse,
    DiffAnalysisItem,
    MetricDelta,
    RegressionConfig,
    RunFingerprint,
)
from app.services.regression_evaluator import RegressionEvaluator

T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# 测试用 Fake LLM Client
# ---------------------------------------------------------------------------


class FakeBlindLLMClient:
    """伪造 LLM 客户端，用于测试双盲评估。

    返回固定的 BlindEvalResponse，可通过构造参数控制 winner。
    """

    def __init__(self, winner: str = "A", confidence: float = 0.8) -> None:
        self._winner = winner
        self._confidence = confidence
        self.last_prompt: str = ""

    def generate_structured(
        self, prompt: str, response_model: Type[T], **kwargs: Any
    ) -> T:
        self.last_prompt = prompt
        if response_model is BlindEvalResponse:
            return response_model(  # type: ignore[return-value]
                surface_diff_summary="Set A 有更多边界用例，Set B 覆盖更广但缺少异常路径",
                diff_analysis=[
                    DiffAnalysisItem(
                        item="Set A 多了 3 个边界条件用例",
                        verdict=f"{self._winner}_better",
                        reason="边界测试对质量保障更重要",
                    ),
                    DiffAnalysisItem(
                        item="Set B 新增了 2 个功能用例",
                        verdict="B_better" if self._winner == "B" else "tie",
                        reason="新增功能覆盖有价值但非关键",
                    ),
                ],
                overall_winner=self._winner,
                confidence=self._confidence,
                one_line_conclusion=f"Set {self._winner} 质量更优",
            )
        raise ValueError(f"Unexpected model: {response_model}")


# ---------------------------------------------------------------------------
# 测试数据工厂
# ---------------------------------------------------------------------------

def _make_test_case(
    tc_id: str,
    title: str,
    checkpoint_id: str = "",
    priority: str = "P2",
    category: str = "functional",
    steps: list[str] | None = None,
    expected_results: list[str] | None = None,
    preconditions: list[str] | None = None,
    evidence_refs: list[dict] | None = None,
    tags: list[str] | None = None,
    code_consistency: dict | None = None,
) -> dict:
    return {
        "id": tc_id,
        "title": title,
        "checkpoint_id": checkpoint_id,
        "priority": priority,
        "category": category,
        "steps": steps or ["步骤1", "步骤2"],
        "expected_results": expected_results or ["预期结果1"],
        "preconditions": preconditions or [],
        "evidence_refs": evidence_refs or [{"section_title": "s1"}],
        "tags": tags or [],
        "code_consistency": code_consistency,
    }


def _make_baseline_cases() -> list[dict]:
    """创建基线测试用例集（模拟 feat/mr-analysis-integration 的输出）。"""
    return [
        _make_test_case("TC-001", "验证 SMS 验证码正常登录", "CP-001", "P0"),
        _make_test_case("TC-002", "验证过期验证码拒绝登录", "CP-002", "P0", "edge_case"),
        _make_test_case("TC-003", "验证 CBO 一致性校验", "CP-003", "P1"),
        _make_test_case("TC-004", "验证 CTA 默认值设置", "CP-004", "P1"),
        _make_test_case("TC-005", "验证广告组创建流程", "CP-005", "P0"),
        _make_test_case(
            "TC-006", "验证代码与 PRD 一致性", "CP-006", "P1",
            tags=["mr_derived"],
            code_consistency={"status": "consistent", "confidence": 0.9},
        ),
        _make_test_case("TC-007", "验证 A4 指标上报", "CP-007", "P2"),
        _make_test_case("TC-008", "验证白名单控制逻辑", "CP-008", "P1", "edge_case"),
    ]


def _make_candidate_cases() -> list[dict]:
    """创建候选测试用例集（模拟 main 的退化输出）。"""
    return [
        _make_test_case("TC-001", "验证 SMS 验证码正常登录", "CP-001", "P0"),
        _make_test_case("TC-002", "验证过期验证码拒绝登录", "CP-002", "P0", "edge_case"),
        # CP-003 (CBO 一致性) 缺失 — 回归
        _make_test_case("TC-004", "验证 CTA 默认值设置", "CP-004", "P1"),
        _make_test_case("TC-005", "验证广告组创建流程", "CP-005", "P0"),
        # CP-006 (MR 分析) 缺失 — 回归
        _make_test_case("TC-007", "验证 A4 指标上报", "CP-007", "P2"),
        # CP-008 (白名单) 缺失 — 回归
    ]


def _make_evaluation_report(overall: float = 0.82) -> dict:
    return {
        "overall_score": overall,
        "dimensions": [
            {"name": "fact_coverage", "score": 0.95},
            {"name": "checkpoint_coverage", "score": 0.88},
            {"name": "evidence_completeness", "score": 0.78},
            {"name": "duplicate_rate", "score": 0.98},
            {"name": "case_completeness", "score": 0.90},
            {"name": "branch_coverage", "score": 0.75},
        ],
    }


def _write_run_dir(
    base_path: Path,
    test_cases: list[dict],
    eval_report: dict | None = None,
    checkpoint_count: int | None = None,
) -> str:
    """在临时目录中创建模拟的运行输出。"""
    base_path.mkdir(parents=True, exist_ok=True)

    run_result = {
        "test_cases": test_cases,
        "checkpoint_count": checkpoint_count or len(
            {tc.get("checkpoint_id") for tc in test_cases if tc.get("checkpoint_id")}
        ),
    }
    (base_path / "run_result.json").write_text(
        json.dumps(run_result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if eval_report:
        (base_path / "evaluation_report.json").write_text(
            json.dumps(eval_report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return str(base_path)


# ---------------------------------------------------------------------------
# 测试类
# ---------------------------------------------------------------------------


class TestRegressionEvaluator:
    """回归评估器完整测试，包含双盲评估实现。"""

    # ----- Phase 1: 指纹提取 -----

    def test_extract_fingerprint_basic(self, tmp_path: Path) -> None:
        """测试从运行目录提取指纹。"""
        cases = _make_baseline_cases()
        eval_report = _make_evaluation_report(0.82)
        run_dir = _write_run_dir(tmp_path / "run1", cases, eval_report)

        evaluator = RegressionEvaluator()
        fp = evaluator.extract_fingerprint(run_dir, "test-branch")

        assert fp.label == "test-branch"
        assert fp.total_test_cases == 8
        assert fp.total_checkpoints == 8
        assert fp.overall_score == 0.82
        assert fp.cases_with_evidence == 8
        assert fp.mr_analysis_present is True  # TC-006 has mr_derived tag
        assert fp.unique_title_ratio == 1.0
        assert fp.six_dim_scores["fact_coverage"] == 0.95
        assert fp.category_distribution["functional"] == 6
        assert fp.category_distribution["edge_case"] == 2

    def test_extract_fingerprint_empty_dir(self, tmp_path: Path) -> None:
        """测试空目录的指纹提取（优雅降级）。"""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        evaluator = RegressionEvaluator()
        fp = evaluator.extract_fingerprint(str(empty_dir))

        assert fp.total_test_cases == 0
        assert fp.total_checkpoints == 0
        assert fp.overall_score == 0.0
        assert fp.mr_analysis_present is False

    def test_extract_fingerprint_no_eval_report(self, tmp_path: Path) -> None:
        """测试缺少 evaluation_report.json 时仍能提取基础指标。"""
        cases = _make_baseline_cases()[:3]
        run_dir = _write_run_dir(tmp_path / "run_no_eval", cases, eval_report=None)

        evaluator = RegressionEvaluator()
        fp = evaluator.extract_fingerprint(run_dir)

        assert fp.total_test_cases == 3
        assert fp.overall_score == 0.0
        assert fp.six_dim_scores == {}

    # ----- Phase 1: 用例配对 -----

    def test_match_cases_by_checkpoint_id(self) -> None:
        """测试按 checkpoint_id 精确配对。"""
        baseline = [
            _make_test_case("TC-001", "登录验证", "CP-001"),
            _make_test_case("TC-002", "过期验证码", "CP-002"),
        ]
        candidate = [
            _make_test_case("TC-A", "登录功能验证", "CP-001"),
            _make_test_case("TC-B", "验证码过期处理", "CP-002"),
        ]

        evaluator = RegressionEvaluator()
        matched, b_only, c_only = evaluator._match_cases(baseline, candidate)

        assert len(matched) == 2
        assert len(b_only) == 0
        assert len(c_only) == 0
        assert all(m.match_score == 1.0 for m in matched)
        assert all("checkpoint_id" in m.match_key for m in matched)

    def test_match_cases_by_title_similarity(self) -> None:
        """测试按标题模糊配对。"""
        baseline = [
            _make_test_case("TC-001", "验证短信验证码登录", ""),
            _make_test_case("TC-002", "验证广告组创建", ""),
        ]
        candidate = [
            _make_test_case("TC-A", "验证短信验证码正常登录流程", ""),
            _make_test_case("TC-B", "验证新建广告组", ""),
        ]

        evaluator = RegressionEvaluator()
        matched, b_only, c_only = evaluator._match_cases(baseline, candidate)

        assert len(matched) == 2
        assert len(b_only) == 0
        assert len(c_only) == 0
        assert all(m.match_score >= 0.6 for m in matched)
        assert all("title_sim" in m.match_key for m in matched)

    def test_match_cases_unmatched(self) -> None:
        """测试不匹配的用例正确归入 baseline_only / candidate_only。"""
        baseline = [
            _make_test_case("TC-001", "验证 CBO 一致性", "CP-003"),
            _make_test_case("TC-002", "验证白名单控制", "CP-008"),
        ]
        candidate = [
            _make_test_case("TC-A", "全新的测试功能 XYZ", "CP-099"),
        ]

        evaluator = RegressionEvaluator()
        matched, b_only, c_only = evaluator._match_cases(baseline, candidate)

        assert len(matched) == 0
        assert len(b_only) == 2
        assert len(c_only) == 1

    # ----- Phase 1: 结构对比 -----

    def test_structural_diff_detects_regression(self, tmp_path: Path) -> None:
        """测试结构对比能检测到明显回归。"""
        b_cases = _make_baseline_cases()
        c_cases = _make_candidate_cases()
        b_dir = _write_run_dir(
            tmp_path / "baseline", b_cases, _make_evaluation_report(0.82)
        )
        c_dir = _write_run_dir(
            tmp_path / "candidate", c_cases, _make_evaluation_report(0.65)
        )

        evaluator = RegressionEvaluator()
        b_fp = evaluator.extract_fingerprint(b_dir, "baseline")
        c_fp = evaluator.extract_fingerprint(c_dir, "candidate")
        diff = evaluator.compare(b_fp, c_fp)

        assert diff.verdict in ("WARNING", "REGRESSION")
        assert len(diff.baseline_only) == 3  # CP-003, CP-006, CP-008 缺失
        assert len(diff.candidate_only) == 0
        assert diff.metric_deltas["total_test_cases"].status in ("WARNING", "REGRESSED")

    def test_structural_diff_ok(self, tmp_path: Path) -> None:
        """测试结构对比——两组基本相同时判定 OK。"""
        cases = _make_baseline_cases()
        eval_report = _make_evaluation_report(0.82)
        b_dir = _write_run_dir(tmp_path / "baseline", cases, eval_report)
        c_dir = _write_run_dir(tmp_path / "candidate", cases, eval_report)

        evaluator = RegressionEvaluator()
        b_fp = evaluator.extract_fingerprint(b_dir)
        c_fp = evaluator.extract_fingerprint(c_dir)
        diff = evaluator.compare(b_fp, c_fp)

        assert diff.verdict == "OK"
        assert len(diff.baseline_only) == 0
        assert len(diff.candidate_only) == 0

    def test_mr_analysis_lost_is_critical(self, tmp_path: Path) -> None:
        """测试 MR 分析丢失被标记为 CRITICAL。"""
        b_cases = _make_baseline_cases()  # 包含 mr_derived
        c_cases = _make_candidate_cases()  # 不包含 mr_derived
        b_dir = _write_run_dir(tmp_path / "b", b_cases, _make_evaluation_report(0.82))
        c_dir = _write_run_dir(tmp_path / "c", c_cases, _make_evaluation_report(0.70))

        evaluator = RegressionEvaluator()
        b_fp = evaluator.extract_fingerprint(b_dir)
        c_fp = evaluator.extract_fingerprint(c_dir)
        diff = evaluator.compare(b_fp, c_fp)

        assert "mr_analysis_present" in diff.metric_deltas
        assert diff.metric_deltas["mr_analysis_present"].status == "CRITICAL"

    # ----- Phase 2: 双盲评估 -----

    def test_blind_evaluate_prompt_is_anonymous(self, tmp_path: Path) -> None:
        """测试双盲 prompt 不泄露 baseline/candidate 标签。"""
        b_cases = _make_baseline_cases()
        c_cases = _make_candidate_cases()
        b_dir = _write_run_dir(tmp_path / "b", b_cases, _make_evaluation_report())
        c_dir = _write_run_dir(tmp_path / "c", c_cases, _make_evaluation_report(0.65))

        fake_llm = FakeBlindLLMClient(winner="A")
        evaluator = RegressionEvaluator(llm_client=fake_llm)

        b_fp = evaluator.extract_fingerprint(b_dir, "feat/mr-analysis-integration")
        c_fp = evaluator.extract_fingerprint(c_dir, "main")
        diff = evaluator.compare(b_fp, c_fp)

        # 写入临时 PRD
        prd_path = tmp_path / "test.md"
        prd_path.write_text("# Login Flow\nTest PRD content", encoding="utf-8")

        evaluator.blind_evaluate(diff, prd_path.read_text())

        # 验证 prompt 中不包含 baseline/candidate 字样
        prompt = fake_llm.last_prompt
        assert "baseline" not in prompt.lower()
        assert "candidate" not in prompt.lower()
        assert "feat/mr" not in prompt.lower()
        # 但包含 Set A / Set B
        assert "Set A" in prompt
        assert "Set B" in prompt

    def test_blind_evaluate_deblinding_when_baseline_is_a(self) -> None:
        """测试去盲逻辑：baseline=A 时，LLM 选 A → winner=baseline。"""
        evaluator = RegressionEvaluator()

        raw = BlindEvalResponse(
            surface_diff_summary="test",
            diff_analysis=[
                DiffAnalysisItem(item="test", verdict="A_better", reason="reason"),
            ],
            overall_winner="A",
            confidence=0.85,
            one_line_conclusion="A 更好",
        )

        verdict = evaluator._deblind(raw, baseline_is_a=True)
        assert verdict.overall_winner == "baseline"
        assert verdict.baseline_was_set == "A"

    def test_blind_evaluate_deblinding_when_baseline_is_b(self) -> None:
        """测试去盲逻辑：baseline=B 时，LLM 选 A → winner=candidate。"""
        evaluator = RegressionEvaluator()

        raw = BlindEvalResponse(
            surface_diff_summary="test",
            diff_analysis=[
                DiffAnalysisItem(item="test", verdict="A_better", reason="reason"),
            ],
            overall_winner="A",
            confidence=0.85,
            one_line_conclusion="A 更好",
        )

        verdict = evaluator._deblind(raw, baseline_is_a=False)
        assert verdict.overall_winner == "candidate"
        assert verdict.baseline_was_set == "B"

    def test_blind_evaluate_full_flow_regression(self, tmp_path: Path) -> None:
        """完整双盲评估流程：模拟检测到回归。"""
        b_cases = _make_baseline_cases()
        c_cases = _make_candidate_cases()
        b_dir = _write_run_dir(tmp_path / "b", b_cases, _make_evaluation_report(0.82))
        c_dir = _write_run_dir(tmp_path / "c", c_cases, _make_evaluation_report(0.65))

        # Fake LLM 总是选 A（我们需要验证去盲后的正确映射）
        fake_llm = FakeBlindLLMClient(winner="A", confidence=0.85)
        evaluator = RegressionEvaluator(llm_client=fake_llm)

        prd_path = tmp_path / "prd.md"
        prd_path.write_text("# Test PRD", encoding="utf-8")

        config = RegressionConfig(
            baseline_run_dir=b_dir,
            candidate_run_dir=c_dir,
            prd_path=str(prd_path),
            baseline_label="good-branch",
            candidate_label="bad-branch",
        )

        report = evaluator.run(config)

        # 结构层面应有回归信号
        assert report.structural_diff is not None
        assert report.structural_diff.verdict in ("WARNING", "REGRESSION")

        # LLM 评估应该存在
        assert report.blind_verdict is not None
        assert report.blind_verdict.confidence > 0

        # 报告应有明确结论
        assert report.overall_verdict in ("WARNING", "REGRESSION", "OK")

    def test_blind_evaluate_full_flow_no_regression(self, tmp_path: Path) -> None:
        """完整流程：两组相同，无回归。"""
        cases = _make_baseline_cases()
        eval_r = _make_evaluation_report(0.82)
        b_dir = _write_run_dir(tmp_path / "b", cases, eval_r)
        c_dir = _write_run_dir(tmp_path / "c", cases, eval_r)

        fake_llm = FakeBlindLLMClient(winner="tie", confidence=0.5)
        evaluator = RegressionEvaluator(llm_client=fake_llm)

        prd_path = tmp_path / "prd.md"
        prd_path.write_text("# Test PRD", encoding="utf-8")

        config = RegressionConfig(
            baseline_run_dir=b_dir,
            candidate_run_dir=c_dir,
            prd_path=str(prd_path),
        )

        report = evaluator.run(config)

        assert report.structural_diff is not None
        assert report.structural_diff.verdict == "OK"
        assert report.blind_verdict is not None
        assert report.blind_verdict.overall_winner == "tie"
        assert report.overall_verdict == "OK"

    def test_phase1_only_no_llm(self, tmp_path: Path) -> None:
        """测试仅 Phase 1（不提供 LLM 客户端）。"""
        cases = _make_baseline_cases()
        b_dir = _write_run_dir(tmp_path / "b", cases, _make_evaluation_report())
        c_dir = _write_run_dir(tmp_path / "c", cases, _make_evaluation_report())

        evaluator = RegressionEvaluator(llm_client=None)
        config = RegressionConfig(
            baseline_run_dir=b_dir, candidate_run_dir=c_dir
        )

        report = evaluator.run(config)

        assert report.structural_diff is not None
        assert report.blind_verdict is None  # 没有 LLM，不做 Phase 2
        assert report.overall_verdict == "OK"

    # ----- 边界情况 -----

    def test_duplicate_titles_detected(self, tmp_path: Path) -> None:
        """测试重复标题被正确统计。"""
        cases = [
            _make_test_case("TC-001", "重复标题", "CP-001"),
            _make_test_case("TC-002", "重复标题", "CP-002"),
            _make_test_case("TC-003", "不同标题", "CP-003"),
        ]
        run_dir = _write_run_dir(tmp_path / "run", cases)

        evaluator = RegressionEvaluator()
        fp = evaluator.extract_fingerprint(run_dir)

        assert fp.unique_title_ratio == pytest.approx(2 / 3)

    def test_empty_vs_nonempty(self, tmp_path: Path) -> None:
        """测试一组为空一组有数据的对比。"""
        b_dir = _write_run_dir(tmp_path / "b", _make_baseline_cases())
        c_dir = _write_run_dir(tmp_path / "c", [])

        evaluator = RegressionEvaluator()
        b_fp = evaluator.extract_fingerprint(b_dir)
        c_fp = evaluator.extract_fingerprint(c_dir)
        diff = evaluator.compare(b_fp, c_fp)

        assert diff.verdict == "REGRESSION"
        assert len(diff.baseline_only) == 8
        assert len(diff.candidate_only) == 0
