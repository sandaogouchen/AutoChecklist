"""评测基准 LLM 逐对评分器。

将匹配后的用例对批量发送给 LLM 进行语义相似度评分，
返回每对的相似度分数（0-1）和差异摘要。

批量评分策略：每批 N 对（默认 5），减少 API 调用次数。
"""

from __future__ import annotations

import logging
from typing import Optional

from app.clients.llm import LLMClient
from app.domain.benchmark_models import (
    BatchEvaluationResult,
    CasePair,
    ScoredPair,
)

logger = logging.getLogger(__name__)

_EVAL_SYSTEM_PROMPT = """\
你是一个测试用例相似度评估专家。你将收到若干对测试用例，每对包含一个 AI 生成的用例和一个人工编写的基准用例。

对于每一对，请评估：
1. similarity (0.0-1.0): 语义相似度，1.0 表示完全等价
2. diff_summary: 简述两者的关键差异（中文，50字以内）

评分标准：
- 1.0: 语义完全一致，仅措辞不同
- 0.8-0.9: 核心测试点相同，细节略有差异
- 0.5-0.7: 测试方向相同但覆盖范围或深度不同
- 0.2-0.4: 有部分重叠但测试重点不同
- 0.0-0.1: 完全不相关

请严格按以下 JSON 格式输出。pair_index 必须与输入中的编号一致。
"""


def _build_user_prompt(pairs: list[CasePair], offset: int) -> str:
    """构建批量评分的 user prompt。

    Args:
        pairs: 本批待评分的用例对列表。
        offset: 全局偏移量，用于标注 pair_index。

    Returns:
        格式化的用户提示文本。
    """
    lines: list[str] = ["请评估以下测试用例对的相似度：\n"]
    for i, pair in enumerate(pairs):
        idx = offset + i
        lines.append(f"--- 第 {idx} 对 ---")
        lines.append(f"AI 用例路径: {pair.ai_case.full_path_str}")
        lines.append(f"AI 用例标题: {pair.ai_case.title}")
        lines.append(f"基准用例路径: {pair.gt_case.full_path_str}")
        lines.append(f"基准用例标题: {pair.gt_case.title}")
        lines.append("")
    return "\n".join(lines)


class BenchmarkEvaluator:
    """LLM 逐对评分器。

    将 CasePair 列表分批送入 LLM，获取结构化的相似度评分。
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    def evaluate_pairs(
        self,
        pairs: list[CasePair],
        batch_size: int = 5,
        *,
        similarity_threshold: float = 0.7,
    ) -> list[ScoredPair]:
        """对所有匹配用例对进行 LLM 评分。

        Args:
            pairs: 匹配后的用例对列表。
            batch_size: 每批评分的用例对数量。
            similarity_threshold: 判定匹配成功的相似度阈值。

        Returns:
            评分后的 ScoredPair 列表，与输入顺序一致。
        """
        if not pairs:
            return []

        scored: list[ScoredPair] = []
        total_batches = (len(pairs) + batch_size - 1) // batch_size

        for batch_idx in range(total_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, len(pairs))
            batch = pairs[start:end]

            logger.info(
                "评分批次 %d/%d: 评估第 %d-%d 对",
                batch_idx + 1,
                total_batches,
                start,
                end - 1,
            )

            batch_result = self._evaluate_batch(batch, offset=start)

            # 将 batch 结果与原始 pair 合并
            eval_map = {e.pair_index: e for e in batch_result.evaluations}
            for i, pair in enumerate(batch):
                idx = start + i
                evaluation = eval_map.get(idx)
                llm_sim = evaluation.similarity if evaluation else 0.0
                diff = evaluation.diff_summary if evaluation else "评分失败"

                scored.append(
                    ScoredPair(
                        ai_case=pair.ai_case,
                        gt_case=pair.gt_case,
                        text_similarity=pair.text_similarity,
                        llm_similarity=round(llm_sim, 4),
                        diff_summary=diff,
                        is_match=llm_sim >= similarity_threshold,
                    )
                )

        logger.info("LLM 评分完成: %d 对", len(scored))
        return scored

    def _evaluate_batch(
        self,
        batch: list[CasePair],
        offset: int,
    ) -> BatchEvaluationResult:
        """对单批用例对调用 LLM 进行评分。

        Args:
            batch: 本批待评分的用例对。
            offset: 全局 pair_index 偏移量。

        Returns:
            BatchEvaluationResult 结构化结果。
        """
        user_prompt = _build_user_prompt(batch, offset)

        try:
            result = self._llm.generate_structured(
                system_prompt=_EVAL_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=BatchEvaluationResult,
                temperature=0.1,
                max_tokens=4096,
            )
            return result
        except Exception:
            logger.exception("LLM 批量评分调用失败 (offset=%d)", offset)
            # 返回空结果，让上层以 0 分处理
            return BatchEvaluationResult(evaluations=[])
