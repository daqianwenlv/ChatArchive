# Preview release process

**English** · [简体中文](RELEASE.md)

The current scope is a single-workspace query preview: local login, archive imports, queries, MCP, backup and recovery. A raw-event store, platform collection management, member roles, DingTalk collection and built-in model analysis are future work.

## Verification

```sh
python -m pip install -r requirements.lock
python -m pip install -r requirements-dev.txt
python -m pip check
python -m pytest tests -q
node --check web/app.js
python scripts/package_source.py
python scripts/release_check.py
python -m pip_audit -r requirements.lock --no-deps --disable-pip --strict
python scripts/verify_docker.py --report docker-verification.json
```

Docker verification requires Engine and Compose v2. The script creates randomly named projects, volumes and a loopback port, uses fictional sample data, ignores any configured administrator token, and removes its own test containers and volumes afterwards.

[Release checks](https://github.com/daqianwenlv/ChatArchive/actions/workflows/checks.yml) runs these checks in GitHub Actions. Action dependencies are pinned to commit SHAs. A configured workflow is not proof of a successful run: inspect the status for the commit being published.

## Distribution checks

The source ZIP uses an explicit file inventory. Runtime data, backups, private configuration, credentials and developer history are excluded. Fixed timestamps and permissions make repeated packaging of the same source reproducible.

`release_check.py` checks inventory, SHA-256, credential patterns, Python syntax and fictional sample IDs. Optionally pass `--deny-file` with a private local JSON file to check that its long string values are absent; the values are not printed. This does not replace manual review or a security audit.

Runtime dependencies include official PyPI distribution hashes, and Docker explicitly installs with `--require-hashes`. Install optional development tools separately. See [validation](VALIDATION.en.md) for the tested network conditions and mirror configuration.

Publish source, SHA256SUMS, release notes, installation instructions, known limitations and verification results together. Screenshots must use fictional data. Never upload the entire private development directory.

## Repository maintenance

- Repository: [daqianwenlv/ChatArchive](https://github.com/daqianwenlv/ChatArchive).
- Keep the private reporting route in [SECURITY.md](../SECURITY.md) accurate.
- Review dependency updates and enable applicable credential protection features.
- Require successful checks for the intended commit before tagging a release.

## Compatibility

0.2.3-preview.1 preserves the 0.2.2 query, account and key schemas. Back up first, retain the previous code or image, and verify before switching. The optional bridge configuration changes introduced in 0.2.1 still require explicit configuration; do not overwrite production environment files.

Reverting code does not revert data. Restore databases into a separate directory or volume and compare before switching. Future schema changes must include migration and rollback instructions.
