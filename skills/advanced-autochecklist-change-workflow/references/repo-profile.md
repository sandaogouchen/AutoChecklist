# Repo Profile

This file holds the current default repo profile and repo-specific hints for this skill.
Choose repository access here:
- `github_mcp` for GitHub MCP access
- `local_git` for local repository reads

The `default_profile` block below is the default repository context for the whole workflow. If the user does not override the repo, use it directly instead of asking for repo confirmation.

## Default Profile

```yaml
default_profile:
  repo_url: "https://github.com/sandaogouchen/AutoChecklist"
  repo_owner: "sandaogouchen"
  repo_name: "AutoChecklist"
  source_branch: "main"
  analysis_branch: "analysis"
  runtime_mode: "local_git"
  focus_topics: []
  focus_notes: ""
  output_language: "zh-CN"
```

## Repo-Specific Hints

Bias the planning discussion toward:

- understanding how the current genFu functionality behaves before proposing expansion
- finding adjacent unmet needs from existing features, workflows, and outputs
- separating "include now" scope from "defer" scope before PRD generation

## Editing Guidance

- Edit only the `default_profile` block when you want to repoint this skill to another repo.
- Change `default_profile.runtime_mode` when you want installation/setup to use local repository reads instead of GitHub MCP, or vice versa.
- Update the hints only when the repository has domain-specific planning concerns that should influence discussion.
