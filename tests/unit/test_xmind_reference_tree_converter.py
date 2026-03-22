"""XMindReferenceTreeConverter 单元测试。"""

from __future__ import annotations

import pytest

from app.domain.xmind_reference_models import XMindReferenceNode
from app.services.xmind_reference_tree_converter import XMindReferenceTreeConverter


@pytest.fixture
def converter() -> XMindReferenceTreeConverter:
    return XMindReferenceTreeConverter()


def _build_sample_tree() -> XMindReferenceNode:
    """构建 3 层参考树用于测试。"""
    return XMindReferenceNode(
        title="支付系统 Checklist",
        children=[
            XMindReferenceNode(
                title="支付流程",
                children=[
                    XMindReferenceNode(
                        title="正常支付",
                        children=[
                            XMindReferenceNode(title="微信支付成功"),
                            XMindReferenceNode(title="支付宝支付成功"),
                        ],
                    ),
                    XMindReferenceNode(title="支付失败处理"),
                ],
            ),
            XMindReferenceNode(
                title="退款流程",
                children=[
                    XMindReferenceNode(title="全额退款"),
                    XMindReferenceNode(title="部分退款"),
                ],
            ),
        ],
    )


class TestConvert:
    """convert() 方法测试。"""

    def test_converts_three_level_tree(self, converter: XMindReferenceTreeConverter) -> None:
        root = _build_sample_tree()
        result = converter.convert(root)

        assert len(result) == 2
        assert result[0].title == "支付流程"
        assert result[1].title == "退款流程"

    def test_top_level_nodes_are_groups(self, converter: XMindReferenceTreeConverter) -> None:
        root = _build_sample_tree()
        result = converter.convert(root)

        for node in result:
            assert node.node_type == "group"

    def test_leaf_nodes_are_expected_result(self, converter: XMindReferenceTreeConverter) -> None:
        root = _build_sample_tree()
        result = converter.convert(root)

        # 支付流程 > 正常支付 > 微信支付成功 (leaf)
        leaf = result[0].children[0].children[0]
        assert leaf.title == "微信支付成功"
        assert leaf.node_type == "expected_result"

    def test_all_nodes_source_is_reference(self, converter: XMindReferenceTreeConverter) -> None:
        root = _build_sample_tree()
        result = converter.convert(root)

        def _check_source(node):
            assert node.source == "reference", f"{node.title} source != reference"
            for child in node.children:
                _check_source(child)

        for node in result:
            _check_source(node)

    def test_node_id_has_ref_prefix(self, converter: XMindReferenceTreeConverter) -> None:
        root = _build_sample_tree()
        result = converter.convert(root)

        def _check_id(node):
            assert node.node_id.startswith("ref-"), f"{node.title} id not ref- prefixed"
            for child in node.children:
                _check_id(child)

        for node in result:
            _check_id(node)

    def test_node_id_is_stable(self, converter: XMindReferenceTreeConverter) -> None:
        root = _build_sample_tree()
        result1 = converter.convert(root)
        result2 = converter.convert(root)

        assert result1[0].node_id == result2[0].node_id
        assert result1[0].children[0].node_id == result2[0].children[0].node_id

    def test_empty_root_returns_empty(self, converter: XMindReferenceTreeConverter) -> None:
        root = XMindReferenceNode(title="Empty", children=[])
        result = converter.convert(root)
        assert result == []

    def test_single_level_children(self, converter: XMindReferenceTreeConverter) -> None:
        root = XMindReferenceNode(
            title="Root",
            children=[
                XMindReferenceNode(title="Leaf A"),
                XMindReferenceNode(title="Leaf B"),
            ],
        )
        result = converter.convert(root)
        assert len(result) == 2
        assert all(n.node_type == "expected_result" for n in result)


class TestGetLeafTitles:
    """get_leaf_titles() 方法测试。"""

    def test_extracts_all_leaves(self, converter: XMindReferenceTreeConverter) -> None:
        root = _build_sample_tree()
        leaves = converter.get_leaf_titles(root)

        expected = {"微信支付成功", "支付宝支付成功", "支付失败处理", "全额退款", "部分退款"}
        assert set(leaves) == expected

    def test_empty_tree(self, converter: XMindReferenceTreeConverter) -> None:
        root = XMindReferenceNode(title="Empty", children=[])
        leaves = converter.get_leaf_titles(root)
        # Root itself is a leaf if no children, but title "Empty" is included
        assert leaves == ["Empty"]

    def test_single_root_no_children(self, converter: XMindReferenceTreeConverter) -> None:
        root = XMindReferenceNode(title="Solo")
        assert converter.get_leaf_titles(root) == ["Solo"]
