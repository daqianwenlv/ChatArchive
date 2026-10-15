# 部署

[English](DEPLOYMENT.en.md) · **简体中文**

当前查询预览版需要 Python 3.12、SQLite 与本机可读的数据源。查询进程使用独立系统用户，只读查询索引，只写账号会话、访问密钥和调用审计。导入任务可以单独运行，以原子替换方式刷新索引。下一版 PostgreSQL 设计尚未实现。

`deploy/chatarchive-api.service`、`chatarchive-index.service`、`chatarchive-index.timer` 是当前 systemd 布局样例。生产路径、SSH 目标、身份文件与 CLI profile 必须在部署机私有环境文件中配置。现有原始采集库保持只读；首次上线前先构建索引，再开启访问入口。

## 旧系统桥接和配置升级

通用入口是 `chatarchive.cli import-jsonl`；企业微信导入需要 `message_facts`、`plaintext_messages` 和 `cursor_state` 表及适配器使用的字段。CLI 不会从平台自动申请存档权限。

全量快照桥接是可选迁移工具，要求同时具备远端 chatlog 目录和本地企业微信库。chatlog 使用 `chats.json`、`names.json`、`state.json`、`data/**/*.jsonl` 和可选 `wechat/**/*.jsonl`、`meta/**/*.json`；消息字段为 `msg_id`、`chat_id`、`ts`、`text` 等。完整格式以 `scripts/export_chatlog.py` 为准。不同原库格式应编写独立适配器。

从 0.2.0 升级时，旧的内置 chatlog 路径不再生效。显式传入 `--chatlog-root` 或设置 `CHATARCHIVE_CHATLOG_ROOT`；连接标签使用 `--connection-label`，默认 `archive`。路径按 Python 字符串传给远端，不拼接 shell 命令。未配置路径时默认 `/data/chatlog`；目录不存在会失败并保留前一查询快照。

每次同步合并到上一快照：上游已删除的记录继续保留。消息带 `media_path` 时，附件原件随同步传回并保存在数据目录 `media/`，已归档的附件不会重复传输。相对路径按 `--media-root`（或 `CHATARCHIVE_MEDIA_ROOT`，默认为 chatlog 根目录）解析，根目录以外的路径一律不读取。单个附件上限由 `CHATARCHIVE_MEDIA_MAX_BYTES` 控制，默认 512 MiB。企业微信库只含明文与 `sdkfileid`，原件需要平台 SDK 下载，目前仍为未下载状态，`sdkfileid` 保存在原始记录中。

systemd 样例读取 `/etc/chatarchive-index.env`，模板为 `deploy/chatarchive-index.env.example`。迁移时先复制所需旧配置到新的私有环境文件，限制为 root 可读，再在临时输出路径验证索引。需要合并 CLI 群目录时增加 `--profile primary=YOUR_PROFILE`；支持多次传入，部署机须安装并配置 lark-cli。

先验证来源计数、群名、连接标签和正文，再切换定时任务。不要用源码包的样例覆盖正在运行的环境文件。原服务配置与原查询快照保留用于回退。

## 创建登录账号

在服务运行用户身份下执行，确保 `CHATARCHIVE_DATA` 与 API 进程一致：

```sh
python -m chatarchive.accounts create admin
python -m chatarchive.accounts reset admin
python -m chatarchive.accounts disable admin
```

`create` / `reset` 交互输入初始密码（15–128 字符），不在命令行参数中传密码。初次登录必须改密；重置撤销所有已有会话。`accounts.sqlite3` 保持服务用户所有、0600 权限，不进入静态目录。当前命令创建的账号均为管理员，没有公开注册或成员邀请。

只向匿名访问开放首页、app.js、app.css 和 favicon.svg；API 校验登录会话。历史 status.json、快照和内部资料继续使用原有认证，不要直接开放整个静态目录。HTTPS 部署会话 Cookie 使用 Secure、HttpOnly 与 SameSite=Lax，路径限定在部署前缀。

## 认证边界

本地账号登录由 API 验证。需要保留既有飞书认证时，将独立 `/sso` 入口经管理员认证后代理到 `/api/sso`，返回的会话用于后续页面查询。可信代理必须覆盖客户端传入的 `X-Auth-Role`、`X-Auth-Oid`，将认证结果作为这两个头传给仅绑定 localhost 的 API。仅 role=admin 且 oid 非空可获得管理权限。

MCP 和机器 HTTP 查询不继承浏览器管理员身份，单独使用 Bearer 密钥；代理清空身份头和 Cookie。不要给 MCP 配置管理员登录重定向，否则客户端会收到 HTML。未携带密钥时应返回 401。

设置 `CHATARCHIVE_TRUST_PROXY=0` 时忽略身份头，本地账号仍可登录。`CHATARCHIVE_ADMIN_TOKEN` 仅为可选的应急管理员 API Bearer，不用于网页登录。机器查询代理还应强制设置 `X-ChatArchive-Machine: 1`；常规 API 清空该头和身份头。可信本机代理覆盖 `X-Real-IP`，供登录限速使用。`.env`、数据库、令牌文件、SSH 配置不得位于静态目录或进入源码包。

## 生命周期

- 查询服务：持续运行，绑定 loopback。
- 查询索引：每 5 分钟刷新，全量只读快照失败时保留前一索引；定时任务有 240 秒超时与文件锁。
- 访问密钥：只存摘要，最长 90 天有效，撤销即时生效。
- 原始采集器：独立维护，本项目不自动迁移或重启已有采集器。
- 回滚：恢复上次代码、静态文件、Nginx 配置；访问库与原始采集库不回滚覆盖。

Docker 安装见 README，隔离验收脚本为 `scripts/verify_docker.py`；备份与恢复见 [BACKUP](BACKUP.md)。发布要求及已知范围见 [RELEASE](RELEASE.md)。
