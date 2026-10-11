# 指令台与任务

[English](TASKS.en.md) · **简体中文**

在「指令台」用自然语言交代需求。系统生成可编辑的确认单：目标、群范围、首次覆盖日期、周期、输出和执行顺序。缺少关键信息时先澄清；保存草稿不会创建任务或执行。点击「确认并首次运行」后，方案版本与首次运行在同一事务中保存，随后进入固定任务专题。

任务专题包含最新成果、执行记录、任务约定。修改已有任务时先显示变更摘要，再确认新版本；历史结果保留原口径。失败不会覆盖上次成功成果。没有配置模型时，界面明确显示状态，并支持手动制定统计方案。

## 配置可选 AI

在服务环境中设置以下变量；Docker Compose 可写入本地 `.env` 后重新创建服务，systemd 修改服务环境文件后重启：

```dotenv
CHATARCHIVE_AI_BASE_URL=https://your-model-service.example/v1
CHATARCHIVE_AI_MODEL=your-model-name
CHATARCHIVE_AI_API_KEY=your-server-side-key
```

接口需要支持 Chat Completions 和 JSON 对象响应。服务地址允许 HTTPS，或回环地址上的 HTTP 本地模型。密钥只在服务器使用。界面显示“已配置”不代表已经完成模型连通性测试；首次生成方案会验证实际响应。

规划时只发送需求、当前方案和群目录。未选群时提供最多 100 个目录项；找不到或同名不明确时应先选择群。内容分析步骤才会发送本次最多 100 条匹配消息摘录，并验证结论引用的消息 ID。配置前确认模型服务适合处理这些内部数据。

## 行为

- 按顺序执行最多 6 个不同种类的步骤：群、日期、发送者、消息类型统计，记录清单，以及带原文引用的内容分析。
- 时间范围：上一完整自然周、上一完整自然月、前 N 个完整自然日（不含当天），或截至执行参考时刻的最近 N 天。按任务时区计算，结果明确记录包含开始、不含结束的时间范围。
- 日/周/月计划按任务的 IANA 时区执行；每月可选 1–28 日。夏令时跳过不存在的时刻，回拨时仅执行第一次。
- 任务由 API 服务内的后台线程执行，每 15 秒检查一次。多进程通过同一数据目录的主机文件锁串行执行。不支持跨主机共享 SQLite 的调度集群。
- 服务停机后，每个到期任务补一次当前统计窗口；不逐次重放遗漏的周期。崩溃时处于运行中的任务记为失败，可手动重新运行。排队规则与结果均保存在 `tasks.sqlite3`。
- 暂停任务取消尚未开始的定时运行；已经开始的运行和明确发起的手动运行继续完成。启用后从下一个计划时间开始。修改并确认暂停中的任务不会自动恢复计划。修改规则不改变已排队或已完成的运行快照。
- 报告保存在工作空间，支持 CSV、Markdown、JSON 下载；不向外部平台发消息。任务数据库纳入备份；恢复后所有计划暂停。

## 统计边界

统计对象是查询索引中的已归档消息。按完整关键词做字面子串匹配，不支持多个词的 OR 表达式，不执行提示词、SQL 或脚本。资料清单包含消息正文摘录和引用；不下载或解析附件。可选内容分析仅针对保留的消息样本，并区分原文事实与待确认事项，不根据发言数量给员工打分。

每条规则最多 50 个群、366 天；保存任务最多 200 个；等待和运行队列最多 20 条；同一保存任务不能重复入队。每个步骤在一个只读索引快照内完成，查询时间上限约 45 秒；多步骤之间索引可能更新，结果各自记录索引时间。总消息数按全部匹配记录计算，结果表格最多 2,000 行；原文依据最多 100 条，每条正文摘录最多 2,000 字。达到上限会明确标记；原文仍可通过消息 ID 查询。

已撤回与无时间记录不参与有时间范围的统计。无时间记录的数量单列，但不能判断其属于哪个统计周期。发送者使用来源和账号编号去重；未知账号不计入参与者总数。不同平台上的同一个人不会自动合并。

运行结果保存时点的快照，后续索引更新不会改写它。结果含聊天资料，沿用私有数据目录保护，仅管理员可查看。当前不自动清理历史运行；部署者需监控数据目录容量。旧版程序不能读取任务备份，恢复时使用本版本或更新版本。

## HTTP 接口

所有路径位于 `/api`，仅管理员账号会话或既有管理员服务凭据可用。受限查询密钥不能读写任务。浏览器写入要求同源 Origin，并记录审计元信息。原有五个 MCP 工具保持只读。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | /task-planner | 模型配置状态，不返回密钥 |
| POST | /task-range | 按服务器时钟核对首次覆盖日期 |
| GET / POST | /task-drafts | 列出未完成草稿 / 生成或保存方案 |
| GET / PUT | /task-drafts/{id} | 读取 / 修订草稿，写入需 revision |
| POST | /task-drafts/{id}/confirm | 核对 revision 后确认，run_now 默认 true；重复提交不重复执行 |
| POST | /task-drafts/{id}/archive | 归档未确认草稿 |
| GET | /tasks/{id}/topic | 最新成功成果、历史与方案版本 |
| POST | /commands | 即时统计，返回 202 与运行 ID |
| GET / POST | /tasks | 列表 / 创建规则 |
| GET / PUT | /tasks/{id} | 查询 / 完整更新规则 |
| POST | /tasks/{id}/pause 或 /resume | 暂停 / 启用 |
| POST | /tasks/{id}/run | 手动运行，返回 202 |
| GET | /task-runs?task_id={id}&offset=0 | 运行记录，30 条一页，task_id 可省略 |
| GET | /task-runs/{id} | 状态、规则快照、结果 |
| GET | /task-runs/{id}/export?format=csv | 导出 csv / markdown / json；section=0..5 可选指定步骤 |

创建任务的请求体：

```json
{
  "name": "每周资料汇总",
  "rule": {
    "groups": [{"source": "feishu", "id": "demo-product"}],
    "keyword": "",
    "message_type": "file",
    "days": 7,
    "window": "complete_days",
    "dimension": "records",
    "timezone": "Asia/Shanghai"
  },
  "schedule": {"frequency": "weekly", "time": "09:00", "weekday": 0, "monthday": 1},
  "output": "csv",
  "enabled": true
}
```

`weekday` 的 0–6 对应周一至周日；`frequency` 为 manual/daily/weekly/monthly；`dimension` 为 group/day/sender/type/records；`window` 为 complete_days/rolling/previous_week/previous_month。即时统计只提交 name、rule、output。运行状态为 queued、running、succeeded、failed、cancelled；只有成功运行可导出。

自然语言草稿提交 `request` 与可选 `groups`；继续调整可附 `context`（当前编辑的 TaskInput）。手工保存提交 `config`；修改已有任务附 `task_id`。模型返回的 `questions` 未解决前不能确认，`notes` 在确认单展示。草稿最多 100 个，修订使用乐观并发控制。

可选 `workflow` 包含 `objective`、`request` 和 `steps`，每步为 `{kind, title, instruction}`。统计类 kind 为上述 dimension，内容分析 kind 为 `summary`。保留旧的 `/tasks` 与 `/commands` 管理接口用于显式 API 操作；新网页使用草稿确认流程。
