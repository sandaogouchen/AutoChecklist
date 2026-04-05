"""前置条件分组：将具有共享前置条件的用例聚合到统一 precondition_group 节点。

职责：
1. 读取 TestCase.preconditions（字符串列表）
2. 以规范化后的 precondition tuple 作为分桶键
3. 同键用例合并为一个 precondition_group 节点
4. 构建 ≤3 层 ChecklistNode 树: root → precondition_group → case
5. (可选) LLM 语义合并：对关键词分桶后的结果使用 LLM 进行语义重新分组

设计约束：
- _MIN_GROUP_SIZE = 2：单条用例不创建分组，直接挂根节点
- _MAX_TREE_DEPTH = 3：仅支持三层结构
- LLM 分组为可选增强，llm_client=None 时退化为纯关键词分桶
- 纯函数，无副作用（LLM 调用除外）
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from collections import Counter, OrderedDict
from typing import TYPE_CHECKING, Sequence

from app.domain.case_models import TestCase
from app.domain.checklist_models import ChecklistNode
from app.domain.precondition_models import PreconditionGroupingResult

if TYPE_CHECKING:
    from app.clients.llm import LLMClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 可调参数
# ---------------------------------------------------------------------------

_MIN_GROUP_SIZE = 2
_MAX_TREE_DEPTH = 3
_OTHER_GROUP_TITLE = "其他"

# 优先匹配反引号内容：用户可见 `optimize goal` 字段 → optimize goal
_BACKTICK_RE = re.compile(r"`([^`]+)`")

# 英文 token/短语：Ad Group / optimize goal / campaign creation
_ASCII_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]*(?:\s+[A-Za-z0-9_\-]+)*")

# 若无反引号/英文短语，则尝试这些中文主关键词（单归属）
_PRIMARY_KEYWORDS = (
    "广告计划",
    "广告组",
    "广告创意",
    "广告主",
    "白名单",
    "素材",
    "人群包",
    "落地页",
    "账户",
    "预算",
    "出价",
    "定向",
    "排期",
    "审核",
    "支付",
)

# 常见噪声中文短语，不应作为分组标题
_NOISE_TOKENS = frozenset(
    {
        "用户",
        "可见",
        "可编辑",
        "可以",
        "能够",
        "支持",
        "字段",
        "按钮",
        "页面",
        "功能",
        "进行",
        "查看",
        "创建",
        "编辑",
        "提交",
        "成功",
        "失败",
        "信息",
        "已",
    }
)

# ---------------------------------------------------------------------------
# LLM Prompt 模板
# ---------------------------------------------------------------------------

_LLM_SYSTEM_PROMPT = """\
你是一个测试前置条件分析专家。你的任务是将语义等价的测试前置条件归为同一组。

规则：
1. 如果两个前置条件描述的是相同的环境准备要求（即使措辞不同），它们属于同一组
2. 如果两个前置条件描述的是不同的环境准备要求，它们属于不同组
3. 每组选择最简洁清晰的前置条件作为该组的代表名称（representative）
4. 不要过度合并——只有真正语义等价的才合并
5. 如果某个前置条件与其他所有条件都不等价，它独立成组

示例：
输入: ["已登录账号", "用户处于登录状态", "广告主余额 > 0", "广告主账户有余额"]
输出: 两组 — {"已登录账号": [1,2]}, {"广告主余额充足": [3,4]}"""

_LLM_USER_PROMPT = """\
以下是 {n} 个测试前置条件，请将语义等价的前置条件归为同一组：

{list}

