"""Checkpoint 分批规划单元测试。

覆盖场景：
1. 分组策略（section-based + fallback）
2. 跨 batch outline 节点去重
3. 路径重映射
4. 单批 / 分批路径选择
5. 边界情况（空输入、threshold 边界）
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.domain.checklist_models import (
    CanonicalOutlineNode,
    CanonicalOutlineNodeCollection,
    CheckpointPathCollection,
    CheckpointPathMapping,
)
from app.domain.checkpoint_models import Checkpoint
from app.domain.research_models import ResearchFact, ResearchOutput
from app.services.checkpoint_outline_planner import (
    CheckpointOutlinePlanner,
    _BatchGroup,
    _normalize_text,
)


def _make_fact(fact_id: str, source_section: str = "") -> ResearchFact:
    return ResearchFact(
        fact_id=fact_id,
        description=f"Description for {fact_id}",
        source_section=source_section,
        category="functional",
    )


def _make_checkpoint(
    checkpoint_id: str,
    title: str,
    fact_ids: list[str] | None = None,
) -> Checkpoint:
    return Checkpoint(
        checkpoint_id=checkpoint_id,
        title=title,
        objective=f"Objective for {title}",
        category="functional",
        risk="medium",
        preconditions=[],
        fact_ids=fact_ids or [],
    )


class TestGroupCheckpointsBySection(unittest.TestCase):
    """Test _group_checkpoints_by_section."""

    def setUp(self):
        self.llm_client = MagicMock()
        self.planner = CheckpointOutlinePlanner(
            llm_client=self.llm_client,
            batch_threshold=5,
            batch_size=3,
        )

    def test_groups_by_source_section(self):
        """Checkpoints 按 fact 的 source_section 分组。"""
        facts = [
            _make_fact("f1", source_section="Login Module"),
            _make_fact("f2", source_section="Login Module"),
            _make_fact("f3", source_section="Payment Module"),
            _make_fact("f4", source_section="Payment Module"),
        ]
        research = ResearchOutput(facts=facts)

        checkpoints = [
            _make_checkpoint("cp1", "Login Success", fact_ids=["f1"]),
            _make_checkpoint("cp2", "Login Failure", fact_ids=["f2"]),
            _make_checkpoint("cp3", "Payment Init", fact_ids=["f3"]),
            _make_checkpoint("cp4", "Payment Confirm", fact_ids=["f4"]),
        ]

        groups = self.planner._group_checkpoints_by_section(checkpoints, research)

        # 应该有 2 个组
        self.assertEqual(len(groups), 2)
        section_names = {g.section_name for g in groups}
        self.assertIn("Login Module", section_names)
        self.assertIn("Payment Module", section_names)

        # 每组各有 2 个 checkpoint
        for g in groups:
            self.assertEqual(len(g.checkpoints), 2)

    def test_fallback_equal_split_when_no_sections(self):
        """source_section 全为空时使用等分 fallback。"""
        facts = [_make_fact("f1"), _make_fact("f2")]
        research = ResearchOutput(facts=facts)

        checkpoints = [
            _make_checkpoint(f"cp{i}", f"CP {i}", fact_ids=["f1"])
            for i in range(7)
        ]

        groups = self.planner._group_checkpoints_by_section(checkpoints, research)

        # batch_size=3, 7 checkpoints → ceil(7/3)=3 groups
        self.assertEqual(len(groups), 3)
        total = sum(len(g.checkpoints) for g in groups)
        self.assertEqual(total, 7)

    def test_large_section_splits_into_sub_batches(self):
        """单个 section 超过 batch_size 时拆分为多个子组。"""
        facts = [_make_fact(f"f{i}", source_section="Big Section") for i in range(5)]
        research = ResearchOutput(facts=facts)

        checkpoints = [
            _make_checkpoint(f"cp{i}", f"CP {i}", fact_ids=[f"f{i % 5}"])
            for i in range(5)
        ]

        groups = self.planner._group_checkpoints_by_section(checkpoints, research)

        # batch_size=3, 5 checkpoints in one section → 2 sub-groups
        self.assertEqual(len(groups), 2)
        self.assertIn("(part", groups[1].section_name)

    def test_unassigned_checkpoints_form_own_group(self):
        """没有 fact_ids 或 fact 无 section 的 checkpoint 归入 __unassigned__。"""
        facts = [_make_fact("f1", source_section="ModuleA")]
        research = ResearchOutput(facts=facts)

        checkpoints = [
            _make_checkpoint("cp1", "Has section", fact_ids=["f1"]),
            _make_checkpoint("cp2", "No facts", fact_ids=[]),
            _make_checkpoint("cp3", "Unknown fact", fact_ids=["f999"]),
        ]

        groups = self.planner._group_checkpoints_by_section(checkpoints, research)

        section_names = {g.section_name for g in groups}
        self.assertIn("ModuleA", section_names)
        self.assertIn("__unassigned__", section_names)


class TestDeduplicateOutlineNodes(unittest.TestCase):
    """Test _deduplicate_outline_nodes."""

    def setUp(self):
        self.llm_client = MagicMock()
        self.planner = CheckpointOutlinePlanner(
            llm_client=self.llm_client,
            batch_threshold=5,
            batch_size=5,
        )

    def test_exact_duplicate_merges(self):
        """相同 display_text 的节点被去重，保留第一个。"""
        nodes = [
            CanonicalOutlineNode(
                node_id="n1",
                semantic_key="campaign",
                display_text="Campaign Management",
                kind="business_object",
                visibility="visible",
            ),
            CanonicalOutlineNode(
                node_id="n2",
                semantic_key="campaign",
                display_text="Campaign Management",
                kind="business_object",
                visibility="visible",
            ),
        ]

        deduped, remap = self.planner._deduplicate_outline_nodes(nodes)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].node_id, "n1")
        self.assertEqual(remap, {"n2": "n1"})

    def test_case_insensitive_dedup(self):
        """大小写不同的 display_text 被视为相同。"""
        nodes = [
            CanonicalOutlineNode(
                node_id="n1",
                semantic_key="login",
                display_text="Login Flow",
                kind="action",
                visibility="visible",
            ),
            CanonicalOutlineNode(
                node_id="n2",
                semantic_key="login",
                display_text="login flow",
                kind="action",
                visibility="visible",
            ),
        ]

        deduped, remap = self.planner._deduplicate_outline_nodes(nodes)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(remap["n2"], "n1")

    def test_no_duplicates_returns_all(self):
        """无重复时全部保留，remap 为空。"""
        nodes = [
            CanonicalOutlineNode(
                node_id="n1",
                semantic_key="a",
                display_text="Node A",
                kind="business_object",
                visibility="visible",
            ),
            CanonicalOutlineNode(
                node_id="n2",
                semantic_key="b",
                display_text="Node B",
                kind="context",
                visibility="visible",
            ),
        ]

        deduped, remap = self.planner._deduplicate_outline_nodes(nodes)

        self.assertEqual(len(deduped), 2)
        self.assertEqual(remap, {})

    def test_aliases_merged_on_dedup(self):
        """去重时合并 aliases。"""
        nodes = [
            CanonicalOutlineNode(
                node_id="n1",
                semantic_key="pay",
                display_text="Payment",
                kind="business_object",
                visibility="visible",
                aliases=["Pay"],
            ),
            CanonicalOutlineNode(
                node_id="n2",
                semantic_key="pay",
                display_text="Payment",
                kind="business_object",
                visibility="visible",
                aliases=["Checkout"],
            ),
        ]

        deduped, remap = self.planner._deduplicate_outline_nodes(nodes)

        self.assertEqual(len(deduped), 1)
        # aliases should include both "Pay" and "Checkout" (and possibly "Payment" removed)
        self.assertIn("Pay", deduped[0].aliases)
        self.assertIn("Checkout", deduped[0].aliases)


class TestRemapPaths(unittest.TestCase):
    """Test _remap_paths."""

    def setUp(self):
        self.llm_client = MagicMock()
        self.planner = CheckpointOutlinePlanner(
            llm_client=self.llm_client,
            batch_threshold=5,
            batch_size=5,
        )

    def test_remap_replaces_old_ids(self):
        """路径中的旧 node_id 被替换为 canonical id。"""
        paths = [
            CheckpointPathMapping(
                checkpoint_id="cp1",
                path_node_ids=["n1", "n2_dup", "n3"],
            ),
        ]
        remap = {"n2_dup": "n2_canonical"}

        result = self.planner._remap_paths(paths, remap)

        self.assertEqual(result[0].path_node_ids, ["n1", "n2_canonical", "n3"])

    def test_empty_remap_returns_unchanged(self):
        """空 remap 返回原始路径。"""
        paths = [
            CheckpointPathMapping(
                checkpoint_id="cp1",
                path_node_ids=["n1", "n2"],
            ),
        ]

        result = self.planner._remap_paths(paths, {})

        self.assertIs(result, paths)


class TestBatchThresholdDecision(unittest.TestCase):
    """Test plan() 中的单批/分批路径选择。"""

    def setUp(self):
        self.llm_client = MagicMock()

    @patch.object(CheckpointOutlinePlanner, "_execute_batched_stage2")
    @patch.object(CheckpointOutlinePlanner, "_group_checkpoints_by_section")
    def test_below_threshold_uses_single_batch(self, mock_group, mock_batch):
        """checkpoint 数 ≤ threshold 时走单批路径，不调用分批方法。"""
        planner = CheckpointOutlinePlanner(
            llm_client=self.llm_client,
            batch_threshold=20,
            batch_size=20,
        )

        # Mock LLM responses for single-batch
        self.llm_client.generate_structured.side_effect = [
            CanonicalOutlineNodeCollection(canonical_nodes=[]),
            CheckpointPathCollection(checkpoint_paths=[]),
        ]

        facts = [_make_fact("f1", "Section A")]
        checkpoints = [_make_checkpoint("cp1", "Test", fact_ids=["f1"])]
        research = ResearchOutput(facts=facts)

        planner.plan(research, checkpoints)

        mock_group.assert_not_called()
        mock_batch.assert_not_called()
        self.assertEqual(self.llm_client.generate_structured.call_count, 2)

    @patch.object(CheckpointOutlinePlanner, "_execute_batched_stage2")
    @patch.object(CheckpointOutlinePlanner, "_group_checkpoints_by_section")
    def test_above_threshold_uses_batched_path(self, mock_group, mock_batch):
        """checkpoint 数 > threshold 时走分批路径。"""
        planner = CheckpointOutlinePlanner(
            llm_client=self.llm_client,
            batch_threshold=3,
            batch_size=3,
        )

        # Setup mocks
        mock_group.return_value = [
            _BatchGroup("Section A", [_make_checkpoint(f"cp{i}", f"CP{i}") for i in range(2)]),
            _BatchGroup("Section B", [_make_checkpoint(f"cp{i+2}", f"CP{i+2}") for i in range(2)]),
        ]
        mock_batch.return_value = ([], [])

        facts = [_make_fact(f"f{i}", f"S{i}") for i in range(5)]
        checkpoints = [
            _make_checkpoint(f"cp{i}", f"CP {i}", fact_ids=[f"f{i}"])
            for i in range(5)
        ]
        research = ResearchOutput(facts=facts)

        planner.plan(research, checkpoints)

        mock_group.assert_called_once()
        mock_batch.assert_called_once()


class TestEmptyInput(unittest.TestCase):
    """边界情况：空输入。"""

    def test_empty_checkpoints_returns_empty(self):
        llm_client = MagicMock()
        planner = CheckpointOutlinePlanner(
            llm_client=llm_client,
            batch_threshold=5,
            batch_size=5,
        )

        result = planner.plan(ResearchOutput(facts=[]), [])

        self.assertEqual(result.canonical_outline_nodes, [])
        self.assertEqual(result.checkpoint_paths, [])
        self.assertEqual(result.optimized_tree, [])
        llm_client.generate_structured.assert_not_called()


class TestEqualSplitGroups(unittest.TestCase):
    """Test _equal_split_groups."""

    def test_splits_evenly(self):
        llm_client = MagicMock()
        planner = CheckpointOutlinePlanner(
            llm_client=llm_client,
            batch_threshold=5,
            batch_size=4,
        )

        checkpoints = [_make_checkpoint(f"cp{i}", f"CP {i}") for i in range(10)]
        groups = planner._equal_split_groups(checkpoints)

        self.assertEqual(len(groups), 3)  # ceil(10/4) = 3
        self.assertEqual(len(groups[0].checkpoints), 4)
        self.assertEqual(len(groups[1].checkpoints), 4)
        self.assertEqual(len(groups[2].checkpoints), 2)


if __name__ == "__main__":
    unittest.main()
