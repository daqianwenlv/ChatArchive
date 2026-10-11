# Data format and query API

**English** · [简体中文](API.md)

## Normalized records

JSONL contains one object per line. Group objects use `kind=group`, `source` (`feishu`, `wecom`, `wechat`, or `dingtalk`), the original platform group `id`, an optional `name`, and `conversation_kind` (`group` or `private`). `connection` is an optional connection label; `enabled`, `in_chat` and `last_sync` may be absent or null.

Message objects require `kind=message`, `source`, `id` and `group_id`. `ts` is a timestamp in milliseconds or null. `sender_id` identifies the account; `sender_name` is a display name. Other fields are `type`, `text`, `deleted`, `parent_id` and `media_state`. The normalized video and voice types are `video` and `voice`; imports map `media` and `audio` accordingly. A missing group name is displayed as its ID. See the entirely fictional [sample](../examples/sample.jsonl).

## HTTP

The default prefix is `/api`. A reverse proxy can expose machine queries under a separate `/query` prefix. All data queries require authentication. Date filters use `CHATARCHIVE_TIMEZONE` (default `Asia/Shanghai`), with inclusive start and end dates.

| Method and path | Parameters | Permission |
| --- | --- | --- |
| GET /sources | — | groups:read |
| GET /groups | source, q, kind=group/private/all, status=all/archived/uncovered, limit, offset | groups:read |
| GET /group | source, group_id | groups:read |
| GET /messages | source, group_id, q, msg_type, start, end, limit, offset | messages:read |
| GET /message | source, message_id | messages:read |
| GET /analysis | source, group_id, start, end | analysis:read |
| GET /integration | — | Authenticated |
| GET/POST /keys | POST: name, sources, groups, permissions, days | Administrator |
| DELETE /keys/{id} | — | Administrator |
| GET /audit | Recent call metadata | Administrator |

Pagination returns `items,total,limit,offset,has_more`, with at most 100 items per page. Messages are sorted by descending timestamp, source and message ID. Text search matches literal Unicode substrings: `%` and `_` are not wildcards. Index updates can move page positions; each response reads a complete database snapshot.

A group filter requires its source. Unauthorized and nonexistent groups both return 404. Status 401 means authentication failed, 403 means insufficient permission, and 429 means rate limited. Browser session writes require a valid Origin; use TLS in production.

## MCP

Transport: [Streamable HTTP](https://modelcontextprotocol.io/specification/latest/basic/transports). The SDK handles initialization, tool discovery and protocol messages. The service authenticates every request and tool call.

| Tool | Purpose |
| --- | --- |
| list_sources | Sources, message counts, group coverage and index time |
| list_groups | Group and private conversation directory; query filters names or IDs |
| search_messages | Message search; query filters text, message_type filters type |
| get_message | One record by source and message_id |
| analyze_group | Descriptive statistics and frequent terms for a group or source |

All tools declare read-only behavior. Key scopes apply to directories, messages, statistics and keyword samples. Group scopes use `source:group_id`; null permits all conversations in the selected sources, including future records. Tools cannot change collection settings or execute arbitrary SQL.

Frequent terms use at most the latest 3,000 `text`/`post`/`mixed` messages within scope. A term counts once per message. Results include the sample size and a retrievable message reference. Without `messages:read`, analysis does not return keywords or text samples. Participants are distinct platform account IDs, not merged display names; these counts do not establish employee performance.

## Account sessions

- `POST /api/session`: `{"username":"admin","password":"…"}`. Returns `must_change_password` and sets an HttpOnly cookie. Send the Origin corresponding to the configured browser URL.
- `GET /api/me`: account, authentication method, permissions and password-change requirement.
- `POST /api/password`: `{"current_password":"…","new_password":"…"}`. Rotates the current session and revokes other sessions for the account.
- `DELETE /api/session`: revokes the current session and clears the cookie.
- `GET /api/sso`: only an authenticated Feishu administrator through a trusted proxy can exchange identity for a session. Clients cannot supply their own trusted identity headers.

Before the initial password change, only account status, password change and logout are available. Browser sessions do not authorize MCP or the separate machine entry point. Passwords are not echoed in validation errors; invalid usernames and passwords return the same login error. Member roles, invitations and MFA are not implemented.

## Command and task API

Administrators can use `/api/commands`, `/api/tasks` and `/api/task-runs` to run statistics, manage schedules and retrieve reports. See [TASKS.en.md](TASKS.en.md) for request bodies, permissions and scheduling semantics.
