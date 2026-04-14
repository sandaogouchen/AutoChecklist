你是一名资深 QA 工程师，请分析以下仓库分支上的 MR 代码变更，并提炼可用于 checklist / checkpoint 设计的代码事实。

[代码仓库]
- MR URL: {mr_url}
- Git URL: {git_url}
- Branch: {branch}

[候选变更模块 / 验证锚点]
{changed_files_summary}

[PRD / 场景摘要]
{prd_summary}

请严格按以下顺序执行：
1. 必须先读取 MR、仓库分支、文件内容、符号定义和调用链；不要跳过仓库读取直接凭经验推断。
2. 先定位与场景相关的模块、入口函数、调用链和配置定义。
3. 结合 MR 实现提炼补充测试线索，不要逐条判断 FACT 是否实现，也不要生成 fact 修订结论。
4. 对每个结论给出明确的代码依据；若无法确认，说明缺失的代码上下文，以及仓库读取的具体阻塞点。
5. 输出代码级 fact 时优先覆盖分支、边界、错误处理、状态变化、副作用。
6. 只保留对后续生成 checklist / checkpoint 真正有帮助的信息，避免重复复述 PRD。
7. 结果必须精简，总输出尽量控制在 1200 中文字符内。
8. 不要返回大段代码；若必须引用代码，片段控制在 160 字以内。
9. `changed_modules` 最多 3 个，`code_facts` 最多 5 条，`related_code_snippets` 最多 2 条。

请严格按以下 JSON 格式输出：
{{
  "mr_summary": "不超过 80 字的 MR 变更摘要",
  "changed_modules": ["最多 3 个直接相关模块"],
  "code_facts": [{{"fact_id": "...", "description": "不超过 80 字", "source_file": "...", "code_snippet": "最多 160 字", "fact_type": "..."}}],
  "related_code_snippets": [{{"file_path": "...", "code_content": "最多 200 字", "relation_type": "..."}}]
}}
