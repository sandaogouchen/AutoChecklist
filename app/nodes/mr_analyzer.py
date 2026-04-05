"""MR 分析核心节点。

在 case_generation 子图中位于 START 之后、scenario_planner 之前，
负责三个阶段的处理：
- 阶段 1：MR Diff 解析与变更摘要
- 阶段 2：Agentic Search（LLM Tool Calling + AST 分析）
- 阶段 3：代码级 Fact 提取 + PRD ↔ MR 一致性校验

支持前后端 MR 分离分析，以及 Coco Agent 委托路径。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable

from app.domain.mr_models import (
    CocoTaskStatus,
    ConsistencyIssue,
    MRAnalysisResult,
    MRCodeFact,
    MRSourceConfig,
    RelatedCodeSnippet,
)
from app.services.codebase_tools import CODEBASE_TOOLS, execute_tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_MAX_TOOL_ROUNDS = 10
"""Agentic search 最大 tool calling 轮数。"""

_SEARCH_TIMEOUT_S = 60
"""Agentic search 整体超时（秒）。"""

_MAX_RELATED_SNIPPETS = 30
"""最大关联代码片段数。"""

_MAX_SNIPPET_LINES = 100
"""单个代码片段最大行数。"""

_CONFIDENCE_THRESHOLD = 0.7
"""一致性校验置信度阈值，低于此值不生成 TODO。"""


# ---------------------------------------------------------------------------
# maybe_wrap 兼容
# ---------------------------------------------------------------------------

def _identity_wrap(name: str, func: Callable, timer: Any = None, idx: int = 0) -> Callable:
    """简易 maybe_wrap 占位：当 app.utils.timing 不可用时原样返回。"""
    return func


try:
    from app.utils.timing import maybe_wrap  # type: ignore[import-untyped]
except ImportError:
    maybe_wrap = _identity_wrap  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Prompt 模板
# ---------------------------------------------------------------------------

_PHASE1_SUMMARY_PROMPT = """\
你是一名资深 QA 工程师，请分析以下 MR diff 信息并生成变更摘要。

[MR 信息]
标题：{mr_title}
描述：{mr_description}

[变更文件列表]
{diff_summary}

请输出 JSON：
{{
  "mr_summary": "中文变更摘要（不超过 200 字）",
  "changed_modules": ["涉及的模块名列表"]
}}
"""

_PHASE2_SEARCH_SYSTEM = """\
你是一名代码分析 Agent。你的任务是根据 MR diff 中的变更，在 codebase 中搜索关联的代码上下文。
你可以使用以下工具进行搜索，每轮选择一个工具调用。当你认为已收集到足够的上下文时，回复 DONE。

可用工具：
{tools_desc}

搜索策略：
1. 从 MR diff 中提取变更的函数名、类名、import 路径
2. 通过 find_references 找到直接引用
3. 通过 get_file_content 获取关键代码的完整函数体
4. 最大搜索深度 2 跳，防止搜索爆炸

当前 MR 变更的关键符号：
{key_symbols}
"""

_PHASE3_EXTRACT_PROMPT = """\
你是一名资深 QA 工程师。请基于以下 MR diff 和关联代码上下文，完成两个任务。

任务 A — 代码级 Fact 提取：
从 MR 变更的代码逻辑中提取可测试的事实。重点关注：
- 新增逻辑分支、错误处理路径、状态变更、边界条件、降级逻辑

任务 B — PRD ↔ MR 一致性校验：
逐条对比 PRD 中描述的预期行为与代码中的实际实现。
置信度阈值：0.7，低于此值的不一致不输出。

[MR Diff]
{diff_content}

[关联代码上下文]
{related_context}

[PRD 预期逻辑]
{prd_facts}

请严格按以下 JSON 格式输出：
{{
  "code_facts": [
    {{
      "fact_id": "MR-FACT-001",
      "description": "代码级事实描述（中文）",
      "source_file": "文件路径",
      "code_snippet": "关键代码片段",
      "fact_type": "code_logic | error_handling | boundary | state_change | side_effect",
      "related_prd_fact_ids": []
    }}
  ],
  "consistency_issues": [
    {{
      "issue_id": "CONSIST-001",
      "severity": "critical | warning | info",
      "prd_expectation": "PRD 中的预期",
      "mr_implementation": "MR 中的实际实现",
      "discrepancy": "差异描述",
      "affected_file": "文件路径",
      "recommendation": "建议操作",
      "confidence": 0.85
    }}
  ]
}}
"""

_COCO_TASK1_PROMPT = """\
你是一名资深 QA 工程师，请分析以下 MR 的代码变更：