请输出分组结果。每组包含一个简洁的代表名称和成员编号列表。"""


# ---------------------------------------------------------------------------
# 规范化工具函数
# ---------------------------------------------------------------------------


def _normalize_text(text: str) -> str:
    """轻量规范化：NFKC、去两端空白、合并连续空白。"""
    text = unicodedata.normalize("NFKC", text).strip()
    return re.sub(r"\s+", " ", text)


def _normalize_preconditions(values: Sequence[str]) -> tuple[str, ...]:
    """将 preconditions 规范化为可比较 tuple。"""
    return tuple(_normalize_text(v) for v in values if _normalize_text(v))


# ---------------------------------------------------------------------------
# 主关键词提取
# ---------------------------------------------------------------------------


def _extract_primary_keyword(text: str) -> str | None:
    """从单条前置条件中提取“最稳定、可复用”的主关键词。

    优先级：
    1. 反引号内容（字段/对象名）
    2. 英文短语（如 Ad Group / optimize goal）
    3. 预设中文业务关键词（如 广告计划 / 广告组）

    返回 None 表示该文本没有可靠关键词，后续可归入“其他”。
    """
    text = _normalize_text(text)

    # 1) 反引号
    m = _BACKTICK_RE.search(text)
    if m:
        return m.group(1).strip()

    # 2) 英文短语：取最长、信息量更高的那个
    ascii_matches = _ASCII_RE.findall(text)
    if ascii_matches:
        ascii_matches.sort(key=lambda s: (-len(s), s.lower()))
        return ascii_matches[0].strip()

    # 3) 中文业务关键词：按出现顺序选择第一个命中的“主对象”
    for kw in _PRIMARY_KEYWORDS:
        if kw in text:
            return kw

    return None


# ---------------------------------------------------------------------------
# ChecklistNode 构造
# ---------------------------------------------------------------------------


def _case_node(tc: TestCase) -> ChecklistNode:
    return ChecklistNode(
        node_id=f"case-{uuid.uuid4().hex}",
        title=tc.title,
        node_type="case",
        source_case_id=tc.id,
        children=[],
    )


def _precondition_group_node(title: str, cases: list[TestCase]) -> ChecklistNode:
    return ChecklistNode(
        node_id=f"group-{uuid.uuid4().hex}",
        title=title,
        node_type="precondition_group",
        children=[_case_node(tc) for tc in cases],
    )


# ---------------------------------------------------------------------------
# 公开服务
# ---------------------------------------------------------------------------


class PreconditionGrouper:
    """按“主关键词单归属 + 其他兜底”策略对用例分组。

    将 list[TestCase] 按主关键词单归属分组，
    返回 list[ChecklistNode]（根节点的 children）。

    当传入 ``llm_client`` 时，会在关键词分桶之后尝试使用 LLM
    对桶进行语义合并——将措辞不同但语义等价的前置条件归入同一组。
    LLM 调用失败时自动回退到纯关键词分桶结果。
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm_client = llm_client

    def group(self, test_cases: list[TestCase]) -> list[ChecklistNode]:
        """执行分组，返回根节点的子节点列表。

        Args:
            test_cases: 待分组的测试用例列表。

        Returns:
            根节点 children 列表；输入为空时返回空列表。
        """
        if not test_cases:
            return []

        buckets = self._bucket_by_keyword(test_cases)

        # LLM 语义合并（可选增强）
        if self._llm_client is not None:
            try:
                buckets = self._llm_merge_buckets(buckets)
            except Exception as e:
                logger.warning(
                    "LLM 语义分组失败，使用关键词分组结果: %s: %s",
                    type(e).__name__, e,
                )

        return self._build_grouped_tree(buckets)

    # ----- LLM 语义合并 -----

    def _llm_merge_buckets(
        self, buckets: OrderedDict[str, list[TestCase]]
    ) -> OrderedDict[str, list[TestCase]]:
        """使用 LLM 对分桶结果进行语义合并。

        将所有桶的 key（关键词）和"其他"桶中各用例的前置条件文本
        一次性提交给 LLM，由 LLM 判定哪些应合并为同一组。

        Args:
            buckets: 关键词分桶的结果。

        Returns:
            合并后的桶。

        Raises:
            任何 LLM 调用异常均向上抛出，由 group() 统一捕获并 fallback。
        """
        if self._llm_client is None:
            raise RuntimeError("_llm_merge_buckets called without llm_client")

        other_cases = list(buckets.get(_OTHER_GROUP_TITLE, []))
        non_other_keys = [k for k in buckets if k != _OTHER_GROUP_TITLE]

        # 为"其他"桶中每个用例生成前置条件摘要文本
        other_case_texts: list[str] = []
        for case in other_cases:
            text = "; ".join(case.preconditions) if case.preconditions else case.title
            other_case_texts.append(text)

        # 去重后的"其他"文本（保持顺序）
        unique_other_texts = list(dict.fromkeys(other_case_texts))

        # 合并为 LLM 输入列表：[关键词桶 key...] + [其他桶前置条件文本...]
        all_entries = non_other_keys + unique_other_texts

        if len(all_entries) <= 1:
            return buckets

        logger.info(
            "LLM 语义分组启动: %d 个条目 (%d 个关键词桶 + %d 个待分组前置条件)",
            len(all_entries),
            len(non_other_keys),
            len(unique_other_texts),
        )

        # 调用 LLM
        numbered = "\n".join(
            f"{i + 1}. {e}" for i, e in enumerate(all_entries)
        )
        result: PreconditionGroupingResult = self._llm_client.generate_structured(
            system_prompt=_LLM_SYSTEM_PROMPT,
            user_prompt=_LLM_USER_PROMPT.format(
                n=len(all_entries), list=numbered,
            ),
            response_model=PreconditionGroupingResult,
        )

        # 应用分组结果
        n_bucket = len(non_other_keys)
        new_buckets: OrderedDict[str, list[TestCase]] = OrderedDict()
        consumed_bucket_keys: set[str] = set()
        consumed_other_texts: set[str] = set()

        for sem_group in result.groups:
            valid_indices = [
                idx - 1
                for idx in sem_group.member_indices
                if 1 <= idx <= len(all_entries)
            ]
            if not valid_indices:
                continue

            group_cases: list[TestCase] = []

            for idx in valid_indices:
                if idx < n_bucket:
                    key = non_other_keys[idx]
                    if key not in consumed_bucket_keys:
                        group_cases.extend(buckets[key])
                        consumed_bucket_keys.add(key)
                else:
                    text = all_entries[idx]
                    if text not in consumed_other_texts:
                        consumed_other_texts.add(text)
                        group_cases.extend(
                            case
                            for case, ct in zip(other_cases, other_case_texts)
                            if ct == text
                        )

            if group_cases:
                new_buckets[sem_group.representative] = group_cases
                logger.debug(
                    "合并语义组: '%s' (%d 个用例)",
                    sem_group.representative,
                    len(group_cases),
                )

        for key in non_other_keys:
            if key not in consumed_bucket_keys:
                new_buckets[key] = buckets[key]

        remaining_other = [
            case
            for case, text in zip(other_cases, other_case_texts)
            if text not in consumed_other_texts
        ]
        if remaining_other:
            new_buckets[_OTHER_GROUP_TITLE] = remaining_other

        logger.info(
            "LLM 语义分组完成: %d 个桶 → %d 个桶",
            len(buckets),
            len(new_buckets),
        )
        return new_buckets

    # ----- 关键词分桶 -----

    def _bucket_by_keyword(
        self, test_cases: list[TestCase]
    ) -> OrderedDict[str, list[TestCase]]:
        """按主关键词单归属分桶。

        优先从每个用例的全部 preconditions 中提取主关键词，
        若多个前置条件命中多个关键词，则选择出现频次更高者；并列时取首次出现。
        未命中任何可靠关键词的用例进入“其他”桶。
        """
        # 统计每个用例的候选关键词（按 precondition 顺序）
        case_to_keywords: list[list[str]] = []
        global_counter: Counter[str] = Counter()

        for tc in test_cases:
            kws: list[str] = []
            for p in tc.preconditions:
                kw = _extract_primary_keyword(p)
                if kw:
                    kws.append(kw)
                    global_counter[kw] += 1
            case_to_keywords.append(kws)

        buckets: OrderedDict[str, list[TestCase]] = OrderedDict()
        others: list[TestCase] = []

        for tc, kws in zip(test_cases, case_to_keywords):
            if not kws:
                others.append(tc)
                continue

            seen: set[str] = set()
            ordered_unique = [k for k in kws if not (k in seen or seen.add(k))]

            ordered_unique.sort(
                key=lambda k: (-global_counter[k], ordered_unique.index(k))
            )
            chosen = ordered_unique[0]

            buckets.setdefault(chosen, []).append(tc)

        if others:
            buckets[_OTHER_GROUP_TITLE] = others

        return buckets

    def _build_grouped_tree(
        self, buckets: OrderedDict[str, list[TestCase]]
    ) -> list[ChecklistNode]:
        """将分桶结果转换为 ChecklistNode 树。

        规则：
        - 命中主关键词的桶：创建 precondition_group 节点
        - 未命中共享关键词的用例：收敛到"其他"桶
        - 仅单条、且无任何可分组上下文时：保持独立 case 节点
        """
        children: list[ChecklistNode] = []

        for title, cases in buckets.items():
            if len(cases) >= _MIN_GROUP_SIZE:
                children.append(_precondition_group_node(title, cases))
            else:
                children.extend(_case_node(tc) for tc in cases)

        return children


__all__ = [
    "PreconditionGrouper",
    "_normalize_text",
    "_normalize_preconditions",
    "_extract_primary_keyword",
]
