"""BenchmarkMatcher 单元测试。"""

from __future__ import annotations

import pytest

from app.domain.benchmark_models import LeafCase
from app.services.benchmark_matcher import BenchmarkMatcher


def _make_leaf(title: str, path: list[str] | None = None) -> LeafCase:
    """辅助函数：创建 LeafCase。"""
    p = path or ["root", title]
    return LeafCase(title=title, path=p, full_path_str=" > ".join(p))


class TestBenchmarkMatcher:
    """BenchmarkMatcher 测试套件。"""

    def setup_method(self):
        self.matcher = BenchmarkMatcher()

    # ----------------------------------------------------------------
    # 空输入
    # ----------------------------------------------------------------

    def test_empty_ai_leaves(self):
        """AI 列表为空时，所有基准用例归为未覆盖。"""
        gt = [_make_leaf("case1"), _make_leaf("case2")]
        pairs, unmatched_ai, uncovered_gt = self.matcher.match([], gt)

        assert pairs == []
        assert unmatched_ai == []
        assert len(uncovered_gt) == 2

    def test_empty_gt_leaves(self):
        """基准列表为空时，所有 AI 用例归为未匹配。"""
        ai = [_make_leaf("case1"), _make_leaf("case2")]
        pairs, unmatched_ai, uncovered_gt = self.matcher.match(ai, [])

        assert pairs == []
        assert len(unmatched_ai) == 2
        assert uncovered_gt == []

    def test_both_empty(self):
        """两侧都为空时，返回空结果。"""
        pairs, unmatched_ai, uncovered_gt = self.matcher.match([], [])

        assert pairs == []
        assert unmatched_ai == []
        assert uncovered_gt == []

    # ----------------------------------------------------------------
    # 完全匹配
    # ----------------------------------------------------------------

    def test_perfect_match(self):
        """标题完全相同时，应全部匹配成功。"""
        titles = ["登录验证", "支付流程", "搜索功能"]
        ai = [_make_leaf(t) for t in titles]
        gt = [_make_leaf(t) for t in titles]

        pairs, unmatched_ai, uncovered_gt = self.matcher.match(ai, gt)

        assert len(pairs) == 3
        assert unmatched_ai == []
        assert uncovered_gt == []

        for pair in pairs:
            assert pair.text_similarity == 1.0
            assert pair.ai_case.title == pair.gt_case.title

    # ----------------------------------------------------------------
    # 完全不相关
    # ----------------------------------------------------------------

    def test_disjoint_lists(self):
        """当 AI 和基准用例完全不同且极短时，低相似度 pair 仍可能被匹配。"""
        ai = [_make_leaf("A")]
        gt = [_make_leaf("Z")]

        pairs, unmatched_ai, uncovered_gt = self.matcher.match(ai, gt)

        # 由于 full_path_str 包含 "root"，两者之间仍有一定相似度
        # 关键是测试不会崩溃，且结果合理
        total = len(pairs) + len(unmatched_ai)
        assert total == 1  # AI 侧总数应为 1

    # ----------------------------------------------------------------
    # 不等长列表
    # ----------------------------------------------------------------

    def test_more_ai_than_gt(self):
        """AI 多于基准时，多余的 AI 用例归为未匹配。"""
        ai = [_make_leaf("登录"), _make_leaf("注册"), _make_leaf("支付")]
        gt = [_make_leaf("登录"), _make_leaf("注册")]

        pairs, unmatched_ai, uncovered_gt = self.matcher.match(ai, gt)

        assert len(pairs) == 2
        assert len(unmatched_ai) == 1
        assert uncovered_gt == []

    def test_more_gt_than_ai(self):
        """基准多于 AI 时，多余的基准用例归为未覆盖。"""
        ai = [_make_leaf("登录")]
        gt = [_make_leaf("登录"), _make_leaf("注册"), _make_leaf("支付")]

        pairs, unmatched_ai, uncovered_gt = self.matcher.match(ai, gt)

        assert len(pairs) == 1
        assert unmatched_ai == []
        assert len(uncovered_gt) == 2

    # ----------------------------------------------------------------
    # 贪心分配正确性
    # ----------------------------------------------------------------

    def test_greedy_prefers_best_match(self):
        """贪心算法应优先选择最高相似度的配对。"""
        ai = [
            _make_leaf("用户登录功能验证", ["root", "认证", "用户登录功能验证"]),
            _make_leaf("用户登录", ["root", "认证", "用户登录"]),
        ]
        gt = [
            _make_leaf("用户登录功能验证", ["root", "认证", "用户登录功能验证"]),
        ]

        pairs, unmatched_ai, uncovered_gt = self.matcher.match(ai, gt)

        assert len(pairs) == 1
        assert len(unmatched_ai) == 1
        assert uncovered_gt == []

        # 完全匹配的那对应该被优先选中
        assert pairs[0].ai_case.title == "用户登录功能验证"
        assert pairs[0].text_similarity == 1.0

    # ----------------------------------------------------------------
    # 路径上下文影响匹配
    # ----------------------------------------------------------------

    def test_path_context_improves_matching(self):
        """路径上下文不同时，即使标题相同，相似度也会有差异。"""
        ai = [_make_leaf("验证", ["root", "登录", "验证"])]
        gt = [_make_leaf("验证", ["root", "支付", "验证"])]

        pairs, _, _ = self.matcher.match(ai, gt)

        assert len(pairs) == 1
        # 路径不同导致相似度 < 1.0
        assert pairs[0].text_similarity < 1.0

    # ----------------------------------------------------------------
    # min_text_similarity 阈值
    # ----------------------------------------------------------------

    def test_min_text_similarity_filters_low_pairs(self):
        """min_text_similarity 过高时，低相似度的 pair 不会被匹配。"""
        ai = [_make_leaf("完全不同的内容A")]
        gt = [_make_leaf("完全不同的内容B")]

        pairs, unmatched_ai, uncovered_gt = self.matcher.match(
            ai, gt, min_text_similarity=0.99
        )

        # 相似度达不到 0.99，不应匹配
        assert len(pairs) == 0
        assert len(unmatched_ai) == 1
        assert len(uncovered_gt) == 1
