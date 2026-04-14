# Input Contract

Use these fields when invoking the skill.

If this skill is called by `genfu-change-workflow`, the parent workflow should populate these shared fields from `../../references/repo-profile.md` plus any explicit user overrides. Treat that merged runtime config as the source of truth.

## Shared Fields

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| `repo_url` | yes | - | Canonical remote URL. |
| `repo_owner` | yes | - | Use for repository lookups. |
| `repo_name` | yes | - | Use for repository lookups. |
| `source_branch` | yes | - | Source branch the PRD refers to. |
| `analysis_branch` | no | `analysis` | Preferred analysis branch. |
| `runtime_mode` | no | value from parent/profile | `github_mcp` or `local_git`. |
| `focus_topics` | no | `[]` | Include `checklist-optimization` when needed. |
| `focus_notes` | no | `""` | Repo-specific hints. |
| `output_language` | no | `zh-CN` | Default response language. |

## Parent Workflow Binding

When nested under `genfu-change-workflow`:

- inherit repository defaults from `../../references/repo-profile.md`
- inherit merge behavior from `../../references/runtime-config-template.md`
- do not replace parent-provided `repo_url`, `repo_owner`, `repo_name`, `source_branch`, `analysis_branch`, `focus_topics`, or `focus_notes` with local guesses

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
