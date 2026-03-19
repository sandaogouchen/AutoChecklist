"""LLM 驱动的语义路径归一化服务。

两阶段流程：
1. 先从一批 test cases 中抽取共享的规范逻辑节点词表
2. 再将每条 test case 映射为有序的规范路径
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.clients.llm import LLMClient
    from app.domain.case_models import TestCase


class SemanticNode(BaseModel):
    """共享语义节点定义。"""

    node_id: str
    semantic_key: str
    display_text: str
    kind: Literal["precondition", "action"] = "action"
    hidden: bool = False
    aliases: list[str] = Field(default_factory=list)


class SemanticNodeCollection(BaseModel):
    """共享语义节点集合。"""

    canonical_nodes: list[SemanticNode] = Field(default_factory=list)


class SemanticPathItem(BaseModel):
    """单条用例的语义路径映射。"""

    test_case_id: str
    path_node_ids: list[str] = Field(default_factory=list)
    expected_results: list[str] = Field(default_factory=list)


class SemanticPathCollection(BaseModel):
    """语义路径集合。"""

    semantic_paths: list[SemanticPathItem] = Field(default_factory=list)


@dataclass
class NormalizedPathSegment:
    """归一化后的单个路径片段。"""

    node_id: str
    display_text: str
    hidden: bool = False
    kind: str = "action"


@dataclass
class NormalizedChecklistPath:
    """单条用例的归一化逻辑路径。"""

    test_case_id: str
    path_segments: list[NormalizedPathSegment]
    expected_results: list[str]
    priority: str
    category: str
    checkpoint_id: str


_VOCAB_SYSTEM_PROMPT = """
You are building a shared checklist logic tree for manual QA test cases.

Your job in this stage:
1. read all test cases together
2. identify canonical reusable precondition/action nodes
3. create semantic anchors that maximize path sharing

Target output shape:
- only canonical nodes
- no case summary nodes
- no fact summary nodes
- no testcase title abstractions like "[TC-027] ..."

Canonicalization rules:
- merge semantically equivalent steps even when wording differs a lot
- prefer business-object anchors such as adgroup, campaign, creative, TTMS account,
  optimize goal, secondary goal, CTA, CBO
- hidden anchors are encouraged when they help multiple paths share a logical prefix
- include unique nodes too when needed, so every case can later be fully mapped
- display_text should be concise and suitable for a checklist/XMind node
- aliases should be short source snippets proving the mapping

Critical example:
Source A: "用户已进入 `Create Ad Group` 页面"
Source B: "已准备一个 `secondary goal` 非 `conversion` 的 campaign/ad group"
Good normalization:
- hidden semantic anchor: adgroup
- visible node examples can stay separate
Bad normalization:
- creating testcase summary nodes
- treating these as unrelated because surface wording differs

Think in terms of a reusable operation tree:
environment -> user state -> page/context -> focused operation -> expected result
""".strip()


_PATH_SYSTEM_PROMPT = """
You are mapping each test case into an ordered reusable logic path using ONLY the
provided canonical nodes.

Hard constraints:
- output only shared precondition/action path segments
- do NOT include testcase titles
- do NOT include fact summaries
- do NOT generate "[TC-xxx]" or similar summary layers
- expected_results must stay as terminal leaves only

Path rules:
- order path_node_ids from broad/shared context to specific operation
- use hidden anchors when they improve structural sharing
- prefer the deepest logically complete path, not a shallow keyword list
- every meaningful precondition/step should be represented by canonical nodes
- do not invent new node ids

Checklist goal:
The final rendered tree should look like:
系统已部署测试版本
  用户已登录系统
    进入 `Create Ad Group` 页面
      定位 `optimize goal` 区域
        预期结果...

It should NOT look like:
[TC-001] optimize goal visible
  前置条件...
  步骤...
""".strip()


class SemanticPathNormalizer:
    """使用 LLM 将原始 test cases 归一化为共享语义路径。"""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    def normalize(self, test_cases: list[TestCase]) -> list[NormalizedChecklistPath]:
        """归一化 test cases 为共享路径。"""
        if not test_cases:
            return []

        case_payload = [
            {
                "id": case.id,
                "title": case.title,
                "preconditions": case.preconditions,
                "steps": case.steps,
                "expected_results": case.expected_results,
            }
            for case in test_cases
        ]

        node_collection = self.llm_client.generate_structured(
            system_prompt=_VOCAB_SYSTEM_PROMPT,
            user_prompt=(
                "Build canonical logic nodes for the following test cases.\n\n"
                f"{json.dumps(case_payload, ensure_ascii=False, indent=2)}"
            ),
            response_model=SemanticNodeCollection,
        )

        path_collection = self.llm_client.generate_structured(
            system_prompt=_PATH_SYSTEM_PROMPT,
            user_prompt=(
                "Map each test case to an ordered logic path using the canonical nodes below.\n\n"
                f"[Canonical Nodes]\n{json.dumps(node_collection.model_dump(mode='json'), ensure_ascii=False, indent=2)}\n\n"
                f"[Test Cases]\n{json.dumps(case_payload, ensure_ascii=False, indent=2)}"
            ),
            response_model=SemanticPathCollection,
        )

        node_lookup = {
            node.node_id: node
            for node in node_collection.canonical_nodes
        }
        path_lookup = {
            item.test_case_id: item
            for item in path_collection.semantic_paths
        }

        normalized_paths: list[NormalizedChecklistPath] = []
        for case in test_cases:
            item = path_lookup.get(case.id)
            path_segments = self._resolve_path_segments(
                item.path_node_ids if item else [],
                node_lookup,
            )
            if not path_segments:
                path_segments = self._fallback_path_segments(case)

            normalized_paths.append(
                NormalizedChecklistPath(
                    test_case_id=case.id,
                    path_segments=path_segments,
                    expected_results=(
                        item.expected_results if item and item.expected_results else list(case.expected_results)
                    ),
                    priority=case.priority,
                    category=case.category,
                    checkpoint_id=case.checkpoint_id,
                )
            )

        return normalized_paths

    def _resolve_path_segments(
        self,
        path_node_ids: list[str],
        node_lookup: dict[str, SemanticNode],
    ) -> list[NormalizedPathSegment]:
        """将节点 ID 映射为规范化路径片段。"""
        path_segments: list[NormalizedPathSegment] = []
        for node_id in path_node_ids:
            node = node_lookup.get(node_id)
            if node is None:
                continue
            path_segments.append(
                NormalizedPathSegment(
                    node_id=node.node_id,
                    display_text=node.display_text,
                    hidden=node.hidden,
                    kind=node.kind,
                )
            )
        return path_segments

    def _fallback_path_segments(
        self,
        case: TestCase,
    ) -> list[NormalizedPathSegment]:
        """当 LLM 未返回有效路径时，退回原始前置/步骤。"""
        raw_segments = list(case.preconditions) + list(case.steps)
        fallback_segments: list[NormalizedPathSegment] = []

        for index, raw_segment in enumerate(raw_segments, start=1):
            text = raw_segment.strip()
            if not text:
                continue
            fallback_segments.append(
                NormalizedPathSegment(
                    node_id=f"{case.id}-fallback-{index}",
                    display_text=text,
                    hidden=False,
                    kind="action",
                )
            )

        return fallback_segments
