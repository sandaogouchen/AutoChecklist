1. [PRD] Brand Auction Ad Creation Flow Updated with Recommended Tab

1. 需求概述
本次变更针对TTAM平台S++模式下的Brand Auction类广告（包含Video View、Reach-Auction Reach、Community Interaction、Consideration投放目标），在ad层级的创意选择环节新增"Recommended Tab"。通过规范创意来源定义、召回逻辑、筛选规则与排序机制，向广告主推荐具有高VTR潜力的创意，降低广告主创意选择决策成本，提升品牌广告创意质量与投放效果，覆盖广告新建、编辑、复制全流程。

2. 功能场景拆解
2.1 功能描述：Brand Auction推荐创意的基建规则定义（来源、召回、过滤、排序）
触发条件：适用于TTAM平台S++模式下，Brand Auction类广告（Video View、Reach-Auction Reach、Community Interaction、Consideration目标）的新建、编辑、复制流程中，进入ad层级创意选择环节时；
核心业务逻辑：
创意来源定义分为两类：
Creator post / Content Suite creatives：离线帖子、从Content Suite同步的TikTok帖子（含TTO）
Advertisers' own contents：从绑定的TikTok账号（TTBA和TTBC）拉取的TikTok帖子、创意库（CL）中的所有视频素材（排除TTO同步的素材）、广告主自有/授权素材
创意召回规则：
Creator post / Content Suite creatives：基于Content Suite推荐模型，召回经品牌相关性校验的达人内容
Advertisers' own contents：当前广告主账号下有权限且cost＞0的素材
创意过滤规则：
定向国家：匹配与广告定向地域重叠的创意
素材权限：复用Spark Ads revamp接口确保用户对素材的访问权限
账户范围：限制为当前广告账户内的素材
回溯时间：优先选择近期上传或使用的素材
创意排序规则：
优先级层级：最近1周内新上传且未投过的创意 > 未投过的高VTR创意 > 已投过的高VTR创意 > 其他创意
分组排序逻辑：新素材（未投广，仅含Content Suite/TTO达人内容）按对应目标的VTR预估排序；历史素材（已投广，广告主有权限且cost＞0）按后验VTR倒序排序
不同投放目标的核心排序指标：
Reach（含Quality Reach）：2s VTR
Video View：6s VTR（对应6-second view目标）、15s VTR（对应15-second view目标）
Community Interaction（MVP阶段）：6s VTR；后续版本：Follow rate（对应Follow目标）、Engagement rate（对应profile visit目标）
Consideration（MVP阶段）：6s VTR；后续版本：CPCO
特殊场景规则：
兜底逻辑：若没有新添加的创意，或非Spark ads无法预估VTR时，VTR默认值为0（TBC）
创意库素材需排除从TTO同步的素材
2.2 功能描述：Reach目标下S++广告ad层级Recommended Tab的展示与交互
触发条件：TTAM平台S++模式下，新建/编辑/复制Reach-Auction Reach目标的广告，进入ad层级点击Add creative按钮打开创意选择抽屉时；
核心业务逻辑：
创意选择抽屉新增"Recommended Tab"，集中展示所有符合规则的推荐创意
推荐创意分为两组展示，每组hover问号图标显示对应tooltip：
TikTok creator content：tooltip内容为"We'll identify potential high-performing creator content from TikTok One and Content Suite. If you haven't used the creative assets before, select them to use in future ads ."
Your own content：tooltip内容为"We've identified creatives with high view rate potential from your Creative Library. Try out new creative assets you haven't used before."
支持编辑筛选条件：Location、Date
投放目标为Reach或Quality Reach时，展示2s VTR指标
默认状态为手动选择，无推荐创意预选
特殊场景规则：无
2.3 功能描述：Video View目标下S++广告ad层级Recommended Tab的展示与交互
触发条件：TTAM平台S++模式下，新建/编辑/复制Video View目标的广告，进入ad层级点击Add creative按钮打开创意选择抽屉时；
核心业务逻辑：
创意选择抽屉新增"Recommended Tab"，仅集中展示符合规则的视频类推荐创意
推荐创意分为两组展示，每组hover问号图标显示对应tooltip：
TikTok creator content：tooltip内容为"We'll identify potential high-performing creator content from TikTok One and Content Suite. If you haven't used the creative assets before, select them to use in future ads ."
Your own content：tooltip内容为"We've identified creatives with high view rate potential from your Creative Library. Try out new creative assets you haven't used before."
支持编辑筛选条件：Location、Date
投放目标为6-second view时展示6s VTR指标，为15-second view时展示15s VTR指标
默认状态为手动选择，无推荐创意预选
特殊场景规则：无
2.4 功能描述：Community Interaction目标下S++广告ad层级Recommended Tab的展示与交互
触发条件：TTAM平台S++模式下，新建/编辑/复制Community Interaction目标的广告，进入ad层级点击Add creative按钮打开创意选择抽屉时；
核心业务逻辑：
创意选择抽屉新增"Recommended Tab"，仅集中展示符合规则的视频类推荐创意
推荐创意分为两组展示，每组hover问号图标显示对应tooltip：
TikTok creator content：tooltip内容为"We'll identify potential high-performing creator content from TikTok One and Content Suite. If you haven't used the creative assets before, select them to use in future ads ."
Your own content：tooltip内容为"We've identified creatives with high view rate potential from your Creative Library. Try out new creative assets you haven't used before."
支持编辑筛选条件：Location、Date
投放目标为CI follow时展示Follow rate指标，为CI profile visit时展示Engagement rate指标；MVP阶段暂用6s VTR指标
默认状态为手动选择，无推荐创意预选
特殊场景规则：无
2.5 功能描述：Consideration目标下S++广告ad层级Recommended Tab的展示与交互
触发条件：TTAM平台S++模式下，新建/编辑/复制Consideration目标的广告，进入ad层级点击Add creative按钮打开创意选择抽屉时；
核心业务逻辑：
创意选择抽屉新增"Recommended Tab"，集中展示所有符合规则的推荐创意
推荐创意分为两组展示，每组hover问号图标显示对应tooltip：
TikTok creator content：tooltip内容为"We'll identify potential high-performing creator content from TikTok One and Content Suite. If you haven't used the creative assets before, select them to use in future ads ."
Your own content：tooltip内容为"We've identified creatives with high view rate potential from your Creative Library. Try out new creative assets you haven't used before."
默认状态为手动选择，无推荐创意预选
MVP阶段采用6s VTR作为排序指标，后续版本替换为CPCO指标
特殊场景规则：无


