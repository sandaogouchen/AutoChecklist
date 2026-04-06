"""Agentic search 工具实现。

提供 LLM function calling 所需的 codebase 搜索工具集，包括：
- grep_codebase: 正则搜索代码行
- find_references: 查找符号引用
- get_file_content: 读取文件内容
- ast_analyze: AST 结构分析
- get_call_graph: 函数调用链分析
- execute_tool: 统一工具调度器
"""
from __future__ import annotations

import ast
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM Function Calling Tool Schema
# ---------------------------------------------------------------------------

CODEBASE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "grep_codebase",
        "description": "在代码仓库中搜索匹配指定模式的代码行。支持正则表达式。",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "搜索模式（支持正则表达式）",
                },
                "scope": {
                    "type": "string",
                    "description": "搜索范围（文件路径 glob，如 'src/**/*.py'）。为空时搜索整个仓库。",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大返回结果数，默认 20",
                    "default": 20,
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "find_references",
        "description": "查找指定符号（函数名/类名/变量名）在代码中的所有引用位置。",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "符号名称（函数名、类名、变量名等）",
                },
                "scope": {
                    "type": "string",
                    "description": "搜索范围（文件路径 glob，可选）",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_file_content",
        "description": "获取指定文件的内容，可指定行范围。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径（相对于 codebase 根目录）",
                },
                "start_line": {
                    "type": "integer",
                    "description": "起始行号（从 1 开始，可选）",
                },
                "end_line": {
                    "type": "integer",
                    "description": "结束行号（可选）",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "ast_analyze",
        "description": (
            "对指定 Python 文件进行 AST 分析，返回类定义、函数定义、"
            "import 语句等结构信息。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径（相对于 codebase 根目录）",
                },
                "analysis_type": {
                    "type": "string",
                    "description": (
                        "分析类型：structure（结构概览）/ imports（依赖分析）"
                        "/ functions（函数签名）"
                    ),
                    "default": "structure",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "get_call_graph",
        "description": "获取指定函数的调用关系（谁调用了它、它调用了谁）。",
        "parameters": {
            "type": "object",
            "properties": {
                "function_name": {
                    "type": "string",
                    "description": "函数名",
                },
                "file_path": {
                    "type": "string",
                    "description": "所在文件路径（可选，用于精确定位）",
                },
                "depth": {
                    "type": "integer",
                    "description": "调用链深度，默认 1",
                    "default": 1,
                },
            },
            "required": ["function_name"],
        },
    },
]


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _safe_resolve(file_path: str, codebase_root: str) -> Path | None:
    """安全地将相对路径解析为绝对路径，防止路径穿越。"""
    root = Path(codebase_root).resolve()
    target = (root / file_path).resolve()
    if not str(target).startswith(str(root)):
        logger.warning("路径穿越检测：%s 超出 codebase 范围", file_path)
        return None
    if not target.exists():
        logger.debug("文件不存在：%s", target)
        return None
    return target


