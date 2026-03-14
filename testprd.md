Team Sign-offs

PRD Signed off
Summary

The requirement of this PRD is to explicitly state the optimize goal for Cads Advertiser, allowing them to independently select it during the ad group creation stage, and conduct refined data analysis after the campaign is launched.
We have had a large number of flows recently. Please clearly specify the scope of your modifications in the Checklist below.
Basic Info

Change Log
Date	Description	By
2025/12/19	PRD created	@mention-user
Relevant Links
Links	POC
Link to Meego ticket	Project (=PRD): project：https://meego.larkoffice.com/ttmp/ttmp_project/detail/6828665641?parentUrl=%2Fworkbench&tabKey=detail#detail requirement：https://meego.larkoffice.com/ttmp/story/detail/6828607536?parentUrl=%2Fworkbench&openScene=2 legal： https://legal.bytedance.com/compliance/detail?id=635417	PM @mention-user
Link to Legal Ticket		Legal
Link to Figma	https://www.figma.com/design/BtpzHW5dgcOO1DTjMYlXzX/Secondary-Optimization-Goals?node-id=16256-40022&t=Rb1phk8bsy1Sqmiu-0	Design
Link to Starling		Content Designer
**Link to Experiment Tracking **		DS
Link to Tech Design		RD
Link to QA Checklist		QA
Link to Comm Doc		PSO
Authors / Core Team
Team	Role	POC
[Please Add Team Name]	PM	@mention-user @mention-user
PSO	@mention-user @mention-user @mention-user @mention-user
DS	@mention-user @mention-user
RD	@mention-user @mention-user @mention-user @mention-user
QA	@mention-user
**Ads Interface **	PM	@mention-user
PSO	
DS	
RD	@mention-user @mention-user @mention-user @mention-user @mention-user
QA	@mention-user
Designer	@mention-user
Content Designer	@mention-user
Localization	
Rough Sizing (Sizing is determined based on 3 criteria. Select 1 choice under each criteria)
Engineering Effort		Revenue Impact *		UX Effort
- [ ] X-Large; >4 weeks for 1 RD		- [ ] X-Large; Opens significant new market opportunity		- [ ] X-Large; >4 weeks for 1 designer; Complete redesign of core user experience
- [ ] Large; 2-4 weeks for 1 RD		- [x] Large; Major revenue impact (P0 project)		- [ ] Large; 2-4 weeks for 1 designer; Major changes to core features
- [x] Medium; 1-2 week for 1 RD		- [ ] Medium; Moderate revenue impact (non-P0 project)		- [ ] Medium; 1-2 week for 1 designer; Noticeable changes for regular users
- [ ] Small; <= 1 week for 1 RD		- [ ] Small; No measurable revenue impact		- [x] Small; <= 1 week for 1 designer; Minimal changes, likely unnoticed by most users
**Note: Consider revenue impact in both the immediate and long term. *
Problem Statement

Target Users

All cads advertisers
User Problems

Consideration ads currently have multiple models such as a3+a4 (a3 high weight), a3+a4 (a4 high weight), and a3+vtr, with the success rate of each model basically stable and meeting expectations. It serves the different needs of advertisers through the form of a unified optimize goal + two allowlists (vtr & a4). Among them, in the row area, a3 + a4 (a3 with high weight) is the default model; in the ttp area, a3 + vtr is the default model.
problems
Allowlist management is relatively complex. Ops submit allowlists to RD based on the differentiated needs of advertisers, which involves a large workload and makes it difficult to quickly troubleshoot and filter different types of model application scenarios.
Customers have a relatively low degree of freedom and flexibility when choosing the optimize goal.
Impact

Advertisers can freely select the optimize goal that best suits their needs when creating ads. This enhances advertiser flexibility and deepens their understanding of CADS, while significantly reducing ops and rds workloads, facilitating overall management and statistical analysis.
Alpha & Beta Test Results / Supporting Research

Include alpha or beta test results in this section to help us prioritize your request. Please include supporting research for requests that require development before alpha or beta testing.
Success Metrics

*Please work with your DS partners to review the success metrics and identify 1-2 metrics. Avoid listing a bunch of metrics as success metrics. *
North Star Metrics
Usage Penetration of Two New Opt Goals
Cost Penetration of Two New Opt Goals
[Optional] Guardrail Metrics
Cads ad submission rate
Proposed Solution / Requirement Details

User Interaction & Design

Ad creation - Ad group

