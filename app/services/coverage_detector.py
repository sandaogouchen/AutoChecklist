"""检测 PRD checkpoint 与参考 XMind 叶子 case 的覆盖关系。

使用字符级 Jaccard 相似度（与 XMindReferenceAnalyzer 中的 routing_hints 一致），
阈值 0.4（略高于 routing_hints 的 0.3，降低误判率）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.domain.checklist_models import Checkpoint

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_COVERAGE_THRESHOLD: float = 0.4


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

class CoverageResult(BaseModel):
    """覆盖度检测结果。"""

    covered_checkpoint_ids: list[str] = Field(default_factory=list)
    uncovered_checkpoint_ids: list[str] = Field(default_factory=list)
    coverage_map: dict[str, str] = Field(
        default_factory=dict,
        description="checkpoint_id -> 匹配到的参考叶子标题",
    )


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class CoverageDetector:
    """基于标题相似度判断 PRD checkpoint 是否已被参考 XMind 覆盖。"""

    def __init__(self, threshold: float = _COVERAGE_THRESHOLD) -> None:
        self.threshold = threshold

    def detect(
        self,
        checkpoints: list,
        reference_leaf_titles: list[str],
    ) -> CoverageResult:
        """返回 CoverageResult。

        一个 checkpoint 如果与参考叶子中任意一条的 Jaccard ≥ threshold，
        即视为 covered。
        """
        if not checkpoints or not reference_leaf_titles:
            return CoverageResult(
                covered_checkpoint_ids=[],
                uncovered_checkpoint_ids=[
                    self._get_id(cp) for cp in checkpoints
                ],
            )

        covered_ids: list[str] = []
        uncovered_ids: list[str] = []
        coverage_map: dict[str, str] = {}

        for cp in checkpoints:
            cp_id = self._get_id(cp)
            cp_title = self._get_title(cp)
            best_title, best_score = self._find_best_match(
                cp_title, reference_leaf_titles,
            )
            if best_score >= self.threshold:
                covered_ids.append(cp_id)
                coverage_map[cp_id] = best_title
            else:
                uncovered_ids.append(cp_id)

        logger.info(
            "覆盖度检测: %d covered, %d uncovered (threshold=%.2f)",
            len(covered_ids), len(uncovered_ids), self.threshold,
        )

        return CoverageResult(
            covered_checkpoint_ids=covered_ids,
            uncovered_checkpoint_ids=uncovered_ids,
            coverage_map=coverage_map,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_best_match(
        title: str,
        candidates: list[str],
    ) -> tuple[str, float]:
        """在 candidates 中找到与 title Jaccard 相似度最高的。"""
        best_title = ""
        best_score = 0.0
        title_chars = set(title)

        for candidate in candidates:
            cand_chars = set(candidate)
            union = title_chars | cand_chars
            if not union:
                continue
            score = len(title_chars & cand_chars) / len(union)
            if score > best_score:
                best_score = score
                best_title = candidate

        return best_title, best_score

    @staticmethod
    def jaccard_similarity(a: str, b: str) -> float:
        """字符级 Jaccard 相似度（公开方法，供外部调用）。"""
        set_a, set_b = set(a), set(b)
        if not set_a and not set_b:
            return 1.0
        union = set_a | set_b
        if not union:
            return 0.0
        return len(set_a & set_b) / len(union)

    @staticmethod
    def _get_id(checkpoint) -> str:
        """兼容 dict 和 Pydantic model 获取 id。"""
        if isinstance(checkpoint, dict):
            return checkpoint.get("checkpoint_id") or checkpoint.get("id", "")
        return getattr(checkpoint, "checkpoint_id", "") or getattr(checkpoint, "id", "")

    @staticmethod
    def _get_title(checkpoint) -> str:
        """兼容 dict 和 Pydantic model 获取 title。"""
        if isinstance(checkpoint, dict):
            return checkpoint.get("title", "")
        return getattr(checkpoint, "title", "")
