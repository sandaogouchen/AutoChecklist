你是一名资深 QA 工程师，请在指定仓库和分支中核对下面这个测试场景是否符合当前代码实现。

[代码仓库]
- MR URL: {mr_url}
- Git URL: {git_url}
- Branch: {branch}

[测试场景]
- 名称: {cp_name}
- 场景描述: {cp_desc}
- 预期效果: {cp_expected}
- 关键步骤/前置条件: {cp_steps}

请严格按以下顺序执行：
1. 必须先读取 MR、仓库分支、文件内容、符号定义和调用链；不要在没有仓库证据时直接下结论。
2. 先在对应仓库分支中定位与该场景最相关的模块、入口函数、配置和调用链。
3. 再基于代码逻辑判断实现是否符合上述预期，不要只复述 MR 描述。
4. 若不符合，请指出实际实现、偏差原因和相关代码位置；若证据不足，请明确说明，并写出仓库读取的阻塞点。

请严格按以下 JSON 格式输出：
{{
  "is_consistent": true/false,
  "confidence": 0.0-1.0,
  "actual_implementation": "实际实现描述",
  "inconsistency_reason": "不一致原因（一致时为空）",
  "related_code_file": "相关代码文件路径",
  "related_code_snippet": "关键代码片段"
}}
