"""自动状态桥接模块。

基于 TypedDict 类型注解自动计算主图 (GlobalState) 和子图 (CaseGenState)
之间的交集字段，实现双向自动转发，消除手动 State Wiring。

用法::

    from app.graphs.state_bridge import build_bridge

    bridge = build_bridge(
        subgraph=compiled_subgraph,
        parent_type=GlobalState,
        child_type=CaseGenState,
        override_in={"language": "zh-CN"},
        exclude_out={"uncovered_checkpoints"},
    )
    builder.add_node("case_generation", bridge)
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, get_type_hints

logger = logging.getLogger(__name__)


@lru_cache(maxsize=16)
def compute_shared_keys(parent_type: type, child_type: type) -> frozenset[str]:
    """计算两个 TypedDict 的交集字段名。

    使用 ``typing.get_type_hints()`` 提取字段名，正确处理
    ``from __future__ import annotations`` 和继承场景。
    结果使用 ``lru_cache`` 缓存，因为 TypedDict 字段定义是静态的。

    Args:
        parent_type: 主图 TypedDict 类型（如 ``GlobalState``）。
        child_type: 子图 TypedDict 类型（如 ``CaseGenState``）。

    Returns:
        两个 TypedDict 交集字段名的 frozenset。
    """
    parent_keys = set(get_type_hints(parent_type).keys())
    child_keys = set(get_type_hints(child_type).keys())
    shared = frozenset(parent_keys & child_keys)
    logger.info(
        "Auto-bridge %s ↔ %s: %d shared keys\nShared keys: %s",
        parent_type.__name__,
        child_type.__name__,
        len(shared),
        sorted(shared),
    )
    return shared


def build_bridge(
    subgraph,
    parent_type: type,
    child_type: type,
    override_in: dict[str, Any] | None = None,
    exclude_out: set[str] | None = None,
):
    """构建自动桥接节点函数。

    返回一个 ``Callable[[dict], dict]``，与 LangGraph 的 node 接口兼容，
    可直接传给 ``builder.add_node()``。

    **入向映射**（主图 → 子图）：

    对于每个交集字段 *key*：

    1. 如果 *key* 在主图 state 中存在且值不为 ``None``：转发
    2. 否则如果 *key* 在 ``override_in`` 中有默认值：使用默认值
    3. 否则：跳过（子图按 ``total=False`` 语义处理缺失）

    **出向映射**（子图 → 主图）：

    对于每个交集字段 *key*：

    1. 如果 *key* 不在 ``exclude_out`` 中且在子图结果中存在：回传
    2. 否则：跳过

    Args:
        subgraph: 编译后的 LangGraph 子图实例。
        parent_type: 主图 TypedDict 类型。
        child_type: 子图 TypedDict 类型。
        override_in: 入向字段的默认值覆盖字典。当主图 state 中没有
            该字段或值为 None 时使用。
        exclude_out: 出向排除集。列出不需要从子图回传到主图的字段名。

    Returns:
        桥接节点函数，签名为 ``(state: dict) -> dict``。
    """
    shared = compute_shared_keys(parent_type, child_type)
    _override_in = override_in or {}
    _exclude_out = exclude_out or set()

    # 启动时校验 override_in 中的 key 是否在交集中
    stale = set(_override_in.keys()) - shared
    if stale:
        logger.warning(
            "override_in contains keys not in shared set: %s", sorted(stale),
        )

    logger.info(
        "Auto-bridge %s ↔ %s configured: %d shared keys, %d override_in, %d exclude_out",
        parent_type.__name__,
        child_type.__name__,
        len(shared),
        len(_override_in),
        len(_exclude_out),
    )

    def bridge_node(state: dict) -> dict:
        # ---- 入向映射：主图 → 子图 ----
        subgraph_input: dict[str, Any] = {}
        forwarded_in = 0
        missing_in = 0
        for key in shared:
            value = state.get(key)
            if value is not None and key in state:
                subgraph_input[key] = value
                forwarded_in += 1
            elif key in _override_in:
                subgraph_input[key] = _override_in[key]
                forwarded_in += 1
            else:
                missing_in += 1

        logger.debug(
            "Bridge IN: forwarded %d/%d shared keys (%d missing in parent state)",
            forwarded_in,
            len(shared),
            missing_in,
        )

        # ---- 子图执行 ----
        subgraph_result = subgraph.invoke(subgraph_input)

        # ---- 出向映射：子图 → 主图 ----
        output: dict[str, Any] = {}
        forwarded_out = 0
        excluded_count = 0
        missing_out = 0
        for key in shared:
            if key in _exclude_out:
                excluded_count += 1
            elif key in subgraph_result:
                output[key] = subgraph_result[key]
                forwarded_out += 1
            else:
                missing_out += 1

        logger.debug(
            "Bridge OUT: forwarded %d keys (%d excluded, %d missing in subgraph result)",
            forwarded_out,
            excluded_count,
            missing_out,
        )
        return output

    return bridge_node