Scenarios	Current version	Proposed version	Error States / Edge Cases
create ad group -- ttms account		- When the advertiser has only 1 active ttms account, it will be backfilled by default without any action required. - When the advertiser has two or more active ttms accounts, display the prompt for select brand . - Add the 4th display item: acc model name~~~~（delete) - Long-term plan: TTMS is expected to launch a requirement in Q1 where one account includes multiple acc models, and the new field real acc model is expected to go live on January 20.	
create ad group -- optimize goal		- New 2 secondary opt goal (optional) - Provide options 2 secondary goals [single selection] - First time - If an advertiser wants more VTR, they can check the VTR option. - If an advertiser wants more a4, they can check the conversion option. - New ad group: Remember the last selection (effective after the last submission) - Show different optimization goals based on the ttms account selected by the advertiser. - TTS TTMS account: all goals avaliable - Web & App TTMS account: only A3 and consideration audience with more 6-second views - Below the selection box, clearly indicate that the selection of ttms account will affect the available options for optimize goal. - Whitelist logic：The whitelists of ttam are all based on the adv dimension. - Whitelist ID: - a3+vtr - idl name：CADS_MORE_VTR - ID：11194 - a3+a4(a4 high weight) - idl name ：CADS_MORE_CONVERSION - ID：11195 - For CBO: - The toggle for the secondary goal remains enabled, but it will be grayed out when users choose the web/app account. - If the goals are different, an error message will be displayed below. - When the user creates the second group, they can only select the same industry as the first group.(other accounts will be grayed out.） - Remind content: This account is not available for this goal. - When they choose the secondary goal,the goal should be the same in different groups. - There will be a shared setting icon to remind users they should select the same goal in CBO	
create creative -- cta		For ad groups selecting the a3+a4 (a4 high weight) opt goal, CTA is required (currently only for TTS account holders)	
create ad group--The campaign that has already been created	Can add new ad group in the cbo campaign	[Edit]：In the historical CBO campaign, it is not allowed to create new adgroups. Attempting to create a new ad group will result in an error.	
Long term solution - toggle solution under video view objective

Scenarios-consideration ads	Current version	Proposed version	Error States / Edge Cases
Consideration ads		- Same as short term solution - Differernt: - Only when TTMS = TTS industry, show secondary goal = A3+A4 - Other TTMS, keep as existing online.	
create ad group -- ttms account		- Same as short term solution - When the advertiser has only 1 active ttms account, it will be backfilled by default without any action required. - When the advertiser has two or more active ttms accounts, display the prompt for select brand .	
create ad group -- optimize goal	Short term solution:	- Only when TTMS = TTS industry, show secondary goal toggle = A3+A4 - Other TTMS won't show this toggle - Switch account logic:When switching between different accounts, the TTMS account will be re-verified and the toggle will be displayed. - For CBO: - The toggle for the secondary goal remains enabled, but it will be grayed out when users choose the web/app account. - If the goals are different, an error message will be displayed below. - There will be a shared setting icon to remind users they should select the same goal in CBO	
create creative -- cta		- Same as short term solution	
Create ad group-The campaign that has already been created	Can add new ad group in the cbo campaign	[Edit]：In the historical CBO campaign, it is not allowed to create new adgroups. Attempting to create a new ad group will result in an error.	
Scenarios-videoview	Current version	Proposed version	Error States / Edge Cases
Campaign level		Only apply to VideoView - manual & S++	
Ad group level		Toggle button 展示场景： - Objective：VideoView - Placements: must include TikTok - Optimization goal: 6-second views (Focused view) - Restrictions: The toggle button capability module will only be triggered when the advertiser hits a new whitelist - 展示 toggle 白名单: Consideration ads 白名单 - Manuel process：Location 选择后 - 如果没有当前选择地区的 TTMS，toggle 不会唤起 - 如有一个或多个，默认不回填（回到上一步的页面） - S++ process: TTMS 账号选择后 - 默认回填 TTMS 账号 - Location 选择后会校验是否包含 TTMS 账号的国家地区，如果没有报错：Need to include the country of selected TTMS account - 本期上线 Manuel 以及 s++ 流程：在 CBO 场景下均不支持 toggle 逻辑，后续再考虑是否需要单独提需求做 CBO 场景兼容	1. 如果不符合条件，则不会展示 button 1. 如果切换后仍符合条件，仍保持 toggle 状态
Ad group level - optimization goal	No feature	Add toggle button 1. Optimize the 6s vtr in video 1. Only when Optimization goal is 6-second views(Focused view) ,this toggle is visible - Editable before launching the campaign, Remains default-checked after adjusting the optimization goal; - Non-editable once launched - New reminder Expiration date: 90 days	todo: 这里应该补一个 toggle 的设计文案，不太能复用 traffic 中的文案的感觉（讨论 with xuhe\jinglu)
Ad group level - TTMS selection	No feature	- Trigger TTMS account binding when Consideration optimization mode is selected - If only 1 TTMS brand account exists, it is filled by default. - If multiple TTMS brand accounts exist, the first is selected by default and can be modified. - Mandatory - Editable before launch - Non-editable once launched - Verification: During the creation process, verify the binding relationship between ttms_account_id and adv.	
Existing campaigns	-	- The module is not displayed and the function is not effective for existing campaigns. - Copy the existing campaign will trigger the function	
Reporting

