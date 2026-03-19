"""文本规范化服务。

提供中英文混排场景下的文本规范化能力：
- 将常见英文动作词替换为中文等价词
- 将常见结构性术语替换为中文等价词
- 保护代码标识符（snake_case、camelCase、ALL_CAPS）、
  反引号包裹内容、URL 等不被错误替换

新增文本精炼（F2）能力：
- ``refine_text``: 去除冗余前缀/后缀，提取动作三元组，截断超长文本
- ``refine_test_case``: 对 TestCase 的所有文本字段做精炼处理
- ``_merge_redundant_steps``: 基于 SequenceMatcher 合并高相似度步骤
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.case_models import TestCase

# ---------------------------------------------------------------------------
# 占位符机制：先把需要保护的内容替换为占位符，处理完再还原
# ---------------------------------------------------------------------------

_PLACEHOLDER_PREFIX = "\x00PH"
_PLACEHOLDER_SUFFIX = "\x00"


def _make_placeholder(index: int) -> str:
    """生成一个唯一的占位符标记。"""
    return f"{_PLACEHOLDER_PREFIX}{index}{_PLACEHOLDER_SUFFIX}"


# ---------------------------------------------------------------------------
# 保护模式：匹配需要被保护（不做翻译替换）的内容
# ---------------------------------------------------------------------------

# 反引号包裹的内容，例如 `Create campaign`
_RE_BACKTICK = re.compile(r"`[^`]+`")

# URL 模式
_RE_URL = re.compile(r"https?://[^\s,;)}\]]+")

# snake_case 标识符：至少包含一个下划线，由字母数字组成
_RE_SNAKE_CASE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9]*(?:_[a-zA-Z0-9]+)+\b")

# camelCase 标识符：小写字母开头，后面跟大写字母（如 handleClick）
_RE_CAMEL_CASE = re.compile(r"\b[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*\b")

# PascalCase 标识符：大写开头且内部含有额外大写（如 TestCase, HttpClient）
_RE_PASCAL_CASE = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z0-9]+)+\b")

# ALL_CAPS 缩写词：2 个或以上连续大写字母（API, URL, JSON, CTA, ID 等）
_RE_ALL_CAPS = re.compile(r"\b[A-Z]{2,}(?:s)?\b")

# 点号分隔的路径/字段引用，如 response.data.items
_RE_DOT_PATH = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+\b")

# 保护模式列表，按优先级排列（先匹配的先保护）
_PROTECT_PATTERNS: list[re.Pattern[str]] = [
    _RE_BACKTICK,
    _RE_URL,
    _RE_DOT_PATH,
    _RE_SNAKE_CASE,
    _RE_CAMEL_CASE,
    _RE_PASCAL_CASE,
    _RE_ALL_CAPS,
]

# ---------------------------------------------------------------------------
# 英文动作词 → 中文映射表
# ---------------------------------------------------------------------------

_ACTION_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bNavigate to\b", re.IGNORECASE), "导航到"),
    (re.compile(r"\bNavigate\b", re.IGNORECASE), "导航"),
    (re.compile(r"\bDouble[- ]click\b", re.IGNORECASE), "双击"),
    (re.compile(r"\bRight[- ]click\b", re.IGNORECASE), "右键点击"),
    (re.compile(r"\bClick on\b", re.IGNORECASE), "点击"),
    (re.compile(r"\bClick\b", re.IGNORECASE), "点击"),
    (re.compile(r"\bSelect\b", re.IGNORECASE), "选择"),
    (re.compile(r"\bInput\b", re.IGNORECASE), "输入"),
    (re.compile(r"\bEnter\b", re.IGNORECASE), "输入"),
    (re.compile(r"\bCheck\b", re.IGNORECASE), "检查"),
    (re.compile(r"\bVerify that\b", re.IGNORECASE), "验证"),
    (re.compile(r"\bVerify\b", re.IGNORECASE), "验证"),
    (re.compile(r"\bConfirm\b", re.IGNORECASE), "确认"),
    (re.compile(r"\bCreate\b", re.IGNORECASE), "创建"),
    (re.compile(r"\bSubmit\b", re.IGNORECASE), "提交"),
    (re.compile(r"\bDelete\b", re.IGNORECASE), "删除"),
    (re.compile(r"\bRemove\b", re.IGNORECASE), "移除"),
    (re.compile(r"\bOpen\b", re.IGNORECASE), "打开"),
    (re.compile(r"\bClose\b", re.IGNORECASE), "关闭"),
    (re.compile(r"\bSave\b", re.IGNORECASE), "保存"),
    (re.compile(r"\bCancel\b", re.IGNORECASE), "取消"),
    (re.compile(r"\bEdit\b", re.IGNORECASE), "编辑"),
    (re.compile(r"\bUpdate\b", re.IGNORECASE), "更新"),
    (re.compile(r"\bSearch\b", re.IGNORECASE), "搜索"),
    (re.compile(r"\bLog\s*in\b", re.IGNORECASE), "登录"),
    (re.compile(r"\bLogin\b", re.IGNORECASE), "登录"),
    (re.compile(r"\bLog\s*out\b", re.IGNORECASE), "登出"),
    (re.compile(r"\bLogout\b", re.IGNORECASE), "登出"),
    (re.compile(r"\bUpload\b", re.IGNORECASE), "上传"),
    (re.compile(r"\bDownload\b", re.IGNORECASE), "下载"),
    (re.compile(r"\bRefresh\b", re.IGNORECASE), "刷新"),
]

# ---------------------------------------------------------------------------
# 结构性术语 → 中文映射表
# ---------------------------------------------------------------------------

_STRUCTURAL_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bPreconditions?\b", re.IGNORECASE), "前置条件"),
    (re.compile(r"\bSteps?\b", re.IGNORECASE), "步骤"),
    (re.compile(r"\bExpected Results?\b", re.IGNORECASE), "预期结果"),
    (re.compile(r"\bMain branch\b", re.IGNORECASE), "主分支"),
    (re.compile(r"\bEdge cases?\b", re.IGNORECASE), "边界场景"),
    (re.compile(r"\bException branch\b", re.IGNORECASE), "异常分支"),
    (re.compile(r"\bError branch\b", re.IGNORECASE), "异常分支"),
]


# ---------------------------------------------------------------------------
# 核心规范化函数
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    """对文本进行中英文混排规范化处理。

    处理流程：
    1. 提取并保护不应被替换的内容（代码标识符、URL、反引号内容等）
    2. 替换常见英文动作词为中文
    3. 替换常见结构性术语为中文
    4. 还原被保护的内容

    Args:
        text: 原始文本。

    Returns:
        规范化后的文本。
    """
    if not text or not text.strip():
        return text

    # 如果文本已经全是中文（不含任何 ASCII 字母），直接返回
    if not re.search(r"[a-zA-Z]", text):
        return text

    # 第一步：保护需要保留的内容
    protected: list[str] = []
    working_text = text

    for pattern in _PROTECT_PATTERNS:
        def _replace_with_placeholder(match: re.Match[str]) -> str:
            idx = len(protected)
            protected.append(match.group(0))
            return _make_placeholder(idx)

        working_text = pattern.sub(_replace_with_placeholder, working_text)

    # 第二步：替换动作词
    for pattern, replacement in _ACTION_MAP:
        working_text = pattern.sub(replacement, working_text)

    # 第三步：替换结构性术语
    for pattern, replacement in _STRUCTURAL_MAP:
        working_text = pattern.sub(replacement, working_text)

    # 第四步：还原被保护的内容
    for idx, original in enumerate(protected):
        working_text = working_text.replace(_make_placeholder(idx), original)

    return working_text


def normalize_test_case(case: "TestCase") -> "TestCase":
    """对 TestCase 对象的文本字段进行规范化处理。

    处理字段包括：title、preconditions、steps、expected_results。
    id、priority、category、checkpoint_id 等标识字段不做处理。

    Args:
        case: 待规范化的测试用例。

    Returns:
        规范化后的测试用例副本（不修改原对象）。
    """
    return case.model_copy(
        update={
            "title": normalize_text(case.title),
            "preconditions": [normalize_text(p) for p in case.preconditions],
            "steps": [normalize_text(s) for s in case.steps],
            "expected_results": [normalize_text(r) for r in case.expected_results],
        }
    )


# ===========================================================================
# 以下为 F2（文本精炼）新增代码
# ===========================================================================

# ---------------------------------------------------------------------------
# 关键标识符保护模式（精炼阶段额外保护）
# ---------------------------------------------------------------------------

_KEY_IDENTIFIER_PATTERNS: list[re.Pattern[str]] = [
    _RE_BACKTICK,
    _RE_URL,
    re.compile(r"\b(?:成功|失败|启用|禁用|开启|关闭|有效|无效|已|未)\b"),  # 状态词
]

# ---------------------------------------------------------------------------
# 中文前缀 / 后缀模式
# ---------------------------------------------------------------------------

_ZH_PREFIX_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^验证(?:用户)?(?:能够|可以)?"),
    re.compile(r"^检查(?:是否)?"),
    re.compile(r"^确认(?:是否)?"),
    re.compile(r"^确保(?:能够|可以)?"),
    re.compile(r"^测试(?:用户)?(?:能否|能够|是否)?"),
    re.compile(r"^(?:请|需要)?(?:先)?"),
    re.compile(r"^用户(?:需要|应该|可以)?"),
    re.compile(r"^预期(?:结果)?(?:为|是)?(?:：|:)?"),
    re.compile(r"^系统(?:应该|应当|需要|会)?"),
    re.compile(r"^(?:当|如果|假设).*?(?:时|后)(?:，|,)?"),
    re.compile(r"^(?:在|于).*?(?:页面|界面|模块)(?:中|上|下)?(?:，|,)?"),
    re.compile(r"^(?:首先|然后|接着|最后)(?:，|,)?"),
    re.compile(r"^(?:步骤|操作)(?:\d+)?(?:：|:)?"),
    re.compile(r"^\d+[\.\)、]\s*"),
    re.compile(r"^(?:前置条件|前提条件)(?:：|:)?"),
    re.compile(r"^(?:预期|期望)(?:：|:)?"),
]

_ZH_SUFFIX_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:是否正常|是否正确|是否成功|是否生效)$"),
    re.compile(r"(?:应该|应当|需要|可以)(?:正常|正确|成功)?(?:工作|运行|显示|生效)?$"),
    re.compile(r"(?:能够|可以)(?:正常)?(?:使用|操作|访问|运行)$"),
    re.compile(r"(?:无误|无问题|没有问题|没有异常)$"),
    re.compile(r"[。.]\s*$"),
    re.compile(r"(?:等|等等)[。.]?\s*$"),
    re.compile(r"(?:符合预期|按预期|如预期)$"),
    re.compile(r"(?:正常|正确)\s*$"),
]

# ---------------------------------------------------------------------------
# 英文前缀 / 后缀模式
# ---------------------------------------------------------------------------

_EN_PREFIX_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^Verify\s+that\s+", re.IGNORECASE),
    re.compile(r"^Verify\s+", re.IGNORECASE),
    re.compile(r"^Check\s+(?:that|if|whether)\s+", re.IGNORECASE),
    re.compile(r"^Ensure\s+(?:that)?\s*", re.IGNORECASE),
    re.compile(r"^Confirm\s+(?:that)?\s*", re.IGNORECASE),
    re.compile(r"^Validate\s+(?:that)?\s*", re.IGNORECASE),
    re.compile(r"^Test\s+(?:that|if|whether)\s+", re.IGNORECASE),
    re.compile(r"^The\s+user\s+(?:should|can|must|needs?\s+to)\s+", re.IGNORECASE),
    re.compile(r"^(?:Step\s+)?\d+[\.\)]\s*", re.IGNORECASE),
    re.compile(r"^(?:Pre-?condition|Prerequisite)s?:\s*", re.IGNORECASE),
]

_EN_SUFFIX_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\s+as\s+expected\.?\s*$", re.IGNORECASE),
    re.compile(r"\s+(?:is|are)\s+(?:correct|successful|working)\.?\s*$", re.IGNORECASE),
    re.compile(r"\s+(?:should|must|shall)\s+(?:work|succeed|pass)\.?\s*$", re.IGNORECASE),
    re.compile(r"\.\s*$"),
    re.compile(r"\s+(?:properly|correctly|successfully)\s*$", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# 长度限制
# ---------------------------------------------------------------------------

_LENGTH_LIMITS: dict[str, dict[str, int]] = {
    "zh-CN": {"title": 80, "step": 120, "precondition": 120, "expected_result": 120},
    "en": {"title": 120, "step": 180, "precondition": 180, "expected_result": 180},
}

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _strip_numbering(text: str) -> str:
    """去除步骤编号前缀。"""
    return re.sub(r"^(?:(?:step\s*)?\d+[\.\)、：:]\s*)", "", text, flags=re.IGNORECASE)


def _protect_and_restore(text: str, func):
    """保护关键标识符 → 执行处理 → 还原。"""
    protected: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        idx = len(protected)
        protected.append(match.group(0))
        return _make_placeholder(idx)

    working = text
    for pat in _KEY_IDENTIFIER_PATTERNS:
        working = pat.sub(_replace, working)

    working = func(working)

    for idx, original in enumerate(protected):
        working = working.replace(_make_placeholder(idx), original)

    return working


def _apply_prefix_removal(text: str, patterns: list[re.Pattern[str]]) -> str:
    """依次尝试前缀模式，命中第一个即移除。"""
    for pat in patterns:
        new_text = pat.sub("", text)
        if new_text != text and new_text.strip():
            return new_text.strip()
    return text


def _apply_suffix_removal(text: str, patterns: list[re.Pattern[str]]) -> str:
    """依次尝试后缀模式，命中第一个即移除。"""
    for pat in patterns:
        new_text = pat.sub("", text)
        if new_text != text and new_text.strip():
            return new_text.strip()
    return text


def _truncate_to_limit(text: str, limit: int) -> str:
    """截断超长文本并加省略号。"""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


# ---------------------------------------------------------------------------
# 公开 API：文本精炼
# ---------------------------------------------------------------------------


def refine_text(
    text: str,
    *,
    text_type: str = "step",
    language: str = "zh-CN",
) -> str:
    """对单条文本执行精炼。

    流程：
    1. 保护关键标识符（反引号内容、URL、状态词）
    2. 去除冗余前缀
    3. 去除冗余后缀
    4. 截断超长文本
    5. 还原被保护的内容

    Args:
        text: 原始文本。
        text_type: 文本类型（title / step / precondition / expected_result）。
        language: 语言标识（zh-CN / en）。

    Returns:
        精炼后的文本。
    """
    if not text or not text.strip():
        return text

    lang_key = "zh-CN" if language.startswith("zh") else "en"

    def _inner(working: str) -> str:
        if lang_key == "zh-CN":
            working = _apply_prefix_removal(working, _ZH_PREFIX_PATTERNS)
            working = _apply_suffix_removal(working, _ZH_SUFFIX_PATTERNS)
        else:
            working = _apply_prefix_removal(working, _EN_PREFIX_PATTERNS)
            working = _apply_suffix_removal(working, _EN_SUFFIX_PATTERNS)
        return working

    result = _protect_and_restore(text.strip(), _inner)

    limit = _LENGTH_LIMITS.get(lang_key, _LENGTH_LIMITS["en"]).get(text_type, 180)
    result = _truncate_to_limit(result, limit)

    return result


# ---------------------------------------------------------------------------
# 冗余步骤合并
# ---------------------------------------------------------------------------

_SIMILARITY_THRESHOLD = 0.85


def _merge_redundant_steps(steps: list[str], *, language: str = "zh-CN") -> list[str]:
    """合并高相似度的连续步骤。

    使用 ``SequenceMatcher`` 计算相邻步骤的相似度，
    当相似度 ≥ 阈值时保留较长的那条。

    Args:
        steps: 步骤列表。
        language: 语言标识。

    Returns:
        去冗余后的步骤列表。
    """
    if len(steps) <= 1:
        return list(steps)

    result: list[str] = [steps[0]]
    for i in range(1, len(steps)):
        prev = result[-1]
        curr = steps[i]
        ratio = SequenceMatcher(None, prev, curr).ratio()
        if ratio >= _SIMILARITY_THRESHOLD:
            # 保留较长的那条
            if len(curr) > len(prev):
                result[-1] = curr
        else:
            result.append(curr)

    return result


# ---------------------------------------------------------------------------
# TestCase 精炼
# ---------------------------------------------------------------------------


def refine_test_case(case: "TestCase", *, language: str = "zh-CN") -> "TestCase":
    """对 TestCase 对象的所有文本字段执行精炼。

    处理字段包括：title、preconditions、steps、expected_results。

    Args:
        case: 待精炼的测试用例。
        language: 语言标识。

    Returns:
        精炼后的测试用例副本（不修改原对象）。
    """
    refined_title = refine_text(case.title, text_type="title", language=language)
    refined_preconditions = [
        refine_text(p, text_type="precondition", language=language)
        for p in case.preconditions
    ]
    refined_steps = [
        refine_text(s, text_type="step", language=language)
        for s in case.steps
    ]
    refined_expected = [
        refine_text(r, text_type="expected_result", language=language)
        for r in case.expected_results
    ]

    # 合并冗余步骤
    refined_steps = _merge_redundant_steps(refined_steps, language=language)

    # 过滤空字符串
    refined_preconditions = [p for p in refined_preconditions if p.strip()]
    refined_steps = [s for s in refined_steps if s.strip()]
    refined_expected = [r for r in refined_expected if r.strip()]

    return case.model_copy(
        update={
            "title": refined_title,
            "preconditions": refined_preconditions,
            "steps": refined_steps,
            "expected_results": refined_expected,
        }
    )
