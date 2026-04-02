[PRD] Consideration ads New Secondary Optimize Goals

Team Sign-offs

Summary

The requirement of this PRD is to explicitly state the optimize goal for Cads Advertiser, allowing them to independently select it during the ad group creation stage, and conduct refined data analysis after the campaign is launched.
We have had a large number of flows recently. Please clearly specify the scope of your modifications in the Checklist below.
Basic Info

Change Log

Date	Description	By
2025/12/19	PRD created	@何昕妍
Relevant Links

Links	POC
Link to Meego ticket	PM @陈静璐
Project (=PRD): project：https://meego.larkoffice.com/ttmp/ttmp_project/detail/6828665641?parentUrl=%2Fworkbench&tabKey=detail#detail requirement：https://meego.larkoffice.com/ttmp/story/detail/6828607536?parentUrl=%2Fworkbench&openScene=2 legal：https://legal.bytedance.com/compliance/detail?id=635417	
Link to Legal Ticket	Legal
Link to Figma: https://www.figma.com/design/BtpzHW5dgcOO1DTjMYlXzX/Secondary-Optimization-Goals?node-id=16256-40022&t=Rb1phk8bsy1Sqmiu-0	Design
Link to Starling	Content Designer
Link to Experiment Tracking	DS
Link to Tech Design	RD
Link to QA Checklist	QA
Link to Comm Doc	PSO
Authors / Core Team

Team	Role	POC
[Please Add Team Name]	PM	@陈静璐@何昕妍
PSO	@徐梦扬@柳月婷@张梦亚@王 澤（Taku）
DS	@Bing Xia@Tingting Gu
RD	@林纵@王伟佳@王博洋@严轶轩
QA	@解力霞
Ads Interface	PM	@高浩原
PSO	
DS	
RD	@张行@董全@胡智静 @蔡声群@曾棱辉
QA	@刘旭
Designer	@Lena Yuan
Content Designer	@许河
Localization	
Rough Sizing (Sizing is determined based on 3 criteria. Select 1 choice under each criteria)

Engineering Effort	Revenue Impact *	UX Effort
X-Large; >4 weeks for 1 RD	X-Large; Opens significant new market opportunity	X-Large; >4 weeks for 1 designer; Complete redesign of core user experience
Large; 2-4 weeks for 1 RD	Large; Major revenue impact (P0 project)	Large; 2-4 weeks for 1 designer; Major changes to core features
Medium; 1-2 week for 1 RD	Medium; Moderate revenue impact (non-P0 project)	Medium; 1-2 week for 1 designer; Noticeable changes for regular users
Small; <= 1 week for 1 RD	Small; No measurable revenue impact	Small; <= 1 week for 1 designer; Minimal changes, likely unnoticed by most users
*Note: Consider revenue impact in both the immediate and long term.
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

Please work with your DS partners to review the success metrics and identify 1-2 metrics. Avoid listing a bunch of metrics as success metrics.
North Star Metrics

Usage Penetration of Two New Opt Goals
Cost Penetration of Two New Opt Goals
[Optional] Guardrail Metrics

Cads ad submission rate
Proposed Solution / Requirement Details

User Interaction & Design

Ad creation - Ad group

