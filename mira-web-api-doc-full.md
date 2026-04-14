# Mira 前端 API 接口完整文档

> 从 `cis-mira` 前端源码 `src/api/`、`src/constants/api.ts`、`src/features/*/api/` 中完整提取。
> 生成时间：2026-04-09

---

## 目录

1. [Base URL 与公共约定](#1-base-url-与公共约定)
2. [会话管理 (Chat/Session)](#2-会话管理-chatsession)
3. [消息管理 (Message)](#3-消息管理-message)
4. [流式消息服务 (Stream)](#4-流式消息服务-stream)
5. [用户与认证 (User & Auth)](#5-用户与认证-user--auth)
6. [文件与上传 (File & Upload)](#6-文件与上传-file--upload)
7. [模型管理 (Model)](#7-模型管理-model)
8. [技能 & 模板管理 (Skill & Template)](#8-技能--模板管理-skill--template)
9. [工具管理 (Tool)](#9-工具管理-tool)
10. [资源搜索 (Resource & Search)](#10-资源搜索-resource--search)
11. [URL 预览](#11-url-预览)
12. [用户设置 (User Settings)](#12-用户设置-user-settings)
13. [全局配置 (Config)](#13-全局配置-config)
14. [DevOps 运维接口](#14-devops-运维接口)
15. [异步任务管理 (Task)](#15-异步任务管理-task)
16. [定时任务调度 (Scheduler)](#16-定时任务调度-scheduler)
17. [报表活动 (Report Campaign)](#17-报表活动-report-campaign)
18. [Persona 人设管理](#18-persona-人设管理)
19. [消息反思 (Message Reflection)](#19-消息反思-message-reflection)
20. [增长绩效 (Growth Performance)](#20-增长绩效-growth-performance)
21. [数据源冗余识别](#21-数据源冗余识别)
22. [财务 AI 接口 (Finance/AICEO)](#22-财务-ai-接口-financeaiceo)
23. [加密解密](#23-加密解密)
24. [API 路由总表](#24-api-路由总表)

---

## 1. Base URL 与公共约定

### 1.1 路由前缀常量

| 常量名 | 值 | 说明 |
|---|---|---|
| `API_BASE` | `/api` | 基础 API |
| `API_BASE_V1` | `/api/v1` | V1 版本 |
| `API_BASE_V2` | `/api/v2` | V2 版本 |
| `MIRA_API_V1` | `/mira/api/v1` | Mira V1 核心 |
| `MIRA_API_CHAT_V1` | `/mira/api/v1/chat` | 聊天核心 |
| `MIRA_API_LARK_V1` | `/mira/api/v1/lark` | 飞书集成 |
| `CHAT_API_BASE_V1` | `/api/v1/chat` | V1 聊天 |
| `MODEL_API_BASE` | `/api/v1/model` | 模型 |
| `DEVOPS_API_BASE` | `/devops` | DevOps |
| `UPLOAD_API_BASE` | `/upload` | 上传 |
| `GLOBAL_CONFIG` | `/global_config` | 全局配置 |
| `AICEO_PROXY_PATH` | `/aicoe/api` | AICEO 代理 |

### 1.2 公共请求头

所有请求通过 `fetchWithJWT` 统一发送，自动注入：

| Header | 说明 |
|---|---|
| `jwt-token` | JWT 认证 Token（从 `window.jwt_token` 获取） |
| `x-mira-client` | 客户端版本号（从 `window.MIRA_CLIENT_VERSION` 获取） |
| `x-mira-timezone` | 用户时区（如 `Asia/Shanghai`） |

### 1.3 通用响应结构

**baseResp 风格**（用于 echo 服务端接口）：
```typescript
{
  success: boolean;
  baseResp: {
    statusCode: number;    // 0 = 成功
    statusMessage: string;
  };
}
```

**code/msg 风格**（用于 Mira 自有接口）：
```typescript
{
  code: number;      // 0 = 成功
  msg: string;
  log_id?: string;
  data?: any;
}
```

### 1.4 业务错误类 `BizError`

```typescript
class BizError extends Error {
  code: number;    // 默认 -1
  msg: string;     // 默认 'biz unknown error'
  logId?: string;
}
```

---

## 2. 会话管理 (Chat/Session)

### 2.1 创建会话

| 项 | 值 |
|---|---|
| **常量** | `CREATE_CHAT_V1` |
| **URL** | `POST /mira/api/v1/chat/create` |

**Request Body** (`CreateSessionRequestBody`):
```typescript
{
  sessionProperties: {
    topic: string;                         // 会话标题
    dataSource: DataSource;                // 默认数据源
    dataSources: DataSource[];             // 数据源列表（必选）
    presetInitialMessageType?: string;     // 预设初始消息类型
    model?: string;                        // 指定模型
  }
}
```

**Response** (`CreateChatResponse`):
```typescript
{
  sessionItem: {
    sessionId: string;
    startTime: number;
    updateTime: number;
    status: string;
    pin?: number;                          // 1=置顶
    sys_label?: string;
    sessionProperties: {
      topic: string;
      dataSource: DataSource;
      dataSources: DataSource[];
      model?: string;
      sessionType?: number;                // 1=系统bot会话
    };
    tasks?: AsyncTaskDetails[];
  }
}
```

---

### 2.2 获取会话详情

| 项 | 值 |
|---|---|
| **常量** | `GET_CHAT_V1` |
| **URL** | `GET /api/v1/chat/?session_id={sessionId}` |

**Response** (`GetChatServerResponse`):
```typescript
{
  success: boolean;
  sessionItem: SessionItem;
  baseResp: { statusCode: number; statusMessage: string };
}
```

---

### 2.3 获取会话列表

| 项 | 值 |
|---|---|
| **常量** | `GET_CHAT_LIST_V1` |
| **URL** | `GET /api/v1/chat/list?pageSize={n}&pageNumber={n}` |

**Query Params**:

| 参数 | 类型 | 说明 |
|---|---|---|
| `pageSize` | number | 每页数量 |
| `pageNumber` | number | 页码 |

**Response** (`GetChatListServerResponse`):
```typescript
{
  sessions: SessionItem[];
  pagination: {
    pageSize: number;
    pageNumber: number;
    total: number;
    hasMore: boolean;
  };
  baseResp: { statusCode: number; statusMessage: string };
}
```

---

### 2.4 更新会话

| 项 | 值 |
|---|---|
| **常量** | `UPDATE_CHAT_V1` |
| **URL** | `POST /api/v1/chat/update` |

**Request Body** (`UpdateChatRequestBody`):
```typescript
{
  sessionId: string;            // 必选
  sessionProperties: {
    topic?: string;
    dataSource?: DataSource;
    dataSources?: DataSource[];
    model?: string;
    sessionType?: number;
  }
}
```

**Response** (`UpdateChatServerResponse`):
```typescript
{
  success: boolean;
  sessionItem: SessionItem;
  baseResp: { statusCode: number; statusMessage: string };
}
```

---

### 2.5 删除会话

| 项 | 值 |
|---|---|
| **常量** | `DELETE_CHAT_V1` |
| **URL** | `POST /api/v1/chat/delete` |

**Request Body**:
```typescript
{ sessionId: string }
```

---

### 2.6 终止会话

| 项 | 值 |
|---|---|
| **常量** | `TERMINATE_CHAT_V1` |
| **URL** | `POST /api/v1/chat/terminate` |

**Request Body** (`TerminateChatRequestBody`):
```typescript
{
  sessionId: string;
  messageSnapshot: Message;    // 当前消息快照
}
```

---

### 2.7 置顶/取消置顶

| 项 | 值 |
|---|---|
| **常量** | `PIN_CHAT_V1` |
| **URL** | `POST /mira/api/v1/chat/pin` |

**Request Body**:
```typescript
{
  session_id: string;
  pin: 0 | 1;                 // 0=取消置顶, 1=置顶
}
```

**Response**:
```typescript
{ code: number; msg: string; data: {} }
```

---

## 3. 消息管理 (Message)

### 3.1 获取会话消息列表

| 项 | 值 |
|---|---|
| **常量** | `GET_CHAT_MESSAGES_V1` |
| **URL** | `POST /mira/api/v1/chat/messages` |

**Request Body** (`GetChatMessagesParams`):
```typescript
{
  sessionId: string;
  pagination?: {
    pageSize?: number;
    pageNumber?: number;
  };
  startRound?: number;        // 起始轮次
  endRound?: number;          // 结束轮次
}
```

**Response** (`GetChatMessagesServerResponse`):
```typescript
{
  messages: RawMessage[];
  baseResp: { statusCode: number; statusMessage: string };
}
```

**`RawMessage` 核心字段**:
```typescript
{
  messageId: string;
  sessionId: string;
  content: string;
  contentType: string;
  messageType: string;
  roundIndex: number;
  sequence: number;
  timestamp: number;
  sender: string;
  dataSources: DataSource[];
  extra: {
    summaryWordCount?: number;
    summaryCostTime?: number;
    inferenceContentCostTime?: number;
    debugLink?: string;
    config?: {
      online?: boolean;
      mode?: 'quick' | 'deep';
      model?: string;
      skill_names?: string[];
      agent_name?: string;
      agent_params?: {
        source_lang: 'auto-detect' | 'zh-CN' | 'en-US';
        target_lang: 'zh-CN' | 'en-US';
      };
    };
  };
  tasks?: TaskDetail[];
  referenceInfo?: ReferenceInfo;
  attachments?: FileAttachment[];
}
```

**`FileAttachment` 类型**:
```typescript
{
  file_name: string;
  uri: string;
  url: string;
  mime_type: string;
  type?: 'lark_drive';
  thumb_url?: string;
  create_time?: number;
}
```

---

### 3.2 获取单条消息

| 项 | 值 |
|---|---|
| **常量** | `TEMPLATE_GET_CHAT_MESSAGE_V1` |
| **URL** | `GET /api/v1/chat/:session_id/message/:message_id` |

**Path Params**:

| 参数 | 说明 |
|---|---|
| `:session_id` | 会话 ID |
| `:message_id` | 消息 ID |

---

### 3.3 消息交互 (点赞/点踩)

| 项 | 值 |
|---|---|
| **常量** | `INTERACT_MESSAGE_V1` |
| **URL** | `POST /api/v1/chat/message/interaction` |

**Request Body** (`InteractMessageParams`):
```typescript
{
  messageId: string;
  action: string;              // 交互动作标识
}
```

---

### 3.4 消息回撤 (Rewind)

| 项 | 值 |
|---|---|
| **常量** | `REWIND_CHAT_V1` |
| **URL** | `POST /mira/api/v1/chat/rewind` |

**Request Body**:
```typescript
{ message_id: string }
```

**Response** (`RewindChatResponse`):
```typescript
{ code: number; msg: string; data: Record<string, unknown> }
```

---

### 3.5 关联推荐查询

| 项 | 值 |
|---|---|
| **常量** | `GET_RELATED` |
| **URL** | `POST /mira/api/v1/chat/more_query` |

**Request Body** (`GetRelatedParams`):
```typescript
{
  session_id: string;
  message_ids: string[];
  num?: number;                // 返回数量
}
```

**Response** (`GetRelatedResponse`):
```typescript
{
  code: number;
  msg: string;
  data: {
    questions: string[];
    count: number;
  };
}
```

---

### 3.6 导出消息为飞书文档

| 项 | 值 |
|---|---|
| **常量** | `DOC_EXPORT` |
| **URL** | `POST /mira/api/v1/chat/export_message` |

**Request Body**:
```typescript
{
  message_id: string;
  assisted_message_id?: string[];   // 辅助消息 ID 列表
}
```

**Response**:
```typescript
{
  code: number;
  msg?: string;
  data?: { url?: string };          // 飞书文档 URL
}
```

---

## 4. 流式消息服务 (Stream)

### 4.1 发送消息 (SSE 流式)

| 项 | 值 |
|---|---|
| **常量** | `SEND_MESSAGE_V1` |
| **URL** | `POST /mira/api/v1/chat/completion` |
| **协议** | SSE (Server-Sent Events)，使用 `@microsoft/fetch-event-source` |

**Request Body** (`SendMessageRequestBody`):
```typescript
{
  sessionId: string;
  content: string;
  messageType: number;                    // 消息类型（Text / Skill 等）
  summaryAgent: string;                   // 模型名称
  dataSources: DataSource[];
  comprehensive: 0 | 1;                  // 0=关闭, 1=开启综合模式
  referenceInfo?: ReferenceInfo;
  attachments?: FileAttachment[];
  config?: {
    online?: boolean;
    mode?: string;                        // 'quick' | 'deep'
    model?: string;
    tool_list?: Array<{ name: string; id?: number; scope?: string }>;
    agent_name?: string;
    agent_params?: Record<string, unknown>;
    skill_names?: string[];
  };
  meta?: {
    location?: {
      type?: 'wgs-84' | 'gcj-02';       // 坐标系
      lng: string;                        // 经度
      lat: string;                        // 纬度
    };
    user_query_context?: string;
  };
}
```

**SSE 事件流**：服务端通过 SSE 逐步返回消息片段。

---

### 4.2 恢复流式消息

| 项 | 值 |
|---|---|
| **常量** | `RESUME_STREAM_MESSAGE_V1` |
| **URL** | `POST /mira/api/v1/chat/completion/resume` |

**Request Body** (`ResumeStreamMessageRequestBody`):
```typescript
{
  sessionId: string;
  messageId: string;
  // 其他断点恢复相关字段
}
```

---

### 4.3 终止流式生成

| 项 | 值 |
|---|---|
| **URL** | `POST /api/v1/chat/completion/terminate` |
| **说明** | Stream feature 内部独立定义的终止接口 |

**Request Body**:
```typescript
{ messageId: string }
```

---

## 5. 用户与认证 (User & Auth)

### 5.1 获取当前用户信息

| 项 | 值 |
|---|---|
| **常量** | `GET_USER_INFO` |
| **URL** | `GET /api/userinfo` |

**Response** (`UserInfo`):
```typescript
{
  sub?: string;                    // open_id
  name: string;                    // 用户姓名
  picture?: string;                // 头像 URL
  open_id: string;
  union_id?: string;
  en_name: string;                 // 英文名
  tenant_key: string;              // 租户标识
  avatar_url: string;
  avatar_thumb: string;            // 72x72
  avatar_middle: string;           // 240x240
  avatar_big: string;              // 640x640
  user_id?: string;
  email?: string;
  mobile?: string;
  platform: string;                // 'feishu' | 'larksuite'
  employee_number?: string;        // 工号
  department: string;
  department_id: string;
}
```

---

### 5.2 根据 UID 批量获取用户信息

| 项 | 值 |
|---|---|
| **常量** | `GET_USER_INFOS` |
| **URL** | `POST /api/getOpenIdByUid` |

**Request Body**:
```typescript
{ uids: string[] }
```

**Response**: `UserInfo[]`

---

### 5.3 根据 PeopleEmployeeId 获取工号

| 项 | 值 |
|---|---|
| **常量** | `GET_EMPLOYEE_NUMBER_BY_JOB_IDS` |
| **URL** | `POST /api/getEmployeeNumberByPeopleEmployeeId` |

**Request Body**:
```typescript
{ people_employee_ids: string[] }
```

**Response**:
```typescript
{ employee_numbers: string[] }
```

---

### 5.4 ID 转换

| 项 | 值 |
|---|---|
| **常量** | `ID_CONVERT` |
| **URL** | `POST /api/idconvert` |

**Request Body**:
```typescript
{
  id: string;
  id_transform_type: number;
}
```

**Response**:
```typescript
{ id: string }
```

---

### 5.5 搜索员工

| 项 | 值 |
|---|---|
| **常量** | `SEARCH_EMPLOYEES` |
| **URL** | `GET /api/search_employees?query={keyword}` |

**Response**: `Employee[]`

```typescript
interface Employee {
  avatar: string;
  name: { default_value: string; i18n_value: { en_us: string; zh_cn: string } };
  employee_id: string;
  // ...
}
```

---

### 5.6 搜索部门

| 项 | 值 |
|---|---|
| **常量** | `SEARCH_DEPARTMENTS` |
| **URL** | `GET /api/search_departments?query={keyword}` |

**Response**: `SearchDepartment[]`

```typescript
interface SearchDepartment {
  data_source: number;
  department_id: string;
  name: {
    default_value: string;
    i18n_value: { en_us: string; ja_jp: string; zh_cn: string };
  };
}
```

---

### 5.7 按部门获取员工

| 项 | 值 |
|---|---|
| **常量** | `SEARCH_USERS_BY_DEPARTMENT` |
| **URL** | `GET /api/get_employees_by_departmentId?department_id={id}` |

**Response**: `Employee[]`

---

### 5.8 飞书组件鉴权签名

| 项 | 值 |
|---|---|
| **常量** | `GET_LARK_COMPONENT_AUTH` |
| **URL** | `GET /api/signature?originUrl={encodedUrl}` |

---

### 5.9 刷新 Token

| 项 | 值 |
|---|---|
| **常量** | `REFRESH_TOKEN` |
| **URL** | `GET /api/refreshToken` |

**Response**:
```typescript
{ code: number; msg: string }     // code=0 表示成功
```

---

### 5.10 验证 Token

| 项 | 值 |
|---|---|
| **常量** | `VALIDATE_TOKEN` |
| **URL** | `GET /api/validate_tokens` |

**Response**:
```typescript
{
  cis_access_token: boolean;
  cis_refresh_token: boolean;
  cis_tenant_token: boolean;
  cis_aico_session: boolean;
}
```

---

### 5.11 登录

| 项 | 值 |
|---|---|
| **常量** | `SIGN_IN` |
| **URL** | `GET /api/sigin` |

---

### 5.12 登出

| 项 | 值 |
|---|---|
| **常量** | `SIGN_OUT` |
| **URL** | `GET /api/signout` |

---

## 6. 文件与上传 (File & Upload)

### 6.1 文件上传 V1

| 项 | 值 |
|---|---|
| **常量** | `UPLOAD_FILE_V1` |
| **URL** | `POST /mira/api/v1/file/upload?sensitive_detection={bool}` |
| **Content-Type** | `multipart/form-data`（浏览器自动设置 boundary） |

**Request**: FormData，字段名 `files`，支持多文件

**Response** (`UploadResponseV1`):
```typescript
{
  code: number;
  log_id: string;
  msg: string;
  data: {
    file_infos: Array<{
      file_name: string;
      url: string;              // CDN 访问地址
      uri: string;              // TOS 存储路径
      mime_type: string;
      sensitive?: boolean;
      is_sensitive?: boolean;
    }>;
  };
}
```

---

### 6.2 文件上传 (Legacy)

| 项 | 值 |
|---|---|
| **常量** | `UPLOAD_FILE` |
| **URL** | `POST /upload/files` |
| **Content-Type** | `multipart/form-data` |

**Response** (`UploadResponse`):
```typescript
{
  code: number;
  message: string;
  data: UploadFileData | UploadFileData[];
}

interface UploadFileData {
  originalname: string;
  filename: string;
  tosPath: string;
  cdnUrl: string;
  size: number;
  mimetype: string;
  uploadTime: string;
  sensitive?: boolean;
}
```

---

### 6.3 获取文件 URL

| 项 | 值 |
|---|---|
| **URL** | `GET /mira/api/v1/file/url/get?url={encodedUrl}` |

**Response**:
```typescript
{
  code: number;
  msg?: string;
  message?: string;
  data?: { url: string };
}
```

---

## 7. 模型管理 (Model)

### 7.1 获取模型元数据

| 项 | 值 |
|---|---|
| **常量** | `MODEL_METADATA` |
| **URL** | `GET /api/v1/model/metadata` |

**Response** (`ModelMetadataResponse`):
```typescript
{
  code: number;
  success: boolean;
  data: {
    models: ModelMetadataItem[];
  };
}

interface ModelMetadataItem {
  key: string;                  // 模型标识
  desc: string;                 // 展示名称
  category?: string;            // 模型分类
  new?: boolean;                // 是否新模型
  default?: boolean;            // 是否默认
  visible?: boolean;            // 是否展示
  support_thinking?: boolean;   // 是否支持思考
  vl: boolean;                  // 是否支持 VL (Vision-Language)
}
```

---

## 8. 技能 & 模板管理 (Skill & Template)

> Base: `/mira/api/v1/skill`

### 8.1 获取 Skill 工具列表

| 项 | 值 |
|---|---|
| **URL** | `GET /mira/api/v1/skill/list?type={market|custom|all}` |
| **Header** | `x-mira-user-id: {userId}`（可选） |

**Response** (`SkillToolListResponse`):
```typescript
{
  code: number;
  msg?: string;
  data?: {
    markets: SkillToolMarket[];
    customs: SkillToolCustom[];
  };
}

interface SkillToolMarket {
  skill_key: string;
  type: 'market';
  name: string;
  description: string;
  enabled: boolean;
  added: boolean;
}

interface SkillToolCustom {
  skill_key: string;
  type: 'custom';
  source?: 'api' | 'agent';
  name: string;
  description: string;
  instructions?: string;
  status?: 'pending_review' | 'reviewing' | 'approved' | 'rejected' | 'active';
  enabled: boolean;
  is_owner: boolean;
  reject_reason?: string;
  added: boolean;
}
```

---

### 8.2 获取模板列表

| 项 | 值 |
|---|---|
| **URL** | `GET /mira/api/v1/skill/template/list?sort_type={usage}` |

**Response**:
```typescript
{
  code: number;
  log_id: string;
  msg: string;
  data: {
    items: Item[];
  };
}

interface Item {
  key: string;
  name: string;
  desc: string;
  creator: string;
  category: string;
  tag?: string[];
  prompt: { content: string; variables?: PromptVariable[] };
  model_config: {
    mode: string;
    model: string;
    tools: Array<{ name: string; scope?: 'GLOBAL' | 'USER'; id?: string }>;
    agent_name?: string;
  };
  usage_count: number;
  create_time: number;
  source?: 'official' | 'user';
  scope?: 1 | 2;                   // 1=私有, 2=公开
  is_favorited?: boolean;
  is_owner?: boolean;
}

interface PromptVariable {
  key: string;
  placeholder: string;
  variable_type: string;
}
```

---

### 8.3 获取我的模板

| 项 | 值 |
|---|---|
| **URL** | `GET /mira/api/v1/skill/template/my?tab={created|favorited}` |

**Response**:
```typescript
{
  code: number;
  data: {
    items: Item[];
    created_count: number;
    favorited_count: number;
  };
}
```

---

### 8.4 创建模板

| 项 | 值 |
|---|---|
| **URL** | `POST /mira/api/v1/skill/template/create` |

**Request Body** (`CreateTemplateRequest`):
```typescript
{
  name: string;
  desc: string;
  scope: 1 | 2;                        // 1=私有, 2=公开
  category?: string;
  prompt: {
    content: string;
    variables?: PromptVariable[];
  };
  model_config?: {
    mode: string;
    model: string;
    tools?: Array<{ name: string; id?: number; scope?: string }>;
    agent_name?: string;
  };
  tag?: string[];
}
```

**Response**: `{ code: number; data: { key: string } }`

---

### 8.5 更新模板

| 项 | 值 |
|---|---|
| **URL** | `POST /mira/api/v1/skill/template/update` |

**Request Body** (`UpdateTemplateRequest`):
```typescript
{
  key: string;                          // 必选，模板标识
  name?: string;
  desc?: string;
  scope?: 1 | 2;
  category?: string;
  prompt?: { content: string; variables?: PromptVariable[] };
  model_config?: { mode: string; model: string; tools?: Array<...>; agent_name?: string };
  tag?: string[];
}
```

---

### 8.6 删除模板

| 项 | 值 |
|---|---|
| **URL** | `POST /mira/api/v1/skill/template/delete` |

**Request Body**: `{ key: string }`

---

### 8.7 收藏/取消收藏模板

| 项 | 值 |
|---|---|
| **URL** | `POST /mira/api/v1/skill/template/favorite` |

**Request Body**: `{ key: string; action: 'add' | 'remove' }`

---

### 8.8 分享模板

| 项 | 值 |
|---|---|
| **URL** | `POST /mira/api/v1/skill/template/share` |

**Request Body**: `{ key: string }`

**Response**: `{ code: number; data: { share_key: string } }`

---

### 8.9 获取分享模板详情

| 项 | 值 |
|---|---|
| **URL** | `GET /mira/api/v1/skill/template/share/{shareKey}` |

**Response**:
```typescript
{
  code: number;
  data: {
    template: Item;
    sharer: { uid: string };
    unavailable_tools?: Array<{ name: string; reason: string }>;
  };
}
```

---

### 8.10 追踪技能使用

| 项 | 值 |
|---|---|
| **URL** | `POST /mira/api/v1/skill/usage/track` |

**Request Body**: `{ key: string }`

---

### 8.11 从会话智能生成模板

| 项 | 值 |
|---|---|
| **URL** | `POST /mira/api/v1/skill/gen` |

**Request Body** (`GenerateTemplateRequest`):
```typescript
{
  session_id: string;
  model?: string;
  source?: string;
  tools?: string[];
}
```

**Response** (`GenerateTemplateResponse`):
```typescript
{
  name: string;
  desc: string;
  prompt: { content: string };
  model_config?: {
    mode: string;
    model: string;
    tools: Array<{ name: string }>;
  };
  sensitive: boolean;
}
```

---

### 8.12 智能提取 Prompt 参数

| 项 | 值 |
|---|---|
| **URL** | `POST /mira/api/v1/skill/param/extract` |

**Request Body**: `{ prompt: string }`

**Response** (`ExtractParamsResponse`):
```typescript
{
  content: string;                      // 参数化后的 prompt
  variables: Array<{
    key: string;
    placeholder: string;
    variable_type: string;
  }>;
  sensitive: boolean;
}
```

---

### 8.13 Prompt 优化

| 项 | 值 |
|---|---|
| **常量** | `PROMPT_OPTIMIZE` |
| **URL** | `POST /mira/api/v1/prompt/optimize` |

---

## 9. 工具管理 (Tool)

### 9.1 获取工具列表（简版）

| 项 | 值 |
|---|---|
| **常量** | `TOOLS_LIST` |
| **URL** | `GET /mira/api/v1/tools?category={category}` |

**Response**:
```typescript
{
  code: number;
  data?: {
    tools?: Array<{
      id: string;
      name: string;
      display_name: Record<string, string>;  // { 'en-US': '...', 'zh-CN': '...' }
      category: string;
      description?: string;
      icon?: string;
      url?: string;
    }>;
  };
}
```

---

### 9.2 获取工具包列表（完整版）

| 项 | 值 |
|---|---|
| **URL** | `POST /mira/api/v1/tool/packages` |

**Request Body**:
```typescript
{ category: string[] }                  // 如 ['search', 'mcp']
```

**Response**:
```typescript
{
  code: number;
  msg?: string;
  data?: { tools?: RawToolItem[] };
}
```

---

## 10. 资源搜索 (Resource & Search)

### 10.1 飞书云文档搜索

| 项 | 值 |
|---|---|
| **常量** | `RESOURCE_SEARCH_API` |
| **URL** | `POST /mira/api/v1/lark/search/drive` |

**Request Body** (`ResourceSearchParams`):
```typescript
{
  query: string;
  docs_types?: ('doc' | 'sheet' | 'slides' | 'bitable' | 'mindnote' | 'file')[];
  count?: number;               // 默认 10
  offset?: number;              // 默认 0
}
```

**Response** (`ResourceSearchResponse`):
```typescript
{
  code: number;
  msg?: string;
  data?: {
    items: Array<{
      docs_token: string;
      docs_type: DocsType;
      title: string;
      owner_id?: string;
    }>;
    has_more: boolean;
    total?: number;
  };
}
```

---

### 10.2 飞书 Wiki 搜索

| 项 | 值 |
|---|---|
| **常量** | `WIKI_SEARCH_API` |
| **URL** | `POST /mira/api/v1/lark/search/wiki` |

**Request Body** (`WikiSearchParams`):
```typescript
{
  query: string;
  page_size?: number;           // 默认 10
  page_token?: string;
}
```

**Response** (`WikiSearchResponse`):
```typescript
{
  code: number;
  data?: {
    items: Array<{
      docs_token: string;
      docs_type: DocsType;
      title: string;
      url: string;
    }>;
    has_more: boolean;
    page_token?: string;
    total?: number;
  };
}
```

---

### 10.3 飞书群聊搜索

| 项 | 值 |
|---|---|
| **常量** | `CHAT_SEARCH_API` |
| **URL** | `GET /mira/api/v1/lark/search/chats?query={q}&page_size={n}&page_token={t}` |

**Response** (`ChatSearchResponse`):
```typescript
{
  code: number;
  data?: {
    items: Array<{
      chat_id: string;
      name: string;
      avatar?: string;
    }>;
    has_more: boolean;
    page_token?: string;
  };
}
```

---

## 11. URL 预览

| 项 | 值 |
|---|---|
| **常量** | `URL_PREVIEW_API` |
| **URL** | `POST /mira/api/v1/lark/drive/meta/list` |

**Request Body** (`UrlPreviewParams`):
```typescript
{ urls: string[] }
```

**Response**:
```typescript
{
  code: number;
  msg?: string;
  data: {
    metas: Array<{
      url: string;
      title: string;
      // ...其他 LinkPreview 字段
    }>;
  };
}
```

---

## 12. 用户设置 (User Settings)

### 12.1 获取用户设置

| 项 | 值 |
|---|---|
| **URL** | `GET /mira/api/v1/user/settings/get` |

**Response**:
```typescript
{
  code: number;
  msg: string;
  data: {
    settings: Record<string, string>;   // key-value 键值对
  };
}
```

---

### 12.2 保存用户设置

| 项 | 值 |
|---|---|
| **URL** | `POST /mira/api/v1/user/settings/save` |
| **说明** | 增量更新，只更新传入的 key/value |

**Request Body**:
```typescript
{
  settings: Record<string, string>;
}
```

**Response**:
```typescript
{ code: number; msg: string }
```

---

## 13. 全局配置 (Config)

### 13.1 Web 配置

| 项 | 值 |
|---|---|
| **常量** | `WEB_CONFIGS` |
| **URL** | `GET /global_config/web_configs` |

---

## 14. DevOps 运维接口

### 14.1 获取角色

| 项 | 值 |
|---|---|
| **常量** | `GET_ROLE` |
| **URL** | `GET /devops/get_role` |

**Response**:
```typescript
{ code: number; msg: string; data: GetRoleResponse }
```

---

### 14.2 切换角色

| 项 | 值 |
|---|---|
| **常量** | `CHANGE_ROLE` |
| **URL** | `GET /devops/change_role?employee_number={}&name={}&email={}&user_id={}` |

**Query Params**:

| 参数 | 类型 | 必选 | 说明 |
|---|---|---|---|
| `employee_number` | string | 否 | 工号 |
| `name` | string | 否 | 姓名 |
| `email` | string | 否 | 邮箱 |
| `user_id` | string | 否 | 用户 ID |

---

### 14.3 重置角色

| 项 | 值 |
|---|---|
| **URL** | `GET /devops/reset_role` |

---

### 14.4 重放查询

| 项 | 值 |
|---|---|
| **常量** | `REPLAY_QUERY` |
| **URL** | `POST /devops/replay` |

**Request Body**:
```typescript
{
  user: { employeeNumber: string; email: string };
  query: string;
  datasource: DataSource;
  isReport?: boolean;
  isAsync?: boolean;
}
```

---

### 14.5 分享会话

| 项 | 值 |
|---|---|
| **常量** | `SHARE_SESSION` |
| **URL** | `POST /devops/share_session` |

**Request Body**:
```typescript
{
  session: string;                      // sessionId
  data: Record<string, any>;
}
```

**Response**:
```typescript
{
  success: boolean;
  shareUrl?: string;
  message?: string;
}
```

---

## 15. 异步任务管理 (Task)

> Base: `/api/v1/task`

### 15.1 获取任务详情

| 项 | 值 |
|---|---|
| **URL** | `GET /api/v1/task/status?taskId={id}&sessionId={id}` |

**Response**:
```typescript
{
  success: boolean;
  message?: string;
  taskDetails: TaskDetail;             // 包含 extra (JSON 字符串自动解析)
}
```

---

### 15.2 创建异步任务

| 项 | 值 |
|---|---|
| **URL** | `POST /api/v1/task/create` |

**Request Body** (`CreateTaskParams`):
```typescript
{
  sessionId: string;
  // 其他 CreateAsyncTaskRequestOptions 字段
}
```

---

### 15.3 获取任务列表

| 项 | 值 |
|---|---|
| **URL** | `GET /api/v1/task/list?sessionId={id}&messageId={id}` |

---

### 15.4 取消任务

| 项 | 值 |
|---|---|
| **URL** | `POST /api/v1/task/cancel` |

**Request Body**: `{ taskId: string; sessionId?: string }`

---

### 15.5 导出报表

| 项 | 值 |
|---|---|
| **URL** | `POST /api/v2/export/report` |

**Request Body**:
```typescript
{ messageId: string; feishuUserId: string }
```

---

## 16. 定时任务调度 (Scheduler)

> Base: `/mira/api/v1/scheduler`
> 所有请求额外注入 Header: `x-mira-session: {mira_session cookie}`

### 16.1 获取任务列表

| 项 | 值 |
|---|---|
| **URL** | `GET /mira/api/v1/scheduler/task/list` |

**Query Params**:

| 参数 | 类型 | 说明 |
|---|---|---|
| `limit` | number | 数量限制 |
| `cursor` | string | 分页游标 |
| `need_count` | boolean | 是否返回总数 |
| `status_list` | string | 状态列表，逗号分隔 |
| `trigger_time_start` | number | 触发时间起始 |
| `trigger_time_end` | number | 触发时间结束 |
| `desc_by_created_at` | boolean | 按创建时间倒序 |
| `need_latest_action` | boolean | 是否包含最近执行记录 |

**Response**:
```typescript
{
  code: number;
  data: {
    tasks: SchedulerTask[];
    next_cursor?: string;
    total?: number;
  };
}
```

**`SchedulerTask` 核心类型**:
```typescript
interface SchedulerTask {
  id: number;
  user_id: string;
  description: string;
  status: TaskStatus;          // 0=PENDING, 1=QUEUED, 2=EXECUTED, 3=FAILED, 4=CANCELLED, 5=PAUSED, 6=RUNNING
  trigger_time?: number;
  trigger_type?: TriggerType;  // 1=TIME, 2=EVENT, 3=MANUAL
  cron_expression?: string;
  cycle_start_time?: number;
  cycle_end_time?: number;
  skills_payload?: TaskPayload;
  meta_info?: { task_tag?: string; timezone?: string };
  concurrency_policy?: ConcurrencyPolicy;
  latest_action?: SchedulerAction;
}

interface TaskPayload {
  user_id?: string;
  content?: string;
  message_type?: number;
  summary_agent?: string;
  data_sources?: string[];
  comprehensive?: number;
  config?: {
    online?: boolean;
    mode?: string;
    model?: string;
    tool_list?: Array<{ name: string; id?: number; scope?: string }>;
    agent_name?: string;
    skill_names?: string[];
  };
  sys_label?: string;
  result_delivery?: number;
  session_id?: string;
  push_configs?: PushConfig[];
}
```

---

### 16.2 按会话获取任务列表

| 项 | 值 |
|---|---|
| **URL** | `GET /mira/api/v1/scheduler/task/list_by_session?session_id={id}` |

---

### 16.3 获取单个任务

| 项 | 值 |
|---|---|
| **URL** | `GET /mira/api/v1/scheduler/task/get?id={taskId}` |

---

### 16.4 创建定时任务

| 项 | 值 |
|---|---|
| **URL** | `POST /mira/api/v1/scheduler/task/create` |

**Request Body** (`CreateTaskBody`):
```typescript
{
  description: string;
  task_biz_id?: string;
  trigger_time: number;
  skills_payload: TaskPayload;
  trigger_type: number;                // 1=TIME, 2=EVENT, 3=MANUAL
  cron_expression?: string;
  cycle_start_time?: number;
  cycle_end_time?: number;
  meta_info?: { task_tag?: string; timezone?: string };
  concurrency_policy?: number;
}
```

**Response**: `{ code: number; data: { task: SchedulerTask } }`

---

### 16.5 更新定时任务

| 项 | 值 |
|---|---|
| **URL** | `POST /mira/api/v1/scheduler/task/update?id={taskId}` |

**Request Body** (`UpdateTaskBody`):
```typescript
{
  description?: string;
  skills_payload?: TaskPayload;
  trigger_type?: number;
  trigger_time?: number;
  cron_expression?: string;
  status?: number;
  cycle_start_time?: number;
  cycle_end_time?: number;
  meta_info?: MetaInfo;
  concurrency_policy?: number;
}
```

---

### 16.6 更新任务状态

| 项 | 值 |
|---|---|
| **URL** | `POST /mira/api/v1/scheduler/task/status/update?id={taskId}&status={status}` |

**Request Body**: `{ status: number }`

---

### 16.7 立即执行任务

| 项 | 值 |
|---|---|
| **URL** | `POST /mira/api/v1/scheduler/task/execute?id={taskId}` |

**Request Body**（可选覆盖 payload）:
```typescript
{ skills_payload?: TaskPayload }
```

**Response**:
```typescript
{ result: string; message: string; session_id: string; message_id: string }
```

---

### 16.8 获取执行记录列表

| 项 | 值 |
|---|---|
| **URL** | `GET /mira/api/v1/scheduler/action/list` |

**Query Params**:

| 参数 | 类型 | 说明 |
|---|---|---|
| `task_id` | number | 任务 ID |
| `limit` | number | 数量限制 |
| `cursor` | string | 分页游标 |
| `need_count` | boolean | 是否返回总数 |
| `status_list` | string | 状态过滤 |
| `desc_by_created_at` | boolean | 按创建时间倒序 |
| `created_at_start` | number | 创建时间起始 |
| `created_at_end` | number | 创建时间结束 |
| `need_task_info` | boolean | 是否包含任务信息 |

**Response**:
```typescript
{
  code: number;
  data: {
    actions: SchedulerAction[];
    next_cursor?: string;
    total?: number;
  };
}

interface SchedulerAction {
  id: number;
  task_id: number;
  trigger_time: number;
  executed_at: number;
  status: ActionStatus;         // 0=QUEUED, 1=RUNNING, 2=SUCCESS, 3=FAILED, 4=TIMEOUT
  skills_payload?: TaskPayload;
  result_payload?: {
    result?: string;
    message?: string;
    session_id?: string;
    message_id?: string;
  };
  task_info?: SchedulerTask;
  error_msg?: string;
  trace_id?: string;
}
```

---

### 16.9 重新执行执行记录

| 项 | 值 |
|---|---|
| **URL** | `POST /mira/api/v1/scheduler/action/reexecute?action_id={actionId}` |

---

## 17. 报表活动 (Report Campaign)

> Base: `/api/v2/task`

### 17.1 获取任务列表

| 项 | 值 |
|---|---|
| **URL** | `GET /api/v2/task/list?{params}` |

---

### 17.2 变更任务

| 项 | 值 |
|---|---|
| **URL** | `POST /api/v2/task/mutate` |

**Request Body** (`MutateTaskRequestParams`): 具体字段依赖 `@/features/report-campaign/types`

---

## 18. Persona 人设管理

> Base: `/api/v1/settings`

### 18.1 获取当前 Persona

| 项 | 值 |
|---|---|
| **URL** | `GET /api/v1/settings/persona/current` |

**Response** (`GetCurrentPersonaResponse`):
```typescript
{ success: boolean; /* persona data */ }
```

---

### 18.2 创建 Persona

| 项 | 值 |
|---|---|
| **URL** | `POST /api/v1/settings/persona/create` |

**Request Body**:
```typescript
{
  persona: string;              // Persona 内容
  enabled: boolean;
}
```

---

### 18.3 更新 Persona

| 项 | 值 |
|---|---|
| **URL** | `POST /api/v1/settings/persona/update` |

**Request Body**:
```typescript
{
  persona: string;
  enabled: boolean;
}
```

---

## 19. 消息反思 (Message Reflection)

### 19.1 获取消息反思

| 项 | 值 |
|---|---|
| **URL** | `GET /api/v1/chat/message/reflection/{sessionId}/{userMessageId}` |

**Response** (`MessageReflectionResponse`):
```typescript
{
  baseResp: { statusCode: number; statusMessage: string };
  // reflection data
}
```

---

## 20. 增长绩效 (Growth Performance)

> Base: `/api/v1/growth/performance`

### 20.1 获取高光话题列表

| URL | 方法 |
|---|---|
| `/api/v1/growth/performance/highlight_topics?type={type}` | GET |

### 20.2 创建高光话题

| URL | 方法 |
|---|---|
| `/api/v1/growth/performance/highlight_topics/create` | POST |

### 20.3 批量创建高光话题

| URL | 方法 |
|---|---|
| `/api/v1/growth/performance/highlight_topics/batch_create` | POST |

### 20.4 检查进度

| URL | 方法 |
|---|---|
| `/api/v1/growth/performance/highlight_topics/check_progress?showListId={}` | GET |

### 20.5 按用户 ID 获取进度

| URL | 方法 |
|---|---|
| `/api/v1/growth/performance/highlight_topics/check_progress_by_user?userId={}&type={}` | GET |

### 20.6 获取最近进度

| URL | 方法 |
|---|---|
| `/api/v1/growth/performance/highlight_topics/recent_progress?size={}&type={}` | GET |

### 20.7 开关触发器

| URL | 方法 |
|---|---|
| `/api/v1/growth/performance/highlight_topics/trigger_toggle` | POST |

### 20.8 标记为已读

| URL | 方法 |
|---|---|
| `/api/v1/growth/performance/highlight_topics/mark_as_read` | POST |

---

## 21. 数据源冗余识别

### 21.1 获取组织部门树

| 项 | 值 |
|---|---|
| **URL** | `GET /api/v1/redundancy_identification/organization_departments` |

**Response** (`GetOrganizationDepartmentsResponse`):
```typescript
{
  baseResp: { statusCode: number; statusMessage: string };
  departmentTrees: DepartmentTree[];
}
```

---

## 22. 财务 AI 接口 (Finance/AICEO)

> Base: `/aicoe/api/finai/`

| 接口 | URL | 方法 | 说明 |
|---|---|---|---|
| 获取对话列表 | `/aicoe/api/finai/conversation/list` | GET | 获取财务会话列表 |
| 重命名对话 | `/aicoe/api/finai/conversation/rename` | POST | 重命名财务会话 |
| 删除对话 | `/aicoe/api/finai/conversation/delete` | POST | 删除财务会话 |
| 用户资料 | `/aicoe/api/finai/user/profile` | GET | 财务用户登录 |

---

## 23. 加密解密

### 23.1 加密

| 项 | 值 |
|---|---|
| **常量** | `ENCRYPT` |
| **URL** | `POST /api/encrypt` |

**Request Body**: `{ text: string }`

**Response**: `{ encrypted: string; iv: string }`

---

### 23.2 解密

| 项 | 值 |
|---|---|
| **常量** | `DECRYPT` |
| **URL** | `POST /api/decrypt` |

**Request Body**: `{ data: string }`

**Response**: `{ data: string }`

---

## 24. API 路由总表

| # | 模块 | 常量名 | 路径 | 方法 |
|---|---|---|---|---|
| 1 | 会话 | `CREATE_CHAT_V1` | `/mira/api/v1/chat/create` | POST |
| 2 | 会话 | `GET_CHAT_V1` | `/api/v1/chat/?session_id=` | GET |
| 3 | 会话 | `GET_CHAT_LIST_V1` | `/api/v1/chat/list` | GET |
| 4 | 会话 | `UPDATE_CHAT_V1` | `/api/v1/chat/update` | POST |
| 5 | 会话 | `DELETE_CHAT_V1` | `/api/v1/chat/delete` | POST |
| 6 | 会话 | `TERMINATE_CHAT_V1` | `/api/v1/chat/terminate` | POST |
| 7 | 会话 | `PIN_CHAT_V1` | `/mira/api/v1/chat/pin` | POST |
| 8 | 消息 | `SEND_MESSAGE_V1` | `/mira/api/v1/chat/completion` | POST(SSE) |
| 9 | 消息 | `RESUME_STREAM_MESSAGE_V1` | `/mira/api/v1/chat/completion/resume` | POST(SSE) |
| 10 | 消息 | — | `/api/v1/chat/completion/terminate` | POST |
| 11 | 消息 | `GET_CHAT_MESSAGES_V1` | `/mira/api/v1/chat/messages` | POST |
| 12 | 消息 | `TEMPLATE_GET_CHAT_MESSAGE_V1` | `/api/v1/chat/:session_id/message/:message_id` | GET |
| 13 | 消息 | `INTERACT_MESSAGE_V1` | `/api/v1/chat/message/interaction` | POST |
| 14 | 消息 | `REWIND_CHAT_V1` | `/mira/api/v1/chat/rewind` | POST |
| 15 | 消息 | `GET_RELATED` | `/mira/api/v1/chat/more_query` | POST |
| 16 | 消息 | `DOC_EXPORT` | `/mira/api/v1/chat/export_message` | POST |
| 17 | 反思 | — | `/api/v1/chat/message/reflection/:sid/:mid` | GET |
| 18 | 用户 | `GET_USER_INFO` | `/api/userinfo` | GET |
| 19 | 用户 | `GET_USER_INFOS` | `/api/getOpenIdByUid` | POST |
| 20 | 用户 | `GET_EMPLOYEE_NUMBER_BY_JOB_IDS` | `/api/getEmployeeNumberByPeopleEmployeeId` | POST |
| 21 | 用户 | `ID_CONVERT` | `/api/idconvert` | POST |
| 22 | 用户 | `SEARCH_EMPLOYEES` | `/api/search_employees` | GET |
| 23 | 用户 | `SEARCH_DEPARTMENTS` | `/api/search_departments` | GET |
| 24 | 用户 | `SEARCH_USERS_BY_DEPARTMENT` | `/api/get_employees_by_departmentId` | GET |
| 25 | 用户 | `GET_LARK_COMPONENT_AUTH` | `/api/signature` | GET |
| 26 | 认证 | `REFRESH_TOKEN` | `/api/refreshToken` | GET |
| 27 | 认证 | `VALIDATE_TOKEN` | `/api/validate_tokens` | GET |
| 28 | 认证 | `SIGN_IN` | `/api/sigin` | GET |
| 29 | 认证 | `SIGN_OUT` | `/api/signout` | GET |
| 30 | 加密 | `ENCRYPT` | `/api/encrypt` | POST |
| 31 | 加密 | `DECRYPT` | `/api/decrypt` | POST |
| 32 | 文件 | `UPLOAD_FILE_V1` | `/mira/api/v1/file/upload` | POST |
| 33 | 文件 | `UPLOAD_FILE` | `/upload/files` | POST |
| 34 | 文件 | `FILE` | `/mira/api/v1/file/url/get` | GET |
| 35 | 模型 | `MODEL_METADATA` | `/api/v1/model/metadata` | GET |
| 36 | 技能 | — | `/mira/api/v1/skill/list` | GET |
| 37 | 技能 | — | `/mira/api/v1/skill/template/list` | GET |
| 38 | 技能 | — | `/mira/api/v1/skill/template/my` | GET |
| 39 | 技能 | — | `/mira/api/v1/skill/template/create` | POST |
| 40 | 技能 | — | `/mira/api/v1/skill/template/update` | POST |
| 41 | 技能 | — | `/mira/api/v1/skill/template/delete` | POST |
| 42 | 技能 | — | `/mira/api/v1/skill/template/favorite` | POST |
| 43 | 技能 | — | `/mira/api/v1/skill/template/share` | POST |
| 44 | 技能 | — | `/mira/api/v1/skill/template/share/:key` | GET |
| 45 | 技能 | — | `/mira/api/v1/skill/usage/track` | POST |
| 46 | 技能 | — | `/mira/api/v1/skill/gen` | POST |
| 47 | 技能 | — | `/mira/api/v1/skill/param/extract` | POST |
| 48 | 技能 | `PROMPT_OPTIMIZE` | `/mira/api/v1/prompt/optimize` | POST |
| 49 | 工具 | `TOOLS_LIST` | `/mira/api/v1/tools` | GET |
| 50 | 工具 | — | `/mira/api/v1/tool/packages` | POST |
| 51 | 搜索 | `RESOURCE_SEARCH_API` | `/mira/api/v1/lark/search/drive` | POST |
| 52 | 搜索 | `WIKI_SEARCH_API` | `/mira/api/v1/lark/search/wiki` | POST |
| 53 | 搜索 | `CHAT_SEARCH_API` | `/mira/api/v1/lark/search/chats` | GET |
| 54 | 预览 | `URL_PREVIEW_API` | `/mira/api/v1/lark/drive/meta/list` | POST |
| 55 | 云盘 | `LARK_MY_FOLDER` | `/mira/api/v1/drive/lark/my_folder` | GET |
| 56 | 设置 | — | `/mira/api/v1/user/settings/get` | GET |
| 57 | 设置 | — | `/mira/api/v1/user/settings/save` | POST |
| 58 | 配置 | `WEB_CONFIGS` | `/global_config/web_configs` | GET |
| 59 | DevOps | `GET_ROLE` | `/devops/get_role` | GET |
| 60 | DevOps | `CHANGE_ROLE` | `/devops/change_role` | GET |
| 61 | DevOps | — | `/devops/reset_role` | GET |
| 62 | DevOps | `REPLAY_QUERY` | `/devops/replay` | POST |
| 63 | DevOps | `SHARE_SESSION` | `/devops/share_session` | POST |
| 64 | 任务 | — | `/api/v1/task/status` | GET |
| 65 | 任务 | — | `/api/v1/task/create` | POST |
| 66 | 任务 | — | `/api/v1/task/list` | GET |
| 67 | 任务 | — | `/api/v1/task/cancel` | POST |
| 68 | 任务 | — | `/api/v2/export/report` | POST |
| 69 | 调度 | — | `/mira/api/v1/scheduler/task/list` | GET |
| 70 | 调度 | — | `/mira/api/v1/scheduler/task/list_by_session` | GET |
| 71 | 调度 | — | `/mira/api/v1/scheduler/task/get` | GET |
| 72 | 调度 | — | `/mira/api/v1/scheduler/task/create` | POST |
| 73 | 调度 | — | `/mira/api/v1/scheduler/task/update` | POST |
| 74 | 调度 | — | `/mira/api/v1/scheduler/task/status/update` | POST |
| 75 | 调度 | — | `/mira/api/v1/scheduler/task/execute` | POST |
| 76 | 调度 | — | `/mira/api/v1/scheduler/action/list` | GET |
| 77 | 调度 | — | `/mira/api/v1/scheduler/action/reexecute` | POST |
| 78 | 报表 | — | `/api/v2/task/list` | GET |
| 79 | 报表 | — | `/api/v2/task/mutate` | POST |
| 80 | 人设 | — | `/api/v1/settings/persona/current` | GET |
| 81 | 人设 | — | `/api/v1/settings/persona/create` | POST |
| 82 | 人设 | — | `/api/v1/settings/persona/update` | POST |
| 83 | 绩效 | — | `/api/v1/growth/performance/highlight_topics` | GET |
| 84 | 绩效 | — | `/api/v1/growth/performance/highlight_topics/create` | POST |
| 85 | 绩效 | — | `/api/v1/growth/performance/highlight_topics/batch_create` | POST |
| 86 | 绩效 | — | `/api/v1/growth/performance/highlight_topics/check_progress` | GET |
| 87 | 绩效 | — | `/api/v1/growth/performance/highlight_topics/check_progress_by_user` | GET |
| 88 | 绩效 | — | `/api/v1/growth/performance/highlight_topics/recent_progress` | GET |
| 89 | 绩效 | — | `/api/v1/growth/performance/highlight_topics/trigger_toggle` | POST |
| 90 | 绩效 | — | `/api/v1/growth/performance/highlight_topics/mark_as_read` | POST |
| 91 | 冗余 | — | `/api/v1/redundancy_identification/organization_departments` | GET |
| 92 | 财务 | — | `/aicoe/api/finai/conversation/list` | GET |
| 93 | 财务 | — | `/aicoe/api/finai/conversation/rename` | POST |
| 94 | 财务 | — | `/aicoe/api/finai/conversation/delete` | POST |
| 95 | 财务 | — | `/aicoe/api/finai/user/profile` | GET |
