You are planning a stable manual-QA checklist hierarchy before testcase drafting.

Stage A responsibilities:
- build canonical reusable outline nodes for the checkpoints below
- hierarchy must be business-object-first
- visible parents are required for core business objects such as Campaign, Ad group,
  Creative, Reporting, TTMS account
- mixed object+state phrases must be split into separate nodes
- no testcase summary nodes
- no "[TC-xxx]" layers
- display_text should be concise and renderable in Markdown/XMind

Allowed node kinds:
- business_object
- context
- page
- action

Visibility rules:
- visible: rendered directly
- required: rendered directly and should not be skipped
- hidden: merge-only anchor, never rendered
