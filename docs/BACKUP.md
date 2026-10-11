# 备份、恢复与回退

[English](BACKUP.en.md) · **简体中文**

预览版的备份包含查询数据库、账号数据库、访问密钥摘要和审计记录。原有采集器的原始数据库、附件、平台凭据、TLS 和反向代理配置需由部署者另行备份。备份含非公开聊天记录和认证元数据，应保存在受限且有加密保护的存储中。

## Python 部署

在服务用户身份下运行，并设置正确的 CHATARCHIVE_DATA：

```sh
python -m chatarchive.maintenance backup ./backups/snapshot.zip
python -m chatarchive.maintenance doctor
```

备份使用 SQLite backup API，分别取得各库的完整快照，支持在线运行；它不是各数据库同一毫秒的联合事务。ZIP 内含文件大小、SHA-256、版本和消息计数。输出文件为 0600，已有文件不会被覆盖。

恢复到一个全新的目录，完成后再启动服务：

```sh
python -m chatarchive.maintenance --data ./recovered restore ./backups/snapshot.zip
python -m chatarchive.maintenance --data ./recovered doctor
python -m chatarchive.accounts reset admin --data ./recovered
```

若原备份没有本地账号，使用 `create admin`。最后将 `CHATARCHIVE_DATA` 指向恢复后的目录，并启动服务。运行中的服务与采集器不能指向恢复目标；已有非空目录一律拒绝覆盖。

## Docker Compose

在项目目录执行；备份名每次使用新的日期或编号：

```sh
docker compose exec -T chatarchive python -m chatarchive.maintenance backup /data/snapshot.zip
mkdir -p backups
chmod 700 backups
docker compose cp chatarchive:/data/snapshot.zip backups/snapshot.zip
chmod 600 backups/snapshot.zip
```

在另一项目名下恢复，会创建单独的数据卷。停止原项目以释放端口，原卷继续保留：

```sh
docker compose stop
docker compose -p chatarchive-recovered run --rm -T chatarchive python -m chatarchive.maintenance restore - < backups/snapshot.zip
docker compose -p chatarchive-recovered run --rm chatarchive python -m chatarchive.accounts reset admin
docker compose -p chatarchive-recovered run --rm -T chatarchive python -m chatarchive.maintenance doctor
docker compose -p chatarchive-recovered up -d --wait
```

`restore -` 从标准输入接收备份，避免主机文件所有者与容器 UID 不一致导致无法读取。较大的备份需要足够的临时空间；Compose 默认 /tmp 为 128 MiB，可在恢复时调整 tmpfs 大小。

确认账号登录、来源计数、群数量和抽样记录，再让客户端连接新服务。回到原数据卷：

```sh
docker compose -p chatarchive-recovered stop
docker compose up -d --wait
```

这些命令不删除任何旧数据卷。停止两边的写入后再决定保留哪一份，避免恢复后的新导入丢失。

## 恢复后的访问权限

所有旧浏览器会话作废，全部旧 API/MCP 密钥撤销。本地密码失效，需在服务器用 `accounts reset` 重设；首次登录仍需改密。原本停用的账号继续停用。历史外部身份账号恢复为停用状态，需另行核实后配置。

这样处理是因为备份可能早于一次密码修改、账号停用或密钥撤销；不能恢复出已经废弃的访问权限。审计记录保留。恢复后在控制台重新签发客户端密钥。

## 失败行为

- ZIP 路径、文件清单、校验和或 SQLite 完整性错误：恢复失败，不发布部分数据库。
- 目标已含数据：拒绝覆盖。
- 可用空间不足：拒绝展开。
- 恢复被强行终止：目标可能保留 `.restore-in-progress`；API 拒绝在该目录启动。保留失败现场，用另一个新目录重试。
- 导入失败：保留上一个查询快照；并发导入会被文件锁拒绝。

先在隔离环境演练，再用于生产。`scripts/verify_docker.py` 使用虚构数据验证备份、新卷恢复、凭据作废和切回原卷。

任务与运行结果保存在 `tasks.sqlite3`，自动纳入备份。恢复时所有任务暂停，排队或运行中的执行标记为取消；登录检查规则后再手动启用。较旧备份没有任务库时仍可恢复。
