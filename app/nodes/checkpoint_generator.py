from app.models.state import WorkflowState
from langchain_core.runnables import RunnableConfig
from app.models.models import Checkpoint
import json
import re


def clean_json_string(text: str) -> str:
    """清理可能包含的 markdown 代码块标记"""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
    if text.endswith("```"):
        text = text[: -len("```")]
    return text.strip()


def parse_checkpoints(text: str) -> list[Checkpoint]:
    """解析LLM输出的检查点JSON"""
    cleaned = clean_json_string(text)

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and "checkpoints" in data:
            items = data["checkpoints"]
        elif isinstance(data, list):
            items = data
        else:
            raise ValueError("Unexpected JSON structure")
    except json.JSONDecodeError:
        json_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if json_match:
            items = json.loads(json_match.group())
        else:
            raise ValueError("Could not find valid JSON array in response")

    checkpoints = []
    for item in items:
        checkpoint = Checkpoint(
            id=item.get("id", ""),
            requirement=item.get("requirement", ""),
            description=item.get("description", ""),
            check_method=item.get("check_method", ""),
            expected_result=item.get("expected_result", ""),
            priority=item.get("priority", "medium"),
        )
        checkpoints.append(checkpoint)

    return checkpoints


def _get_xmind_reference_section(state: dict) -> str:
    """Extract XMind reference section for prompt injection.

    If the state contains an ``xmind_reference_summary``, return a
    formatted prompt section that guides the LLM to align checkpoint
    coverage dimensions with the reference structure.

    Returns an empty string when no reference is available.
    """
    xmind_ref = state.get("xmind_reference_summary")
    if not xmind_ref:
        return ""

    # Support both Pydantic model and plain dict representations
    if hasattr(xmind_ref, "formatted_summary"):
        formatted = xmind_ref.formatted_summary
    elif isinstance(xmind_ref, dict):
        formatted = xmind_ref.get("formatted_summary", "")
    else:
        formatted = ""

    if not formatted:
        return ""

    return (
        "\n\n## 参考 Checklist 结构\n"
        f"{formatted}\n"
        "请参考上述已有 Checklist 的覆盖维度和组织方式来生成检查点，"
        "确保生成的检查点在结构和命名风格上与参考保持一致。\n"
    )


async def generate_checkpoints(
    state: WorkflowState, config: RunnableConfig
) -> WorkflowState:
    """生成检查点的节点函数"""
    from app.models.models import get_model

    # 获取分析结果
    analysis = state.get("analysis_result", "")
    requirement = state.get("requirement", "")
    prd_content = state.get("prd_content", "")

    # 获取 XMind 参考注入段落
    xmind_section = _get_xmind_reference_section(state)

    # 构建提示词
    prompt = f"""基于以下需求分析结果，生成详细的测试检查点列表。

## 原始需求
{requirement}

## PRD文档内容
{prd_content}

## 需求分析结果
{analysis}
{xmind_section}
请生成一个JSON格式的检查点列表，每个检查点包含以下字段：
- id: 检查点编号（如 CP001, CP002）
- requirement: 对应的需求描述
- description: 检查点详细描述
- check_method: 检查方法
- expected_result: 预期结果
- priority: 优先级（high/medium/low）

请确保：
1. 覆盖所有功能需求
2. 包含边界条件测试
3. 包含异常场景测试
4. 检查点描述清晰明确
5. 每个检查点可独立验证

请直接返回JSON数组，格式如下：
```json
[
    {{
        "id": "CP001",
        "requirement": "需求描述",
        "description": "检查点描述",
        "check_method": "检查方法",
        "expected_result": "预期结果",
        "priority": "high"
    }}
]
```"""

    # 调用LLM
    model = get_model(config)
    response = await model.ainvoke(prompt)
    response_text = response.content if hasattr(response, "content") else str(response)

    # 解析检查点
    checkpoints = parse_checkpoints(response_text)

    return {
        **state,
        "checkpoints": [cp.model_dump() for cp in checkpoints],
        "checkpoint_count": len(checkpoints),
    }