MR URL: {mr_url}

请完成以下任务：
1. 阅读 MR 的 diff 内容，提取所有变更的函数/类/模块
2. 在 codebase 中搜索与这些变更相关的上下文代码（caller、callee、类型定义等）
3. 从代码逻辑中提取可测试的事实（逻辑分支、边界条件、错误处理、状态变更）
4. 对比以下 PRD 预期逻辑与代码实现，识别不一致之处：

[PRD 预期逻辑]
{prd_summary}

请严格按以下 JSON 格式输出：
{{
  "mr_summary": "MR 变更摘要",
  "changed_modules": ["模块1", "模块2"],
  "code_facts": [{{"fact_id": "...", "description": "...", "source_file": "...", "fact_type": "..."}}],
  "consistency_issues": [{{"issue_id": "...", "severity": "...", "prd_expectation": "...", "mr_implementation": "...", "discrepancy": "...", "confidence": 0.0}}],
  "related_code_snippets": [{{"file_path": "...", "code_content": "...", "relation_type": "..."}}]
}}
"""


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------


def build_mr_analyzer_node(
    llm_client: Any,
    codebase_root: str | None = None,
    coco_settings: Any | None = None,
) -> Callable[..., dict[str, Any]]:
    """构建 MR 分析节点。

    Args:
        llm_client: LLM 客户端，用于 agentic search 和 fact 提取。
        codebase_root: 代码仓库根目录路径（用于本地文件搜索）。
            为 None 时跳过 agentic search，仅分析 diff 本身。
        coco_settings: Coco Agent 配置（CocoSettings 实例）。

    Returns:
        ``mr_analyzer_node(state: CaseGenState) -> dict`` 节点函数。
    """

    async def mr_analyzer_node(state: dict[str, Any]) -> dict[str, Any]:
        """MR 分析节点主逻辑。

        当 state 中无 MR 数据时直接 pass-through，不影响现有流程。
        支持前后端 MR 串行分析，以及 Coco 委托路径。
        """
        frontend_mr_config: MRSourceConfig | None = state.get("frontend_mr_config")
        backend_mr_config: MRSourceConfig | None = state.get("backend_mr_config")

        # 同时检查旧版 mr_input 字段做兼容
        mr_input = state.get("mr_input")
        has_any_mr = (
            (frontend_mr_config and frontend_mr_config.mr_url)
            or (backend_mr_config and backend_mr_config.mr_url)
            or (mr_input and getattr(mr_input, "diff_files", None))
        )

        if not has_any_mr:
            logger.info("mr_analyzer: 无 MR 数据，pass-through")
            return {}

        all_code_facts: list[MRCodeFact] = []
        all_consistency_issues: list[ConsistencyIssue] = []
        summaries: list[str] = []

        frontend_result: MRAnalysisResult | None = None
        backend_result: MRAnalysisResult | None = None

        # ---- 前端 MR 分析 ----
        if frontend_mr_config and frontend_mr_config.mr_url:
            logger.info("mr_analyzer: 开始分析前端 MR — %s", frontend_mr_config.mr_url)
            frontend_result = await _analyze_single_side(
                side="frontend",
                mr_config=frontend_mr_config,
                state=state,
                llm_client=llm_client,
                codebase_root=codebase_root,
                coco_settings=coco_settings,
                prefix="FE-",
            )
            if frontend_result:
                all_code_facts.extend(frontend_result.code_facts)
                all_consistency_issues.extend(frontend_result.consistency_issues)
                if frontend_result.mr_summary:
                    summaries.append(f"[前端] {frontend_result.mr_summary}")

        # ---- 后端 MR 分析 ----
        if backend_mr_config and backend_mr_config.mr_url:
            logger.info("mr_analyzer: 开始分析后端 MR — %s", backend_mr_config.mr_url)
            backend_result = await _analyze_single_side(
                side="backend",
                mr_config=backend_mr_config,
                state=state,
                llm_client=llm_client,
                codebase_root=codebase_root,
                coco_settings=coco_settings,
                prefix="BE-",
            )
            if backend_result:
                all_code_facts.extend(backend_result.code_facts)
                all_consistency_issues.extend(backend_result.consistency_issues)
                if backend_result.mr_summary:
                    summaries.append(f"[后端] {backend_result.mr_summary}")

        combined_summary = "\n".join(summaries) if summaries else ""

        result: dict[str, Any] = {
            "mr_code_facts": all_code_facts,
            "mr_consistency_issues": all_consistency_issues,
            "mr_combined_summary": combined_summary,
        }

        if frontend_result:
            result["frontend_mr_result"] = frontend_result
            result["mr_analysis_result"] = frontend_result
        if backend_result:
            result["backend_mr_result"] = backend_result
            if "mr_analysis_result" not in result:
                result["mr_analysis_result"] = backend_result

        logger.info(
            "mr_analyzer 完成: code_facts=%d, consistency_issues=%d",
            len(all_code_facts),
            len(all_consistency_issues),
        )
        return result

    return mr_analyzer_node


# ---------------------------------------------------------------------------
# 单端分析
# ---------------------------------------------------------------------------


async def _analyze_single_side(
    side: str,
    mr_config: MRSourceConfig,
    state: dict[str, Any],
    llm_client: Any,
    codebase_root: str | None,
    coco_settings: Any | None,
    prefix: str,
) -> MRAnalysisResult:
    """分析单端（前端/后端）的 MR。

    根据 ``use_coco`` 标志选择 Coco 委托路径或本地分析路径。
    """
    if mr_config.use_coco:
        return await _analyze_via_coco(
            mr_config=mr_config,
            state=state,
            llm_client=llm_client,
            coco_settings=coco_settings,
            prefix=prefix,
            side=side,
        )

    return await _analyze_locally(
        mr_config=mr_config,
        state=state,
        llm_client=llm_client,
        codebase_root=codebase_root or mr_config.codebase.local_path,
        prefix=prefix,
        side=side,
    )


# ---------------------------------------------------------------------------
# Coco 委托路径
# ---------------------------------------------------------------------------


async def _analyze_via_coco(
    mr_config: MRSourceConfig,
    state: dict[str, Any],
    llm_client: Any,
    coco_settings: Any | None,
    prefix: str,
    side: str,
) -> MRAnalysisResult:
    """通过 Coco Agent 进行代码分析（Task 1）。"""
    from app.services.coco_client import CocoClient, CocoTaskError

    if not coco_settings:
        logger.warning("Coco 委托路径: coco_settings 未配置，跳过 %s 端", side)
        return MRAnalysisResult(mr_summary=f"Coco 配置缺失，跳过{side}端分析")

    client = CocoClient(coco_settings, llm_client=llm_client)

    # 构造 PRD 摘要
    prd_summary = _build_prd_summary(state)

    prompt = _COCO_TASK1_PROMPT.format(
        mr_url=mr_config.mr_url,
        prd_summary=prd_summary[:3000],
    )

    start_time = time.monotonic()
    try:
        task_id = await client.send_task(
            prompt=prompt,
            mr_url=mr_config.mr_url,
            git_url=mr_config.codebase.git_url,
        )
        task = await client.poll_task(task_id)
        result = await client.extract_result(task)
        elapsed = time.monotonic() - start_time

        # 添加前缀
        result = _apply_prefix(result, prefix)

        result.coco_task_status = CocoTaskStatus(
            task_id=task_id,
            status="completed",
            elapsed_seconds=elapsed,
        )

        logger.info(
            "Coco Task 1 [%s] 完成: facts=%d, issues=%d, elapsed=%.1fs",
            side, len(result.code_facts), len(result.consistency_issues), elapsed,
        )
        return result

    except CocoTaskError as exc:
        elapsed = time.monotonic() - start_time
        logger.error("Coco Task 1 [%s] 失败: %s", side, exc)
        return MRAnalysisResult(
            mr_summary=f"Coco 分析失败: {exc}",
            search_trace=[f"coco_error: {exc}"],
            coco_task_status=CocoTaskStatus(
                task_id=getattr(exc, "task_id", ""),
                status="failed",
                elapsed_seconds=elapsed,
                error_message=str(exc),
            ),
        )
    except TimeoutError as exc:
        elapsed = time.monotonic() - start_time
        logger.error("Coco Task 1 [%s] 超时: %s", side, exc)
        return MRAnalysisResult(
            mr_summary=f"Coco 分析超时",
            search_trace=["coco_timeout"],
            coco_task_status=CocoTaskStatus(
                status="timeout",
                elapsed_seconds=elapsed,
                error_message=str(exc),
            ),
        )
    except Exception as exc:
        logger.error("Coco Task 1 [%s] 未知异常: %s", side, exc, exc_info=True)
        return MRAnalysisResult(
            mr_summary=f"Coco 分析异常: {exc}",
            search_trace=[f"coco_exception: {exc}"],
        )


# ---------------------------------------------------------------------------
# 本地分析路径
# ---------------------------------------------------------------------------


async def _analyze_locally(
    mr_config: MRSourceConfig,
    state: dict[str, Any],
    llm_client: Any,
    codebase_root: str,
    prefix: str,
    side: str,
) -> MRAnalysisResult:
    """本地 Agentic Search + LLM 分析路径。"""
    mr_input = state.get("mr_input")
    diff_files = getattr(mr_input, "diff_files", []) if mr_input else []

    # ---- 阶段 1：MR Diff 解析与摘要 ----
    diff_summary = _build_diff_summary(diff_files)
    mr_title = getattr(mr_input, "mr_title", "") if mr_input else ""
    mr_description = getattr(mr_input, "mr_description", "") if mr_input else ""

    summary_prompt = _PHASE1_SUMMARY_PROMPT.format(
        mr_title=mr_title,
        mr_description=mr_description,
        diff_summary=diff_summary[:4000],
    )

    try:
        summary_resp = await llm_client.chat(summary_prompt)
        summary_json = _safe_parse_json(summary_resp)
        mr_summary = summary_json.get("mr_summary", "")
        changed_modules = summary_json.get("changed_modules", [])
    except Exception as exc:
        logger.warning("阶段 1 摘要生成失败: %s", exc)
        mr_summary = f"MR 变更了 {len(diff_files)} 个文件"
        changed_modules = [df.file_path for df in diff_files[:10]] if diff_files else []

    # ---- 阶段 2：Agentic Search ----
    related_snippets: list[RelatedCodeSnippet] = []
    search_trace: list[str] = []

    if codebase_root:
        key_symbols = _extract_key_symbols(diff_files)
        related_snippets, search_trace = await _run_agentic_search(
            llm_client=llm_client,
            codebase_root=codebase_root,
            key_symbols=key_symbols,
        )
    else:
        search_trace.append("skipped: no codebase_root")
        logger.info("阶段 2: 无 codebase_root，跳过 agentic search")

    # ---- 阶段 3：Fact 提取 + 一致性校验 ----
    prd_facts = _build_prd_summary(state)
    diff_content = "\n".join(
        f"--- {df.file_path} ({df.change_type}) ---\n{df.diff_content[:2000]}"
        for df in (diff_files or [])
    )[:6000]

    related_context = "\n".join(
        f"--- {s.file_path} ({s.relation_type}) ---\n{s.code_content[:500]}"
        for s in related_snippets[:10]
    )[:4000]

    extract_prompt = _PHASE3_EXTRACT_PROMPT.format(
        diff_content=diff_content,
        related_context=related_context,
        prd_facts=prd_facts[:3000],
    )

    code_facts: list[MRCodeFact] = []
    consistency_issues: list[ConsistencyIssue] = []

    try:
        extract_resp = await llm_client.chat(extract_prompt)
        extract_json = _safe_parse_json(extract_resp)

        for i, f in enumerate(extract_json.get("code_facts", [])):
            code_facts.append(MRCodeFact(
                fact_id=f"{prefix}MR-FACT-{i + 1:03d}",
                description=f.get("description", ""),
                source_file=f.get("source_file", ""),
                code_snippet=f.get("code_snippet", ""),
                fact_type=f.get("fact_type", "code_logic"),
                related_prd_fact_ids=f.get("related_prd_fact_ids", []),
            ))

        for i, ci in enumerate(extract_json.get("consistency_issues", [])):
            confidence = float(ci.get("confidence", 0))
            if confidence < 0.5:
                continue
            consistency_issues.append(ConsistencyIssue(
                issue_id=f"{prefix}CONSIST-{i + 1:03d}",
                severity=ci.get("severity", "warning"),
                prd_expectation=ci.get("prd_expectation", ""),
                mr_implementation=ci.get("mr_implementation", ""),
                discrepancy=ci.get("discrepancy", ""),
                affected_file=ci.get("affected_file", ""),
                recommendation=ci.get("recommendation", ""),
                confidence=confidence,
            ))

    except Exception as exc:
        logger.error("阶段 3 提取失败: %s", exc, exc_info=True)

    result = MRAnalysisResult(
        mr_summary=mr_summary,
        changed_modules=changed_modules,
        related_code_snippets=related_snippets,
        code_facts=code_facts,
        consistency_issues=consistency_issues,
        search_trace=search_trace,
    )

    logger.info(
        "本地分析 [%s] 完成: facts=%d, issues=%d, snippets=%d",
        side, len(code_facts), len(consistency_issues), len(related_snippets),
    )
    return result


# ---------------------------------------------------------------------------
# Agentic Search 循环
# ---------------------------------------------------------------------------


async def _run_agentic_search(
    llm_client: Any,
    codebase_root: str,
    key_symbols: list[str],
) -> tuple[list[RelatedCodeSnippet], list[str]]:
    """执行 LLM 驱动的 agentic search 循环。

    最大 10 轮 tool calling，整体超时 60 秒。

    Returns:
        ``(related_snippets, search_trace)``。
    """
    snippets: list[RelatedCodeSnippet] = []
    trace: list[str] = []
    start = time.monotonic()

    tools_desc = json.dumps(
        [{"name": t["name"], "description": t["description"]} for t in CODEBASE_TOOLS],
        ensure_ascii=False,
    )

    system_msg = _PHASE2_SEARCH_SYSTEM.format(
        tools_desc=tools_desc,
        key_symbols=", ".join(key_symbols[:20]),
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": system_msg}]
    messages.append({
        "role": "user",
        "content": (
            f"请开始搜索与以下符号相关的代码上下文：{', '.join(key_symbols[:10])}\n"
            "每轮选择一个工具调用，以 JSON 格式输出 tool_call：\n"
            '{"tool": "<tool_name>", "arguments": {...}}\n'
            "当你认为已收集到足够上下文时回复 DONE。"
        ),
    })

    for round_idx in range(_MAX_TOOL_ROUNDS):
        elapsed = time.monotonic() - start
        if elapsed > _SEARCH_TIMEOUT_S:
            trace.append(f"round {round_idx}: timeout ({elapsed:.1f}s)")
            logger.info("Agentic search 超时 (%.1fs)，使用已收集结果", elapsed)
            break

        if len(snippets) >= _MAX_RELATED_SNIPPETS:
            trace.append(f"round {round_idx}: max snippets reached")
            break

        try:
            resp = await llm_client.chat(
                messages[-1]["content"] if len(messages) <= 2 else json.dumps(messages, ensure_ascii=False)[:8000],
            )
        except Exception as exc:
            trace.append(f"round {round_idx}: llm error — {exc}")
            logger.warning("Agentic search LLM 调用失败 (round %d): %s", round_idx, exc)
            break

        # 检查是否结束
        if "DONE" in resp.upper():
            trace.append(f"round {round_idx}: LLM 返回 DONE")
            break

        # 尝试解析 tool call
        tool_call = _parse_tool_call(resp)
        if not tool_call:
            trace.append(f"round {round_idx}: 无法解析 tool call")
            break

        tool_name = tool_call.get("tool", "")
        arguments = tool_call.get("arguments", {})
        trace.append(f"round {round_idx}: {tool_name}({json.dumps(arguments, ensure_ascii=False)[:100]})")

        # 执行工具
        tool_result = execute_tool(tool_name, arguments, codebase_root)

        # 从结果中提取 snippet
        _collect_snippets(tool_name, tool_result, snippets)

        # 将结果反馈给 LLM
        messages.append({"role": "assistant", "content": resp})
        messages.append({
            "role": "user",
            "content": f"工具 {tool_name} 返回结果：\n{json.dumps(tool_result, ensure_ascii=False)[:3000]}\n\n请继续搜索或回复 DONE。",
        })

    logger.info("Agentic search 完成: %d 轮, %d 片段", len(trace), len(snippets))
    return snippets, trace


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _build_diff_summary(diff_files: list[Any]) -> str:
    """构建 diff 文件摘要文本。"""
    lines: list[str] = []
    for df in diff_files[:20]:
        fp = getattr(df, "file_path", str(df))
        ct = getattr(df, "change_type", "modified")
        adds = getattr(df, "additions", 0)
        dels = getattr(df, "deletions", 0)
        lines.append(f"- {fp} ({ct}, +{adds}/-{dels})")
    return "\n".join(lines)


def _build_prd_summary(state: dict[str, Any]) -> str:
    """从 state 中构建 PRD 事实摘要。"""
    parts: list[str] = []

    # 尝试从 research_output 获取
    research = state.get("research_output") or state.get("parsed_document")
    if research:
        if isinstance(research, str):
            parts.append(research[:2000])
        elif isinstance(research, dict):
            facts = research.get("facts", research.get("research_facts", []))
            for f in facts[:15]:
                if isinstance(f, str):
                    parts.append(f"- {f}")
                elif isinstance(f, dict):
                    parts.append(f"- {f.get('description', f.get('content', ''))}")

    return "\n".join(parts) if parts else "（无 PRD 信息）"


def _extract_key_symbols(diff_files: list[Any]) -> list[str]:
    """从 diff 文件中提取关键符号（函数名、类名等）。"""
    import re
    symbols: list[str] = []
    seen: set[str] = set()

    for df in (diff_files or []):
        content = getattr(df, "diff_content", "")
        # 匹配 Python def / class
        for m in re.finditer(r"^\+\s*(?:async\s+)?def\s+(\w+)", content, re.MULTILINE):
            sym = m.group(1)
            if sym not in seen and not sym.startswith("_"):
                seen.add(sym)
                symbols.append(sym)
        for m in re.finditer(r"^\+\s*class\s+(\w+)", content, re.MULTILINE):
            sym = m.group(1)
            if sym not in seen:
                seen.add(sym)
                symbols.append(sym)
        # 匹配 JS/TS function / export
        for m in re.finditer(r"^\+\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)", content, re.MULTILINE):
            sym = m.group(1)
            if sym not in seen:
                seen.add(sym)
                symbols.append(sym)

    return symbols[:30]


def _parse_tool_call(text: str) -> dict[str, Any] | None:
    """从 LLM 回复中解析 tool call JSON。"""
    import re
    # 尝试匹配 {"tool": ..., "arguments": ...}
    m = re.search(r'\{[^{}]*"tool"\s*:\s*"[^"]+?"[^{}]*"arguments"\s*:\s*\{[^{}]*\}[^{}]*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # 宽松匹配
    m = re.search(r'(\{[\s\S]*\})', text)
    if m:
        try:
            parsed = json.loads(m.group(1))
            if "tool" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

    return None


def _collect_snippets(
    tool_name: str,
    tool_result: dict[str, Any],
    snippets: list[RelatedCodeSnippet],
) -> None:
    """从工具结果中收集 RelatedCodeSnippet。"""
    if tool_name == "get_file_content":
        content = tool_result.get("content", "")
        if content:
            snippets.append(RelatedCodeSnippet(
                file_path=tool_result.get("file_path", ""),
                start_line=tool_result.get("start_line", 0),
                end_line=tool_result.get("end_line", 0),
                code_content=content[:3000],
                relation_type="file_content",
            ))
    elif tool_name in ("grep_codebase", "find_references"):
        matches = tool_result.get("matches", tool_result.get("references", []))
        for m in matches[:5]:
            snippets.append(RelatedCodeSnippet(
                file_path=m.get("file", ""),
                start_line=m.get("line", 0),
                code_content=m.get("content", ""),
                relation_type=m.get("ref_type", "grep_match"),
            ))


def _safe_parse_json(text: str) -> dict[str, Any]:
    """安全解析 JSON（兼容 markdown 代码块）。"""
    from app.services.coco_response_validator import CocoResponseValidator
    result = CocoResponseValidator._extract_json(text)
    return result if result else {}


def _apply_prefix(result: MRAnalysisResult, prefix: str) -> MRAnalysisResult:
    """为 MRAnalysisResult 中的 ID 添加前缀。"""
    for i, f in enumerate(result.code_facts):
        if not f.fact_id.startswith(prefix):
            f.fact_id = f"{prefix}MR-FACT-{i + 1:03d}"
    for i, ci in enumerate(result.consistency_issues):
        if not ci.issue_id.startswith(prefix):
            ci.issue_id = f"{prefix}CONSIST-{i + 1:03d}"
    return result
