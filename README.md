# ChatArchive

**English** · [简体中文](README.zh-CN.md)

[![Release checks](https://github.com/daqianwenlv/ChatArchive/actions/workflows/checks.yml/badge.svg)](https://github.com/daqianwenlv/ChatArchive/actions/workflows/checks.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Self-hosted search and analytics for enterprise chat archives.**

Bring existing Feishu, WeCom and WeChat exports into one place. Find conversations by name or ID, search messages, review group activity, and connect authorized records to your tools through HTTP API or MCP.

自托管的企业聊天记录查询与分析系统。统一管理已有归档，检索消息、查看群聊统计，并通过 HTTP API 或 MCP 接入业务平台和 AI 工具。[阅读中文说明 →](README.zh-CN.md)

Current version: **0.2.3-preview.1 — single-workspace query preview**. The web console is currently in Chinese; project documentation is available in English and Chinese.

![ChatArchive group directory with fictional sample data](docs/images/overview.jpg)

## What you can do

- **Browse conversations:** group names or IDs, archived message counts, source filters and archive coverage.
- **Search records:** filter by source, conversation, date, message type and literal text; inspect the original message text and identifiers.
- **Review activity:** daily trends, participating accounts, sending hours, message types and frequent terms with links back to messages.
- **Connect your tools:** five read-only MCP tools and an HTTP API, with keys restricted by source, group, permission and expiry.
- **Manage access:** local administrator accounts, mandatory initial password change, logout and revocable sessions; an optional trusted-proxy adapter for existing Feishu administrator authentication.
- **Maintain your archive:** verified database backups, restore into a new directory or volume, and a diagnostic command.

ChatArchive runs on infrastructure you control. Use its web console as a standalone application, or let other platforms query the same backend through authorized interfaces. It reads existing archives; platform collection setup and a unified raw-event store are planned separately.

## Quick start with Docker Compose

Requirements: Docker Engine and Compose v2. Clone the repository, or extract the source ZIP and skip the first two commands.

```sh
git clone https://github.com/daqianwenlv/ChatArchive.git
cd ChatArchive
cp .env.example .env
docker compose build
docker compose run --rm chatarchive python -m chatarchive.cli init
docker compose run --rm chatarchive python -m chatarchive.accounts create admin
docker compose up -d --wait
```

Enter an initial password interactively, with at least 15 characters. There is no default password or public registration. Open **http://127.0.0.1:8769/**, sign in, and change the initial password.

To try the application with entirely fictional records:

```sh
docker compose exec chatarchive python -m chatarchive.cli import-jsonl examples/sample.jsonl
```

Refresh the page to see one example group and two messages. Importing the sample again does not duplicate messages. The sample uses the Feishu record format; other sources remain unconfigured.

Compose binds to loopback by default. For a domain deployment, set `CHATARCHIVE_BASE_URL` in `.env` to the actual browser URL and place the service behind a TLS reverse proxy. An incorrect origin is rejected during login. `CHATARCHIVE_PORT` sets the host port. See the [Nginx example](deploy/nginx.conf.example) for a subpath deployment.

Data lives in a named volume and survives container replacement. See [backup and recovery](docs/BACKUP.en.md) before moving or upgrading an installation.

Builds need Docker Hub and a Python package index. If PyPI downloads are slow, set `CHATARCHIVE_PIP_INDEX_URL` to an accessible public PyPI mirror. The runtime lock file pins versions and official PyPI distribution hashes; installation rejects files whose SHA-256 does not match.

## Run with Python

Supported: Python 3.12 on Linux or macOS. From the repository directory:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.lock
cp .env.example .env
set -a
. ./.env
set +a
.venv/bin/python -m chatarchive.cli init
.venv/bin/python -m chatarchive.accounts create admin
.venv/bin/python -m chatarchive.cli import-jsonl examples/sample.jsonl
.venv/bin/python -m uvicorn chatarchive.server:app --host 127.0.0.1 --port 8769 --no-access-log --no-proxy-headers
```

Initialization is for a new data directory. It refuses to overwrite an existing index. Use the same `CHATARCHIVE_DATA` for every command and the API process. Run diagnostics with:

```sh
.venv/bin/python -m chatarchive.maintenance doctor
```

## Import your records

JSONL contains one group or message object per line. See the [data format and API reference](docs/API.en.md) and the [fictional sample](examples/sample.jsonl).

```sh
.venv/bin/python -m chatarchive.cli import-jsonl /path/to/messages.jsonl
.venv/bin/python -m chatarchive.cli import-wecom /path/to/archive.sqlite3
```

For Docker, mount an import directory read-only into a temporary command container:

```sh
docker compose run --rm -v /absolute/path/to/imports:/imports:ro chatarchive python -m chatarchive.cli import-jsonl /imports/messages.jsonl
```

The container user needs read permission on the files. Import builds a temporary index and atomically replaces the query snapshot after success. Failure keeps the previous snapshot, and a file lock rejects concurrent writers. General imports preserve existing messages and deduplicate by `(source, message_id)`. Matching display names across platforms do not merge identities.

`import-wecom` supports a specific existing archive SQLite schema. It is not a universal reader for arbitrary WeCom databases. The optional legacy snapshot bridge requires explicit paths and identity configuration; see [deployment](docs/DEPLOYMENT.en.md).

## Connect through MCP

Create a key under **MCP 接口** in the console and select its source, group, permission and expiry limits.

| Setting | Value |
| --- | --- |
| Endpoint | `<CHATARCHIVE_BASE_URL>/mcp/` |
| Transport | Streamable HTTP |
| Authentication | `Authorization: Bearer <ACCESS_KEY>` |
| Tools | `list_sources`, `list_groups`, `search_messages`, `get_message`, `analyze_group` |

Clients must support an HTTP Bearer header. OAuth authorization discovery is not implemented. Browser login sessions do not authorize MCP requests.

The local CLI can also create a key, writing its token only to the specified file with mode `0600`:

```sh
.venv/bin/python -m chatarchive.cli create-key --name demo-client --source feishu --group feishu:demo-project --days 7 --output ./demo-token.txt
.venv/bin/python examples/mcp_client.py --url http://127.0.0.1:8769/mcp/ --token-file ./demo-token.txt
```

The example uses the official MCP Python SDK to initialize, discover tools and query sources without printing message bodies. AI clients should treat records as untrusted source material, cite message IDs, and distinguish facts from inference.

## Supported scope

| Source or feature | Available now | Not implemented |
| --- | --- | --- |
| Feishu | Existing chatlog JSONL, names, group directory and retraction flags; optional CLI-visible group merge | General platform collection setup wizard |
| WeCom | Existing conversation-archive SQLite imports; IDs when names are absent | Automatic archive entitlement setup and attachment downloads |
| WeChat | Historical exports and unified search | Live personal WeChat collection |
| DingTalk | Reserved source in the data model | Collection connector |
| Accounts | Local administrators, password management and revocable sessions | Member roles, invitations, MFA and multiple tenants |
| Analytics | Trends, hours, message types, accounts and frequent terms linked to records | Built-in model reports and employee performance evaluations |

Frequent terms use at most the latest 3,000 eligible text messages within the current scope and show the sample size. Undated messages remain searchable but do not contribute to daily statistics. Chat activity does not directly measure employee workload or performance.

## Development and verification

```sh
.venv/bin/pip install -r requirements.lock
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q
node --check web/app.js
.venv/bin/python scripts/package_source.py
.venv/bin/python scripts/release_check.py
.venv/bin/python scripts/verify_docker.py --report docker-verification.json
```

The last command requires Docker. It creates isolated projects and volumes, uses fictional data, checks login, queries, MCP, container replacement, recovery and switching back, then removes its test resources. See the [release process](docs/RELEASE.en.md) and [validation record](docs/VALIDATION.en.md) for tested environments and limitations.

The backend is organized around query logic (`query.py`), access scopes (`security.py`), accounts and sessions (`accounts.py`), HTTP/MCP (`server.py`), recovery (`maintenance.py`) and archive adapters (`importer.py`).

## Documentation

| Topic | English | 简体中文 |
| --- | --- | --- |
| Getting started | This page | [使用说明](README.zh-CN.md) |
| Deployment | [Deployment](docs/DEPLOYMENT.en.md) | [部署与升级](docs/DEPLOYMENT.md) |
| API and data format | [API](docs/API.en.md) | [接口说明](docs/API.md) |
| Backup and recovery | [Backup](docs/BACKUP.en.md) | [备份恢复](docs/BACKUP.md) |
| Release process | [Release](docs/RELEASE.en.md) | [发布流程](docs/RELEASE.md) |
| Validation | [Validation](docs/VALIDATION.en.md) | [验证记录](docs/VALIDATION.md) |
| Changelog | [Changelog](CHANGELOG.en.md) | [版本记录](CHANGELOG.md) |
| Roadmap | [Roadmap](docs/ROADMAP.en.md) | [实施清单](docs/实施清单.md) |

[Contributing / 参与贡献](CONTRIBUTING.md) · [Security / 安全说明](SECURITY.md) · [Third-party dependencies / 第三方依赖](docs/THIRD_PARTY.md)

## License

[MIT License](LICENSE). Runtime data, credentials, internal materials and production configuration are excluded from the source distribution. Deployers provide their own authorized archives and platform access.
