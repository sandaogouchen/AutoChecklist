"""检查点领域模型。

定义了 fact 与 test case 之间的中间层数据结构，包括：
- ``Checkpoint``：从业务事实中提炼出的可验证测试点
- ``CheckpointCoverage``：单个 checkpoint 的用例覆盖状态
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, Field

from app.domain.research_models import EvidenceRef


class Checkpoint(BaseModel):
    """单个检查点。

    代表从业务变化事实中提炼出来的可验证测试点，
    先于 testcase 存在，作为生成、评估、去重、回溯的统一锚点。

    Attributes:
        checkpoint_id: 稳定的唯一标识，基于 fact_ids 与 title 的哈希生成。
        title: 检查点标题，简要描述待验证的内容。
        objective: 验证目标，说明该检查点要证明什么。
        category: 类别（functional / edge_case / performance / security）。
        risk: 风险等级（low / medium / high）。
        branch_hint: 建议的测试分支提示（如正常流、异常流、边界值）。
        fact_ids: 该 checkpoint 来源的上游事实 ID 列表。
        evidence_refs: 关联的 PRD 原文证据引用。
        preconditions: 验证该检查点前需满足的前置条件。
        coverage_status: 覆盖状态（uncovered / partial / covered）。
    """

    checkpoint_id: str = ""
    title: str
    objective: str = ""
    category: str = "functional"
    risk: str = "medium"
    branch_hint: str = ""
    fact_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    coverage_status: str = "uncovered"


class CheckpointCoverage(BaseModel):
    """单个 checkpoint 的用例覆盖记录。

    Attributes:
        checkpoint_id: 对应的 checkpoint 标识。
        covered_by_test_ids: 覆盖该 checkpoint 的测试用例 ID 列表。
        coverage_status: 覆盖状态（uncovered / partial / covered）。
    """

    checkpoint_id: str
    covered_by_test_ids: list[str] = Field(default_factory=list)
    coverage_status: str = "uncovered"


def generate_checkpoint_id(fact_ids: list[str], title: str) -> str:
    """基于 fact_ids 和 title 生成稳定的 checkpoint ID。

    使用 SHA-256 哈希的前 8 位，确保同一输入始终生成相同 ID，
    支持增量更新与评估回路的可比性。

    Args:
        fact_ids: 来源事实 ID 列表。
        title: 检查点标题。

    Returns:
        格式为 ``CP-<hash8>`` 的稳定标识。
    """
    raw = "|".join(sorted(fact_ids)) + "||" + title.strip().casefold()
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"CP-{digest}"
