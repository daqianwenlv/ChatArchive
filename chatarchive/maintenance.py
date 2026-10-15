"""Portable snapshot backup, verified restore to an empty directory, and diagnostics."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, re, shutil, sqlite3, stat, sys, tempfile, time, zipfile
from contextlib import closing
from pathlib import Path
from . import __version__
from .database import private_dir, read_db
from .media import DIGEST

DATABASES = {
    'archive.sqlite3': {'sources', 'groups', 'messages', 'metadata'},
    'access.sqlite3': {'tokens', 'audit'},
    'accounts.sqlite3': {'users', 'sessions', 'login_limits'},
    'tasks.sqlite3': {'tasks', 'task_runs'},
    'catalog.sqlite3': {'categories', 'group_labels', 'catalog_jobs'},
}
MAX_MANIFEST_BYTES = 65536
MEDIA_ENTRY = re.compile(r'media/([0-9a-f]{2})/([0-9a-f]{64})')


def media_files(data):
    """Archived attachments; the file name is the SHA-256 of its content."""
    root = Path(data)/'media'
    if not root.is_dir():
        return []
    return sorted(f for f in root.glob('??/*') if f.is_file() and not f.is_symlink() and DIGEST.fullmatch(f.name) and f.parent.name == f.name[:2])


def copy_verified(src, dst, digest):
    h = hashlib.sha256()
    while chunk := src.read(1024*1024):
        h.update(chunk)
        dst.write(chunk)
    if h.hexdigest() != digest:
        raise ValueError('Attachment checksum mismatch: '+digest)


def checksum(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def validate_database(path, name):
    with read_db(path) as db:
        db.execute('PRAGMA trusted_schema=OFF')
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('Database integrity check failed: '+name)
        tables = {r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not DATABASES[name] <= tables:
            raise ValueError('Unsupported database schema: '+name)
        if name == 'archive.sqlite3':
            return dict(db.execute('SELECT source,COUNT(*) FROM messages GROUP BY source'))
    return None


def backup(data, output):
    data, output = Path(data).resolve(), Path(output).resolve()
    if not (data/'archive.sqlite3').is_file():
        raise ValueError('Initialize or import an archive before backing up')
    if output.exists():
        raise FileExistsError('Backup destination already exists')
    private_dir(output.parent)
    manifest = {'format': 2, 'version': __version__, 'created_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'files': {}}
    with tempfile.TemporaryDirectory(prefix='.chatarchive-backup-', dir=output.parent) as temp:
        temp = Path(temp)
        for name in DATABASES:
            source = data/name
            if not source.exists():
                continue
            if source.is_symlink():
                raise ValueError('Database symlinks are not supported')
            destination = temp/name
            with read_db(source) as src, closing(sqlite3.connect(destination)) as dst:
                src.backup(dst)
            destination.chmod(0o600)
            counts = validate_database(destination, name)
            manifest['files'][name] = {'bytes': destination.stat().st_size, 'sha256': checksum(destination)}
            if counts is not None:
                manifest['messages'] = counts
        bundle = temp/'backup.zip'
        with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as z:
            for name in manifest['files']:
                z.write(temp/name, name)
            # Attachments are immutable and already compressed; store them as is, verifying each one.
            count = size = 0
            for path in media_files(data):
                with path.open('rb') as src, z.open(zipfile.ZipInfo('media/'+path.name[:2]+'/'+path.name), 'w', force_zip64=True) as dst:
                    copy_verified(src, dst, path.name)
                count += 1
                size += path.stat().st_size
            manifest['media'] = {'files': count, 'bytes': size}
            z.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
        bundle.chmod(0o600)
        with bundle.open('rb') as f:
            os.fsync(f.fileno())
        # Exclusive publication: never overwrite an older backup, even in a race.
        os.link(bundle, output)
    return {'ok': True, 'backup': str(output), 'sha256': checksum(output), 'messages': manifest['messages'], 'media': manifest['media']}


def restore(bundle, data):
    bundle, data = Path(bundle).resolve(), Path(data).resolve()
    if data.exists() and (not data.is_dir() or any(data.iterdir())):
        raise ValueError('Restore requires a new or empty data directory; existing data is never overwritten')
    private_dir(data)
    created = []
    marker = data/'.restore-in-progress'
    with marker.open('x') as f:
        f.write('Do not start the API until restoration finishes.\n')
    try:
        with tempfile.TemporaryDirectory(prefix='.restore-', dir=data) as temp, zipfile.ZipFile(bundle) as z:
            temp = Path(temp)
            entries = z.infolist()
            media = [entry for entry in entries if MEDIA_ENTRY.fullmatch(entry.filename)]
            names = [entry.filename for entry in entries if not MEDIA_ENTRY.fullmatch(entry.filename)]
            if len(entries) != len({entry.filename for entry in entries}) or not set(names) <= set(DATABASES)|{'manifest.json'}:
                raise ValueError('Unexpected or duplicate backup entries')
            if 'manifest.json' not in names or z.getinfo('manifest.json').file_size > MAX_MANIFEST_BYTES:
                raise ValueError('Missing or oversized backup manifest')
            manifest = json.loads(z.read('manifest.json'))
            if not isinstance(manifest, dict) or manifest.get('format') not in (1, 2) or not isinstance(manifest.get('files'), dict):
                raise ValueError('Unsupported backup format')
            files = manifest['files']
            if 'archive.sqlite3' not in files or set(names) != set(files)|{'manifest.json'}:
                raise ValueError('Backup manifest does not match its contents')
            if len(media) != (manifest.get('media') or {}).get('files', 0):
                raise ValueError('Backup attachment count does not match its manifest')
            size = sum(entry.file_size for entry in entries)
            if size + 16*1024*1024 > shutil.disk_usage(data).free:
                raise ValueError('Not enough free space to restore this backup')
            for name, metadata in files.items():
                if not isinstance(metadata, dict) or not isinstance(metadata.get('bytes'), int) or not isinstance(metadata.get('sha256'), str):
                    raise ValueError('Invalid file metadata: '+name)
                entry = z.getinfo(name)
                if stat.S_ISLNK(entry.external_attr >> 16) or entry.is_dir():
                    raise ValueError('Backup entries must be ordinary database files')
                if entry.file_size != metadata.get('bytes'):
                    raise ValueError('Backup size mismatch: '+name)
                destination = temp/name
                with z.open(entry) as src, destination.open('xb') as dst:
                    shutil.copyfileobj(src, dst, length=1024*1024)
                destination.chmod(0o600)
                if checksum(destination) != metadata.get('sha256'):
                    raise ValueError('Backup checksum mismatch: '+name)
                validate_database(destination, name)
            # A historical backup must not revive revoked access or old passwords.
            if (temp/'access.sqlite3').exists():
                with closing(sqlite3.connect(temp/'access.sqlite3')) as db:
                    db.execute('PRAGMA trusted_schema=OFF')
                    db.execute('UPDATE tokens SET revoked_at=? WHERE revoked_at IS NULL', (int(time.time()),))
                    db.commit()
            if (temp/'accounts.sqlite3').exists():
                with closing(sqlite3.connect(temp/'accounts.sqlite3')) as db:
                    db.execute('PRAGMA trusted_schema=OFF')
                    db.execute('DELETE FROM sessions')
                    db.execute('DELETE FROM login_limits')
                    db.execute("UPDATE users SET password='',must_change=1 WHERE external_id IS NULL")
                    db.execute('UPDATE users SET disabled=1 WHERE external_id IS NOT NULL')
                    db.commit()
            if (temp/'tasks.sqlite3').exists():
                with closing(sqlite3.connect(temp/'tasks.sqlite3')) as db:
                    db.execute('PRAGMA trusted_schema=OFF')
                    db.execute('UPDATE tasks SET enabled=0,next_run=NULL')
                    if db.execute("SELECT name FROM sqlite_master WHERE name='task_run_steps'").fetchone():
                        db.execute("UPDATE task_run_steps SET status='cancelled',error='Restored backup',finished_at=? WHERE status IN ('queued','running')", (int(time.time()),))
                    db.execute("UPDATE task_runs SET status='cancelled',error='Restored backup: run cancelled',finished_at=? WHERE status IN ('queued','running')", (int(time.time()),))
                    db.commit()
            if (temp/'catalog.sqlite3').exists():
                with closing(sqlite3.connect(temp/'catalog.sqlite3')) as db:
                    db.execute('PRAGMA trusted_schema=OFF')
                    db.execute("UPDATE catalog_jobs SET status='failed',error='Restored backup',finished_at=? WHERE status='running'", (int(time.time()),))
                    db.commit()
            for entry in media:
                if stat.S_ISLNK(entry.external_attr >> 16) or entry.is_dir():
                    raise ValueError('Backup entries must be ordinary files')
                prefix, digest = MEDIA_ENTRY.fullmatch(entry.filename).groups()
                if prefix != digest[:2]:
                    raise ValueError('Invalid attachment entry')
                destination = temp/entry.filename
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
                with z.open(entry) as src, destination.open('xb') as dst:
                    copy_verified(src, dst, digest)
                destination.chmod(0o640)
            for name in files:
                destination = data/name
                os.link(temp/name, destination)
                created.append(destination)
            for entry in media:
                destination = data/entry.filename
                (data/'media').mkdir(exist_ok=True, mode=0o750)
                destination.parent.mkdir(exist_ok=True, mode=0o750)
                os.link(temp/entry.filename, destination)
                created.append(destination)
            report = {'ok': True, 'version': __version__, 'backup_version': manifest.get('version'),
                      'messages': manifest.get('messages', {}), 'media': manifest.get('media', {'files': 0, 'bytes': 0}), 'credentials_invalidated': True,
                      'next': 'Reset the local administrator password on this server and issue new API keys before use.'}
            return report
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    finally:
        marker.unlink(missing_ok=True)


def doctor(data):
    data = Path(data)
    result = {'ok': True, 'version': __version__, 'databases': {}}
    if (data/'.restore-in-progress').exists():
        result['ok'] = False
        result['error'] = 'A restore has not completed'
    for name in DATABASES:
        path = data/name
        if not path.exists():
            result['databases'][name] = {'status': 'missing'}
            if name == 'archive.sqlite3':
                result['ok'] = False
            continue
        try:
            counts = validate_database(path, name)
            detail = {'status': 'ok', 'bytes': path.stat().st_size, 'mode': oct(stat.S_IMODE(path.stat().st_mode))}
            if counts is not None:
                detail['messages'] = counts
            if path.stat().st_mode & 0o007:
                detail['status'] = 'world_accessible'
                result['ok'] = False
            result['databases'][name] = detail
        except (sqlite3.Error, ValueError):
            result['ok'] = False
            result['databases'][name] = {'status': 'invalid'}
    stored = media_files(data)
    detail = {'files': len(stored), 'bytes': sum(f.stat().st_size for f in stored), 'missing': 0}
    names = {f.name for f in stored}
    if result['databases'].get('archive.sqlite3', {}).get('status') in ('ok', 'world_accessible'):
        with read_db(data/'archive.sqlite3') as db:
            if any(r['name'] == 'media_sha256' for r in db.execute('PRAGMA table_info(messages)')):
                detail['missing'] = sum(1 for r in db.execute('SELECT DISTINCT media_sha256 FROM messages WHERE media_sha256 IS NOT NULL') if r[0] not in names)
    if detail['missing'] or ((data/'media').is_dir() and (data/'media').stat().st_mode & 0o007):
        result['ok'] = False
    result['media'] = detail
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path(os.environ.get('CHATARCHIVE_DATA', './var')))
    commands = parser.add_subparsers(dest='command', required=True)
    b = commands.add_parser('backup'); b.add_argument('output', type=Path)
    r = commands.add_parser('restore'); r.add_argument('backup', type=Path)
    commands.add_parser('doctor')
    args = parser.parse_args()
    try:
        if args.command == 'restore' and str(args.backup) == '-':
            with tempfile.TemporaryDirectory(prefix='chatarchive-restore-input-') as temp:
                incoming = Path(temp)/'backup.zip'
                with incoming.open('xb') as f:
                    shutil.copyfileobj(sys.stdin.buffer, f, length=1024*1024)
                incoming.chmod(0o600)
                result = restore(incoming, args.data)
        else:
            result = backup(args.data, args.output) if args.command == 'backup' else restore(args.backup, args.data) if args.command == 'restore' else doctor(args.data)
    except (ValueError, OSError, sqlite3.Error, zipfile.BadZipFile, KeyError, TypeError) as exc:
        raise SystemExit('Maintenance failed: '+str(exc)) from None
    print(json.dumps(result, ensure_ascii=False))
    if not result['ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
