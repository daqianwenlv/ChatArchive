# 数据与查询接口

[English](API.en.md) · **简体中文**

## 统一数据

JSONL 群对象：`kind=group`，`source` 为 feishu/wecom/wechat/dingtalk，`id` 为平台原始群编号，`name` 为可空名称，`conversation_kind` 为 group/private，`connection` 为可选连接标签，`enabled`、`in_chat` 和 `last_sync` 为可空状态。

消息对象：`kind=message`，`source`、`id`、`group_id` 必填；`ts` 为毫秒时间戳或 null；`sender_id` 与 `sender_name` 分别是身份与显示名称；`type`、`text`、`deleted`、`parent_id`、`media_state` 为类型、正文、撤回标记、回复引用和附件状态。标准视频/语音类型为 video/voice，导入时归一化 media/audio。缺失群名显示编号，不用推测名称。示例数据完全虚构。

## HTTP

默认路径位于 `/api`。生产反向代理可将机器查询映射为单独 `/query` 前缀。所有数据查询需要经过认证。查询日期采用 `CHATARCHIVE_TIMEZONE`，默认 Asia/Shanghai；起止日期均包含在内。

| 方法及路径 | 参数 | 权限 |
| --- | --- | --- |
| GET /sources | — | groups:read |
| GET /groups | source, q, kind=group/private/all, status=all/archived/uncovered, limit, offset | groups:read |
| GET /group | source, group_id | groups:read |
| GET /messages | source, group_id, q, msg_type, start, end, limit, offset | messages:read |
| GET /message | source, message_id | messages:read |
| GET /analysis | source, group_id, start, end | analysis:read |
| GET /integration | — | 已认证 |
| GET/POST /keys | POST 为名称、来源、群范围、权限与天数 | 管理员 |
| DELETE /keys/{id} | — | 管理员 |
| GET /audit | 最近调用元信息 | 管理员 |

分页返回 `items,total,limit,offset,has_more`。每页最多 100 条；消息按时间倒序、来源及消息 ID 排序。原文搜索是 Unicode 字面子串匹配，`%`、`_` 不作为通配符。索引更新可能导致分页位置移动，响应是查询时刻的完整数据库快照。

指定群时必须同时指定来源。未授权群和不存在的群均返回 404。401 表示认证失败；403 表示权限不足；429 表示限流。浏览器会话写操作验证 Origin，生产使用 TLS。

## MCP

官方协议：[Streamable HTTP](https://modelcontextprotocol.io/specification/latest/basic/transports)。SDK 负责协议初始化、工具发现与消息格式；本服务验证每次请求与每次工具调用的密钥。

| 工具 | 查询能力 |
| --- | --- |
| list_sources | 来源、消息量、群覆盖与索引时间 |
| list_groups | 群目录与私聊目录；query 是群名/编号关键词 |
| search_messages | 原文检索；query 是正文关键词，message_type 是类型 |
| get_message | 按 source + message_id 取得单条记录 |
| analyze_group | 群或来源的描述性统计与高频词 |

所有工具声明只读。密钥范围应用于目录、消息、统计与关键词样本，客户端不能通过改参数绕过。group scopes 使用 `source:group_id`；null 表示所选来源的全部会话，包含将来新增记录。工具不能修改采集配置或执行数据库 SQL。

高频词根据当前范围最新最多 3000 条 text/post/mixed 消息分词，每条消息的同一词只计一次；返回样本量和一条可查询的消息引用。只有 analysis:read 而没有 messages:read 时不返回关键词或原文样本。参与人数按平台内发送者 ID 去重，不按姓名合并，不据此推断工作绩效。


## 账号会话（0.2.2）

- `POST /api/session`：`{"username":"admin","password":"…"}`；返回 `must_change_password` 并设置 HttpOnly 会话 Cookie。须提供与配置访问地址一致的 `Origin`。
- `GET /api/me`：当前账号、认证方式、权限及是否必须改密。
- `POST /api/password`：`{"current_password":"…","new_password":"…"}`；轮换当前会话并撤销该账号其他会话。
- `DELETE /api/session`：撤销当前会话，清除 Cookie。
- `GET /api/sso`：仅可信代理完成飞书管理员认证后可交换会话；普通客户端不能自行传入身份头。

首次改密前，仅允许读取自己的登录状态、改密和退出。浏览器会话不授予 MCP 或独立机器入口访问权。密码及校验错误不会回显提交内容；无效账号与密码返回相同错误。角色、成员邀请与 MFA 仍属于后续版本。

## 指令台与任务 API

管理员可通过 `/api/commands`、`/api/tasks` 和 `/api/task-runs` 创建统计、管理周期并读取结果。完整请求体、权限与调度语义见 [TASKS.md](TASKS.md)。
