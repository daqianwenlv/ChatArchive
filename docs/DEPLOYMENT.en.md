# Deployment and upgrades

**English** · [简体中文](DEPLOYMENT.md)

The query preview uses Python 3.12, SQLite and locally readable archives. The API runs as a dedicated user, reads the query index, and writes accounts, sessions, access keys and audit records. Import jobs can run separately and atomically replace the index. PostgreSQL is a future design, not a current dependency.

Start with the [README](../README.md) for Docker or Python installation. The files under `deploy/` are systemd and Nginx examples. Keep production paths, SSH identities and CLI profiles in private configuration; build an index before exposing the service.

## Optional legacy snapshot bridge

The general import interface is `chatarchive.cli import-jsonl`. WeCom import expects the specific `message_facts`, `plaintext_messages` and `cursor_state` schema used by its adapter. It does not request platform archive entitlements.

The full-snapshot bridge requires both a remote chatlog directory and a local WeCom archive. The chatlog layout includes `chats.json`, `names.json`, `state.json`, `data/**/*.jsonl`, and optional `wechat/**/*.jsonl` and `meta/**/*.json`. The exporter expects fields such as `msg_id`, `chat_id`, `ts` and `text`; see `scripts/export_chatlog.py`. Other upstream formats need their own adapters.

When upgrading from 0.2.0, explicitly set `--chatlog-root` or `CHATARCHIVE_CHATLOG_ROOT`; previous built-in paths no longer apply. `--connection-label` defaults to `archive`. The fallback root is `/data/chatlog`; a missing directory fails the import and preserves the old snapshot.

The systemd index example reads `/etc/chatarchive-index.env`; use `deploy/chatarchive-index.env.example` as a template, readable only by root. Validate a temporary output index first. To merge CLI-visible groups, install and configure `lark-cli` and pass `--profile primary=YOUR_PROFILE`; this flag is repeatable.

Compare source counts, group names, connection labels and message samples before changing the scheduled import. Do not overwrite live environment files with examples. Preserve previous configuration and snapshots for rollback.

## Accounts

Run commands as the service user with the same `CHATARCHIVE_DATA` as the API:

```sh
python -m chatarchive.accounts create admin
python -m chatarchive.accounts reset admin
python -m chatarchive.accounts disable admin
```

Create and reset prompt for an initial password of 15–128 characters. Never pass a password in command-line arguments. The first login requires a password change, and resets revoke all sessions. Keep `accounts.sqlite3` owned by the service user with mode `0600`, outside any static directory. All current local accounts are administrators; there is no public registration or member invitation flow.

Expose only the application shell and its listed assets anonymously. API queries require authentication. Do not expose an entire archive or legacy snapshot directory. HTTPS session cookies use Secure, HttpOnly and SameSite=Lax and are scoped to the deployment prefix.

## Authentication boundaries

Local login is verified by the API. An existing Feishu administrator login can use a separate `/sso` proxy entry point routed to `/api/sso` after authentication. The trusted proxy must replace `X-Auth-Role` and `X-Auth-Oid`; the backend must bind only to loopback. Only a verified `admin` role with a nonempty identity may obtain administrator access.

MCP and machine queries use Bearer keys, not browser identity. Strip identity headers and cookies at these proxy locations, and force `X-ChatArchive-Machine: 1`. Keep ordinary API routes separate and clear that header there. Do not redirect machine clients to an HTML login page. Missing keys should return 401.

`CHATARCHIVE_TRUST_PROXY=0` ignores identity headers while keeping local login available. `CHATARCHIVE_ADMIN_TOKEN` is an optional emergency API Bearer, not a browser password. A trusted local proxy replaces `X-Real-IP` for login throttling. Keep all credentials and databases outside the web root and source distribution.

## Service lifecycle

- The API runs continuously on loopback.
- The sample index timer refreshes every five minutes; failures preserve the previous snapshot. Its service has a 240-second timeout and a file lock.
- Access keys store digests, expire within 90 days, and can be revoked immediately.
- Upstream collectors are operated separately; this application does not migrate or restart them automatically.
- Back up before upgrades, retain the previous code or image, and verify before switching. Reverting code does not revert data.

See [backup and recovery](BACKUP.en.md), [release checks](RELEASE.en.md) and the [validation record](VALIDATION.en.md). This version keeps the 0.2.2 query, account and access-key schemas unchanged.