2. [Tech Design] AOS adlevel mid 支持后验指标排序

背景

While Brand advertisers have limited visibility into high-quality Content Suite creatives. Using recent ads level 2.0/3.0 upgrades in Performance Ads as reference, we aim to introduce a new and centralized “Recommended Creatives” tab that displays all recommended creatives to give advertisers clearer exposure to TikTok-recommended assets, and help them understand what is being recommended and why2.
需求文档：[PRD] Brand Auction Ad Creation Flow Updated with Recommended Tab2.
Meego：TTAM 后端技术文档 [BE Tech Design] BA creatives support Recommended Tab
业务功能 / 技术迭代方案

迭代功能

新增支持根据投后指标规则排序，vmid_rule_rank_score_res2.
PRD Todo List

是否每次请求只有一个 opt goal？多个 opt goal 排序结果如何处理？
只有一个 optgoal，但建议直接用排序指标来指定，便于扩展
指标统计时间范围？
概要设计

模块调用设计

流程设计

新增支持根据投后指标规则排序，vmid_rule_rank_score_res
上下游影响（重要）

Crux 服务新增 vmid 维度后验验证指标查询。
Caller: ad.diagnosis.ahs_strategy
接口要求

传入 mid 数量：<100
时延要求：1s
QPS：峰值 10 qps，平均 3-4 qps
时间范围：Todo: [l7d-l1d]
filter:
advertiser_id
material_id
material_type = 3
新增维度：
advertiser_id
material_id
指标：
ctr
2S VTR
6S VTR
15S VTR
Follow rate
paid profile visit rate
req_sample

req: ad.stats.crux_unified_service::queryMetricAggStat
Diagnosis 集群
core_link_material_stats
material_id
material_type
指标对应 TTAM

2S VTR -> stat_play_duration_2s_rate
6s VTR -> stat_play_duration_6s_rate
15s VTR -> engaged_view_15s_billed_vv_rate
Follows -> ad_net_follow
paid profile visit rate -> ad_home_visited_rate2.
详细设计

对外接口

https://code.byted.org/idl/i18n_ad/merge_requests/27636
修改接口：ad.diagnosis.ahs_strategy::GetMaterialScore(1:GetMaterialScoreRequest req)
// request --------------------------------------------------
struct MaterialInfo {
    1: required i64 vmid,
    2: optional i64 create_time, // timestamp
    3: optional i64 item_id,  // creator+ 新素材预估主要用这个
    4: optional ahs_common.MaterialSource material_source,
    5: optional i64 user_id,
    6: optional ahs_common.MaterialVerticalType vertical_type,
    7: optional ahs_common.VmidRankRule vmid_rank_rule,
}

struct GetMaterialScoreRequest {
    1: required i64 advertiser_id,
    2: required list<MaterialInfo> material_list,
    3: optional ahs_common.ExperimentVersion experiment_version,
    255: optional base.Base base;
}

// response -------------------------------------------------
struct GetMaterialScoreResponse {
    1: optional list<MaterialScoreInfo> vmid_score_list,
    2: optional list<MaterialScoreInfo> creator_new_material_score_list,  // creator + 新素材排序队列
    3: optional map<ahs_common.VmidRankRule, list<MaterialScoreInfo>> vmid_rule_rank_score_res,

    255: optional base.BaseResp BaseResp;
}

service AHSStragetyService {
    GetMaterialScoreResponse GetMaterialScore(1:GetMaterialScoreRequest req)
}
ahs_common

enum VmidRankRule {
    CTR = 1,
    VTR_2S = 2,
    VTR_6S = 3,
    VTR_15S = 4
    FOLLOW_RATE = 5,
    PaidProfileVisitRate = 6,
}
