"""测试用例领域模型。

定义了测试用例（``TestCase``）和质量报告（``QualityReport``）的数据结构，
作为工作流最终输出的核心模型。

新增模版绑定字段，支持 testcase 继承 checkpoint 的模版归属信息。
新增 tags 和 code_consistency 字段，支持 MR 代码分析结果标注。
"""

from __future__ import annotations

from typing import Any

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
        checkpoint_id: 所属的 checkpoint 标识，用于回溯 fact -> checkpoint -> testcase 链路。
        project_id: 所属项目 ID。
        template_leaf_id: 绑定的模版叶子节点 ID（继承自 checkpoint）。
        template_path_ids: 从模版根到叶子的节点 ID 路径（继承自 checkpoint）。
        template_path_titles: 从模版根到叶子的节点标题路径（继承自 checkpoint）。
        template_match_confidence: 模版匹配置信度（继承自 checkpoint）。
        template_match_low_confidence: 低置信度标记（继承自 checkpoint）。
        tags: 标签列表，用于标注测试用例的来源或特征（如 'mr_derived'）。
        code_consistency: 代码一致性校验结果。
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

    # ---- 模版绑定字段（继承自 checkpoint） ----
    template_leaf_id: str = ""
    template_path_ids: list[str] = Field(default_factory=list)
    template_path_titles: list[str] = Field(default_factory=list)
    template_match_confidence: float = 0.0
    template_match_low_confidence: bool = False

    # ---- MR 分析字段 ----
    tags: list[str] = Field(default_factory=list)
    code_consistency: dict[str, Any] | None = None


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
