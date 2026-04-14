1. [TTAM] Pulse Custom Lineups Default Frequency Cap and Minimum Campaign Length

All fields are required unless otherwise stated. We will only accept completed PRDs for the pre-review session.
Please write the PRD in English, including diagrams, flowcharts, title etc
Recommended reading to understand how we approach platform product build: TTAM Feature Guidelines and Launch/Deprecation Framework (产品原则及上下线机制)
Team Sign-offs
Instruction: The PRD should be reviewed and signed off by your +1's. For a large product feature sign-off from your +2's. For interns, +2's should sign-off and +1's should be in the pre-review meeting. Use the box below to collect their sign-offs.
Summary

This PRD proposes to update the following features on TTAM creation flow for Pulse Custom Lineups:
Lower minimum campaign length from 14 days to 7 days to unblock revenue from clients with short campaign needs
Increase the default frequency cap from "3 impressions per 7 days" to "4 impressions per 1 day" to reduce underdelivery cases where we cannot fulfill the required impressions due to a low frequency cap
Basic Info

Change Log



X-Large; Opens significant new market opportunity
Large; Major revenue impact (P0 project)
Medium; Moderate revenue impact (non-P0 project)
Small; No measurable revenue impact
UX Effort

X-Large; >4 weeks for 1 designer; Complete redesign of core user experience
Large; 2-4 weeks for 1 designer; Major changes to core features
Medium; 1-2 week for 1 designer; Noticeable changes for regular users
Small; <= 1 week for 1 designer; Minimal changes, likely unnoticed by most users
Note: Consider revenue impact in both the immediate and long term.
Problem Statement

Target Users

All advertisers using Pulse Custom Lineups (currently 127 advertisers)
User Problems

Restriction on minimum campaign length (14 days):

image.png
Many clients have campaign flights that run shorter than 14 days. Due to the current 14-day-minimum restrictions, these client teams have historically used the following workarounds:
Booked the full two-week window and then canceled in the middle of the campaign, which creates a high potential for campaign under-delivery; OR
Escalated and demanded a manual exception or workaround to enable campaign bookings, which takes a lot of manual coordination between Brand Ads and TTAM PM/PSO/RD teams and causes client frustration while they wait for the solution to unfold.
To minimize the negative impact of the above workarounds, we need a systematic solution that still enables accurate inventory forecasts and reservation ads commitments to full delivery, while automatically allowing campaigns with <14-day flight time given sufficient inventory to fulfill the campaign's minimum spend.
Frequency cap defaults to 3 times/7 days:

Custom Lineups have very limited inventory, especially in non-US countries. Therefore, the product's reach and impression forecasts assume the maximum frequency cap (4 times/1 day) to maximize impressions given a limited reach. Even on the product's CommDoc, 4 times/1 day is the recommended frequency cap (screenshot below):
image.png
However, on TTAM, the default frequency cap is 3 times/7 days, which significantly limits the number of impressions we can deliver given a small reachable audience.
image.png
As a result, most advertisers who do not customize the frequency cap are faced with higher risks of underdelivery. An example of underdelivery that happened due to low frequency cap is below:
image.png
Impact

Lowering minimum campaign duration from 14 days to 7 days:

We expect $30M in additional revenue/year unlocked from Media & Entertainment vertical alone, where clients have a hard limit of 7-day campaign length
In addition to Media & Entertainment, multiple client teams have repeatedly asked to lower the minimum campaign length requirements to run campaigns shorter than 14 days (see below)
Key reason for <14 day campaign	Description	Client team conversation screenshots
Broader campaign alignment	2-week window requirements may not always perfectly align with the desired media campaign period, making it easier to default to other efforts.	image.png / image.png
Missing out on key verticals	Media planning for some verticals, including media and entertainment, focuses on shorter bursts (typically <7 days). These flight lengths are standardized and usually non-negotiable.	image.png
Billing/tracking purposes	Billing requirements on client-side often require flexibility with the campaign set-up. Even if clients want the ability to book campaigns with shorter flight windows and adjusted budget sizes per campaign, they are still willing to spend to the min. spend.	image.png / image.png / image.png
Campaign delays	Clients may have challenges meeting their own campaign start date deadlines due to creative delays. While the start day may be moveable, often times the end date may not be, meaning they will need to pivot towards more flexible offering.	image.png
Increasing default frequency cap to 4 times/1 day:

We expect all custom lineup campaigns to benefit from a lower risk of underdelivery, which increases client trust and reduces budget loss on a reservation ads product.
Success Metrics

North Star Metrics:

Incremental revenue from all custom lineup campaigns with <14 day-length
Decreased rate of underdelivery across all custom lineup campaigns
Proposed Solution / Requirement Details

User Interaction & Design

Scenarios	Current version	Proposed version	Error States / Edge Cases
Minimum campaign length setting	image.png Show an error if campaign length is less than 14 days	image.png Only show an error if campaign length is less than 7 days	
Frequency cap setting	image.png Default frequency cap is 3 impressions over 7 days	image.png Default frequency cap is 4 impressions per day. Advertiser can still customize their frequency cap if they do not want the default frequency cap	
Impact on other TTAM flows or horizontal modules (if applicable)

Please outline the potential impact or divergence this proposal will have on other flows and modules.
If you are not sure which modules are involved, you can refer to the checklist below.
Scenarios	Current version	Proposed version
E.g., Split Test		
Proposed Launch Plan

Please review TTAM Product Launch Flow Guidelines
User Behavior Event Logging

