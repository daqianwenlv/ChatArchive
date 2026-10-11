# Roadmap

**English** · [简体中文](实施清单.md)

This roadmap describes future work, not current functionality or a release-date commitment. Current capabilities are listed in the [README](../README.md).

## Available in the archive and tasks preview

Conversation directory, archive imports, message search, descriptive statistics, local administrator accounts, scoped HTTP/MCP keys, audit records, verified backups and recovery, Docker/Python installation, fictional examples and release checks. The command console supports cross-group statistics, daily/weekly/monthly tasks, persistent results and CSV/Markdown/JSON report exports.

## Raw archives and data model

Introduce connection instances, raw objects, event and message versions, PostgreSQL migrations, private object storage, and durable jobs. Preserve provenance and missing-field information in legacy imports. Validate retries, interruptions, cursor commits, deduplication and rollback before replacing existing collectors.

## Members and authorization

Add owner setup, invitations, enterprise identity adapters, member roles and connection/group permissions. Separate message access, statistics, exports and raw-object access. Verify isolation and revocation across every query and background job before describing the product as a multi-tenant service.

## Collection and normalization

Add connection setup, identity checks, group discovery, selected collection scope, pause/resume and backfill. Track original timestamps, content blocks, retractions, edits and conflicting events. Version cleaning rules, isolate malformed records, support replay and compare results without overwriting originals.

## Later integrations

Evaluate DingTalk connectors, attachment processing, full archive exports, OAuth discovery, optional S3-compatible storage, and larger-scope content analysis beyond the current cited sample summaries. Add each capability only with a working implementation and its own verification.

## Stable-release work

Exercise schema migrations, disaster recovery, retention and deletion behavior, full-disk failures and representative concurrent loads. Complete an independent review of authentication, authorization and export handling. Keep documentation, compatibility notes and private security reporting current.

The detailed target architecture is currently documented in [Chinese](架构与接口草案.md).
