"""自动状态桥接模块。

基于 TypedDict 类型注解自动计算主图 (GlobalState) 和子图 (CaseGenState)
之间的交集字段，实现双向自动转发，消除手动 State Wiring。

注意：自动桥接只负责“字段搬运”，不负责“字段语义设计”。
为了避免子图内部中间态意外泄漏回主图，本模块采用如下硬约束：

1. 入向（主图 → 子图）默认按 shared keys 自动转发，减少漏接线概率。
2. 出向（子图 → 主图）必须显式 allowlist，避免默认全量回传放宽状态边界。
3. override_in 仅在“字段缺失（key not in state）”时生效；若字段显式存在但值为 None，
   则保留 None 的业务语义，不自动替换为默认值。

用法::

    from app.graphs.state_bridge import build_bridge

    bridge = build_bridge(
        subgraph=compiled_subgraph,
        parent_type=GlobalState,
        child_type=CaseGenState,
        override_in={"language": "zh-CN"},
        include_out={"draft_cases", "test_cases"},
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
    include_out: set[str] | None = None,
):
    """构建自动桥接节点函数。

    返回一个 ``Callable[[dict], dict]``，与 LangGraph 的 node 接口兼容，
    可直接传给 ``builder.add_node()``。

    设计原则：

    - **入向默认自动转发**：只要字段同时存在于父/子 TypedDict 中，就默认允许从主图
      传给子图，从而降低新增字段时忘记接线的概率。
    - **出向必须显式 allowlist**：只有被 ``include_out`` 明确列出的共享字段，才允许
      从子图回传到主图。这是故意的保守设计，用来保护主图/子图之间的语义边界，
      避免子图内部中间态因为“恰好同名”而被默认提升为主图稳定输出。
    - **None 与缺失分离**：``override_in`` 只在字段“完全缺失”时生效；如果字段显式
      存在且值为 ``None``，则认为调用方是在主动表达“空值/置空/禁用”的业务语义，
      bridge 不应擅自用默认值覆盖它。

    **入向映射**（主图 → 子图）：

    对于每个交集字段 *key*：

    1. 如果 *key* 在主图 state 中存在：直接转发当前值（包括 ``None``）
    2. 否则如果 *key* 在 ``override_in`` 中有默认值：使用默认值
    3. 否则：跳过（子图按 ``total=False`` 语义处理缺失）

    **出向映射**（子图 → 主图）：

    对于每个交集字段 *key*：

    1. 只有当 *key* 在 ``include_out`` 中且在子图结果中存在：才回传
    2. 其他字段一律不回传，即使它们属于 shared keys

    Args:
        subgraph: 编译后的 LangGraph 子图实例。
        parent_type: 主图 TypedDict 类型。
        child_type: 子图 TypedDict 类型。
        override_in: 入向字段的默认值覆盖字典。仅当主图 state 中**缺少该 key** 时使用；
            不会覆盖显式存在的 ``None``。
        include_out: 出向允许集。仅列出允许从子图回传到主图的字段名。
            该参数采用 allowlist 设计，而不是 exclude 设计；这是本模块最重要的
            安全边界之一。后续若要新增主图可见输出，请在此处显式登记并补充测试。

    Returns:
        桥接节点函数，签名为 ``(state: dict) -> dict``。
    """
    shared = compute_shared_keys(parent_type, child_type)
    _override_in = override_in or {}
    _include_out = include_out or set()

    # 启动时校验 override_in / include_out 中的 key 是否在交集中，避免配置漂移。
    stale_override = set(_override_in.keys()) - shared
    if stale_override:
        logger.warning(
            "override_in contains keys not in shared set: %s", sorted(stale_override),
        )

    stale_include = set(_include_out) - shared
    if stale_include:
        logger.warning(
            "include_out contains keys not in shared set: %s", sorted(stale_include),
        )

    logger.info(
        "Auto-bridge %s ↔ %s configured: %d shared keys, %d override_in, %d include_out",
        parent_type.__name__,
        child_type.__name__,
        len(shared),
        len(_override_in),
        len(_include_out),
    )

    def bridge_node(state: dict) -> dict:
        # ---- 入向映射：主图 → 子图 ----
        subgraph_input: dict[str, Any] = {}
        forwarded_in = 0
        missing_in = 0
        for key in shared:
            if key in state:
                # 显式存在就原样转发，哪怕值为 None。
                # 这样可以保留“显式置空”和“字段缺失”的语义差异。
                subgraph_input[key] = state[key]
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
        # 这里故意采用 include_out allowlist，而不是“shared keys 默认全回传”。
        # 原因：一旦父子状态模型中新增了同名字段，default-allow 会在没有代码评审的
        # 情况下自动放宽主图可见状态边界；而 allowlist 可以强制开发者在新增输出字段时
        # 明确评估该字段是否应该成为主图契约的一部分。
        output: dict[str, Any] = {}
        forwarded_out = 0
        skipped_not_allowed = 0
        missing_out = 0
        for key in shared:
            if key not in _include_out:
                skipped_not_allowed += 1
            elif key in subgraph_result:
                output[key] = subgraph_result[key]
                forwarded_out += 1
            else:
                missing_out += 1

        logger.debug(
            "Bridge OUT: forwarded %d allowed keys (%d not allowed, %d missing in subgraph result)",
            forwarded_out,
            skipped_not_allowed,
            missing_out,
        )
        return output

    return bridge_node
