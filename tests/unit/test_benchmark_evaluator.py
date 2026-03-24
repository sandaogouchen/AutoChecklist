"""BenchmarkEvaluator 单元测试。

使用 mock LLM 客户端进行确定性测试，遵循 conftest.py 的 fake LLM 模式。
"""

from __future__ import annotations

import json
from typing import Any, Optional, Type, TypeVar
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from app.domain.benchmark_models import (
    BatchEvaluationResult,
    CasePair,
    LeafCase,
    PairEvaluation,
)
from app.services.benchmark_evaluator import BenchmarkEvaluator

T = TypeVar("T", bound=BaseModel)


class FakeLLMClient:
    """Fake LLM 客户端，返回预设的结构化响应。"""

    def __init__(self, responses: list[BatchEvaluationResult] | None = None):
        self._responses = list(responses or [])
        self._call_count = 0

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[T],
        model: Optional[str] = None,
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> T:
        """返回预设响应。"""
        if self._call_count < len(self._responses):
            result = self._responses[self._call_count]
            self._call_count += 1
            return result
        # 默认返回空结果
        return BatchEvaluationResult(evaluations=[])

    @property
    def call_count(self) -> int:
        return self._call_count


def _make_leaf(title: str) -> LeafCase:
    """辅助函数：创建 LeafCase。"""
    path = ["root", title]
    return LeafCase(title=title, path=path, full_path_str=" > ".join(path))


def _make_pair(ai_title: str, gt_title: str, sim: float = 0.5) -> CasePair:
    """辅助函数：创建 CasePair。"""
    return CasePair(
        ai_case=_make_leaf(ai_title),
        gt_case=_make_leaf(gt_title),
        text_similarity=sim,
    )


class TestBenchmarkEvaluator:
    """BenchmarkEvaluator 测试套件。"""

    # ----------------------------------------------------------------
    # 空输入
    # ----------------------------------------------------------------

    def test_empty_pairs(self):
        """空列表输入应返回空结果。"""
        fake_llm = FakeLLMClient()
        evaluator = BenchmarkEvaluator(fake_llm)

        result = evaluator.evaluate_pairs([])

        assert result == []
        assert fake_llm.call_count == 0

    # ----------------------------------------------------------------
    # 单 pair 评分
    # ----------------------------------------------------------------

    def test_single_pair_scoring(self):
        """单个用例对应被正确评分。"""
        expected_eval = BatchEvaluationResult(
            evaluations=[
                PairEvaluation(
                    pair_index=0,
                    similarity=0.85,
                    diff_summary="核心测试点相同，AI 缺少边界条件",
                ),
            ]
        )
        fake_llm = FakeLLMClient(responses=[expected_eval])
        evaluator = BenchmarkEvaluator(fake_llm)

        pairs = [_make_pair("登录验证", "用户登录验证")]
        result = evaluator.evaluate_pairs(pairs, batch_size=5)

        assert len(result) == 1
        assert result[0].llm_similarity == 0.85
        assert result[0].diff_summary == "核心测试点相同，AI 缺少边界条件"
        assert result[0].is_match is True  # 0.85 >= 0.7
        assert fake_llm.call_count == 1

    # ----------------------------------------------------------------
    # 批次拆分
    # ----------------------------------------------------------------

    def test_batch_splitting(self):
        """7 个 pair、batch_size=3 应产生 3 次 LLM 调用。"""
        responses = [
            BatchEvaluationResult(
                evaluations=[
                    PairEvaluation(pair_index=i, similarity=0.8, diff_summary=f"diff-{i}")
                    for i in range(start, min(start + 3, 7))
                ]
            )
            for start in range(0, 7, 3)
        ]
        fake_llm = FakeLLMClient(responses=responses)
        evaluator = BenchmarkEvaluator(fake_llm)

        pairs = [_make_pair(f"ai-{i}", f"gt-{i}") for i in range(7)]
        result = evaluator.evaluate_pairs(pairs, batch_size=3)

        assert len(result) == 7
        assert fake_llm.call_count == 3  # ceil(7/3) = 3
        for scored in result:
            assert scored.llm_similarity == 0.8

    # ----------------------------------------------------------------
    # 阈值判定
    # ----------------------------------------------------------------

    def test_threshold_below(self):
        """低于阈值的 pair 应标记为不匹配。"""
        expected_eval = BatchEvaluationResult(
            evaluations=[
                PairEvaluation(pair_index=0, similarity=0.3, diff_summary="完全不同"),
            ]
        )
        fake_llm = FakeLLMClient(responses=[expected_eval])
        evaluator = BenchmarkEvaluator(fake_llm)

        pairs = [_make_pair("A", "B")]
        result = evaluator.evaluate_pairs(
            pairs, batch_size=5, similarity_threshold=0.7
        )

        assert len(result) == 1
        assert result[0].is_match is False

    def test_threshold_exact(self):
        """恰好等于阈值的 pair 应标记为匹配。"""
        expected_eval = BatchEvaluationResult(
            evaluations=[
                PairEvaluation(pair_index=0, similarity=0.7, diff_summary="边界"),
            ]
        )
        fake_llm = FakeLLMClient(responses=[expected_eval])
        evaluator = BenchmarkEvaluator(fake_llm)

        pairs = [_make_pair("A", "B")]
        result = evaluator.evaluate_pairs(
            pairs, batch_size=5, similarity_threshold=0.7
        )

        assert len(result) == 1
        assert result[0].is_match is True

    # ----------------------------------------------------------------
    # LLM 调用失败
    # ----------------------------------------------------------------

    def test_llm_failure_returns_zero_scores(self):
        """LLM 调用失败时，pair 应以 0 分和失败标记返回。"""
        # 不提供任何预设响应，FakeLLM 将返回空 BatchEvaluationResult
        fake_llm = FakeLLMClient(responses=[])
        evaluator = BenchmarkEvaluator(fake_llm)

        pairs = [_make_pair("A", "B")]
        result = evaluator.evaluate_pairs(pairs, batch_size=5)

        assert len(result) == 1
        assert result[0].llm_similarity == 0.0
        assert result[0].diff_summary == "评分失败"
        assert result[0].is_match is False

    # ----------------------------------------------------------------
    # text_similarity 保持不变
    # ----------------------------------------------------------------

    def test_text_similarity_preserved(self):
        """ScoredPair 应保留原始 CasePair 的 text_similarity。"""
        expected_eval = BatchEvaluationResult(
            evaluations=[
                PairEvaluation(pair_index=0, similarity=0.9, diff_summary="ok"),
            ]
        )
        fake_llm = FakeLLMClient(responses=[expected_eval])
        evaluator = BenchmarkEvaluator(fake_llm)

        pairs = [_make_pair("A", "A", sim=0.95)]
        result = evaluator.evaluate_pairs(pairs, batch_size=5)

        assert result[0].text_similarity == 0.95
        assert result[0].llm_similarity == 0.9
