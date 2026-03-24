"""评测基准指标聚合与改进建议分析器。

提供两大功能：
1. ``compute_metrics``：纯计算，聚合 Precision / Recall / F1 / 平均相似度
2. ``generate_improvement_suggestions``：调用 LLM，基于指标和 diff 详情生成改进建议
"""

from __future__ import annotations

import logging
from typing import Optional

from app.clients.llm import LLMClient
from app.domain.benchmark_models import (
    BenchmarkMetrics,
    ImprovementSuggestion,
    LeafCase,
    ScoredPair,
)

logger = logging.getLogger(__name__)

_IMPROVEMENT_SYSTEM_PROMPT = """\
你是一个测试用例生成系统的质量分析专家。基于以下评测指标和具体的 case 差异详情，
分析 AI 生成的测试用例与人工基准之间的差距，并给出可行的改进建议。

请从以下维度分析：
1. overall_assessment: 总体评价（中文，100字以内）
2. strength_areas: AI 表现好的方面（列表）
3. weakness_areas: AI 需要改进的方面（列表）
4. specific_improvements: 具体可操作的改进建议（列表，每条50字以内）
5. priority_actions: 优先级最高的 3 个改进动作（列表）

请严格按 JSON 格式输出。
"""


class BenchmarkAnalyzer:
    """评测指标聚合与改进建议生成器。"""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    # ------------------------------------------------------------------
    # 纯计算：指标聚合
    # ------------------------------------------------------------------

    @staticmethod
    def compute_metrics(
        scored_pairs: list[ScoredPair],
        unmatched_ai: list[LeafCase],
        uncovered_gt: list[LeafCase],
        threshold: float = 0.7,
    ) -> BenchmarkMetrics:
        """计算评测聚合指标。

        Args:
            scored_pairs: LLM 评分后的用例对。
            unmatched_ai: 未被匹配的 AI 用例。
            uncovered_gt: 未被覆盖的基准用例。
            threshold: 匹配成功的相似度阈值。

        Returns:
            BenchmarkMetrics 指标对象。
        """
        matched = [p for p in scored_pairs if p.llm_similarity >= threshold]
        matched_count = len(matched)

        total_ai = len(scored_pairs) + len(unmatched_ai)
        total_gt = len(scored_pairs) + len(uncovered_gt)

        precision = matched_count / total_ai if total_ai > 0 else 0.0
        recall = matched_count / total_gt if total_gt > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        avg_sim = (
            sum(p.llm_similarity for p in scored_pairs) / len(scored_pairs)
            if scored_pairs
            else 0.0
        )

        # 相似度分桶统计
        buckets = {
            "0.0-0.3": 0,
            "0.3-0.5": 0,
            "0.5-0.7": 0,
            "0.7-0.9": 0,
            "0.9-1.0": 0,
        }
        for p in scored_pairs:
            s = p.llm_similarity
            if s < 0.3:
                buckets["0.0-0.3"] += 1
            elif s < 0.5:
                buckets["0.3-0.5"] += 1
            elif s < 0.7:
                buckets["0.5-0.7"] += 1
            elif s < 0.9:
                buckets["0.7-0.9"] += 1
            else:
                buckets["0.9-1.0"] += 1

        return BenchmarkMetrics(
            total_ai_cases=total_ai,
            total_gt_cases=total_gt,
            matched_count=matched_count,
            unmatched_ai_cases=unmatched_ai,
            uncovered_gt_cases=uncovered_gt,
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1=round(f1, 4),
            avg_similarity=round(avg_sim, 4),
            similarity_distribution=buckets,
        )

    # ------------------------------------------------------------------
    # LLM：改进建议
    # ------------------------------------------------------------------

    def generate_improvement_suggestions(
        self,
        metrics: BenchmarkMetrics,
        scored_pairs: list[ScoredPair],
        unmatched_ai: list[LeafCase],
        uncovered_gt: list[LeafCase],
    ) -> ImprovementSuggestion:
        """调用 LLM 生成结构化的改进建议。

        Args:
            metrics: 聚合指标。
            scored_pairs: 评分后的用例对（用于提取低分详情）。
            unmatched_ai: 未匹配的 AI 用例。
            uncovered_gt: 未覆盖的基准用例。

        Returns:
            ImprovementSuggestion 改进建议对象。
        """
        user_prompt = self._build_improvement_prompt(
            metrics, scored_pairs, unmatched_ai, uncovered_gt
        )

        try:
            result = self._llm.generate_structured(
                system_prompt=_IMPROVEMENT_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=ImprovementSuggestion,
                temperature=0.3,
                max_tokens=4096,
            )
            return result
        except Exception:
            logger.exception("LLM 改进建议生成失败")
            return ImprovementSuggestion(
                overall_assessment="改进建议生成失败，请检查 LLM 配置。"
            )

    @staticmethod
    def _build_improvement_prompt(
        metrics: BenchmarkMetrics,
        scored_pairs: list[ScoredPair],
        unmatched_ai: list[LeafCase],
        uncovered_gt: list[LeafCase],
    ) -> str:
        """构建改进建议的 user prompt。"""
        lines: list[str] = [
            "## 评测指标概览\n",
            f"- AI 生成用例总数: {metrics.total_ai_cases}",
            f"- 人工基准用例总数: {metrics.total_gt_cases}",
            f"- 匹配成功数: {metrics.matched_count}",
            f"- 精确率 (Precision): {metrics.precision:.4f}",
            f"- 召回率 (Recall): {metrics.recall:.4f}",
            f"- F1 分数: {metrics.f1:.4f}",
            f"- 平均相似度: {metrics.avg_similarity:.4f}",
            f"- 相似度分布: {metrics.similarity_distribution}",
            "",
        ]

        # 低分 pair 详情（取最多 10 个最低分）
        if scored_pairs:
            sorted_pairs = sorted(scored_pairs, key=lambda p: p.llm_similarity)
            worst = sorted_pairs[:10]
            lines.append("## 低分用例对详情（相似度最低的 10 对）\n")
            for i, p in enumerate(worst):
                lines.append(f"### 第 {i + 1} 对 (相似度: {p.llm_similarity:.2f})")
                lines.append(f"- AI: {p.ai_case.full_path_str}")
                lines.append(f"- 基准: {p.gt_case.full_path_str}")
                lines.append(f"- 差异: {p.diff_summary}")
                lines.append("")

        # 未匹配 AI 用例（过度生成）
        if unmatched_ai:
            lines.append(f"## AI 过度生成的用例（共 {len(unmatched_ai)} 个）\n")
            for case in unmatched_ai[:10]:
                lines.append(f"- {case.full_path_str}")
            if len(unmatched_ai) > 10:
                lines.append(f"- ... 以及其他 {len(unmatched_ai) - 10} 个")
            lines.append("")

        # 未覆盖基准用例（遗漏）
        if uncovered_gt:
            lines.append(f"## AI 遗漏的基准用例（共 {len(uncovered_gt)} 个）\n")
            for case in uncovered_gt[:10]:
                lines.append(f"- {case.full_path_str}")
            if len(uncovered_gt) > 10:
                lines.append(f"- ... 以及其他 {len(uncovered_gt) - 10} 个")
            lines.append("")

        return "\n".join(lines)
