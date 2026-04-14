# PRD Structure

Generate a complete PRD with the following sections.

## Required Sections

| Section | Must Include |
| --- | --- |
| 文档信息 | title, version, date, repo URL, analysis basis, status |
| 背景与目标 | project background, core goals, success metrics, non-goals |
| 用户与场景 | target users, at least 3 user stories, key journey |
| 功能需求 | detailed feature breakdown, rules, exceptions, data requirements, UI/UX if relevant |
| 非功能需求 | performance, security, availability, compatibility, maintainability, extensibility |
| 技术方案概要 | architecture impact, technical choices, model changes, API impact, file-change list |
| 兼容性与迁移 | backward compatibility, migration, rollout |
| 里程碑与排期建议 | phased schedule with estimated effort |
| 风险与依赖 | risk table with mitigations |
| 开放问题 | unresolved items with suggested direction |
| 附录 | glossary, references, analyzed files read, change history |

## Citation Rules

- Use analysis citations such as `app/services/_ANALYSIS.md#§2.3` when the analysis branch was used.
- Use `新增` for net-new implementation areas.
- Use `[需基于分析分支补充]` only in degraded mode.

## Quality Rules

- Expand each feature; never leave a feature as title-only bullets.
- Quantify non-functional requirements wherever possible.
- Default to Chinese and treat 3000 Chinese characters as the minimum size.
- List every `_ANALYSIS.md` consumed in the appendix.