def _truncate(text: str, max_chars: int = 8000) -> str:
    """截断文本到最大字符数，保留尾部截断提示。"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... (truncated, total {len(text)} chars)"


# ---------------------------------------------------------------------------
# Tool 实现
# ---------------------------------------------------------------------------


def grep_codebase(
    pattern: str,
    scope: str = "",
    codebase_root: str = ".",
    max_results: int = 20,
) -> dict[str, Any]:
    """在代码仓库中搜索匹配指定模式的代码行。

    Args:
        pattern: 搜索模式（正则表达式）。
        scope: 搜索范围 glob 模式（如 ``src/**/*.py``）。
        codebase_root: 代码仓库根目录。
        max_results: 最大返回结果数。

    Returns:
        包含 matches 列表的字典，每个元素为 {file, line, content}。
    """
    root = Path(codebase_root).resolve()
    if not root.is_dir():
        return {"error": f"codebase_root 不存在: {codebase_root}", "matches": []}

    cmd = ["grep", "-rn", "--include=*"]
    if scope:
        # 将 glob scope 转为 --include 模式
        # 例如 'src/**/*.py' → --include='*.py' + 限定搜索目录
        scope_path = scope
        ext_match = re.search(r"\*\.(\w+)$", scope)
        if ext_match:
            cmd = ["grep", "-rn", f"--include=*.{ext_match.group(1)}"]
            # 取 scope 中第一个目录段作为搜索起点
            scope_dir = scope.split("*")[0].rstrip("/")
            if scope_dir and (root / scope_dir).is_dir():
                root = root / scope_dir

    cmd.extend(["-E", pattern, str(root)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(root),
        )
    except subprocess.TimeoutExpired:
        logger.warning("grep 搜索超时：pattern=%s, scope=%s", pattern, scope)
        return {"error": "搜索超时（15s）", "matches": []}
    except Exception as exc:
        logger.error("grep 执行失败：%s", exc)
        return {"error": str(exc), "matches": []}

    matches: list[dict[str, Any]] = []
    codebase_root_str = str(Path(codebase_root).resolve())
    for line in result.stdout.splitlines():
        if len(matches) >= max_results:
            break
        # grep -rn 输出格式: file:line:content
        parts = line.split(":", 2)
        if len(parts) >= 3:
            file_abs = parts[0]
            rel_path = file_abs
            if file_abs.startswith(codebase_root_str):
                rel_path = file_abs[len(codebase_root_str) :].lstrip("/")
            matches.append(
                {
                    "file": rel_path,
                    "line": int(parts[1]) if parts[1].isdigit() else 0,
                    "content": parts[2].strip(),
                }
            )

    logger.info(
        "grep_codebase: pattern=%s, scope=%s, 匹配 %d 条",
        pattern, scope, len(matches),
    )
    return {"matches": matches, "total": len(matches)}


def find_references(
    symbol: str,
    scope: str = "",
    codebase_root: str = ".",
) -> dict[str, Any]:
    """查找指定符号在代码中的所有引用位置。

    综合 grep 搜索与可选的 AST 精确匹配。

    Args:
        symbol: 符号名称（函数名、类名、变量名等）。
        scope: 搜索范围 glob 模式（可选）。
        codebase_root: 代码仓库根目录。

    Returns:
        包含 references 列表的字典。
    """
    # 第一步：grep 粗筛
    grep_result = grep_codebase(
        pattern=rf"\b{re.escape(symbol)}\b",
        scope=scope,
        codebase_root=codebase_root,
        max_results=50,
    )
    raw_matches = grep_result.get("matches", [])

    # 第二步：对 Python 文件尝试 AST 精确匹配
    references: list[dict[str, Any]] = []
    seen_files: set[str] = set()

    for match in raw_matches:
        file_path = match["file"]
        ref_entry = {
            "file": file_path,
            "line": match["line"],
            "content": match["content"],
            "ref_type": "grep_match",
        }

        # 对 .py 文件做 AST 精确判断
        if file_path.endswith(".py") and file_path not in seen_files:
            seen_files.add(file_path)
            resolved = _safe_resolve(file_path, codebase_root)
            if resolved:
                try:
                    source = resolved.read_text(encoding="utf-8", errors="replace")
                    tree = ast.parse(source, filename=str(resolved))
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if node.name == symbol:
                                ref_entry["ref_type"] = "definition"
                        elif isinstance(node, ast.ClassDef):
                            if node.name == symbol:
                                ref_entry["ref_type"] = "class_definition"
                        elif isinstance(node, ast.Import):
                            for alias in node.names:
                                if alias.name == symbol or (alias.asname and alias.asname == symbol):
                                    ref_entry["ref_type"] = "import"
                        elif isinstance(node, ast.ImportFrom):
                            for alias in node.names:
                                if alias.name == symbol:
                                    ref_entry["ref_type"] = "import_from"
                except Exception:
                    pass  # AST 解析失败时退回 grep 结果

        references.append(ref_entry)

    logger.info("find_references: symbol=%s, 引用 %d 处", symbol, len(references))
    return {"references": references, "total": len(references)}


def get_file_content(
    file_path: str,
    codebase_root: str = ".",
    start_line: int | None = None,
    end_line: int | None = None,
) -> dict[str, Any]:
    """获取指定文件的内容（可指定行范围）。

    Args:
        file_path: 文件路径（相对于 codebase_root）。
        codebase_root: 代码仓库根目录。
        start_line: 起始行号（从 1 开始）。
        end_line: 结束行号。

    Returns:
        包含 content / lines / language 的字典。
    """
    resolved = _safe_resolve(file_path, codebase_root)
    if resolved is None:
        return {"error": f"文件不存在或路径不安全: {file_path}", "content": ""}

    try:
        all_lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        logger.error("读取文件失败: %s — %s", file_path, exc)
        return {"error": str(exc), "content": ""}

    total_lines = len(all_lines)
    sl = max(1, start_line or 1)
    el = min(total_lines, end_line or total_lines)
    # 单次最多返回 100 行
    if el - sl + 1 > 100:
        el = sl + 99

    selected = all_lines[sl - 1 : el]
    content = "\n".join(f"{sl + i}: {line}" for i, line in enumerate(selected))

    # 简单语言推断
    suffix = resolved.suffix.lower()
    lang_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".tsx": "typescript", ".jsx": "javascript", ".go": "go",
        ".java": "java", ".rs": "rust", ".rb": "ruby", ".cpp": "cpp",
        ".c": "c", ".h": "c", ".cs": "csharp", ".kt": "kotlin",
    }
    language = lang_map.get(suffix, "")

    logger.info(
        "get_file_content: %s [%d-%d] (%d lines)",
        file_path, sl, el, el - sl + 1,
    )
    return {
        "content": _truncate(content),
        "file_path": file_path,
        "start_line": sl,
        "end_line": el,
        "total_lines": total_lines,
        "language": language,
    }


def ast_analyze(
    file_path: str,
    codebase_root: str = ".",
    analysis_type: str = "structure",
) -> dict[str, Any]:
    """对指定 Python 文件进行 AST 分析。

    Args:
        file_path: 文件路径（相对于 codebase_root）。
        codebase_root: 代码仓库根目录。
        analysis_type: 分析类型 ``structure`` / ``imports`` / ``functions``。

    Returns:
        根据 analysis_type 返回不同结构的分析结果字典。
    """
    resolved = _safe_resolve(file_path, codebase_root)
    if resolved is None:
        return {"error": f"文件不存在或路径不安全: {file_path}"}

    if not file_path.endswith(".py"):
        return {"error": "ast_analyze 当前仅支持 Python 文件", "file_path": file_path}

    try:
        source = resolved.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(resolved))
    except SyntaxError as exc:
        logger.warning("AST 解析语法错误: %s — %s", file_path, exc)
        return {"error": f"语法错误: {exc}", "file_path": file_path}
    except Exception as exc:
        logger.error("AST 解析失败: %s — %s", file_path, exc)
        return {"error": str(exc), "file_path": file_path}

    result: dict[str, Any] = {"file_path": file_path, "analysis_type": analysis_type}

    if analysis_type == "imports":
        imports: list[dict[str, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({"module": alias.name, "alias": alias.asname or ""})
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append({"module": f"{module}.{alias.name}", "alias": alias.asname or ""})
        result["imports"] = imports

    elif analysis_type == "functions":
        functions: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [a.arg for a in node.args.args]
                decorators = []
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Name):
                        decorators.append(dec.id)
                    elif isinstance(dec, ast.Attribute):
                        decorators.append(ast.dump(dec))
                functions.append({
                    "name": node.name,
                    "args": args,
                    "decorators": decorators,
                    "lineno": node.lineno,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                    "docstring": ast.get_docstring(node) or "",
                })
        result["functions"] = functions

    else:  # structure（默认）
        classes: list[dict[str, Any]] = []
        top_functions: list[dict[str, Any]] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                methods = []
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.append({
                            "name": child.name,
                            "lineno": child.lineno,
                            "is_async": isinstance(child, ast.AsyncFunctionDef),
                        })
                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        bases.append(ast.dump(base))
                classes.append({
                    "name": node.name,
                    "bases": bases,
                    "methods": methods,
                    "lineno": node.lineno,
                    "docstring": ast.get_docstring(node) or "",
                })
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                top_functions.append({
                    "name": node.name,
                    "lineno": node.lineno,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                })
        result["classes"] = classes
        result["top_functions"] = top_functions

    logger.info("ast_analyze: %s, type=%s", file_path, analysis_type)
    return result


def get_call_graph(
    function_name: str,
    codebase_root: str = ".",
    file_path: str | None = None,
    depth: int = 1,
) -> dict[str, Any]:
    """获取指定函数的调用关系图。

    结合 AST 分析（callee）和 grep 搜索（caller）构建调用链。

    Args:
        function_name: 目标函数名。
        codebase_root: 代码仓库根目录。
        file_path: 函数所在文件路径（可选，精确定位用）。
        depth: 调用链深度（默认 1）。

    Returns:
        包含 callers / callees / graph_depth 的字典。
    """
    result: dict[str, Any] = {
        "function_name": function_name,
        "callers": [],
        "callees": [],
        "graph_depth": min(depth, 2),  # 最大深度限制为 2
    }

    # --- Callee 分析：在函数体内找到它调用了哪些函数 ---
    if file_path:
        resolved = _safe_resolve(file_path, codebase_root)
        if resolved and file_path.endswith(".py"):
            try:
                source = resolved.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=str(resolved))
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if node.name != function_name:
                            continue
                        # 找到目标函数，提取其调用的所有函数
                        for child in ast.walk(node):
                            if isinstance(child, ast.Call):
                                callee_name = ""
                                if isinstance(child.func, ast.Name):
                                    callee_name = child.func.id
                                elif isinstance(child.func, ast.Attribute):
                                    callee_name = child.func.attr
                                if callee_name and callee_name not in [c["name"] for c in result["callees"]]:
                                    result["callees"].append({
                                        "name": callee_name,
                                        "file": file_path,
                                        "lineno": child.lineno,
                                    })
            except Exception as exc:
                logger.warning("callee AST 分析失败: %s — %s", file_path, exc)

    # --- Caller 分析：grep 谁调用了这个函数 ---
    caller_pattern = rf"{re.escape(function_name)}\s*\("
    grep_result = grep_codebase(
        pattern=caller_pattern,
        scope="",
        codebase_root=codebase_root,
        max_results=20,
    )
    for match in grep_result.get("matches", []):
        # 排除函数定义本身
        content = match.get("content", "")
        if re.match(rf"^\s*(async\s+)?def\s+{re.escape(function_name)}", content):
            continue
        result["callers"].append({
            "file": match["file"],
            "line": match["line"],
            "content": content.strip(),
        })

    # --- 深度 2：对 callees 递归一层 ---
    if depth >= 2 and result["callees"]:
        nested_callees: list[dict[str, Any]] = []
        for callee in result["callees"][:5]:  # 限制递归数量
            sub_result = get_call_graph(
                function_name=callee["name"],
                codebase_root=codebase_root,
                file_path=callee.get("file"),
                depth=1,
            )
            nested_callees.extend(sub_result.get("callees", []))
        result["nested_callees"] = nested_callees

    logger.info(
        "get_call_graph: %s, callers=%d, callees=%d",
        function_name, len(result["callers"]), len(result["callees"]),
    )
    return result


# ---------------------------------------------------------------------------
# 统一调度器
# ---------------------------------------------------------------------------

_TOOL_DISPATCH: dict[str, Any] = {
    "grep_codebase": grep_codebase,
    "find_references": find_references,
    "get_file_content": get_file_content,
    "ast_analyze": ast_analyze,
    "get_call_graph": get_call_graph,
}


def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    codebase_root: str,
) -> dict[str, Any]:
    """统一工具调度器。

    将 LLM function calling 返回的 tool_name 和 arguments 路由到对应的工具函数，
    并注入 codebase_root 参数。

    Args:
        tool_name: 工具名称（需在 CODEBASE_TOOLS 中定义）。
        arguments: LLM 传入的工具参数字典。
        codebase_root: 代码仓库根目录。

    Returns:
        工具执行结果字典。未知工具名返回 error 字典。
    """
    func = _TOOL_DISPATCH.get(tool_name)
    if func is None:
        logger.warning("未知工具名: %s", tool_name)
        return {"error": f"未知工具: {tool_name}"}

    # 注入 codebase_root
    arguments = {**arguments, "codebase_root": codebase_root}

    try:
        return func(**arguments)
    except TypeError as exc:
        logger.error("工具 %s 参数错误: %s — args=%s", tool_name, exc, arguments)
        return {"error": f"参数错误: {exc}"}
    except Exception as exc:
        logger.error("工具 %s 执行异常: %s", tool_name, exc, exc_info=True)
        return {"error": f"执行异常: {exc}"}