Scenarios	Current version	Proposed version	Error States / Edge Cases
create ad group -- ttms account	(image.png)		When the advertiser has only 1 active ttms account, it will be backfilled by default without any action required. When the advertiser has two or more active ttms accounts, display the prompt for "select brand". Add the 4th display item: acc model name（delete) Long-term plan: TTMS is expected to launch a requirement in Q1 where one account includes multiple acc models, and the new field real acc model is expected to go live on January 20.
create ad group -- optimize goal	(截屏 2025-12-22 17.41.55.png)	(image.png)	New 2 secondary opt goal (optional) Provide options 2 secondary goals [single selection] First time If an advertiser wants more VTR, they can check the VTR option. If an advertiser wants more a4, they can check the conversion option. New ad group: Remember the last selection (effective after the last submission) Show different optimization goals based on the ttms account selected by the advertiser. TTS TTMS account: all goals avaliable. Web & App TTMS account: only A3 and consideration audience with more 6-second views. Below the selection box, clearly indicate that the selection of ttms account will affect the available options for optimize goal. Whitelist logic：The whitelists of ttam are all based on the "adv" dimension. Whitelist ID: a3+vtr idl name：CADS_MORE_VTR ID：11194. a3+a4(a4 high weight) idl name：CADS_MORE_CONVERSION ID：11195. For CBO: The toggle for the secondary goal remains enabled, but it will be grayed out when users choose the web/app account. If the goals are different, an error message will be displayed below. When the user creates the second group, they can only select the same industry as the first group.(other accounts will be grayed out.) Remind content: This account is not available for this goal. When they choose the secondary goal,the goal should be the same in different groups. There will be a "shared setting" icon to remind users they should select the same goal in CBO. (image.png)
[Edit] : Not allow edit after created. Switch Account Logic: When switching between different accounts, the system will update the corresponding secondary goal.(if in CBO,the account should be in the same industry, otherwise they can not choose) (image.png)			
create creative -- cta	(image.png)	(image.png)	For ad groups selecting the a3+a4 (a4 high weight) opt goal, CTA is required (currently only for TTS account holders)
create ad group--The campaign that has already been created	Can add new ad group in the cbo campaign		[Edit]：In the historical CBO campaign, it is not allowed to create new adgroups. Attempting to create a new ad group will result in an error.
Long term solution - toggle solution under video view objective

Scenarios-consideration ads	Current version	Proposed version	Error States / Edge Cases
Consideration ads		Same as short term solution. Differernt: Only when TTMS = TTS industry, show secondary goal = A3+A4. Other TTMS, keep as existing online.	
create ad group -- ttms account	(image.png)	Same as short term solution. When the advertiser has only 1 active ttms account, it will be backfilled by default without any action required. When the advertiser has two or more active ttms accounts, display the prompt for "select brand".	
create ad group -- optimize goal	Short term solution: (image.png)	(image.png) Only when TTMS = TTS industry, show secondary goal toggle = A3+A4. Other TTMS won't show this toggle. Switch account logic: When switching between different accounts, the TTMS account will be re-verified and the toggle will be displayed. For CBO: The toggle for the secondary goal remains enabled, but it will be grayed out when users choose the web/app account. If the goals are different, an error message will be displayed below. There will be a "shared setting" icon to remind users they should select the same goal in CBO. (image.png)	
create creative -- cta	(image.png)	Same as short term solution	
Create ad group-The campaign that has already been created	Can add new ad group in the cbo campaign		[Edit]：In the historical CBO campaign, it is not allowed to create new adgroups. Attempting to create a new ad group will result in an error.
Scenarios-videoview	Current version	Proposed version	Error States / Edge Cases
Campaign level	(image.png)	Only apply to VideoView - manual & S++	
Ad group level	(image.png)	Toggle button 展示场景：Objective：VideoView. Placements: must include TikTok. Optimization goal: 6-second views (Focused view). Restrictions: The toggle button capability module will only be triggered when the advertiser hits a new whitelist. 展示 toggle 白名单: Consideration ads 白名单. Manuel process：Location 选择后 如果没有当前选择地区的 TTMS，toggle 不会唤起 如有一个或多个，默认不回填（回到上一步的页面）. S++ process: TTMS 账号选择后 默认回填 TTMS 账号 Location 选择后会校验是否包含 TTMS 账号的国家地区，如果没有报错：Need to include the country of selected TTMS account. (image.png) 本期上线 Manuel 以及 s++ 流程：在 CBO 场景下均不支持 toggle 逻辑，后续再考虑是否需要单独提需求做 CBO 场景兼容。如果不符合条件，则不会展示 button. 如果切换后仍符合条件，仍保持 toggle 状态.	
Ad group level - optimization goal	(image.png) No feature	Add toggle button. Optimize the 6s vtr in video. Only when Optimization goal is "6-second views (Focused view)", this toggle is visible. Editable before launching the campaign, Remains default-checked after adjusting the optimization goal; Non-editable once launched. New reminder Expiration date: 90 days. todo: 这里应该补一个 toggle 的设计文案，不太能复用 traffic 中的文案的感觉（讨论 with xuhe\jinglu) (image.png)	
Ad group level - TTMS selection	No feature	(image.png) Trigger TTMS account binding when Consideration optimization mode is selected. If only 1 TTMS brand account exists, it is filled by default. If multiple TTMS brand accounts exist, the first is selected by default and can be modified. Mandatory. Editable before launch. Non-editable once launched. Verification: During the creation process, verify the binding relationship between ttms_account_id and adv.	
Existing campaigns	-	The module is not displayed and the function is not effective for existing campaigns. Copy the existing campaign will trigger the function.	
Reporting

