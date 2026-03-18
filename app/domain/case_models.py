"""测试用例领域模型。

定义了测试用例（``TestCase``）和质量报告（``QualityReport``）的数据结构，
作为工作流最终输出的核心模型。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.research_models import EvidenceRef


class TestCase(BaseModel):
    """单个测试用例。

    Attributes:
        id: 用例编号（如 TC-001）。
        title: 用例标题，简要描述测试目标。
        preconditions: 执行用例前需满足的前置条件列表。
        steps: 操作步骤列表。
        expected_results: 每一步或整体的预期结果。
        priority: 优先级（P0-P3），默认 P2。
        category: 用例类别（functional / edge_case / performance 等）。
        evidence_refs: 关联的 PRD 原文证据引用。
        checkpoint_id: 所属的 checkpoint 标识，用于回溯 fact → checkpoint → testcase 链路。
    """

    # 防止 pytest 将此类误识别为测试类
    __test__ = False

    id: str
    title: str
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    expected_results: list[str] = Field(default_factory=list)
    priority: str = "P2"
    category: str = "functional"
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    checkpoint_id: str = ""
    project_id: str = ""


class QualityReport(BaseModel):
    """测试用例质量报告。

    记录去重结果、覆盖率评估、警告信息、自动修复字段，
    以及 checkpoint 层面的质量告警。
    """

    duplicate_groups: list[list[str]] = Field(default_factory=list)
    coverage_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    repaired_fields: list[str] = Field(default_factory=list)
    checkpoint_warnings: list[str] = Field(default_factory=list)
    missing_required_modules: list[str] = Field(default_factory=list)
