# Repo Defaults

This skill is pinned to the AutoChecklist repository by default.

## Fixed Invocation Context

```yaml
repo_url: "https://github.com/sandaogouchen/AutoChecklist"
repo_owner: "sandaogouchen"
repo_name: "AutoChecklist"
source_branch: "main"
analysis_branch: "analysis"
runtime_mode: "auto"
focus_topics:
  - "checklist-optimization"
output_language: "zh-CN"
```

## Override Rules

- Ignore repo-level overrides unless the user explicitly says to target a different repo or branch.
- Keep `focus_topics: ["checklist-optimization"]` unless the user explicitly asks to remove it.
- Treat this file as the source of truth when calling:
  - `repo-prd-generator`
  - `repo-prd-executor`

## Practical Meaning

This skill is optimized for AutoChecklist changes around:

- checklist path quality
- semantic normalization
- merge and deduplication logic
- project checklist templates
- mandatory skeleton enforcement
- markdown and XMind rendering impact
