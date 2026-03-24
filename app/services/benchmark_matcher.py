"""评测基准用例匹配器。

基于 ``difflib.SequenceMatcher`` 的贪心最优匹配算法，
将 AI 生成的叶子用例与人工基准叶子用例进行一对一配对。

匹配使用 ``full_path_str``（含祖先路径上下文）而非仅叶子标题，
以提高中文短文本场景下的匹配准确度。
"""

from __future__ import annotations

import difflib
import logging

from app.domain.benchmark_models import CasePair, LeafCase

logger = logging.getLogger(__name__)


class BenchmarkMatcher:
    """贪心最优匹配器。

    算法流程：
    1. 构建 gt × ai 的相似度矩阵
    2. 按相似度从高到低贪心分配：每次取全局最高分的未分配 pair
    3. 剩余 AI 用例归为 unmatched_ai（过度生成）
    4. 剩余基准用例归为 uncovered_gt（遗漏）
    """

    def match(
        self,
        ai_leaves: list[LeafCase],
        gt_leaves: list[LeafCase],
        *,
        min_text_similarity: float = 0.1,
    ) -> tuple[list[CasePair], list[LeafCase], list[LeafCase]]:
        """执行一对一匹配。

        Args:
            ai_leaves: AI 生成的叶子用例列表。
            gt_leaves: 人工基准的叶子用例列表。
            min_text_similarity: 最低文本相似度阈值，低于此值不考虑匹配。

        Returns:
            三元组：
            - matched pairs 列表
            - unmatched AI cases 列表（AI 中多余的）
            - uncovered GT cases 列表（基准中未覆盖的）
        """
        if not ai_leaves or not gt_leaves:
            return [], list(ai_leaves), list(gt_leaves)

        # 构建候选 pair 列表（带相似度）
        candidates: list[tuple[float, int, int]] = []
        for gi, gt_case in enumerate(gt_leaves):
            for ai, ai_case in enumerate(ai_leaves):
                sim = self._compute_similarity(
                    ai_case.full_path_str, gt_case.full_path_str
                )
                if sim >= min_text_similarity:
                    candidates.append((sim, gi, ai))

        # 按相似度降序排列
        candidates.sort(key=lambda x: x[0], reverse=True)

        # 贪心分配
        assigned_ai: set[int] = set()
        assigned_gt: set[int] = set()
        pairs: list[CasePair] = []

        for sim, gi, ai in candidates:
            if gi in assigned_gt or ai in assigned_ai:
                continue
            pairs.append(
                CasePair(
                    ai_case=ai_leaves[ai],
                    gt_case=gt_leaves[gi],
                    text_similarity=round(sim, 4),
                )
            )
            assigned_ai.add(ai)
            assigned_gt.add(gi)

        # 收集未匹配项
        unmatched_ai = [
            ai_leaves[i] for i in range(len(ai_leaves)) if i not in assigned_ai
        ]
        uncovered_gt = [
            gt_leaves[i] for i in range(len(gt_leaves)) if i not in assigned_gt
        ]

        logger.info(
            "匹配完成: %d 对, %d 未匹配 AI, %d 未覆盖基准",
            len(pairs),
            len(unmatched_ai),
            len(uncovered_gt),
        )
        return pairs, unmatched_ai, uncovered_gt

    @staticmethod
    def _compute_similarity(text_a: str, text_b: str) -> float:
        """基于 SequenceMatcher 计算两段文本的相似度。

        Args:
            text_a: 第一段文本。
            text_b: 第二段文本。

        Returns:
            0.0–1.0 之间的相似度分数。
        """
        if not text_a or not text_b:
            return 0.0
        return difflib.SequenceMatcher(None, text_a, text_b).ratio()
