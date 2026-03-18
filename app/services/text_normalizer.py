"""文本规范化服务。

提供中英文混排场景下的文本规范化能力：
- 将常见英文动作词替换为中文等价词
- 将常见结构性术语替换为中文等价词
- 保护代码标识符（snake_case、camelCase、ALL_CAPS）、
  反引号包裹内容、URL 等不被错误替换
"""

from __future__ import annotations

import re
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
