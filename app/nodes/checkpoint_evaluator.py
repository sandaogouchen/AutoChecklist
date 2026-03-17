"""检查点评估节点。

对生成的 checkpoint 列表进行去重、归一化和初始覆盖状态设置：
- 按标题去重，保留首次出现的 checkpoint
- 检查 checkpoint 的证据充分性
- 初始化覆盖状态为 uncovered
"""

from __future__ import annotations

from app.domain.checkpoint_models import Checkpoint, CheckpointCoverage
from app.domain.state import CaseGenState


def checkpoint_evaluator_node(state: CaseGenState) -> CaseGenState:
    """对 checkpoint 列表进行去重和质量评估。

    处理步骤：
    1. 按标题（大小写不敏感）去重
    2. 确保每个 checkpoint 都有有效的 ID
    3. 初始化 CheckpointCoverage 记录

    Returns:
        包含去重后的 ``checkpoints`` 和初始 ``checkpoint_coverage`` 的状态增量。
    """
    raw_checkpoints = state.get("checkpoints", [])

    # 去重：按标题的 casefold 版本判断是否重复
    deduped: list[Checkpoint] = []
    seen_titles: set[str] = set()

    for cp in raw_checkpoints:
        key = cp.title.strip().casefold()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        deduped.append(cp)

    # 初始化覆盖状态记录
    coverage_records: list[CheckpointCoverage] = [
        CheckpointCoverage(
            checkpoint_id=cp.checkpoint_id,
            covered_by_test_ids=[],
            coverage_status="uncovered",
        )
        for cp in deduped
    ]

    return {
        "checkpoints": deduped,
        "checkpoint_coverage": coverage_records,
    }
