"""单元测试：ChecklistMerger Trie 合并逻辑。"""

from __future__ import annotations

import pytest

from app.domain.checklist_models import ChecklistNode
from app.services.checklist_merger import ChecklistMerger, _normalize_for_comparison


# ---------------------------------------------------------------------------
# 测试替身
# ---------------------------------------------------------------------------

class FakeTestCase:
    """模拟 TestCase 的轻量替身。"""

    __test__ = False

    def __init__(
        self,
        id: str = "TC-001",
        title: str = "测试用例",
        preconditions: list[str] | None = None,
        steps: list[str] | None = None,
        expected_results: list[str] | None = None,
        priority: str = "P2",
        category: str = "functional",
        evidence_refs: list | None = None,
        checkpoint_id: str = "",
    ):
        self.id = id
        self.title = title
        self.preconditions = preconditions or []
        self.steps = steps or []
        self.expected_results = expected_results or []
        self.priority = priority
        self.category = category
        self.evidence_refs = evidence_refs or []
        self.checkpoint_id = checkpoint_id


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _collect_leaves(nodes: list[ChecklistNode]) -> list[ChecklistNode]:
    """递归收集所有 case 叶子节点。"""
    result: list[ChecklistNode] = []
    for n in nodes:
        if n.node_type == "case":
            result.append(n)
        else:
            result.extend(_collect_leaves(n.children))
    return result


def _assert_no_single_child_groups(nodes: list[ChecklistNode]) -> None:
    """断言不存在只有一个子节点且该子节点也是 group 的情况（剪枝后）。"""
    for n in nodes:
        if n.node_type == "group":
            if len(n.children) == 1 and n.children[0].node_type == "group":
                raise AssertionError(
                    f"Single-child group chain detected: {n.title} → {n.children[0].title}"
                )
            _assert_no_single_child_groups(n.children)


# ---------------------------------------------------------------------------
# 归一化测试
# ---------------------------------------------------------------------------

class TestNormalization:
    """_normalize_for_comparison 归一化逻辑。"""

    def test_strip_numbering(self):
        assert _normalize_for_comparison("1. 打开浏览器") == "打开浏览器"
        assert _normalize_for_comparison("Step 2: Login") == "login"

    def test_casefold(self):
        assert _normalize_for_comparison("Navigate to HOME") == "navigate to home"

    def test_chinese_punctuation(self):
        result = _normalize_for_comparison("输入用户名，点击确认")
        assert "，" not in result  # 中文逗号应被替换


# ---------------------------------------------------------------------------
# 合并测试
# ---------------------------------------------------------------------------

class TestChecklistMerger:
    """ChecklistMerger 核心功能。"""

    def test_empty_input(self):
        merger = ChecklistMerger()
        assert merger.merge([]) == []

    def test_single_case(self):
        case = FakeTestCase(
            id="TC-001",
            title="单用例",
            preconditions=["打开浏览器"],
            steps=["点击登录"],
        )
        tree = ChecklistMerger().merge([case])  # type: ignore[arg-type]
        leaves = _collect_leaves(tree)
        assert len(leaves) == 1
        assert leaves[0].test_case_ref == "TC-001"

    def test_shared_prefix_creates_group(self):
        cases = [
            FakeTestCase(
                id="TC-001",
                preconditions=["打开浏览器", "导航到登录页"],
                steps=["输入用户名", "点击登录"],
                title="正常登录",
            ),
            FakeTestCase(
                id="TC-002",
                preconditions=["打开浏览器", "导航到登录页"],
                steps=["输入错误密码", "点击登录"],
                title="错误密码",
            ),
        ]
        tree = ChecklistMerger().merge(cases)  # type: ignore[arg-type]

        # 应该有 group 节点
        has_group = any(n.node_type == "group" for n in tree)
        assert has_group, "Shared prefix should create a group node"

        leaves = _collect_leaves(tree)
        assert len(leaves) == 2

    def test_no_shared_prefix(self):
        cases = [
            FakeTestCase(id="TC-001", steps=["步骤A"], title="用例A"),
            FakeTestCase(id="TC-002", steps=["步骤B"], title="用例B"),
        ]
        tree = ChecklistMerger().merge(cases)  # type: ignore[arg-type]
        leaves = _collect_leaves(tree)
        assert len(leaves) == 2

    def test_pruning_removes_single_child_chains(self):
        cases = [
            FakeTestCase(
                id="TC-001",
                preconditions=["A", "B", "C"],
                steps=["D"],
                title="深链",
            ),
            FakeTestCase(
                id="TC-002",
                preconditions=["A", "B", "C"],
                steps=["E"],
                title="深链2",
            ),
        ]
        tree = ChecklistMerger().merge(cases)  # type: ignore[arg-type]
        _assert_no_single_child_groups(tree)

    def test_max_depth_respected(self):
        long_steps = [f"步骤{i}" for i in range(20)]
        case = FakeTestCase(id="TC-001", steps=long_steps, title="超长")
        tree = ChecklistMerger().merge([case])  # type: ignore[arg-type]
        # 应该不崩溃，且叶子节点有 remaining_steps
        leaves = _collect_leaves(tree)
        assert len(leaves) == 1
