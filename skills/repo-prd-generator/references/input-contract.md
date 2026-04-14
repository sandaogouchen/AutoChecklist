# Input Contract

Use these fields when invoking the skill.

## Shared Fields

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| `repo_url` | yes | - | Canonical remote URL. |
| `repo_owner` | yes | - | Use for GitHub MCP lookups. |
| `repo_name` | yes | - | Use for GitHub MCP lookups. |
| `source_branch` | yes | - | Source branch the PRD refers to. |
| `analysis_branch` | no | `analysis` | Preferred analysis branch. |
| `runtime_mode` | no | `auto` | `auto`, `github_mcp`, or `local_git`. |
| `focus_topics` | no | `[]` | Include `checklist-optimization` when needed. |
| `focus_notes` | no | `""` | Repo-specific hints. |
| `output_language` | no | `zh-CN` | Default response language. |

## Skill-Specific Fields

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| `requirement` | yes | - | Detailed business and technical requirement text. |
| `extra_notes` | no | `""` | Design links, constraints, deadlines, cross-system context. |
| `output_format` | no | `markdown_file` | `markdown_file` or `feishu_doc`. |

## Output Contract

- Produce a full PRD rather than a short outline.
- State whether the PRD was based on `analysis_branch` or degraded mode.
- Preserve open questions instead of silently filling gaps.
