# Backup, recovery and switching back

**English** · [简体中文](BACKUP.md)

Backups contain the query database, account database, access-key digests and audit records. Back up upstream collectors, attachments, platform credentials, TLS and proxy configuration separately. The ZIP contains private records and authentication metadata; store it in restricted, encrypted storage.

## Python installations

Run as the service user with the correct `CHATARCHIVE_DATA`:

```sh
python -m chatarchive.maintenance backup ./backups/snapshot.zip
python -m chatarchive.maintenance doctor
```

The SQLite backup API takes a consistent snapshot of each database while the service runs. The three files are not one simultaneous cross-database transaction. The ZIP includes sizes, SHA-256 checksums, application version and message counts. Output mode is `0600`, and an existing backup is never overwritten.

Restore into a new directory before starting the service:

```sh
python -m chatarchive.maintenance --data ./recovered restore ./backups/snapshot.zip
python -m chatarchive.maintenance --data ./recovered doctor
python -m chatarchive.accounts reset admin --data ./recovered
```

If the backup has no local account, use `create admin` instead. Point `CHATARCHIVE_DATA` at the recovered directory and start the service. No running service or importer may use the restore target. A nonempty target is rejected.

## Docker Compose

Use a new backup filename each time:

```sh
docker compose exec -T chatarchive python -m chatarchive.maintenance backup /data/snapshot.zip
mkdir -p backups
chmod 700 backups
docker compose cp chatarchive:/data/snapshot.zip backups/snapshot.zip
chmod 600 backups/snapshot.zip
```

A different Compose project name creates a separate data volume. Stop the original service to release the port while preserving its volume:

```sh
docker compose stop
docker compose -p chatarchive-recovered run --rm -T chatarchive python -m chatarchive.maintenance restore - < backups/snapshot.zip
docker compose -p chatarchive-recovered run --rm chatarchive python -m chatarchive.accounts reset admin
docker compose -p chatarchive-recovered run --rm -T chatarchive python -m chatarchive.maintenance doctor
docker compose -p chatarchive-recovered up -d --wait
```

`restore -` reads from stdin so a difference between host file ownership and the container UID does not prevent access. It stages the ZIP in temporary storage. The default Compose `/tmp` limit is 128 MiB; increase the tmpfs size for a larger backup.

Check login, source and group counts, and sample records before reconnecting clients. To switch back:

```sh
docker compose -p chatarchive-recovered stop
docker compose up -d --wait
```

These commands do not delete old volumes. Stop writes on both sides before deciding which data to retain, so new imports made after recovery are not lost.

## Credentials after recovery

All historical browser sessions and API/MCP keys are invalidated. Local passwords are cleared: reset them on the server with `accounts reset`, then change the initial password at login. Previously disabled local accounts remain disabled. Restored external-identity accounts are disabled pending separate verification. Audit records are retained.

A backup can predate a password change, account disablement or key revocation. Recovery must not reactivate obsolete credentials. Issue new client keys after verification.

## Failure behavior

- Invalid ZIP paths, inventory, checksums or SQLite integrity: no partial databases are published.
- Nonempty target: existing data is preserved and restore is refused.
- Insufficient space: extraction is refused.
- Forced termination: `.restore-in-progress` may remain; the API refuses to start there. Preserve the failed directory and retry in another new directory.
- Failed import: the previous query snapshot remains available. Concurrent index writers are rejected by a file lock.

Practice in isolation first. `scripts/verify_docker.py` exercises recovery and switching back using fictional data.

Tasks and run snapshots live in `tasks.sqlite3` and are included in backups. Restore pauses every task and cancels queued/running executions. Review rules after signing in before resuming schedules. Older backups without this database remain supported.

Version 0.4 also stores drafts, plan versions and per-step status in the task database. Downgrading to 0.3 requires restoring the pre-upgrade task database as well: older code cannot parse workflows or calendar week/month rules. Do not run new rules with an older scheduler.
