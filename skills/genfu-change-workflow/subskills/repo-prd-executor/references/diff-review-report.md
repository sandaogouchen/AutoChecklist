# Diff Review Report

Build the reviewer-facing report from the real diff.

## Per-File Structure

For each changed file, include:

| Field | Content |
| --- | --- |
| 文件路径 | Full file path |
| 变更类型 | Added, Modified, Removed, or Renamed |
| 改动概述 | One-sentence purpose |
| 核心变更点 | What changed, why, and how for each key hunk |
| 与其他文件的关联 | Cross-file dependency or call-path impact |
| 潜在风险与关注点 | Boundary cases, error handling, performance, security, compatibility |

## Overall Summary

Also include:

- the main logic chain or data flow touched by the PR
- dependencies between changed files
- PRD-to-implementation coverage check
- top 3 reviewer focus areas

## Self-Check Checklist

- Are new functions or methods documented where needed?
- Did any hard-coded values need configuration instead?
- Is error handling complete?
- Was duplicate code introduced?
- Are names clear and consistent with the repo?
- Are there obvious performance hazards?

## Hard Rule

Do not write this report from memory. Use PR diff APIs when available; otherwise use local `git diff` and the final working tree.
