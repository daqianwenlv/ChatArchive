# Command console and tasks

**English** · [简体中文](TASKS.md)

Describe the work in the command console. Review an editable plan with its objective, groups, first reporting dates, schedule, output and ordered steps. Missing essential details require clarification. Saving a draft does not create an executable task. **Confirm and run** atomically saves the version and queues the first execution, then opens a permanent task page.

Each task has latest results, execution history and a versioned agreement. Changes require another review; historical reports retain their original rules. A failed run leaves the last successful report available. Without an AI configuration, users can create manual statistical plans.

## Optional AI configuration

Set these server environment variables. With Compose, edit your local `.env` and recreate the service; with systemd, update the service environment file and restart it.

```dotenv
CHATARCHIVE_AI_BASE_URL=https://your-model-service.example/v1
CHATARCHIVE_AI_MODEL=your-model-name
CHATARCHIVE_AI_API_KEY=your-server-side-key
```

The endpoint must support Chat Completions and JSON object responses. HTTPS is required except for loopback HTTP model services. Keys stay on the server. “Configured” does not assert a successful connection test; generating a plan exercises the service.

Planning sends the request, current plan and group directory only. Without selected groups, the directory is limited to 100 entries; select groups explicitly when a name is missing or ambiguous. Content-analysis steps send at most 100 matching message excerpts and validate every returned citation ID. Ensure your configured service is appropriate for this internal data.

## Execution model

- Run up to six different step kinds in order: group, day, sender or message-type counts, record inventory, and optional cited content analysis.
- Windows cover the previous calendar week, previous calendar month, preceding complete calendar days excluding today, or recent days up to execution time. Boundaries use the rule's IANA timezone and are recorded as inclusive start / exclusive end.
- Daily, weekly and monthly schedules use wall-clock time; monthly days range from 1 to 28. Nonexistent DST times are skipped; a repeated local time executes only once.
- A background thread in the API checks every 15 seconds. An OS file lock serializes execution across processes sharing the same data directory on one host. Multi-host scheduling over shared SQLite is unsupported.
- After downtime, each overdue task runs once for its current window, rather than replaying every missed interval. Interrupted running jobs are marked failed and can be rerun manually. Rules, queue state and reports persist in `tasks.sqlite3`.
- Pausing cancels queued scheduled executions; started jobs and explicitly requested manual runs finish normally. Resuming schedules the next future occurrence. Confirming a changed plan never resumes an already paused schedule. Editing does not rewrite queued or historical execution snapshots.
- Download CSV, Markdown or JSON from the workspace. No external messages are sent. Backups include tasks and results; restore pauses all schedules.

## Scope and limits

Rules operate on archived messages in the query index. Keywords are literal substrings, not OR expressions. Rules cannot execute prompts, SQL or scripts. Record inventories include message excerpts and references; they do not download or parse attachments. Optional summaries cover the retained message sample, distinguish facts from follow-ups, and do not score employee performance.

Limits: 50 groups per rule, 366 days per window, 200 saved tasks and 20 queued/running jobs. The same saved task cannot be queued twice concurrently. Each step reads one consistent archive snapshot with an approximately 45-second query budget. Indexes may change between steps; each section retains its index timestamp. Counts include all matching messages; output tables contain at most 2,000 rows, evidence contains at most 100 recent messages, and excerpts contain at most 2,000 characters. Truncation is explicit; full messages remain retrievable by ID.

Revoked and undated messages are excluded. Undated records are counted separately because their reporting period is unknown. Participants are distinct source/account IDs; unknown accounts do not contribute to participant totals. Accounts on different platforms are not automatically merged.

Reports are snapshots and are not rewritten by index updates. They contain chat data, remain in the private data directory and require administrator access. There is no automatic history deletion; monitor disk usage. Restore task backups using this version or newer, not an older release.

## HTTP API

All paths below use `/api` and require an administrator session or an existing administrator service credential. Scoped query keys cannot access tasks. Browser writes require same-origin validation; operations are audited. The existing five MCP tools remain read-only.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /task-planner | Model configuration status; no credentials |
| POST | /task-range | Server-calculated first reporting range |
| GET / POST | /task-drafts | List unfinished drafts / generate or save a plan |
| GET / PUT | /task-drafts/{id} | Read / revise; writes require revision |
| POST | /task-drafts/{id}/confirm | Confirm revision; run_now defaults to true; duplicate requests do not duplicate execution |
| POST | /task-drafts/{id}/archive | Archive an unconfirmed draft |
| GET | /tasks/{id}/topic | Last successful report, history and plan versions |
| POST | /commands | Queue an immediate report; returns 202 and run ID |
| GET / POST | /tasks | List / create saved rules |
| GET / PUT | /tasks/{id} | Retrieve / fully replace a rule |
| POST | /tasks/{id}/pause or /resume | Pause / enable scheduling |
| POST | /tasks/{id}/run | Queue a manual execution; returns 202 |
| GET | /task-runs?task_id={id}&offset=0 | Run history, 30 per page; optional task filter |
| GET | /task-runs/{id} | Status, rule snapshot and report |
| GET | /task-runs/{id}/export?format=csv | Download csv / markdown / json; optional section=0..5 selects a step |

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

`weekday` is Monday=0 through Sunday=6; `frequency` is manual/daily/weekly/monthly; `dimension` is group/day/sender/type/records; `window` is complete_days/rolling/previous_week/previous_month. Immediate commands accept only name, rule and output. Run states are queued/running/succeeded/failed/cancelled; exports require succeeded.

Natural-language drafts accept `request`, optional `groups`, and optional `context` containing the currently edited TaskInput for refinement. Manual drafts use `config`; changes to an existing task include `task_id`. Unresolved `questions` block confirmation; `notes` appear in the review. Up to 100 unfinished drafts are retained, with optimistic revision checks.

Optional `workflow` contains `objective`, `request`, and `steps`; each step has `{kind, title, instruction}`. Statistical kinds match dimension; analysis uses `summary`. Existing `/tasks` and `/commands` remain available for explicit API operations; the new web flow uses draft confirmation.
