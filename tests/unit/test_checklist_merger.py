"""Unit tests for semantic-path checklist merging."""

from __future__ import annotations

from app.services.checklist_merger import ChecklistMerger
from app.services.semantic_path_normalizer import (
    NormalizedChecklistPath,
    NormalizedPathSegment,
)


def _segment(
    node_id: str,
    display_text: str,
    *,
    hidden: bool = False,
    kind: str = "action",
) -> NormalizedPathSegment:
    return NormalizedPathSegment(
        node_id=node_id,
        display_text=display_text,
        hidden=hidden,
        kind=kind,
    )


def _path(
    test_case_id: str,
    path_segments: list[NormalizedPathSegment],
    expected_results: list[str],
) -> NormalizedChecklistPath:
    return NormalizedChecklistPath(
        test_case_id=test_case_id,
        path_segments=path_segments,
        expected_results=expected_results,
        priority="P1",
        category="functional",
        checkpoint_id=f"CP-{test_case_id}",
    )


def test_merges_shared_visible_prefix_and_deduplicates_expected_results() -> None:
    merger = ChecklistMerger()

    tree = merger.merge(
        [
            _path(
                "TC-001",
                [
                    _segment("adgroup", "adgroup", hidden=True, kind="precondition"),
                    _segment("enter-page", "进入 `Create Ad Group` 页面"),
                    _segment("locate-goal", "定位 `optimize goal` 区域"),
                ],
                ["`optimize goal` 字段在创建阶段显式可见。"],
            ),
            _path(
                "TC-002",
                [
                    _segment("adgroup", "adgroup", hidden=True, kind="precondition"),
                    _segment("enter-page", "进入 `Create Ad Group` 页面"),
                    _segment("locate-goal", "定位 `optimize goal` 区域"),
                ],
                ["`optimize goal` 字段在创建阶段显式可见。"],
            ),
        ]
    )

    assert [node.title for node in tree] == ["进入 `Create Ad Group` 页面"]

    page_node = tree[0]
    assert page_node.node_type == "group"
    assert [child.title for child in page_node.children] == ["定位 `optimize goal` 区域"]

    locate_node = page_node.children[0]
    assert [child.title for child in locate_node.children] == [
        "`optimize goal` 字段在创建阶段显式可见。"
    ]
    assert locate_node.children[0].node_type == "expected_result"
    assert locate_node.children[0].source_test_case_refs == ["TC-001", "TC-002"]


def test_hidden_anchor_is_not_rendered_but_still_merges_paths() -> None:
    merger = ChecklistMerger()

    tree = merger.merge(
        [
            _path(
                "TC-001",
                [
                    _segment("adgroup", "adgroup", hidden=True, kind="precondition"),
                    _segment("prepare", "已准备一个 `secondary goal` 非 `conversion` 的 ad group"),
                ],
                ["表单允许继续配置。"],
            ),
            _path(
                "TC-002",
                [
                    _segment("adgroup", "adgroup", hidden=True, kind="precondition"),
                    _segment("enter", "进入 `Create Ad Group` 页面"),
                ],
                ["页面加载成功。"],
            ),
        ]
    )

    assert [node.title for node in tree] == [
        "已准备一个 `secondary goal` 非 `conversion` 的 ad group",
        "进入 `Create Ad Group` 页面",
    ]
    assert all(node.title != "adgroup" for node in tree)
