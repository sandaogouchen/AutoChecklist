"""研究分析领域模型。

定义了 PRD 上下文研究阶段的数据结构，包括：
- ``EvidenceRef``：PRD 原文中的证据引用
- ``ResearchFact``：从 PRD 中提取的业务变化事实
- ``PlannedScenario``：规划的测试场景
- ``ResearchOutput``：上下文研究的完整输出
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceRef(BaseModel):
    """PRD 原文证据引用。

    将测试用例与 PRD 原文建立可追溯的关联，
    记录引用来源的章节标题、摘录片段、行号范围及置信度。
    """

    section_title: str
    excerpt: str = ""
    line_start: int = 0
    line_end: int = 0
    confidence: float = 0.0


class ResearchFact(BaseModel):
    """从 PRD 中提取的业务变化事实。

    每个 fact 代表一条独立的、可被进一步拆分为 checkpoint 的业务信息。

    Attributes:
        fact_id: 事实的唯一标识（如 FACT-001）。
        description: 事实的文字描述。
        source_section: 该事实来源的文档章节标题。
        evidence_refs: 关联的 PRD 原文证据引用。
        category: 事实类别（requirement / constraint / assumption / behavior）。
    """

    fact_id: str = ""
    description: str
    source_section: str = ""
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    category: str = "requirement"


class PlannedScenario(BaseModel):
    """规划的测试场景。

    由 scenario_planner 节点根据研究输出生成，
    每个场景对应一个待测试的用户行为或功能点。

    Attributes:
        title: 场景标题。
        category: 场景类别（functional / edge_case / performance）。
        risk: 风险等级（low / medium / high）。
        rationale: 选择该场景的理由或依据。
    """

    title: str
    category: str = "functional"
    risk: str = "medium"
    rationale: str = ""


class ResearchOutput(BaseModel):
    """上下文研究输出。

    由 LLM 从 PRD 文档中提取的、与测试相关的结构化信息，
    作为后续场景规划和用例生成的输入依据。

    ``facts`` 字段是新增的结构化事实列表，默认为空列表以保持向后兼容。
    """

    feature_topics: list[str] = Field(default_factory=list)
    user_scenarios: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    test_signals: list[str] = Field(default_factory=list)
    facts: list[ResearchFact] = Field(default_factory=list)
