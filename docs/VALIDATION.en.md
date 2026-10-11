# 0.4.0-preview.1 validation record

2026-10-11: 51 automated tests passed and all three frontend scripts passed syntax checks. A real browser with fictional data exercised group selection, ordering, draft persistence, confirmation, version changes, historical reports, pause/resume and per-step CSV exports. 390px and 320px viewports have no page-level horizontal overflow; mobile confirmation remains reachable. Model planning, citations and concurrent confirmation were verified with test doubles; no production model is configured and external model quality has not been validated. Earlier container and installation records below are historical, not a substitute for current deployment verification.

---

# 0.2.3-preview.1 validation record

**English** · [简体中文](VALIDATION.md)

Date: 2026-10-11. Scope: the single-workspace query preview. This record describes local and isolated-server validation. Commit-specific remote results are shown in [GitHub Actions](https://github.com/daqianwenlv/ChatArchive/actions/workflows/checks.yml).

| Check | Result |
| --- | --- |
| Extract source and install in an independent Python 3.12 environment | Passed; pip check reported no conflicts |
| Account, permission, query, import and recovery tests | 27 passed |
| Actual HTTP login, initial password change, session revocation, groups, messages and analysis | Passed with one fictional group and two messages |
| Official MCP Python SDK 2.3.0 | Streamable HTTP initialization, discovery of five tools and source query passed |
| Frontend syntax and browser preview | Passed; fictional screenshot and no observed console errors |
| Runtime dependency audit | pip-audit 2.10.1 checked 39 locked packages; no known vulnerabilities found on the validation date |
| Source distribution checks | Inventory, credential patterns, Python syntax, sample IDs and exclusion of known private credential values passed |
| Existing Python service upgrade | 0.2.2 query service upgraded after backup; accounts and collector configuration preserved; health and anonymous-access rejection passed |

A dependency scan does not prove the absence of unknown vulnerabilities. These checks are not an independent security audit.

## Container validation

Environment: Linux amd64, Docker 28.1.1, Compose 2.35.1 and Python 3.12.15. The test used extracted source, isolated projects and new volumes, without production data or platform credentials.

All stages of `scripts/verify_docker.py` passed:

1. Build the Dockerfile and verify runtime distributions against official SHA-256 hashes.
2. Initialize, create a local account and import the sample twice; retain one group and two messages.
3. Change the initial password, invalidate old sessions, enforce origin and access checks, and exercise HTTP and official MCP SDK queries.
4. Replace the container while retaining accounts and records; create an online backup.
5. Restore to another volume, reject old credentials, reset the account and verify queries and MCP again.
6. Switch back to the original volume and verify its account and records.

Test containers and volumes were removed afterwards; existing services continued running.

The server could not pull directly from Docker Hub and PyPI downloads were slow. The official Python image was downloaded on a machine with Docker Hub access and loaded on the test server. Packages were fetched through the Tsinghua PyPI mirror with mandatory official distribution hash verification. This does not establish direct Docker Hub connectivity from the test server.

Tested `python:3.12-slim` amd64 manifest: `sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe`. Tags can change; rebuild and validate future releases.

## Limits of this verification

- ARM64 containers, large-scale concurrent workloads and an independent security review have not been tested.
- This version has no schema migration. Container replacement and volume switching do not validate cross-schema migration.
- Upstream raw archives, attachments, platform credentials and proxy configuration require separate backups.
- MCP clients must support HTTP Bearer. OAuth discovery and compatibility with other clients need separate validation.

See the [release process](RELEASE.en.md) for reproduction commands.
