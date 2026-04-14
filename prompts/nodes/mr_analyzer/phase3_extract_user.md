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