Scenarios	Current version	Proposed version	Error States / Edge Cases
reporting--	Currently, only the reporting of A3-related metrics is available on the TTAM platform, with no reporting of A4-related metrics.	Only make modifications at the campaign and ad group levels. After the data service team finishes processing the A4-related metrics, report the A4 metrics on TTAM, with the display format the same as that of A3. a3 related data full reporting. Only when an advertiser selects the secondary goal of conversion, a4 related data will be displayed. In other cases, the data service team provides the ttam backend with data "0", and the platform frontend displays it as "0". White list: a3+a4(a4 high weight) idl name：CADS_MORE_CONVERSION ID：11195	
Metric definition

15-day new conversion audience: Number of new brand buyers who had not made a purchase in the prior 180 days, but were shown your ads within 15 days prior to purchase.
15-day new conversion rate: Percentage of people who made a purchase after clicking your ads within a 15-day attribution window, with no payment records on your brand in the prior 180 days.
Cost per New 15-day conversion: Average cost per new purchase attributed to your ads within a 15-day window, with no payments on your brand in the prior 180 days.
[PRD] Include A4 - related Metrics in TTAM
Impact on other TTAM flows or horizontal modules (if applicable)

*Please outline the potential impact or divergence this proposal will have on other flows and modules. If you are not sure which modules are involved, you can refer to the checklist below.
Scenarios	Current version	Proposed version
E.g., Split Test	NA	NA
Proposed Launch Plan

Please review TTAM Product Launch Flow Guidelines
User Behavior Event Logging

Background: Ads Interface event-tracking standard of classification & location
Naming convention: Ads Interface Products Page Module division
Solution: TT4B Event Tracking Solution introduction｜TT4B Event Tracking Solution User Manual
Event Tracking Management: Event tracking management (design and registration)
Event Tracking Business Params Template Doc(Make a copy)：business event tracking template
User behavior event doc: [Make a copy] Ads interface Front End event-tracking review template
Platform Experiment Design

