"""Unit tests for semantic path normalization."""

from __future__ import annotations

from app.domain.case_models import TestCase
from app.services.semantic_path_normalizer import (
    SemanticNode,
    SemanticNodeCollection,
    SemanticPathCollection,
    SemanticPathItem,
    SemanticPathNormalizer,
)


class _FakeSemanticLLM:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate_structured(self, **kwargs):
        response_model = kwargs["response_model"]
        self.calls.append(response_model.__name__)

        if response_model.__name__ == "SemanticNodeCollection":
            return SemanticNodeCollection(
                canonical_nodes=[
                    SemanticNode(
                        node_id="node-1",
                        semantic_key="adgroup",
                        display_text="adgroup",
                        kind="precondition",
                        hidden=True,
                        aliases=["Create Ad Group 页面", "campaign/ad group"],
                    ),
                    SemanticNode(
                        node_id="node-2",
                        semantic_key="enter_create_ad_group_page",
                        display_text="进入 `Create Ad Group` 页面",
                        kind="action",
                        hidden=False,
                        aliases=["用户已进入 `Create Ad Group` 页面"],
                    ),
                ]
            )

        if response_model.__name__ == "SemanticPathCollection":
            return SemanticPathCollection(
                semantic_paths=[
                    SemanticPathItem(
                        test_case_id="TC-001",
                        path_node_ids=["node-1", "node-2"],
                        expected_results=["显示正确结果"],
                    )
                ]
            )

        raise AssertionError(f"Unexpected response model: {response_model.__name__}")


def test_normalizer_calls_llm_twice_and_returns_segments() -> None:
    llm = _FakeSemanticLLM()
    normalizer = SemanticPathNormalizer(llm)

    cases = [
        TestCase(
            id="TC-001",
            title="测试用例",
            preconditions=["用户已进入 `Create Ad Group` 页面"],
            steps=["定位 `optimize goal` 区域"],
            expected_results=["显示正确结果"],
        )
    ]

    normalized = normalizer.normalize(cases)

    assert llm.calls == ["SemanticNodeCollection", "SemanticPathCollection"]
    assert len(normalized) == 1
    assert [segment.display_text for segment in normalized[0].path_segments] == [
        "adgroup",
        "进入 `Create Ad Group` 页面",
    ]
    assert normalized[0].path_segments[0].hidden is True
    assert normalized[0].expected_results == ["显示正确结果"]


class _MissingPathLLM(_FakeSemanticLLM):
    def generate_structured(self, **kwargs):
        response_model = kwargs["response_model"]
        self.calls.append(response_model.__name__)

        if response_model.__name__ == "SemanticNodeCollection":
            return SemanticNodeCollection(canonical_nodes=[])

        if response_model.__name__ == "SemanticPathCollection":
            return SemanticPathCollection(semantic_paths=[])

        raise AssertionError(f"Unexpected response model: {response_model.__name__}")


def test_normalizer_falls_back_to_raw_preconditions_and_steps() -> None:
    llm = _MissingPathLLM()
    normalizer = SemanticPathNormalizer(llm)

    cases = [
        TestCase(
            id="TC-002",
            title="测试用例",
            preconditions=["用户已登录系统"],
            steps=["进入 `Create Ad Group` 页面"],
            expected_results=["页面正常展示"],
        )
    ]

    normalized = normalizer.normalize(cases)

    assert [segment.display_text for segment in normalized[0].path_segments] == [
        "用户已登录系统",
        "进入 `Create Ad Group` 页面",
    ]
    assert normalized[0].expected_results == ["页面正常展示"]
