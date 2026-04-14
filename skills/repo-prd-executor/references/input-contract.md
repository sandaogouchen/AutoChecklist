# Input Contract

Use these fields when invoking the skill.

## Shared Fields

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| `repo_url` | yes | - | Canonical remote URL. |
| `repo_owner` | yes | - | Use for GitHub MCP lookups. |
| `repo_name` | yes | - | Use for GitHub MCP lookups. |
| `source_branch` | yes | - | Source branch for the implementation. |
| `analysis_branch` | no | `analysis` | Analysis branch to consume or sync. |
| `runtime_mode` | no | `auto` | `auto`, `github_mcp`, or `local_git`. |
| `focus_topics` | no | `[]` | Include `checklist-optimization` when needed. |
| `focus_notes` | no | `""` | Repo-specific hints or constraints. |
| `output_language` | no | `zh-CN` | Default explanation language. |

## Skill-Specific Fields

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| `prd_markdown` | conditional | - | Inline PRD content. Use this or `prd_file_path`. |
| `prd_file_path` | conditional | - | Path to the PRD file. Use this or `prd_markdown`. |
| `create_pr` | no | `true` | If false, stop after local branch or commit preparation. |
| `sync_analysis` | no | `true` | Attempt analysis sync after code changes. |

## Output Contract

- Return the implemented change or an explicit blocked-state report.
- Return a reviewer-facing diff explanation.
- Return an analysis-sync report or a warning that sync was skipped or impossible.