Background: Ads Interface event-tracking standard of classification & location
Naming convention: Ads Interface Products Page Module division
Solution: TT4B Event Tracking Solution introduction｜TT4B Event Tracking Solution User Manual
Event Tracking Management: Event tracking management (design and registration)
Event Tracking Business Params Template Doc (Make a copy): business event tracking template
User behavior event doc: [Make a copy] Ads interface Front End event-tracking review template
Platform Experiment Design

Please work with your DS partners to review and sign off the experiment plan.
Guidance: Ads Interfaces Experimentation Self-serve Guide
Best practices: TTAM Experiment Design Best Practices
Experiment design example: [Experiment Design] Ad creative experience optimization
Experiment design doc: TTAM Experiment Template
Group	Traffic Allocation	Treatment (what's different)	Design
v1 (Control)			
v2			
Checklist

Compliance & Safety

【动态更新】国际产品线 - 合规评估适用场景说明 Situations Subject to Compliance Review
Platform/Product(s)	Objectives & Buying Type	Placements	TTAM Platform Modules
Appendix

Brainstormed Ideas & Options Considered - Link to References / Screenshot
Competitors & Product Inspiration - Link to References / Screenshot
Future Work - List follow-up features if there are any
Meeting Notes - Update discussion notes from alignment meetings if there are any
2. [FE Design] Pulse Custom Lineups Default Frequency Cap and Minimum Campaign Length

Relevant Links

POC	Links	PM
@Laurence Tran @彭晓		
Meego	
PRD	[TTAM] Pulse Custom Lineups Default Frequency Cap and Minimum Campaign Length
BE	
QA	self-test
Translate Doc	
PPE/BOE Env	
Code Branch	
Background and Goal

Target Users

All advertisers using Pulse Custom Lineups (currently 127 advertisers)
User Problems

Restriction on minimum campaign length (14 days):

image.png
Many clients have campaign flights that run shorter than 14 days. Due to the current 14-day-minimum restrictions, these client teams have historically used the following workarounds:
Booked the full two-week window and then canceled in the middle of the campaign, which creates a high potential for campaign under-delivery; OR
Escalated and demanded a manual exception or workaround to enable campaign bookings, which takes a lot of manual coordination between Brand Ads and TTAM PM/PSO/RD teams and causes client frustration while they wait for the solution to unfold.
To minimize the negative impact of the above workarounds, we need a systematic solution that still enables accurate inventory forecasts and reservation ads commitments to full delivery, while automatically allowing campaigns with <14-day flight time given sufficient inventory to fulfill the campaign's minimum spend.
Frequency cap defaults to 3 times/7 days:

Custom Lineups have very limited inventory, especially in non-US countries. Therefore, the product's reach and impression forecasts assume the maximum frequency cap (4 times/1 day) to maximize impressions given a limited reach. Even on the product's CommDoc, 4 times/1 day is the recommended frequency cap (screenshot below):
image.png
However, on TTAM, the default frequency cap is 3 times/7 days, which significantly limits the number of impressions we can deliver given a small reachable audience.
image.png
As a result, most advertisers who do not customize the frequency cap are faced with higher risks of underdelivery. An example of underdelivery that happened due to low frequency cap is below:
image.png
Detailed Design

Logic Analysis

For Pulse Custom Lineup, we are going to make modifications to two restrictions:
Minimum campaign length setting ====> from 14 days ====> 7 days
Frequency cap setting ====> from 3 impressions over 7 days ====> Default frequency cap is 4 impressions per day, user able to adjust.
Component Design

* 必填

Creation 开发指南：TTAM Creation Developer Guide、评估 Checklist: Creation 复制场景评估 checklist
大原则：创编流程 -> 模块 -> 具体功能场景
* 功能描述

* 交互

* 模块逻辑设计

* 模块影响


1-N-N Creation Flow

Minimum campaign length setting

When user selects Custom Lineup in Pulse creation, error state is shown when the selected time is shorter than a specified time range
Current: user will get error message when selected time range is shorter than 14 days
New: user will get error message when selected time range is shorter than 7 days
Frequency cap setting

When user selects Custom Lineup in Pulse creation, In frequency cap setting, user can choose from two options, default option and custom option
Current: the default option is 'Show ads no more than 3 times every 7 days'
New: the default option is 'Show ads no more than 4 times per day', custom option is unchanged.
Minimum campaign length setting

Current UI:
image.png
New UI:
image.png
Frequency cap setting

Current UI
image.png
New UI
image.png
Minimum campaign length setting

Need change on Starling Key
module_rf_content_targeting_custom_lineups_time_validate_minimum_error_msg
Current: "Campaigns using a custom lineup must be at least 14 days in duration."
New: "Campaigns using a custom lineup must be at least 7 days in duration."
Change MIN_CUSTOM_LINEUP_SCHEDULE from 14 to 7
apps/rf-creation/src/constants/schedule-budget.ts
image.png
Frequency cap setting

Starling Key:
No extra changes
Change default option display in pulsePremiereFrequencyCapOptions
image.png
For ENUM_COVER_FREQUENCY_TYPE_VALUE
Originally, custom lineup uses option default and custom, where default means 3 impressions / 7 days
We updated custom lineup to use option tentpoleEventDefault and custom, which means 4 impressions per day
And when we select tentpoleEventDefault, custom option default values automatically updates to 4 and 1 following current logic, no changes needed.
image.png
Make sure after selecting default, FREQUENCY_FIELD and FREQUENCY_SCHEDULE_FIELD contains the right number in all the reactions.
Reaction when start-time and end-time changes:
Keep same
Reaction when contextual_tags and contextual_extend_type changes:
Keep same
Reaction when type changes (tentpoleEventDefault and custom):
Keep same
Code repository: ttam_brand_mono/apps/rf-creation
Pulse Custom Lineup Starling Keys