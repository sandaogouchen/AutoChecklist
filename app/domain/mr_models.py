"""MR 分析领域模型。

定义 MR（Merge Request）代码变更分析所需的全部数据模型，
包括 diff 文件信息、代码级事实、一致性校验结果，以及 Coco Agent 集成相关模型。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# MR Diff 与输入
# ---------------------------------------------------------------------------


class MRDiffFile(BaseModel):
    """MR 中单个文件的 diff 信息。"""

    file_path: str = ""
    """文件路径。"""

    change_type: str = "modified"
    """变更类型：added / modified / deleted / renamed。"""

    old_path: str = ""
    """renamed 时的旧路径。"""

    diff_content: str = ""
    """unified diff 内容。"""

    language: str = ""
    """文件语言（python / go / java / typescript 等）。"""

    additions: int = 0
    """新增行数。"""

    deletions: int = 0
    """删除行数。"""


class MRInput(BaseModel):
    """MR 输入数据（解耦接口）。

    本期通过调用方直接构造传入，后续迭代实现 GitLab / GitHub API 拉取。
    """

    mr_id: str = ""
    """MR 标识。"""

    mr_title: str = ""
    """MR 标题。"""

    mr_description: str = ""
    """MR 描述。"""

    source_branch: str = ""
    """源分支。"""

    target_branch: str = ""
    """目标分支。"""

    diff_files: list[MRDiffFile] = Field(default_factory=list)
    """diff 文件列表。"""

    mr_url: str = ""
    """MR 链接（可选）。"""


# ---------------------------------------------------------------------------
# Agentic Search 产出
# ---------------------------------------------------------------------------


class RelatedCodeSnippet(BaseModel):
    """通过 agentic search 找到的关联代码片段。"""

    file_path: str = ""
    """文件路径。"""

    start_line: int = 0
    """起始行。"""

    end_line: int = 0
    """结束行。"""

    code_content: str = ""
    """代码内容。"""

    relation_type: str = ""
    """关联类型：caller / callee / sibling / import / type_ref。"""

    relevance_reason: str = ""
    """LLM 解释的关联原因。"""


# ---------------------------------------------------------------------------
# 代码级事实 & 一致性问题
# ---------------------------------------------------------------------------


class MRCodeFact(BaseModel):
    """从 MR 代码中提取的代码级事实。

    类似 ResearchFact，但来源是代码而非 PRD 文档。
    """

    fact_id: str = ""
    """如 MR-FACT-001 / FE-MR-FACT-001 / BE-MR-FACT-001。"""

    description: str = ""
    """代码级事实描述（中文）。"""

    source_file: str = ""
    """来源文件。"""

    code_snippet: str = ""
    """关键代码片段。"""

    fact_type: str = "code_logic"
    """code_logic / error_handling / boundary / state_change / side_effect。"""

    related_prd_fact_ids: list[str] = Field(default_factory=list)
    """关联的 PRD fact ID。"""


class ConsistencyIssue(BaseModel):
    """PRD ↔ MR 一致性问题。"""

    issue_id: str = ""
    """如 CONSIST-001 / FE-CONSIST-001 / BE-CONSIST-001。"""

    severity: str = "warning"
    """critical / warning / info。"""

    prd_expectation: str = ""
    """PRD / Tech Design 中的预期逻辑。"""

    mr_implementation: str = ""
    """MR 中的实际实现。"""

    discrepancy: str = ""
    """差异描述。"""

    affected_file: str = ""
    """涉及的文件。"""

    affected_checkpoint_ids: list[str] = Field(default_factory=list)
    """受影响的 checkpoint。"""

    recommendation: str = ""
    """建议操作。"""

    confidence: float = 0.0
    """校验置信度（0.0-1.0）。"""


# ---------------------------------------------------------------------------
# Coco Agent 相关
# ---------------------------------------------------------------------------


class CocoTaskConfig(BaseModel):
    """Coco Agent 任务配置。"""

    agent_name: str = "sandbox"
    """Coco agent 类型。"""

    timeout: int = 300
    """最大等待超时（秒）。"""

    poll_interval_start: int = 5
    """初始轮询间隔（秒）。"""

    poll_interval_max: int = 20
    """最大轮询间隔（秒）。"""


class CocoTaskStatus(BaseModel):
    """Coco 任务执行状态（记录在 MRAnalysisResult 中）。"""

    task_id: str = ""
    """Coco 平台返回的任务 ID。"""

    status: str = ""
    """submitted / running / completed / failed / timeout。"""

    elapsed_seconds: float = 0.0
    """任务耗时（秒）。"""

    error_message: str = ""
    """错误信息（失败时有值）。"""


# ---------------------------------------------------------------------------
# 代码一致性校验结果（附加在 checkpoint / case 上）
# ---------------------------------------------------------------------------


class CodeConsistencyResult(BaseModel):
    """代码一致性校验结果，附加在每个 checkpoint / case 上。"""

    status: str = "unverified"
    """confirmed / mismatch / unverified。"""

    confidence: float = 0.0
    """置信度 0.0-1.0。"""

    actual_implementation: str = ""
    """代码实际实现描述。"""

    inconsistency_reason: str = ""
    """不一致原因（status=mismatch 时有值）。"""

    related_code_file: str = ""
    """相关代码文件路径。"""

    related_code_snippet: str = ""
    """关键代码片段。"""

    verified_by: str = ""
    """校验来源："coco" / "local" / "coco+llm_fallback" / ""。"""


# ---------------------------------------------------------------------------
# MR 分析完整结果
# ---------------------------------------------------------------------------


class MRAnalysisResult(BaseModel):
    """MR 分析的完整结果。"""

    mr_summary: str = ""
    """MR 变更摘要（中文）。"""

    changed_modules: list[str] = Field(default_factory=list)
    """变更涉及的模块。"""

    related_code_snippets: list[RelatedCodeSnippet] = Field(default_factory=list)
    """agentic search 关联代码片段。"""

    code_facts: list[MRCodeFact] = Field(default_factory=list)
    """代码级事实列表。"""

    consistency_issues: list[ConsistencyIssue] = Field(default_factory=list)
    """一致性问题列表。"""

    search_trace: list[str] = Field(default_factory=list)
    """agentic search 的搜索轨迹（debug 用）。"""

    coco_task_status: CocoTaskStatus | None = None
    """Coco 任务状态（仅 use_coco 时有值）。"""


# ---------------------------------------------------------------------------
# API 接口模型 — CaseGenerationRequest 新增字段
# ---------------------------------------------------------------------------


class CodebaseSource(BaseModel):
    """代码仓库来源配置。

    支持多种 Git 平台（GitHub、GitLab、code.bytedance.org 等）和本地路径两种方式，
    优先使用 Git 链接，不可用时降级使用本地路径。
    分支可显式指定，也可从 git_url / mr_url 中自动解析。
    """

    git_url: str = ""
    """Git 仓库链接（GitHub / GitLab / code.bytedance.org 等）。"""

    local_path: str = ""
    """本地文件夹路径（如 /home/user/projects/frontend）。"""

    branch: str = ""
    """分支名（可选，可自动解析）。"""

    commit_sha: str = ""
    """精确 commit SHA（可选，优先级高于 branch）。"""


class MRSourceConfig(BaseModel):
    """单端（前端 / 后端）的 MR + Codebase 配置。

    当 use_coco=True 时，仅使用 mr_url + codebase.git_url，
    local_path 会被忽略（Coco 无法访问本地文件系统）。
    若 mr_url 和 git_url 均为空则跳过该端分析。
    """

    mr_url: str = ""
    """MR 链接（GitLab / GitHub / code.bytedance.org MR/PR URL）。"""

    codebase: CodebaseSource = Field(default_factory=CodebaseSource)
    """代码仓库来源配置。"""

    use_coco: bool = False
    """是否启用 Coco Agent 进行代码分析（权限不足时开启）。"""