Please work with your DS partners to review and sign off the experiment plan.
Guidance: [2025] Ads Interfaces Experimentation Self-serve Guide
Best practices: TTAM Experiment Design Best Practices
Experiment design example: [Experiment Design] Ad creative experience optimization
Experiment design doc: TTAM Experiment Template
Group	Traffic Allocation	Treatment (what's different)	Design
v1 (Control)			
v2			
Checklist

Compliance & Safety

【动态更新】国际产品线 - 合规评估适用场景说明 Situations Subject to Compliance Review
Platform/Product(s)	Objectives & Buying Type
Placements	TTAM Platform Modules
Appendix

Brainstormed Ideas & Options Considered - Link to References / Screenshot
Competitors & Product Inspiration - Link to References / Screenshot
Future Work - List follow-up features if there are any
Meeting Notes - Update discussion notes from alignment meetings if there are any
Demo

The ttam Copywriting Team supports the modification of English expressions: It is necessary to highlight the advantages of each goal, and ensure that the language expression is unbiased.
history

Ad group

ttam explicitly shows the opt goals of historical campaigns and adgroups
Rule correspondence between historical ad groups and new opt goals: all ad groups under the historical adv granularity
region	History model（advid）	New opt goal（ad group）
row	Default a3+a4（a3 high weight）	a3+a4（a3 high weight）
a3+vtr【whitelist】	a3+vtr
a3+a4（a4 high weight）【whitelist】	a3+a4（a4 high weight）
ttp	Default a3+vtr	a3+vtr
a3+a4（a3 high weight）【whitelist】	a3+a4（a3 high weight）
a3+a4（a4 high weight）【whitelist】	a3+a4（a4 high weight）
Modifying the opt goal of historical campaigns and adgroups is not allowed.
The 2 new secondary goals override the previous allowlist logic. New and old plans are distinguished by the plan creation time.
creative

Aligning with cpnew allowlist —— selecting optimize a3+a4 (a4 high weight) defaults to making cta required
Aligning with cpnew allowlist —— selecting optimize a3+a4 (a4 high weight) defaults to making cta required





[Backend Tech Design] Cads New Secondary Optimize Goals


Design Preparation

Backgroud

Consideration ads currently have multiple models such as a3+a4 (a3 high weight) (<=> A3), a3+a4 (a4 high weight), and a3+vtr, with the success rate of each model basically stable and meeting expectations. Now we need to platformize these three products.
Advertisers can freely select the optimize goal that best suits their needs when creating ads. This enhances advertiser flexibility and deepens their understanding of CADS, while significantly reducing ops and rds workloads, facilitating overall management and statistical analysis.
Cads(Consideration Ads)
VideView
Add a3+a4(a4 high)
Add a3+vtr
PRD: [PRD] Consideration ads New Secondary Optimize Goals


General Design

Add two fields：
ttms_secondary_optimize_goal：store secondary optimization goals. The delivery side decides which delivery flow to follow based on this field.
real_acc_model_id：Store the real Acc model ID, used by TTMS and the placement side.
UI screenshot

Ad Level
field	value
ad group > ttms_account_id	eg: 7387981492036763666, Not editable
ad group > optimize_goal	Cads: 129(A3), VV: 118(ENGAGED_VIEW), Not editable
ad group > [new field] ttms_secondary_optimize_goal	nil/0/1/2
enum TtmsSecondaryOptimizeGoal {
    UNSET = 0           // 展示，但不打开 toggle
    MORE_VTR = 1        // a3+vtr
    MORE_CONVERSION = 2 // a3+a4(a4 high)
}
Not editable
== nil, 前端不展示 toggle
| ad group > [new field] real_acc_model_id | eg: 101000, Not editable |
If >0 is new ad group, else Is old ad group
Cads Goal

goal	model	简称	Judgment caliber
Consideration audience acquisition	a3+a4(a3 high weight)	a3	optimize_goal = 129 && ttms_secondary_optimize_goal in (nil, 0)
More video watch time	a3+vtr	vtr	Cads: (short term) optimize_goal = 129 && ttms_secondary_optimize_goal = 1; VV: (long term) optimize_goal = 118 && ttms_secondary_optimize_goal = 1
More assisted new conversions	a3+a4(a4 high weight)	a4	optimize_goal = 129 && ttms_secondary_optimize_goal = 2
TTMS Account 与 Secondary Goal 关系

TTS: All goals available
More video watch time （a3+vtr)
More assisted new conversions (a3+a4(a4 high))
Web & App: Only A3 and consideration audience with more 6-second views
More video watch time（a3+vtr)
Architecture Design

Required field
Main logic:
TTAM creation:
Query TTMS account list/info with realAccModels
According to conversion type to enable secondary optimize goals
Store ttms_secondary_optimize_goal and real_acc_model_id for ttms and delivery.
TTMS:
https://bytedance.larkoffice.com/wiki/GnETw5cGTioWctkOhMicFHkznze
Return realAccModels
Delivery side
Technical docs：
TTAM reporting: Reporting A4-related metrics
MAPI
Bulk CSV
Working flow Design

Required field
All key changes must be reflected in the flowchart or sequence diagram.
Query ttms account List/Info

In the ad group page initial stage, FE query ttms account list from TTMS by brand_bff/brand_core.
In edit page, FE query ttms account info
Creation process

In the ad core creation process, we need to support 1NN(snap/sketch), normal update/detail flow, Manual and S+2.0.
In BuildStore/CreationRPC, we will do some logic validation and field adapation. And query the ttms account list and new allowlist.
Snap + Sketch

In the draft stage, we only write snap redis and sketch db, without logic tree. And we haven't any logical change. So we only need to pay attention to request params and storage.
Redis: toutiao.redis.ad_snap
MySQL: ad_sketch
CBO

Two features:
Old Cads CBO Campaign - can't create new ad group
How to identify old Cads CBO campaign？
campaign.data.budget_optimize_switch == 1 && 
ad.data.real_acc_model_id == nil/0
New CBO Campaign
Cads CBO: ttms_secondary_optimize_goal must be same.
VideoView CBO: can't support toggle logic.
ad core creation flow

