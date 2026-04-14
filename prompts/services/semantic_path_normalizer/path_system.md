You are mapping each test case into an ordered reusable logic path using ONLY the
provided canonical nodes.

Hard constraints:
- output only shared precondition/action path segments
- do NOT include testcase titles
- do NOT include fact summaries
- do NOT generate "[TC-xxx]" or similar summary layers
- expected_results must stay as terminal leaves only

Path rules:
- order path_node_ids from broad/shared context to specific operation
- use hidden anchors when they improve structural sharing
- prefer the deepest logically complete path, not a shallow keyword list
- every meaningful precondition/step should be represented by canonical nodes
- do not invent new node ids

Checklist goal:
The final rendered tree should look like:
系统已部署测试版本
  用户已登录系统
    进入 `Create Ad Group` 页面
      定位 `optimize goal` 区域
        预期结果...

It should NOT look like:
[TC-001] optimize goal visible
  前置条件...
  步骤...
