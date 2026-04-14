# Self-Feedback Loop

Run this after the first-pass implementation and verification, and before final PR packaging.

## Goals

This is a focused reflection pass with four jobs:

1. find likely bugs or regressions
2. check whether the implemented effect matches the PRD intent
3. check whether the current user-visible outcome matches expectations
4. think about how the feature could evolve next
5. check whether this PR deletes a large amount of code from any file, and verify that the deletion is intentional

## Minimum Checklist

- Re-read the relevant PRD sections.
- Re-read the actual changed files and verification output.
- Inspect the actual diff for large code deletions from any single file.
- Look for:
  - broken edge cases
  - missing validation or error handling
  - partial implementation of the promised behavior
  - places where the implementation technically works but the effect is weaker than expected
- If a file shows large code deletion, open a separate investigation task to explain why that deletion happened.
- In that investigation, determine whether the deletion is:
  - intentional simplification or refactor
  - required removal because the code is dead or replaced
  - accidental deletion caused by agent misread or scope drift
- If the deletion came from agent misjudgment, restore or re-implement the wrongly removed code before closing.
- Capture 1-3 evolution ideas if they are obvious and grounded in the current implementation.

## Output Shape

Return a short self-feedback summary with:

- `must_fix_now`
- `looks_correct`
- `expectation_gaps`
- `deletion_investigation`
- `next_evolution_ideas`

## Decision Rule

- If `must_fix_now` is non-empty, go back to implementation before closing.
- If `deletion_investigation` finds accidental deletion or unjustified destructive edits, treat that as `must_fix_now` and route back to implementation.
- If only `next_evolution_ideas` remain, keep them as follow-up suggestions and continue.
