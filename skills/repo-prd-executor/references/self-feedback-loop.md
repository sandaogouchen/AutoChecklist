# Self-Feedback Loop

Run this after the first-pass implementation and verification, and before final PR packaging.

## Goals

This is a focused reflection pass with four jobs:

1. find likely bugs or regressions
2. check whether the implemented effect matches the PRD intent
3. check whether the current user-visible outcome matches expectations
4. think about how the feature could evolve next

## Minimum Checklist

- Re-read the relevant PRD sections.
- Re-read the actual changed files and verification output.
- Look for:
  - broken edge cases
  - missing validation or error handling
  - partial implementation of the promised behavior
  - places where the implementation technically works but the effect is weaker than expected
- Capture 1-3 evolution ideas if they are obvious and grounded in the current implementation.

## Output Shape

Return a short self-feedback summary with:

- `must_fix_now`
- `looks_correct`
- `expectation_gaps`
- `next_evolution_ideas`

## Decision Rule

- If `must_fix_now` is non-empty, go back to implementation before closing.
- If only `next_evolution_ideas` remain, keep them as follow-up suggestions and continue.
