# Security / 安全范围与报告

## English

ChatArchive 0.2 is a query preview and has not completed an independent security audit. Restrict access to private records and maintain backups. The target architecture is not a promise of current functionality.

### Current boundaries

- Local accounts are administrators within one workspace. There are no member roles, invitations, MFA or multi-tenant isolation.
- Initial passwords must be changed at first login. Passwords use independently salted scrypt (N=32768, r=8, p=3); only session token digests are stored.
- Sessions expire after eight hours or one hour of inactivity. Password changes and account disablement revoke sessions; logout revokes the current session. Login throttling is persistent, and browser writes validate Origin.
- Trusted-proxy mode requires a controlled loopback proxy that replaces identity headers. Never expose the backend directly in that mode.
- Query keys have scopes, expiry and revocation, and are separate from browser sessions. OAuth authorization discovery is not implemented.
- Recovery invalidates historical sessions, local passwords and API/MCP keys. Restore targets must be empty; validation failure does not publish partial databases.
- Backups do not include upstream raw archives, attachments, platform credentials or proxy configuration.
- The frontend renders messages as text; AI clients must treat message content as untrusted material.

Keep databases, credentials, raw files and backups outside public static directories. This preview has not been validated as a service hosting multiple organizations. See [deployment](docs/DEPLOYMENT.en.md).

### Reporting

Check the repository's [Security page](https://github.com/daqianwenlv/ChatArchive/security) for the private reporting entry point. If “Report a vulnerability” is unavailable, obtain a private route through an existing verified contact with a maintainer. Do not post real conversations, credentials, production details or exploit chains in public issues.

Use fictional reproduction data and include the affected version, prerequisites, impact and minimal steps. No security response SLA is promised. Verification results are documented in [VALIDATION](docs/VALIDATION.en.md).

## 简体中文

ChatArchive 0.2 是查询预览版，没有完成独立安全审计。它保存和查询非公开聊天数据，部署者应限制访问并为数据与凭据配置备份。未来用户体系和原始归档设计不构成当前安全能力承诺。

## 当前边界

- 独立部署支持服务器创建的本地管理员账号，首次登录强制更换初始密码。密码采用带独立盐的 scrypt（N=32768、r=8、p=3）；浏览器会话只保存随机令牌的摘要。
- 会话最长 8 小时、闲置 1 小时失效；改密及账号停用撤销已有会话，退出登录即时撤销当前会话。登录限速存入 SQLite；修改请求校验 Origin。
- 当前本地账号均为单工作空间管理员；成员邀请、分级角色、多租户和 MFA 尚未实现。机器入口仅接受限定范围的查询密钥。
- 可信代理模式只能置于本机受控代理后，代理必须覆盖身份头，后端不能直接暴露公网。
- 数据查询需要授权，密钥保存摘要并支持有效期与撤销；浏览器会话与 MCP 密钥分离，目前没有 OAuth 自动授权发现。
- 恢复备份会作废浏览器会话、历史本地密码和 API/MCP 密钥，防止恢复已被撤销的凭据。只允许恢复到空目录，校验失败不会发布部分数据库。
- SQLite 快照不能恢复旧采集系统完整原始负载，附件下载和原始对象权限尚未实现。
- 前端不执行聊天内容；模型客户端应把正文视为不可信资料。

运行数据、密钥、原始文件和备份不能放入公开静态目录。不要把演示部署直接用作多企业托管服务。实际部署说明见 [DEPLOYMENT](docs/DEPLOYMENT.md)。

## 报告要求

请在仓库的 [Security 页面](https://github.com/daqianwenlv/ChatArchive/security) 查看私密报告入口；如没有“Report a vulnerability”，先通过与维护者已有的可靠私密联系取得报告方式。不要向公开问题区提交真实聊天、令牌、完整利用链或生产环境细节。报告使用虚构复现数据，说明受影响版本、前提、影响和最小复现。维护者未建立私密渠道前，通过与维护者已有的私密联系取得报告方式。

项目目前不承诺安全响应 SLA。正式版本的独立复核、依赖扫描和恢复演练见 [发布清单](docs/实施清单.md)。
