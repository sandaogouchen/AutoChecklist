"""Coco Task 2 一致性校验节点。

在 mr_code_checkpoint_injector 之后、coverage_detector 之前执行。
对每个 checkpoint 通过 Coco Agent 进行代码一致性校验（多线程并行），
校验结果标注到 checkpoint.code_consistency 字段和 tags 上。

并发控制：
- asyncio.Semaphore(5) 限制最大并发数
- 单 case 超时 120s
- 总超时 600s
- 失败策略：标记为 unverified，不阻断其他 case

仅当 use_coco=True 时激活，否则 pass-through。
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Callable

from app.domain.mr_models import (
    CodeConsistencyResult,
    MRSourceConfig,
)

logger = logging.getLogger(__name__)

from app.utils.filesystem import ensure_directory, write_json


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_MAX_CONCURRENCY = 5
"""最大并发校验数。"""

_PER_CASE_TIMEOUT_S = 120
"""单个 checkpoint 校验的最大等待时间（秒）。"""

_TOTAL_TIMEOUT_S = 6000
"""全部 checkpoint 校验的最大总时间（秒）。"""

_CONFIDENCE_THRESHOLD = 0.7
"""置信度阈值：低于此值的 mismatch 不标注 TODO。"""


def _resolve_total_timeout_s(checkpoint_count: int) -> float:
    """根据 checkpoint 数量推导本轮 Coco 校验的总超时。

    现有配置中的 `_TOTAL_TIMEOUT_S` 作为下限；
    当 checkpoint 数量较多时，按 `ceil(count / concurrency) * per_case_timeout`
    放大总超时，避免配置上出现“理论最短串批耗时已经超过总超时”的情况。
    """
    if checkpoint_count <= 0:
        return float(_TOTAL_TIMEOUT_S)

    concurrency = max(int(_MAX_CONCURRENCY), 1)
    waves = (checkpoint_count + concurrency - 1) // concurrency
    required_timeout = waves * float(_PER_CASE_TIMEOUT_S)
    return max(float(_TOTAL_TIMEOUT_S), required_timeout)


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------


def build_coco_consistency_validator_node(
    llm_client: Any | None = None,
    coco_settings: Any | None = None,
) -> Callable[..., dict[str, Any]]:
    """构建 Coco 一致性校验节点。

    Args:
        llm_client: LLM 客户端（用于 CocoResponseValidator 的 LLM 推断）。
        coco_settings: Coco Agent 配置对象。

    Returns:
        ``coco_consistency_validator_node(state: CaseGenState) -> dict`` 节点函数。
    """

    async def _run_validation(state: dict[str, Any]) -> dict[str, Any]:
        """Coco Task 2 — 逐 checkpoint 一致性校验主逻辑。

        当 use_coco 未启用或无 checkpoint 时直接 pass-through。
        """
        checkpoints = state.get("checkpoints", [])
        if not checkpoints:
            logger.info("coco_consistency_validator: 无 checkpoints，pass-through")
            return {}

        # ---- 收集启用 Coco 的端配置 ----
        coco_configs: list[tuple[str, MRSourceConfig]] = []

        frontend_mr = state.get("frontend_mr_config")
        if isinstance(frontend_mr, MRSourceConfig) and frontend_mr.use_coco:
            coco_configs.append(("frontend", frontend_mr))
        elif isinstance(frontend_mr, dict) and frontend_mr.get("use_coco"):
            coco_configs.append(("frontend", MRSourceConfig(**frontend_mr)))

        backend_mr = state.get("backend_mr_config")
        if isinstance(backend_mr, MRSourceConfig) and backend_mr.use_coco:
            coco_configs.append(("backend", backend_mr))
        elif isinstance(backend_mr, dict) and backend_mr.get("use_coco"):
            coco_configs.append(("backend", MRSourceConfig(**backend_mr)))

        if not coco_configs:
            logger.info("coco_consistency_validator: 无 Coco 端配置，pass-through")
            return {}

        if not coco_settings or not getattr(coco_settings, "coco_jwt_token", ""):
            raise RuntimeError("Coco 校验已启用，但 coco_settings / COCO_JWT_TOKEN 未配置")

        logger.info(
            "coco_consistency_validator: 开始校验 %d 个 checkpoint (Coco 端: %s)",
            len(checkpoints),
            [side for side, _ in coco_configs],
        )

        # ---- 构造 MR 上下文 ----
        mr_context = _build_mr_context(coco_configs)

        # ---- 多线程并行校验 ----
        semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)
        start_time = time.monotonic()
        effective_total_timeout_s = _resolve_total_timeout_s(len(checkpoints))

        task2_records: list[dict[str, Any]] = []

        async def _validate_single(cp: Any, index: int) -> tuple[int, CodeConsistencyResult]:
            """校验单个 checkpoint，带信号量和超时控制。"""
            async with semaphore:
                # 总超时检查
                elapsed = time.monotonic() - start_time
                if elapsed > effective_total_timeout_s:
                    logger.warning(
                        "coco_consistency_validator: 总超时 %.1fs > %.1fs，跳过 checkpoint #%d",
                        elapsed, effective_total_timeout_s, index,
                    )
                    return index, CodeConsistencyResult(status="unverified", verified_by="")

                try:
                    result, artifact_record = await asyncio.wait_for(
                        _validate_checkpoint_via_coco(
                            checkpoint=cp,
                            mr_context=mr_context,
                            coco_settings=coco_settings,
                            llm_client=llm_client,
                            artifact_context={
                                "run_output_dir": state.get("run_output_dir"),
                                "checkpoint_index": index,
                            },
                        ),
                        timeout=_PER_CASE_TIMEOUT_S,
                    )
                    task2_records.append(artifact_record)
                    return index, result
                except asyncio.TimeoutError:
                    cp_name = _get_cp_name(cp)
                    logger.warning(
                        "coco_consistency_validator: checkpoint '%s' 校验超时 (%ds)",
                        cp_name, _PER_CASE_TIMEOUT_S,
                    )
                    return index, CodeConsistencyResult(
                        status="unverified",
                        verified_by="",
                    )
                except Exception as exc:
                    cp_name = _get_cp_name(cp)
                    logger.error(
                        "coco_consistency_validator: checkpoint '%s' 校验异常: %s",
                        cp_name, exc,
                    )
                    return index, CodeConsistencyResult(
                        status="unverified",
                        verified_by="",
                    )

        # 并发执行
        tasks = {
            asyncio.create_task(_validate_single(cp, i)): i
            for i, cp in enumerate(checkpoints)
        }
        raw_results: list[Any] = []

        done, pending = await asyncio.wait(
            tasks.keys(),
            timeout=effective_total_timeout_s,
        )

        for task in done:
            try:
                raw_results.append(task.result())
            except Exception as exc:
                raw_results.append(exc)

        if pending:
            logger.error(
                "coco_consistency_validator: 全部校验总超时 (configured=%.1fs, effective=%.1fs, pending=%d)",
                _TOTAL_TIMEOUT_S,
                effective_total_timeout_s,
                len(pending),
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        # ---- 整理结果 ----
        results_map: dict[int, CodeConsistencyResult] = {}
        for item in raw_results:
            if isinstance(item, Exception):
                continue
            if isinstance(item, tuple) and len(item) == 2:
                idx, result = item
                results_map[idx] = result

        # ---- 标注到 checkpoint ----
        annotated = _annotate_checkpoints(checkpoints, results_map)

        # ---- 构建汇总 ----
        summary = _build_validation_summary(results_map, len(checkpoints))

        total_elapsed = time.monotonic() - start_time
        coco_artifacts = _persist_task2_artifacts(
            state=state,
            mr_context=mr_context,
            summary=summary,
            records=task2_records,
        )
        logger.info(
            "coco_consistency_validator 完成: "
            "total=%d, confirmed=%d, mismatch=%d, unverified=%d, elapsed=%.1fs",
            summary["total"],
            summary["confirmed"],
            summary["mismatch"],
            summary["unverified"],
            total_elapsed,
        )
        if summary["unverified"] > 0:
            logger.warning(
                "coco_consistency_validator: 存在未完成校验，继续后续流程: total=%d, unverified=%d",
                summary["total"],
                summary["unverified"],
            )

        return {
            "checkpoints": annotated,
            "coco_validation_summary": summary,
            "coco_artifacts": {
                **state.get("coco_artifacts", {}),
                **coco_artifacts,
            },
        }

    def coco_consistency_validator_node(state: dict[str, Any]) -> dict[str, Any]:
        """同步 LangGraph 节点入口，内部显式执行异步校验流程。"""
        return asyncio.run(_run_validation(state))

    return coco_consistency_validator_node


# ---------------------------------------------------------------------------
# 单 checkpoint Coco 校验
# ---------------------------------------------------------------------------


async def _validate_checkpoint_via_coco(
    checkpoint: Any,
    mr_context: dict[str, str],
    coco_settings: Any | None,
    llm_client: Any | None,
    artifact_context: dict[str, Any] | None = None,
) -> tuple[CodeConsistencyResult, dict[str, Any]]:
    """向 Coco 发送单个 checkpoint 的一致性校验请求。

    Args:
        checkpoint: Checkpoint 对象或字典。
        mr_context: MR 上下文 ``{"mr_url": ..., "git_url": ...}``。
        coco_settings: Coco 配置。
        llm_client: LLM 客户端。

    Returns:
        CodeConsistencyResult。
    """
    from app.services.coco_client import CocoClient

    if not coco_settings:
        return CodeConsistencyResult(status="unverified", verified_by="")

    client = CocoClient(coco_settings, llm_client=llm_client)

    try:
        result, artifacts = await client.run_validation_task(
            checkpoint=checkpoint,
            mr_context=mr_context,
        )
        record = {
            "checkpoint_id": _get_attr_safe(checkpoint, "checkpoint_id", ""),
            "checkpoint_title": _get_cp_name(checkpoint),
            "mr_context": mr_context,
            **artifacts,
        }
        run_output_dir = (artifact_context or {}).get("run_output_dir")
        checkpoint_index = (artifact_context or {}).get("checkpoint_index", 0)
        if run_output_dir:
            coco_dir = ensure_directory(Path(run_output_dir) / "coco")
            detail_path = write_json(
                coco_dir / f"task2_checkpoint_{checkpoint_index:03d}.json",
                record,
            )
            record["artifact_file"] = str(detail_path)
        return result, record
    except Exception as exc:
        cp_name = _get_cp_name(checkpoint)
        logger.warning("Coco Task 2 校验失败 [%s]: %s", cp_name, exc)
        record = {
            "checkpoint_id": _get_attr_safe(checkpoint, "checkpoint_id", ""),
            "checkpoint_title": cp_name,
            "mr_context": mr_context,
            "error_type": exc.__class__.__name__,
            "error_message": str(exc),
        }
        return CodeConsistencyResult(status="unverified", verified_by=""), record


# ---------------------------------------------------------------------------
# 标注逻辑
# ---------------------------------------------------------------------------


def _annotate_checkpoints(
    checkpoints: list[Any],
    results_map: dict[int, CodeConsistencyResult],
) -> list[Any]:
    """将校验结果标注到 checkpoint 上。

    对每个 checkpoint：
    - 设置 code_consistency 字段
    - 追加对应的 tags
    - mismatch + 高置信度时追加行内 TODO 文本
    """
    for idx, cp in enumerate(checkpoints):
        result = results_map.get(idx)
        if result is None:
            result = CodeConsistencyResult(status="unverified", verified_by="")

        # ---- 设置 code_consistency ----
        _set_attr_safe(cp, "code_consistency", result)

        # ---- 设置 tags ----
        existing_tags = _get_tags(cp)

        if result.status == "confirmed":
            if "code_confirmed" not in existing_tags:
                existing_tags.append("code_confirmed")

        elif result.status == "mismatch":
            if "code_mismatch" not in existing_tags:
                existing_tags.append("code_mismatch")
            if "consistency_todo" not in existing_tags:
                existing_tags.append("consistency_todo")

            # 高置信度时追加行内 TODO
            if result.confidence >= _CONFIDENCE_THRESHOLD:
                expected = _get_attr_safe(cp, "expected_result", "")
                cp_name = _get_cp_name(cp)
                todo_text = (
                    f"\n\n**TODO: 代码实现与预期不一致** — "
                    f"预期「{expected[:50]}」，"
                    f"但代码实现为「{result.actual_implementation[:80]}」"
                    f"（置信度 {result.confidence:.2f}）"
                )
                new_expected = (expected or "") + todo_text
                _set_attr_safe(cp, "expected_result", new_expected)
        elif result.status == "unverified":
            if "code_unverified" not in existing_tags:
                existing_tags.append("code_unverified")

        _set_attr_safe(cp, "tags", existing_tags)

    return checkpoints


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _build_mr_context(
    coco_configs: list[tuple[str, MRSourceConfig]],
) -> dict[str, str]:
    """从 Coco 端配置中构建 MR 上下文。

    优先使用 backend 端的配置，如果没有则使用 frontend 端。
    """
    mr_url = ""
    git_url = ""
    branch = ""
    for side, config in coco_configs:
        if config.mr_url:
            mr_url = mr_url or config.mr_url
        if config.codebase.git_url:
            git_url = git_url or config.codebase.git_url
        if config.codebase.branch:
            branch = branch or config.codebase.branch
    return {"mr_url": mr_url, "git_url": git_url, "branch": branch}


def _persist_task2_artifacts(
    state: dict[str, Any],
    mr_context: dict[str, str],
    summary: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, str]:
    """持久化 Task 2 汇总与原始返回。"""
    run_output_dir = state.get("run_output_dir")
    if not run_output_dir:
        return {}

    coco_dir = ensure_directory(Path(run_output_dir) / "coco")
    summary_payload = {
        "mr_context": mr_context,
        "summary": summary,
        "record_count": len(records),
    }
    summary_path = write_json(coco_dir / "task2_summary.json", summary_payload)
    results_path = write_json(coco_dir / "task2_results.json", records)
    return {
        "task2_summary": str(summary_path),
        "task2_results": str(results_path),
    }


def _build_validation_summary(
    results_map: dict[int, CodeConsistencyResult],
    total_checkpoints: int,
) -> dict[str, Any]:
    """构建校验汇总统计。"""
    confirmed = 0
    mismatch = 0
    unverified = 0

    for result in results_map.values():
        if result.status == "confirmed":
            confirmed += 1
        elif result.status == "mismatch":
            mismatch += 1
        else:
            unverified += 1

    # 未校验的 checkpoint 也计入 unverified
    not_covered = total_checkpoints - len(results_map)
    unverified += not_covered

    return {
        "total": total_checkpoints,
        "confirmed": confirmed,
        "mismatch": mismatch,
        "unverified": unverified,
    }


def _get_cp_name(cp: Any) -> str:
    """安全获取 checkpoint 名称。"""
    if isinstance(cp, dict):
        return cp.get("title", cp.get("name", "<unnamed>"))
    return getattr(cp, "title", getattr(cp, "name", "<unnamed>"))


def _get_tags(cp: Any) -> list[str]:
    """安全获取 checkpoint 的 tags 列表。"""
    if isinstance(cp, dict):
        tags = cp.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        cp["tags"] = tags
        return tags
    tags = getattr(cp, "tags", [])
    if not isinstance(tags, list):
        tags = []
        setattr(cp, "tags", tags)
    return tags


def _get_attr_safe(obj: Any, attr: str, default: Any = "") -> Any:
    """安全获取对象属性（兼容 dict 和对象）。"""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _set_attr_safe(obj: Any, attr: str, value: Any) -> None:
    """安全设置对象属性（兼容 dict 和对象）。"""
    if isinstance(obj, dict):
        obj[attr] = value
    else:
        try:
            setattr(obj, attr, value)
        except (AttributeError, TypeError, ValueError):
            logger.debug("无法设置属性 %s on %s", attr, type(obj).__name__)