11N and normal creation use the same code. I put them together.
Manual in BuildStone and S+2.0 in CreationRPC(BS2.0). The technical details here take CreationRPC as an example
Ad Group Level:
In all write + read interfaces, add two fields(ttms_secondary_optimize_goal + real_acc_model_id).
These two fields are not editable.
Derived flow
use template values directly
NOTICE: need to regress to the derived and edit response process
Special logic for Cads and VideoView
Cads - a3+a4(a4 high)
ttms_secondary_optimize_goal must match with accModel.conversion_type.
VideoView - a3+vtr
Validate allowlist - VIDEOVIEW_A3_OPTIMIZATION
Fixed some fields
optimize_goal = 118(EngageView)
smart_bid_type=7(NO_BID)
Don't support CBO
Creative Level:
In Cads, if users select the a3+a4(a4 high) opt goal and selected TTMS account is TTS type , CTA is required
[Required] Allowlist/Experimental Design

New allowlist/experimental Design

Allowlist ID/Libra link, complete the design before technical review
VIDEOVIEW_A3_OPTIMIZATION = TODO
CADS_MORE_VTR = 11194
CADS_MORE_CONVERSION = 11195
Stock Allowlist/Experimental Impact Assessment

Evaluate the whitelists/experiments affected after the required whitelist is enabled. We need to focus on code compatibility and test regression. Query tool: https://quantum-sg.bytedance.net/page-galaxy/whitelist
none
Storage Design

Optional
field_name	field_path	field_table	field_type	Value	Reading service
ttms_account_id	ad.data	ad	int64	123456789012345678	ad.nebula.build_stone_i18n, ad.tt4b.creation_rpc
[new] real_acc_model_id	ad.data	ad	int64	123456789012345678	ad.nebula.build_stone_i18n, ad.tt4b.creation_rpc
optimize_goal	ad.data	ad	enum OptimizeGoal { ENGAGED_VIEW = 118, A3 = 129 }	129	ad.nebula.build_stone_i18n, ad.tt4b.creation_rpc
[new] ttms_secondary_optimize_goal	ad.data	ad	enum TtmsSecondaryOptimizeGoal { UNSET = 0, MORE_VTR = 1, MORE_CONVERSION = 2 }	1	ad.nebula.build_stone_i18n, ad.tt4b.creation_rpc
Detailed Design

Scenario Influence Evaluation

Scenario	Status
11N Ad Creation	✅
1NN Ad Creation	✅
Edit	✅
Copy	✅
1NN Copy	✅
Draft	✅
Allowlist

enum AdverFunc {
    CADS_MORE_VTR = 11194          // a3+vtr
    CADS_MORE_CONVERSION = 11195   // a3+a4(a4 high weight)
}
ad.tt4b.creation_bff — Update IDL, Add new fields
ad.platform.tt_ads — Update IDL, Add new fields
brand_bff_i18n — Update IDL, Add new fields
brand_core_i18n — Update IDL, Add new fields
ad.nebula.build_stone_i18n
CBO consistency check
a. If Cads, check ttms_secondary_optimize_goal.
ttam_monorepo/app/build_stone_i18n/biz/snap_creation/snap_context/check_snap_cbo_consistency_context.go
ad.tt4b.creation_rpc
CBO
If Cads, check ttms_secondary_optimize_goal.
If firstAd.real_acc_model_id == nil/0, block creation.
ttam_monorepo/app/tt4b_creation_rpc/biz/spp_1mn_consistence/spp_1mn_consistence.go
API Design

Optional
IDL design or API documentation.
HTTP

