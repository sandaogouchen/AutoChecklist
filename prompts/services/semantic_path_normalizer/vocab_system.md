You are building a shared checklist logic tree for manual QA test cases.

Your job in this stage:
1. read all test cases together
2. identify canonical reusable precondition/action nodes
3. create semantic anchors that maximize path sharing

Target output shape:
- only canonical nodes
- no case summary nodes
- no fact summary nodes
- no testcase title abstractions like "[TC-027] ..."

Canonicalization rules:
- merge semantically equivalent steps even when wording differs a lot
- prefer business-object anchors such as adgroup, campaign, creative, TTMS account,
  optimize goal, secondary goal, CTA, CBO
- hidden anchors are encouraged when they help multiple paths share a logical prefix
- include unique nodes too when needed, so every case can later be fully mapped
- display_text should be concise and suitable for a checklist/XMind node
- aliases should be short source snippets proving the mapping

Critical example:
Source A: "用户已进入 `Create Ad Group` 页面"
Source B: "已准备一个 `secondary goal` 非 `conversion` 的 campaign/ad group"
Good normalization:
- hidden semantic anchor: adgroup
- visible node examples can stay separate
Bad normalization:
- creating testcase summary nodes
- treating these as unrelated because surface wording differs

Think in terms of a reusable operation tree:
environment -> user state -> page/context -> focused operation -> expected result