Scenarios	Current version	Proposed version	Error States / Edge Cases
reporting--	Currently, only the reporting of A3-related metrics is available on the TTAM platform, with no reporting of A4-related metrics.	- Only make modifications at the campaign and ad group levels - After the data service team finishes processing the A4-related metrics, report the A4 metrics on TTAM, with the display format the same as that of A3. - a3 related data full reporting - Only when an advertiser selects the secondary goal of conversion, a4 related data will be displayed. In other cases, the data service team provides the ttam backend with data 0 , and the platform frontend displays it as 0 . - White list:a3+a4(a4 high weight) - idl name ：CADS_MORE_CONVERSION - ID：11195	
Metric definition	- 15-day new conversion audience - Number of new brand buyers who had not made a purchase in the prior 180 days, but were shown your ads within 15 days prior to purchase. - 15-day new conversion rate - Percentage of people who made a purchase after clicking your ads within a 15-day attribution window, with no payment records on your brand in the prior 180 days. - Cost per New 15-day conversion - Average cost per new purchase attributed to your ads within a 15-day window, with no payments on your brand in the prior 180 days.	
[PRD] Include A4 - related Metrics in TTAM
Impact on other TTAM flows or horizontal modules (if applicable)

*Please outline the potential impact or divergence this proposal will have on other flows and modules.
If you are not sure which modules are involved, you can refer to the checklist below.
Scenarios	Current version	Proposed version
E.g., Split Test	NA	NA
Proposed Launch Plan

Please review TTAM Product Launch Flow Guidelines
Yes, will add some new events
User Behavior Event Logging

Background: Ads Interface event-tracking standard of classification & location
Naming convention: Ads Interface Products Page Module division
Solution:TT4B Event Tracking Solution introduction｜TT4B Event Tracking Solution User Manual
Event Tracking Management: Event tracking management (design and registration)
Event Tracking Business Params Template Doc(Make a copy)：business event tracking template
~~User behavior event doc: [Make a copy] Ads interface Front End event-tracking review template ~~
Platform Experiment Design

*Please work with your DS partners to review and sign off the experiment plan. *
Guidance: [2025] Ads Interfaces Experimentation Self-serve Guide
*Best practices: *TTAM Experiment Design Best Practices
*Experiment design example: *[Experiment Design] Ad creative experience optimization
Experiment design doc: TTAM Experiment Template
Group	Traffic Allocation	Treatment (what's different)	Design
v1 (Control)			
v2			
Checklist

Compliance & Safety

【动态更新】国际产品线 - 合规评估适用场景说明 Situations Subject to Compliance Review* *
Platform/Product(s)

Objectives & Buying Type

Placements

**TTAM Platform Modules **

Appendix

**Brainstormed Ideas & Options Considered - Link to References / Screenshot
Competitors & Product Inspiration -* ***Link to References / Screenshot
**Future Work - List follow-up features if there are any
**Meeting Notes *- *Update discussion notes from alignment meetings if there are any
Demo
The ttam Copywriting Team supports the modification of English expressions:
It is necessary to highlight the advantages of each goal, and ensure that the language expression is unbiased.
history

Ad group

ttam explicitly shows the opt goals of historical campaigns and adgroups
Rule correspondence between historical ad groups and new opt goals: all ad groups under the historical adv granularity
region	History model（advid）	New opt goal（ad group）
row	Default a3+a4（a3high weight）	a3+a4（a3high weight）
a3+vtr【whitelist】	a3+vtr
a3+a4（a4high weight）【whitelist】	a3+a4（a4high weight）
ttp	Default a3+vtr	a3+vtr
a3+a4（a3high weight）【whitelist】	a3+a4（a3high weight）
a3+a4（a4high weight）【whitelist】	a3+a4（a4high weight）
Modifying the opt goal of historical campaigns and adgroups is not allowed.
The 2 new secondary goals override the previous allowlist logic. New and old plans are distinguished by the plan creation time.
creative

Aligning with cpnew allowlist —— selecting optimize a3+a4 (a4 high weight) defaults to making cta required