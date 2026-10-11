# Changelog

**English** · [简体中文](CHANGELOG.md)

## 0.3.0-preview.1 — Command console and recurring tasks

- Added cross-group statistics, daily/weekly/monthly schedules, pause/resume and manual runs.
- Persisted rules, run status, result snapshots and message references; CSV, Markdown and JSON exports.
- Host process lock prevents duplicate workers. Restoring a backup pauses schedules and cancels unfinished runs.
- Task endpoints require an administrator and inherit origin checks and auditing.

## 0.2.3-preview.1 — Independent installation and maintenance

- Documented clean installation, local login, fictional sample data and a synthetic screenshot.
- Added backup, verified restore into an empty directory and diagnostics. Restore invalidates historical sessions, local passwords and API/MCP keys.
- Serialized general imports with an index writer lock to prevent concurrent snapshot replacement.
- Displayed the configured timezone and stopped reporting continuous-collection delay for manually imported records.
- Added an official MCP SDK client example, complete Docker verification and dependency/release checks.
- Locked runtime distribution hashes from official PyPI; configurable package mirrors still require matching SHA-256 hashes.
- Added reproducible source packaging, contribution and recovery documentation, and a GitHub Actions workflow.
- Prepared English and Chinese project documentation and community templates for public hosting.

The query, account and access-key schemas remain compatible with 0.2.2. This is a single-workspace query preview; member roles, a raw-event store and platform collection setup are not implemented.

## 0.2.2-preview.1 — Account login

- Added local administrator accounts, mandatory initial password change, session revocation, logout and server-side reset/disable commands.
- Separated browser sessions from MCP keys while retaining trusted-proxy Feishu administrator login.
- Verified a deployed login, password change, private queries, MCP discovery and key revocation. Nineteen automated tests passed at that version.

## 0.2.1-preview.1 — Release preparation

- Documented the target server architecture, current scope and staged acceptance criteria.
- Made legacy bridge paths and connection labels configurable; added path escaping and missing-directory tests.
- Restricted source packaging to a file inventory and rejected symlinks.

This version did not implement PostgreSQL or member roles. The bridge configuration requires explicit migration; see [deployment](docs/DEPLOYMENT.en.md).

## 0.2.0 — Query preview

- Conversation directory, message search, statistics and message references.
- Existing Feishu, WeCom and WeChat archive imports, private SQLite snapshots and scoped query keys.
- Five read-only MCP tools, HTTP queries, Python startup, sample data and source packaging.

Python and protocol behavior were validated at this version. Actual container verification was added in 0.2.3-preview.1.
