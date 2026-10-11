# Command console and tasks

**English** · [简体中文](TASKS.md)

In the command console, select groups, message type, literal keyword, time window, aggregation and export format. **Run now** creates a persisted execution. **Save as task** stores the rule and schedules future runs; saving does not immediately generate a report.

Example: select product and delivery groups, collect file messages from the preceding seven complete calendar days, generate a record inventory every Monday at 09:00, and download the result as CSV. Groups can span sources; unnamed groups use their IDs.

## Execution model

- Aggregate by group, day, sender or message type, or produce a record inventory.
- Windows cover preceding complete calendar days, excluding today, or recent days up to the execution reference time. Boundaries use the rule's IANA timezone and are recorded as inclusive start / exclusive end.
- Daily, weekly and monthly schedules use wall-clock time; monthly days range from 1 to 28. Nonexistent DST times are skipped; a repeated local time executes only once.
- A background thread in the API checks every 15 seconds. An OS file lock serializes execution across processes sharing the same data directory on one host. Multi-host scheduling over shared SQLite is unsupported.
- After downtime, each overdue task runs once for its current window, rather than replaying every missed interval. Interrupted running jobs are marked failed and can be rerun manually. Rules, queue state and reports persist in `tasks.sqlite3`.
- Pausing cancels queued scheduled executions; started jobs and explicitly requested manual runs finish normally. Resuming schedules the next future occurrence. Editing does not rewrite queued or historical execution snapshots.
- Download CSV, Markdown or JSON from the workspace. No external messages are sent. Backups include tasks and results; restore pauses all schedules.

## Scope and limits

Rules operate on archived messages in the query index. Keywords are literal substrings, not OR expressions. Rules cannot execute prompts, SQL or scripts. Record inventories include message excerpts and references; they do not download or parse attachments, produce model-based summaries or score employee performance.

Limits: 50 groups per rule, 366 days per window, 200 saved tasks and 20 queued/running jobs. The same saved task cannot be queued twice concurrently. Each report reads one consistent archive snapshot with an approximately 45-second query budget. Counts include all matching messages; output tables contain at most 2,000 rows, evidence contains at most 100 recent messages, and excerpts contain at most 2,000 characters. Truncation is explicit; full messages remain retrievable by ID.

Revoked and undated messages are excluded. Undated records are counted separately because their reporting period is unknown. Participants are distinct source/account IDs; unknown accounts do not contribute to participant totals. Accounts on different platforms are not automatically merged.

Reports are snapshots and are not rewritten by index updates. They contain chat data, remain in the private data directory and require administrator access. There is no automatic history deletion; monitor disk usage. Restore task backups using this version or newer, not an older release.

## HTTP API

All paths below use `/api` and require an administrator session or an existing administrator service credential. Scoped query keys cannot access tasks. Browser writes require same-origin validation; operations are audited. The existing five MCP tools remain read-only.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | /commands | Queue an immediate report; returns 202 and run ID |
| GET / POST | /tasks | List / create saved rules |
| GET / PUT | /tasks/{id} | Retrieve / fully replace a rule |
| POST | /tasks/{id}/pause or /resume | Pause / enable scheduling |
| POST | /tasks/{id}/run | Queue a manual execution; returns 202 |
| GET | /task-runs?task_id={id}&offset=0 | Run history, 30 per page; optional task filter |
| GET | /task-runs/{id} | Status, rule snapshot and report |
| GET | /task-runs/{id}/export?format=csv | Download csv / markdown / json |

Create-task body:

```json
{
  "name": "Weekly file inventory",
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

`weekday` is Monday=0 through Sunday=6; `frequency` is manual/daily/weekly/monthly; `dimension` is group/day/sender/type/records; `window` is complete_days/rolling. Immediate commands accept only name, rule and output. Run states are queued/running/succeeded/failed/cancelled; exports require succeeded.
