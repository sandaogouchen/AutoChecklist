"""回归评估服务。

提供基于 Golden Request 基线的快速回归检测：
- Phase 1：结构指纹对比（零 LLM 调用，秒级完成）
- Phase 2：LLM 双盲质量评估（可选，需 LLM 客户端）
"""

from __future__ import annotations

import json
import logging
import random
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Protocol, Type, TypeVar, runtime_checkable

from pydantic import BaseModel

from app.domain.regression_models import (
    BlindEvalResponse,
    BlindVerdict,
    CaseMatch,
    MetricDelta,
    RegressionConfig,
    RegressionReport,
    RunFingerprint,
    StructuralDiff,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class StructuredLLMClient(Protocol):
    """LLM 客户端协议，兼容 OpenAICompatibleLLMClient。"""

    def generate_structured(
        self, prompt: str, response_model: Type[T], **kwargs: Any
    ) -> T: ...


# ---------------------------------------------------------------------------
# 核心评估器
# ---------------------------------------------------------------------------


class RegressionEvaluator:
    """回归评估器。

    用法::

        evaluator = RegressionEvaluator(llm_client=my_client)
        report = evaluator.run(config)
        print(report.overall_verdict)
    """

    def __init__(self, llm_client: StructuredLLMClient | None = None) -> None:
        self.llm_client = llm_client

    # ----- 公开方法 -----

    def run(self, config: RegressionConfig) -> RegressionReport:
        """执行完整评估流程（Phase 1 + 可选 Phase 2）。"""
        baseline_fp = self.extract_fingerprint(
            config.baseline_run_dir, config.baseline_label
        )
        candidate_fp = self.extract_fingerprint(
            config.candidate_run_dir, config.candidate_label
        )

        structural_diff = self.compare(baseline_fp, candidate_fp)

        blind_verdict = None
        if self.llm_client and config.prd_path:
            prd_path = Path(config.prd_path)
            if prd_path.exists():
                prd_text = prd_path.read_text(encoding="utf-8")
                blind_verdict = self.blind_evaluate(structural_diff, prd_text)
            else:
                logger.warning("PRD 文件不存在: %s，跳过 Phase 2", config.prd_path)

        overall = self._determine_overall_verdict(structural_diff, blind_verdict)
        summary = self._build_summary(structural_diff, blind_verdict, overall)

        return RegressionReport(
            structural_diff=structural_diff,
            blind_verdict=blind_verdict,
            overall_verdict=overall,
            summary=summary,
        )

    def extract_fingerprint(
        self, run_dir: str, label: str = ""
    ) -> RunFingerprint:
        """从运行目录提取结构指纹。"""
        run_path = Path(run_dir)
        fp = RunFingerprint(run_dir=run_dir, label=label)

        test_cases = self._load_test_cases(run_path)
        fp.test_cases_raw = test_cases
        fp.total_test_cases = len(test_cases)
        fp.total_checkpoints = self._load_checkpoint_count(run_path, test_cases)

        if test_cases:
            steps_counts = [len(tc.get("steps", [])) for tc in test_cases]
            fp.avg_steps_per_case = (
                sum(steps_counts) / len(steps_counts) if steps_counts else 0.0
            )
            fp.cases_with_evidence = sum(
                1 for tc in test_cases if tc.get("evidence_refs")
            )
            fp.cases_with_preconditions = sum(
                1 for tc in test_cases if tc.get("preconditions")
            )

            titles = [tc.get("title", "").strip().casefold() for tc in test_cases]
            unique_count = len(set(titles))
            fp.unique_title_ratio = (
                unique_count / len(titles) if titles else 1.0
            )

            for tc in test_cases:
                cat = tc.get("category", "unknown")
                fp.category_distribution[cat] = (
                    fp.category_distribution.get(cat, 0) + 1
                )
                pri = tc.get("priority", "unknown")
                fp.priority_distribution[pri] = (
                    fp.priority_distribution.get(pri, 0) + 1
                )

            fp.mr_analysis_present = any(
                "mr_derived" in tc.get("tags", [])
                or tc.get("code_consistency")
                for tc in test_cases
            )

        eval_report = self._load_json(run_path / "evaluation_report.json")
        if eval_report:
            fp.overall_score = eval_report.get("overall_score", 0.0)
            for dim in eval_report.get("dimensions", []):
                if isinstance(dim, dict) and "name" in dim:
                    fp.six_dim_scores[dim["name"]] = dim.get("score", 0.0)

        return fp

    def compare(
        self, baseline: RunFingerprint, candidate: RunFingerprint
    ) -> StructuralDiff:
        """Phase 1：结构对比。"""
        matched, b_only, c_only = self._match_cases(
            baseline.test_cases_raw, candidate.test_cases_raw
        )

        deltas = self._compute_metric_deltas(baseline, candidate)

        # 判定
        critical = sum(
            1 for m in deltas.values() if m.status == "CRITICAL"
        )
        regressed = sum(
            1 for m in deltas.values() if m.status == "REGRESSED"
        )
        warnings = sum(
            1 for m in deltas.values() if m.status == "WARNING"
        )

        if critical > 0 or regressed >= 2:
            verdict = "REGRESSION"
        elif regressed > 0 or warnings >= 2:
            verdict = "WARNING"
        else:
            verdict = "OK"

        return StructuralDiff(
            baseline_fingerprint=baseline,
            candidate_fingerprint=candidate,
            matched_pairs=matched,
            baseline_only=b_only,
            candidate_only=c_only,
            metric_deltas=deltas,
            verdict=verdict,
        )

    def blind_evaluate(
        self, diff: StructuralDiff, prd_text: str
    ) -> BlindVerdict:
        """Phase 2：LLM 双盲评估。

        随机将 baseline/candidate 分配为 Set A / Set B，
        让 LLM 在不知道哪个是基线的情况下判断质量优劣。
        """
        if not self.llm_client:
            raise ValueError("Phase 2 需要 LLM 客户端")

        # 随机分配 A/B（双盲）
        baseline_is_a = random.choice([True, False])

        if baseline_is_a:
            a_cases = diff.baseline_fingerprint.test_cases_raw
            b_cases = diff.candidate_fingerprint.test_cases_raw
            a_only = diff.baseline_only
            b_only = diff.candidate_only
        else:
            a_cases = diff.candidate_fingerprint.test_cases_raw
            b_cases = diff.baseline_fingerprint.test_cases_raw
            a_only = diff.candidate_only
            b_only = diff.baseline_only

        prompt = self._build_blind_prompt(
            prd_text=prd_text,
            a_cases=a_cases,
            b_cases=b_cases,
            a_only=a_only,
            b_only=b_only,
            matched_pairs=diff.matched_pairs,
            baseline_is_a=baseline_is_a,
        )

        raw: BlindEvalResponse = self.llm_client.generate_structured(
            prompt, BlindEvalResponse
        )

        return self._deblind(raw, baseline_is_a)

    # ----- 内部方法 -----

    def _match_cases(
        self, baseline_cases: list[dict], candidate_cases: list[dict]
    ) -> tuple[list[CaseMatch], list[dict], list[dict]]:
        """配对用例：先按 checkpoint_id 精确匹配，再按标题模糊匹配。"""
        matched: list[CaseMatch] = []
        matched_b_ids: set[str] = set()
        matched_c_ids: set[str] = set()

        # Step 1: checkpoint_id 精确匹配
        b_by_cpid: dict[str, dict] = {}
        for tc in baseline_cases:
            cpid = tc.get("checkpoint_id", "")
            if cpid:
                b_by_cpid[cpid] = tc

        c_by_cpid: dict[str, dict] = {}
        for tc in candidate_cases:
            cpid = tc.get("checkpoint_id", "")
            if cpid:
                c_by_cpid[cpid] = tc

        for cpid, b_tc in b_by_cpid.items():
            if cpid in c_by_cpid:
                matched.append(
                    CaseMatch(
                        baseline_case=b_tc,
                        candidate_case=c_by_cpid[cpid],
                        match_score=1.0,
                        match_key=f"checkpoint_id:{cpid}",
                    )
                )
                matched_b_ids.add(b_tc.get("id", ""))
                matched_c_ids.add(c_by_cpid[cpid].get("id", ""))

        # Step 2: 剩余用例按标题模糊匹配（贪心最优）
        remaining_b = [
            tc for tc in baseline_cases if tc.get("id", "") not in matched_b_ids
        ]
        remaining_c = [
            tc for tc in candidate_cases if tc.get("id", "") not in matched_c_ids
        ]

        if remaining_b and remaining_c:
            # 构建全量相似度矩阵
            scores: list[tuple[float, int, int]] = []
            for i, b_tc in enumerate(remaining_b):
                for j, c_tc in enumerate(remaining_c):
                    sim = SequenceMatcher(
                        None,
                        b_tc.get("title", "").casefold(),
                        c_tc.get("title", "").casefold(),
                    ).ratio()
                    scores.append((sim, i, j))

            scores.sort(reverse=True)
            used_b: set[int] = set()
            used_c: set[int] = set()

            for sim, i, j in scores:
                if sim < 0.6:
                    break
                if i in used_b or j in used_c:
                    continue
                matched.append(
                    CaseMatch(
                        baseline_case=remaining_b[i],
                        candidate_case=remaining_c[j],
                        match_score=sim,
                        match_key=f"title_sim:{sim:.2f}",
                    )
                )
                used_b.add(i)
                used_c.add(j)

            b_only = [
                remaining_b[i]
                for i in range(len(remaining_b))
                if i not in used_b
            ]
            c_only = [
                remaining_c[j]
                for j in range(len(remaining_c))
                if j not in used_c
            ]
        else:
            b_only = remaining_b
            c_only = remaining_c

        return matched, b_only, c_only

    def _compute_metric_deltas(
        self, baseline: RunFingerprint, candidate: RunFingerprint
    ) -> dict[str, MetricDelta]:
        """计算各指标的对比结果。"""
        deltas: dict[str, MetricDelta] = {}

        # 数量类指标（百分比变化）
        for name, b_val, c_val, threshold_pct in [
            ("total_test_cases", baseline.total_test_cases, candidate.total_test_cases, 15),
            ("total_checkpoints", baseline.total_checkpoints, candidate.total_checkpoints, 15),
        ]:
            if b_val == 0:
                delta_pct = 0.0 if c_val == 0 else 100.0
            else:
                delta_pct = ((c_val - b_val) / b_val) * 100

            if delta_pct < -threshold_pct * 2:
                status = "REGRESSED"
            elif delta_pct < -threshold_pct:
                status = "WARNING"
            else:
                status = "OK"

            deltas[name] = MetricDelta(
                baseline_value=b_val,
                candidate_value=c_val,
                delta=f"{delta_pct:+.0f}%",
                status=status,
            )

        # 评分类指标（绝对值差）
        deltas["overall_score"] = self._score_delta(
            "overall_score",
            baseline.overall_score,
            candidate.overall_score,
            warn_drop=0.05,
            regress_drop=0.10,
        )

        # 6 维分数
        all_dim_names = set(baseline.six_dim_scores) | set(candidate.six_dim_scores)
        for dim_name in sorted(all_dim_names):
            b_score = baseline.six_dim_scores.get(dim_name, 0.0)
            c_score = candidate.six_dim_scores.get(dim_name, 0.0)
            deltas[dim_name] = self._score_delta(
                dim_name, b_score, c_score, warn_drop=0.05, regress_drop=0.15
            )

        # 布尔类关键信号
        if baseline.mr_analysis_present and not candidate.mr_analysis_present:
            deltas["mr_analysis_present"] = MetricDelta(
                baseline_value=True,
                candidate_value=False,
                delta="lost",
                status="CRITICAL",
            )

        return deltas

    def _score_delta(
        self,
        name: str,
        b_val: float,
        c_val: float,
        warn_drop: float,
        regress_drop: float,
    ) -> MetricDelta:
        delta = c_val - b_val
        if delta < -regress_drop:
            status = "REGRESSED"
        elif delta < -warn_drop:
            status = "WARNING"
        else:
            status = "OK"
        return MetricDelta(
            baseline_value=round(b_val, 4),
            candidate_value=round(c_val, 4),
            delta=f"{delta:+.4f}",
            status=status,
        )

    def _build_blind_prompt(
        self,
        *,
        prd_text: str,
        a_cases: list[dict],
        b_cases: list[dict],
        a_only: list[dict],
        b_only: list[dict],
        matched_pairs: list[CaseMatch],
        baseline_is_a: bool,
    ) -> str:
        """构建双盲评估 prompt。"""
        # 截断 PRD 避免超长
        prd_summary = prd_text[:8000] if len(prd_text) > 8000 else prd_text

        # 表面差距
        a_only_titles = self._format_title_list(a_only)
        b_only_titles = self._format_title_list(b_only)

        # 配对中内容有差异的
        diff_pairs_text = self._format_diff_pairs(matched_pairs, baseline_is_a)

        # 仅 A / 仅 B 的详情（限制数量）
        a_only_details = self._format_cases_detail(a_only, max_count=15)
        b_only_details = self._format_cases_detail(b_only, max_count=15)

        return f"""你是测试用例质量评审专家。以下是针对同一份 PRD 生成的两组测试用例（Set A / Set B），\
顺序已随机化，你不知道哪组是原版哪组是新版。

## PRD 需求文档
{prd_summary}

## 表面差距
- Set A: {len(a_cases)} 个用例
- Set B: {len(b_cases)} 个用例
- 仅在 Set A 中的用例 ({len(a_only)} 个):
{a_only_titles}
- 仅在 Set B 中的用例 ({len(b_only)} 个):
{b_only_titles}
- 配对但内容有差异 ({len(matched_pairs)} 对):
{diff_pairs_text}

## 仅 Set A 的用例详情
{a_only_details if a_only else "(无)"}

## 仅 Set B 的用例详情
{b_only_details if b_only else "(无)"}

## 请分析

1. 先总结表面差距：两组的主要区别是什么？
2. 再逐项分析每个差异：是改进还是退化？
3. 给出整体结论。

请严格以 JSON 格式回答，不要输出其他内容：
{{
  "surface_diff_summary": "2-3 句话总结两组最大的表面差距",
  "diff_analysis": [
    {{"item": "差异项描述", "verdict": "A_better 或 B_better 或 tie", "reason": "理由"}}
  ],
  "overall_winner": "A" 或 "B" 或 "tie",
  "confidence": 0.0到1.0的置信度,
  "one_line_conclusion": "一句话结论"
}}"""

    def _deblind(
        self, raw: BlindEvalResponse, baseline_is_a: bool
    ) -> BlindVerdict:
        """将 LLM 的 A/B 结果去盲，映射为 baseline/candidate。"""
        winner_map = {"A": "baseline", "B": "candidate"}
        if not baseline_is_a:
            winner_map = {"A": "candidate", "B": "baseline"}

        overall_winner = winner_map.get(raw.overall_winner, "tie")

        # 去盲每个 diff_analysis 的 verdict
        reasons: list[str] = []
        for item in raw.diff_analysis:
            verdict_deblind = item.verdict
            if "A_better" in item.verdict:
                actual = "baseline" if baseline_is_a else "candidate"
                verdict_deblind = f"{actual}_better"
            elif "B_better" in item.verdict:
                actual = "candidate" if baseline_is_a else "baseline"
                verdict_deblind = f"{actual}_better"
            reasons.append(f"[{verdict_deblind}] {item.item}: {item.reason}")

        return BlindVerdict(
            surface_analysis=raw.surface_diff_summary,
            quality_analysis="\n".join(reasons) if reasons else raw.one_line_conclusion,
            overall_winner=overall_winner,
            confidence=raw.confidence,
            key_reasons=[item.reason for item in raw.diff_analysis],
            baseline_was_set="A" if baseline_is_a else "B",
            raw_response=raw,
        )

    # ----- 格式化辅助 -----

    @staticmethod
    def _format_title_list(cases: list[dict], max_show: int = 20) -> str:
        if not cases:
            return "  (无)"
        lines = []
        for tc in cases[:max_show]:
            tid = tc.get("id", "?")
            title = tc.get("title", "?")
            pri = tc.get("priority", "?")
            lines.append(f"  - [{tid}] {title} ({pri})")
        if len(cases) > max_show:
            lines.append(f"  ... 以及其他 {len(cases) - max_show} 个")
        return "\n".join(lines)

    @staticmethod
    def _format_cases_detail(cases: list[dict], max_count: int = 15) -> str:
        if not cases:
            return "(无)"
        parts = []
        for tc in cases[:max_count]:
            tid = tc.get("id", "?")
            title = tc.get("title", "?")
            pri = tc.get("priority", "?")
            cat = tc.get("category", "?")
            steps = tc.get("steps", [])
            expected = tc.get("expected_results", [])
            preconds = tc.get("preconditions", [])

            part = f"### [{tid}] {title} ({pri}/{cat})"
            if preconds:
                part += f"\n前置条件: {'; '.join(preconds[:5])}"
            if steps:
                step_str = " → ".join(f"{i+1}.{s}" for i, s in enumerate(steps[:8]))
                part += f"\n步骤: {step_str}"
            if expected:
                part += f"\n预期: {'; '.join(expected[:5])}"
            parts.append(part)

        if len(cases) > max_count:
            parts.append(f"\n... 以及其他 {len(cases) - max_count} 个用例")
        return "\n\n".join(parts)

    @staticmethod
    def _format_diff_pairs(
        pairs: list[CaseMatch], baseline_is_a: bool
    ) -> str:
        if not pairs:
            return "  (无差异配对)"
        lines = []
        for pair in pairs[:15]:
            b_title = pair.baseline_case.get("title", "?")
            c_title = pair.candidate_case.get("title", "?")
            if baseline_is_a:
                lines.append(f"  - A: {b_title} ↔ B: {c_title} (匹配度 {pair.match_score:.2f})")
            else:
                lines.append(f"  - A: {c_title} ↔ B: {b_title} (匹配度 {pair.match_score:.2f})")
        if len(pairs) > 15:
            lines.append(f"  ... 以及其他 {len(pairs) - 15} 对")
        return "\n".join(lines)

    # ----- 数据加载 -----

    @staticmethod
    def _load_json(path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("读取 %s 失败: %s", path, exc)
            return None

    def _load_test_cases(self, run_path: Path) -> list[dict]:
        """从运行目录加载 test cases，兼容多种文件结构。"""
        # 尝试 run_result.json
        result = self._load_json(run_path / "run_result.json")
        if result and isinstance(result.get("test_cases"), list):
            return result["test_cases"]

        # 尝试 result.json
        result = self._load_json(run_path / "result.json")
        if result and isinstance(result.get("test_cases"), list):
            return result["test_cases"]

        # 遍历目录找到包含 test_cases 的 JSON
        if run_path.is_dir():
            for json_file in sorted(run_path.glob("*.json")):
                data = self._load_json(json_file)
                if data and isinstance(data.get("test_cases"), list):
                    logger.info("从 %s 加载 test_cases", json_file.name)
                    return data["test_cases"]

        logger.warning("未在 %s 找到 test_cases", run_path)
        return []

    def _load_checkpoint_count(
        self, run_path: Path, test_cases: list[dict]
    ) -> int:
        """加载 checkpoint 数量。"""
        # 尝试从 run_result 获取
        result = self._load_json(run_path / "run_result.json")
        if result and isinstance(result.get("checkpoint_count"), int):
            return result["checkpoint_count"]

        # 从 test cases 的唯一 checkpoint_id 推算
        cp_ids = {
            tc.get("checkpoint_id", "")
            for tc in test_cases
            if tc.get("checkpoint_id")
        }
        return len(cp_ids)

    # ----- 综合判定 -----

    @staticmethod
    def _determine_overall_verdict(
        diff: StructuralDiff, blind: BlindVerdict | None
    ) -> str:
        if blind:
            if blind.overall_winner == "candidate":
                return "OK" if diff.verdict != "REGRESSION" else "WARNING"
            if blind.overall_winner == "baseline":
                return "REGRESSION"
            # tie → 依赖 structural
            return diff.verdict
        return diff.verdict

    @staticmethod
    def _build_summary(
        diff: StructuralDiff,
        blind: BlindVerdict | None,
        overall: str,
    ) -> str:
        b_label = diff.baseline_fingerprint.label or "baseline"
        c_label = diff.candidate_fingerprint.label or "candidate"
        lines = [f"比较 {b_label} vs {c_label}:"]

        b_n = diff.baseline_fingerprint.total_test_cases
        c_n = diff.candidate_fingerprint.total_test_cases
        lines.append(f"  用例数: {b_n} → {c_n} (差 {c_n - b_n:+d})")
        lines.append(
            f"  仅基线有: {len(diff.baseline_only)} | 仅候选有: {len(diff.candidate_only)} | 配对: {len(diff.matched_pairs)}"
        )
        lines.append(f"  结构判定: {diff.verdict}")

        if blind:
            lines.append(f"  LLM 判定: {blind.overall_winner} (置信度 {blind.confidence:.0%})")
            lines.append(f"  LLM 结论: {blind.surface_analysis}")

        lines.append(f"  综合结论: {overall}")
        return "\n".join(lines)
