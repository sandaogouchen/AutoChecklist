# Execution Flow

Follow this order. Do not skip straight to coding.

## Step 1: Understand the Current Repo

1. Prefer `analysis_branch` and `_INDEX.md` if they exist.
2. Read only the analysis files relevant to the PRD scope.
3. If the analysis branch is missing or incomplete, read source files directly.
4. Output a concise architecture overview:
   - tech stack
   - relevant directories
   - relevant modules or files
   - analysis citations when available

## Step 2: Make a Concrete Change Plan

- List file paths plus change summaries.
- Explain why each change is needed.
- Compare multiple approaches only when there is a real tradeoff.

## Step 3: Implement

- Match existing style.
- Add comments only when they clarify non-obvious logic.
- Do not break unrelated behavior.

## Step 4: Branch, Commit, PR

- This step happens only after the self-feedback loop is complete.
- Create a feature branch from the latest source branch when possible.
- Default branch names:
  - `feat/<short-topic>`
  - `fix/<short-topic>`
- Use Conventional Commits, for example `feat: add actionable checklist path enforcement`.
- Prefer GitHub MCP for PR creation; use local git plus explicit handoff if remote PR creation is unavailable.

## Step 4.5: Self-Feedback Loop

- Run the dedicated self-feedback loop after initial verification and before final PR packaging.
- If it finds must-fix issues, route them back into implementation immediately.
- If it finds only future improvement ideas, keep them in the final summary without blocking closure.

## Step 5: Branch, Commit, PR

- Create or update the feature branch only after the self-feedback loop is complete.
- Prefer GitHub MCP for PR creation; use local git plus explicit handoff if remote PR creation is unavailable.

## Step 6: Diff Explanation

- Build the reviewer report from the actual diff or PR file list.
- Explain each key hunk at behavior level, not as vague summaries.

## Step 7: Analysis Sync

- If `sync_analysis=true`, update `analysis_branch` using the separate sync rules.
- If the analysis branch is absent or malformed, report that limitation explicitly.

## Hard Rules

- Do not implement before understanding the repo.
- Do not skip the self-feedback loop after verification.
- Do not push straight to `main`.
- If the PRD conflicts with current code or is materially ambiguous, stop and surface the conflict first.
