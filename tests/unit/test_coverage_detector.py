"""CoverageDetector 单元测试。"""

from __future__ import annotations

import pytest

from app.services.coverage_detector import CoverageDetector, CoverageResult


@pytest.fixture
def detector() -> CoverageDetector:
    return CoverageDetector()


class _FakeCheckpoint:
    """轻量 checkpoint 模拟。"""

    def __init__(self, id: str, title: str) -> None:
        self.id = id
        self.title = title


class TestDetect:
    """detect() 方法测试。"""

    def test_full_coverage(self, detector: CoverageDetector) -> None:
        cps = [_FakeCheckpoint("cp1", "微信支付成功")]
        refs = ["微信支付成功"]
        result = detector.detect(cps, refs)

        assert "cp1" in result.covered_checkpoint_ids
        assert result.uncovered_checkpoint_ids == []

    def test_partial_coverage(self, detector: CoverageDetector) -> None:
        cps = [
            _FakeCheckpoint("cp1", "微信支付成功"),
            _FakeCheckpoint("cp2", "新增功能测试"),
        ]
        refs = ["微信支付成功"]
        result = detector.detect(cps, refs)

        assert "cp1" in result.covered_checkpoint_ids
        assert "cp2" in result.uncovered_checkpoint_ids

    def test_zero_coverage(self, detector: CoverageDetector) -> None:
        cps = [_FakeCheckpoint("cp1", "全新功能ABC")]
        refs = ["完全不同的XYZ"]
        result = detector.detect(cps, refs)

        assert result.covered_checkpoint_ids == []
        assert "cp1" in result.uncovered_checkpoint_ids

    def test_empty_checkpoints(self, detector: CoverageDetector) -> None:
        result = detector.detect([], ["微信支付成功"])
        assert result.covered_checkpoint_ids == []
        assert result.uncovered_checkpoint_ids == []

    def test_empty_references(self, detector: CoverageDetector) -> None:
        cps = [_FakeCheckpoint("cp1", "测试")]
        result = detector.detect(cps, [])
        assert result.covered_checkpoint_ids == []
        assert "cp1" in result.uncovered_checkpoint_ids

    def test_coverage_map_populated(self, detector: CoverageDetector) -> None:
        cps = [_FakeCheckpoint("cp1", "微信支付成功")]
        refs = ["微信支付成功"]
        result = detector.detect(cps, refs)

        assert result.coverage_map.get("cp1") == "微信支付成功"

    def test_dict_checkpoint_support(self, detector: CoverageDetector) -> None:
        cps = [{"id": "cp1", "title": "微信支付成功"}]
        refs = ["微信支付成功"]
        result = detector.detect(cps, refs)

        assert "cp1" in result.covered_checkpoint_ids

    def test_threshold_boundary(self) -> None:
        # Jaccard of two very different strings should be below 0.4
        detector = CoverageDetector(threshold=0.4)
        cps = [_FakeCheckpoint("cp1", "ABCDE")]
        refs = ["VWXYZ"]
        result = detector.detect(cps, refs)

        assert "cp1" in result.uncovered_checkpoint_ids


class TestJaccardSimilarity:
    """jaccard_similarity() 方法测试。"""

    def test_identical_strings(self) -> None:
        assert CoverageDetector.jaccard_similarity("abc", "abc") == 1.0

    def test_completely_different(self) -> None:
        assert CoverageDetector.jaccard_similarity("abc", "xyz") == 0.0

    def test_partial_overlap(self) -> None:
        score = CoverageDetector.jaccard_similarity("abcd", "cdef")
        # intersection = {c, d}, union = {a, b, c, d, e, f}
        assert abs(score - 2 / 6) < 1e-9

    def test_empty_strings(self) -> None:
        assert CoverageDetector.jaccard_similarity("", "") == 1.0

    def test_one_empty(self) -> None:
        assert CoverageDetector.jaccard_similarity("abc", "") == 0.0

    def test_chinese_support(self) -> None:
        score = CoverageDetector.jaccard_similarity("微信支付成功", "微信支付失败")
        # intersection = {微,信,支,付}, union = {微,信,支,付,成,功,失,败}
        assert abs(score - 4 / 8) < 1e-9
