"""MR Checkpoint 注入节点。

在 checkpoint_evaluator 之后执行，将 MR 代码级 fact 转换为 checkpoint
并合并到主 checkpoint 列表。

核心职责：
1. 将每个 MRCodeFact 转换为 Checkpoint 对象（MR-CP- 前缀）
2. fact_type → category 映射
3. 基于 title 相似度进行去重
4. 合并到现有 checkpoints 列表
5. 记录 mr_injected_checkpoint_ids
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from typing import Any, Callable

from app.domain.mr_models import MRCodeFact

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# fact_type → category 映射表
# ---------------------------------------------------------------------------

_FACT_TYPE_TO_CATEGORY: dict[str, str] = {
    "code_logic": "functional",
    "error_handling": "edge_case",
    "boundary": "edge_case",
    "state_change": "functional",
    "side_effect": "edge_case",
    "logic_branch": "functional",
    "config_change": "functional",
}
"""将 MRCodeFact.fact_type 映射到 Checkpoint category。"""

_DEFAULT_CATEGORY = "functional"


# ---------------------------------------------------------------------------
# 文本归一化 & 相似度
# ---------------------------------------------------------------------------


def _normalize_text(text: str) -> str:
    """将文本归一化为可比较的标准形式。

    - 转为小写
    - 移除标点和特殊字符
    - Unicode 正规化 (NFKC)
    - 折叠空白
    """
    text = unicodedata.normalize("NFKC", text.lower())
    # 移除标点符号和特殊字符（保留中文、字母、数字）
    text = re.sub(r"[^\w\u4e00-\u9fff]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _text_similarity(a: str, b: str) -> float:
    """计算两段文本的简单相似度（基于字符级 n-gram 重叠）。

    Returns:
        0.0-1.0 之间的相似度值。
    """
    na = _normalize_text(a)
    nb = _normalize_text(b)

    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0

    # 字符 bigram 集合
    n = 2
    set_a = set(na[i : i + n] for i in range(len(na) - n + 1))
    set_b = set(nb[i : i + n] for i in range(len(nb) - n + 1))

    if not set_a or not set_b:
        return 0.0

    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


_DEDUP_THRESHOLD = 0.75
"""去重相似度阈值：title 相似度超过此值视为重复。"""


# ---------------------------------------------------------------------------
# Checkpoint 生成
# ---------------------------------------------------------------------------


def _generate_checkpoint_id(prefix: str, index: int) -> str:
    """生成带前缀的 checkpoint ID。

    Args:
        prefix: ``"FE-"`` / ``"BE-"`` / ``""``。
        index: 序号。

    Returns:
        如 ``FE-MR-CP-0001`` 或 ``MR-CP-0001``。
    """
    return f"{prefix}MR-CP-{index:04d}"


def _fact_to_checkpoint(
    fact: MRCodeFact,
    checkpoint_id: str,
) -> dict[str, Any]:
    """将 MRCodeFact 转换为 Checkpoint 字典。

    注意：这里输出字典而非直接导入 Checkpoint 模型，
    以避免对 checkpoint_models 的硬依赖；
    下游消费者应自行校验/转换。

    Returns:
        包含 checkpoint 必要字段的字典。
    """
    category = _FACT_TYPE_TO_CATEGORY.get(fact.fact_type, _DEFAULT_CATEGORY)

    # 从 fact_id 推断端标识
    side_label = ""
    if fact.fact_id.startswith("FE-"):
        side_label = "[前端] "
    elif fact.fact_id.startswith("BE-"):
        side_label = "[后端] "

    title = f"{side_label}{fact.description[:100]}"
    description = fact.description
    if fact.code_snippet:
        description += f"\n\n关键代码：\n```\n{fact.code_snippet[:500]}\n```"

    return {
        "checkpoint_id": checkpoint_id,
        "title": title,
        "description": description,
        "category": category,
        "source": "mr_code_analysis",
        "source_file": fact.source_file,
        "fact_ids": [fact.fact_id],
        "related_prd_fact_ids": fact.related_prd_fact_ids,
        "tags": ["mr_code_checkpoint"],
    }


# ---------------------------------------------------------------------------
# 去重逻辑
# ---------------------------------------------------------------------------


def _deduplicate_checkpoints(
    new_checkpoints: list[dict[str, Any]],
    existing_checkpoints: list[Any],
) -> list[dict[str, Any]]:
    """对 MR checkpoint 与已有 checkpoint 做去重。

    基于 title 的归一化文本相似度。超过阈值视为重复并跳过。

    Args:
        new_checkpoints: 待注入的 MR checkpoint 字典列表。
        existing_checkpoints: 现有 checkpoint 列表（支持 dict 或对象）。

    Returns:
        去重后的新 checkpoint 列表。
    """
    existing_titles: list[str] = []
    for cp in existing_checkpoints:
        if isinstance(cp, dict):
            t = cp.get("title", cp.get("name", ""))
        else:
            t = getattr(cp, "title", getattr(cp, "name", ""))
        existing_titles.append(t)

    deduplicated: list[dict[str, Any]] = []
    dedup_titles: list[str] = list(existing_titles)

    for new_cp in new_checkpoints:
        new_title = new_cp.get("title", "")
        is_duplicate = False

        for existing_title in dedup_titles:
            sim = _text_similarity(new_title, existing_title)
            if sim >= _DEDUP_THRESHOLD:
                logger.debug(
                    "去重跳过: '%s' ≈ '%s' (sim=%.2f)",
                    new_title[:50], existing_title[:50], sim,
                )
                is_duplicate = True
                break

        if not is_duplicate:
            deduplicated.append(new_cp)
            dedup_titles.append(new_title)

    skipped = len(new_checkpoints) - len(deduplicated)
    if skipped > 0:
        logger.info("MR checkpoint 去重: 跳过 %d / %d 条", skipped, len(new_checkpoints))

    return deduplicated


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------


def build_mr_checkpoint_injector_node() -> Callable[..., dict[str, Any]]:
    """构建 MR checkpoint 注入节点。

    不需要 llm_client 参数，纯逻辑转换。

    Returns:
        ``mr_checkpoint_injector_node(state: CaseGenState) -> dict`` 节点函数。
    """

    def mr_checkpoint_injector_node(state: dict[str, Any]) -> dict[str, Any]:
        """将 MR 代码级 checkpoint 注入主 checkpoint 列表。

        当 state 中无 mr_code_facts 时直接 pass-through。
        """
        mr_code_facts: list[MRCodeFact] = state.get("mr_code_facts", [])

        if not mr_code_facts:
            logger.info("mr_checkpoint_injector: 无 mr_code_facts，pass-through")
            return {}

        existing_checkpoints = state.get("checkpoints", [])

        # ---- Step 1: 将每个 MRCodeFact 转换为 Checkpoint ----
        new_checkpoints: list[dict[str, Any]] = []
        for idx, fact in enumerate(mr_code_facts):
            # 从 fact_id 推断前缀
            prefix = ""
            if fact.fact_id.startswith("FE-"):
                prefix = "FE-"
            elif fact.fact_id.startswith("BE-"):
                prefix = "BE-"

            cp_id = _generate_checkpoint_id(prefix, idx + 1)
            cp_dict = _fact_to_checkpoint(fact, cp_id)
            new_checkpoints.append(cp_dict)

        logger.info(
            "mr_checkpoint_injector: 从 %d 个 facts 生成 %d 个候选 checkpoint",
            len(mr_code_facts), len(new_checkpoints),
        )

        # ---- Step 2: 去重 ----
        deduplicated = _deduplicate_checkpoints(new_checkpoints, existing_checkpoints)

        # ---- Step 3: 合并到现有列表 ----
        merged = list(existing_checkpoints) + deduplicated
        injected_ids = [cp["checkpoint_id"] for cp in deduplicated]

        # ---- Step 4: 关联一致性问题 ----
        consistency_issues = state.get("mr_consistency_issues", [])
        if consistency_issues and deduplicated:
            _link_consistency_issues(consistency_issues, deduplicated)

        logger.info(
            "mr_checkpoint_injector 完成: 注入 %d 个 checkpoint (去重后)，总计 %d 个",
            len(deduplicated), len(merged),
        )

        return {
            "checkpoints": merged,
            "mr_injected_checkpoint_ids": injected_ids,
        }

    return mr_checkpoint_injector_node


# ---------------------------------------------------------------------------
# 辅助：一致性问题关联
# ---------------------------------------------------------------------------


def _link_consistency_issues(
    issues: list[Any],
    checkpoints: list[dict[str, Any]],
) -> None:
    """将一致性问题与新注入的 checkpoint 建立关联。

    通过文件路径匹配将 ConsistencyIssue.affected_checkpoint_ids
    补充为对应的 MR checkpoint ID。
    """
    for issue in issues:
        affected_file = getattr(issue, "affected_file", "")
        if not affected_file:
            continue

        for cp in checkpoints:
            source_file = cp.get("source_file", "")
            if source_file and affected_file in source_file:
                affected_ids = getattr(issue, "affected_checkpoint_ids", [])
                cp_id = cp["checkpoint_id"]
                if cp_id not in affected_ids:
                    affected_ids.append(cp_id)
                    # 更新回 issue 对象
                    if hasattr(issue, "affected_checkpoint_ids"):
                        issue.affected_checkpoint_ids = affected_ids