ad.platform.brand_bff_i18n
/api/v4/i18n/brand/tool/ttms_account_list/ | query ttms account list by advid
Get advID from cookies, so there is no need req parms in the body.
Add RealAccModels fields
/api/v4/i18n/brand/tool/ttms_account_info/ | query ttms account info by ttms account id.
Add RealAccModels fields
ad.platform.tt_ads & ad.tt4b.creation_bff
Related API (ad/snap/sketch)
BAM: https://cloud-i18n.bytedance.net/bam/rd/ad.tt4b.creation_bff/api_doc/show_doc?api_branch=feat-traffic-cads&endpoint_id=1681847&cluster=default
Service	Tag	HTTP API	RPC API (ad.nebula.build_stone_i18n/ad.tt4b.creation_rpc)	Our Changes
ad.tt4b.creation_bff	Save Snap/Sketch	/api/v4/i18n/creation/ad_snap/save/	SaveAdSnap	Update Sketch Form Data, Add new fields
Get Snap/Sketch	/api/v4/i18n/creation/snap/detail/	MGetSnapByIds	
Copy creative snap/sketch in creation flow	/api/v4/i18n/creation/ad_snap/copy/	CopyAdSnap	
ad.platform.tt_ads	Consideration Auction creation flow	/api/v3/i18n/perf/ad/update/	CreateAd	
/api/v3/i18n/perf/ad/detail/, /api/v3/i18n/perf/ad/copy/	MGetAdInfoByIds	
Write Interface
path="/api/v4/i18n/creation/ad_snap/save"
     "/api/v3/i18n/perf/ad/update"
method="GET"
req={
    "ad_sketch_form_data or base_info": {
        "ttms_account_id": 7340171258740473857，
        "real_acc_model_id": 1234567890
        "ttms_secondary_optimize_goal": -1/0/1/2
    }
}

res={
    "msg": "success",
    "code": 0,
    "data": {},
    "extra": {}
}
Read Interface
path="/api/v4/i18n/creation/snap/detail/"
     "/api/v4/i18n/creation/ad_snap/copy/"
     "/api/v3/i18n/perf/ad/detail/"
     "/api/v3/i18n/perf/ad/copy/"
method="GET"
req={
    "ad_id or ad_snap_id or": 
}

res={
    "msg": "success",
    "code": 0,
    "data": {
        "ad_snap_map/xxxx or base_info": {
            "ttms_account_id": 7340171258740473857，
            "real_acc_model_id": 1234567890
            "ttms_secondary_optimize_goal": -1/0/1/2
        } 
    },
    "extra": {}
}
RPC

ad.platform.brand_core_i18n
Same as brand_bff_i18n.
Outer Dependencies

TTMS

Cads Secondary Optimize Goals TTMS 后端适配方案
接口升级
PSM: ad.ttms.circuit
升级接口：
GetAccountsByAdvId
GetAccountInfo
IDL：
红色下划线 表示本次变更：接口整体不变，仅在 Account 结构体中新增了 AccModel 字段
enum AccountStatus {
    ENABLE = 1
    DISABLE = 2
}

enum ConversionType {
    // @desc: Tiktok Shop
    TTS = 1
    // @desc: Web
    WEB = 2
    // @desc: App
    APP = 3
}

struct RealAccModel {
    1: required i64 accModelId
    // 101000 | 201000
    2: required i64 realAccModelId
    // TTS Purchase | Web payment
    3: required string name
    // TTS | WEB
    4: required ConversionType conversionType
}

struct Account {
    // @desc: TTMS账户ID
    1: required i64 accountId
    // @desc: TTMS账户名称
    2: required string accountName
    // @desc: 账户Logo图片地址（有效期24小时）
    3: required string logoUrl
    // @desc: 国家码
    4: required string countryCode
    // @desc: 国家名称（英文）
    5: required string countryName
    // @desc: 入驻行业ID
    6: required i64 industryId
    // @desc: 入驻行业名称（英文）
    7: required string industryName
    // @desc: TTMS账户状态
    8: required AccountStatus status
    // @desc: ACC模型信息 (本次新增)
    9: optional list<RealAccModel> realAccModels
}

struct GetAccountsByAdvIdRequest {
    // @desc: Advertiser ID
    1: required i64 advId
    255: base.Base Base
}

struct GetAccountsByAdvIdResponse {
    // @desc: 关联的TTMS账户列表
    1: optional list<open.Account> accounts
    255: base.BaseResp BaseResp
}

struct GetAccountInfoRequest {
    // @desc: TTMS账户ID
    1: required i64 accountId
    255: base.Base Base
}

struct GetAccountInfoResponse {
    // @desc: 品牌信息
    1: optional open.Account account
    255: base.BaseResp BaseResp
}

service TTMSOpenService {
    GetAccountsByAdvIdResponse GetAccountsByAdvId(1: GetAccountsByAdvIdRequest req) (api.category = 'Account')
    GetAccountInfoResponse GetAccountInfo(1: GetAccountInfoRequest req) (api.category = 'Account')
}
