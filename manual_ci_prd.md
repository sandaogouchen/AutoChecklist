Problem Statement

Target Users

Brand advertisers with live streaming capabilities.
User Problems

Brand S++ currently cannot support CI to Live, which leads to low ROI and hinders S++ volume.
Impact

The lack of CI to Live support in Brand S++ has directly affected advertisers' ROI and S++ volume, which is a key pain point. Besides, it is not suitable to directly migrate CI to live on brand S++ now because the RD effort is too high (more than one month); and CI will undergo significant changes in the future.
Expected Impact: Increase the ROI of relevant advertisers and reduce the blockage on S++ volume.
Success Metrics

North Star Metrics

The increase in ROI of advertisers using this manual CI to Live feature
The reduction in S++ volume blockage rate
Proposed Solution / Requirement Details

User Interaction & Design

Campaign level:
Add a "LIVE campaign toggle" on campaign level of CI. The campaign created under this toggle will be manual CI.
CBO is determined by the CI live toggle:
When the CI live toggle is not selected, the budget strategy can choose CBO
When the CI live toggle is selected, CBO is not visible in the budget strategy
If users enter adg level without enabling the toggle and keep editing, then go back to campaign level to enable the toggle, show a secondary pop-up window: "Settings will be reset to the default version"
Need to check the whitelist of LIVE
Since CI Live does not support copy (including previous manual campaigns), campaigns with the Live toggle enabled cannot be copied either
New CI S++ page visit/follow cannot be copied to the new CI live with toggle enabled



前端设计改动​
◦
ad group 层级改动​
▪
交互设计：打开 toggle 进入手动流，默认选中 live，隐藏模块，展示 identity 模块；关闭则无改动。​
​
Adgroup层级默认选中LIVE的交互界面（来自共享）
Adgroup层级默认选中LIVE的交互界面（来自共享）​
​
▪
展示条件：objective type 为 CI 且 campaign 的 data 中有新字段 menu CI live open 为 1 时，external type 设置为 live（值为 305），改变展示条件。​
◦
campaign list 改动​
▪
按钮置灰：打开 campaign 层的 toggle 后，将复制按钮置灰，添加多语言提示原因。​
​
Campaign List中复制按钮置灰界面（来自共享）
Campaign List中复制按钮置灰界面（来自共享）​
​
▪
代码逻辑：判断 menu CI open to live 字段为 1 时置灰按钮。​
◦
多语言添加：在 campaign 的 toggle 中添加 title 和 subtitle，在 campaign list 中添加 hover 提示。​
•
后端改动​
◦
主要改动内容​
▪
写入 tag 字段：在 campaign 中写入 tag 字段，前提是同时打开新白名单和原有白名单，可创建新的 CI。​
▪
更新限制：创建后更新场景不允许改动开关状态。​
▪
禁止复制场景：不允许 follow page visit 复制到 CI，判断条件为新字段开关打开时，optimize goal 不等于 108 和 122，后改为使用 external type 判断（值为 305）。​
◦
字段存储和交互​
▪
字段存储：s storage 字段存在于 campaign 层级。​
▪
白名单：白名单编号为 11287，已提交。​
▪
RPC IDL 变更：字段交互主要在草稿和正式创编的 form data 中。​
◦
枚举值更新：更新枚举值为 0、1、2，1 表示打开，2 表示关闭，0 和 undefine 表示无值，非 1 和 2 不处理。