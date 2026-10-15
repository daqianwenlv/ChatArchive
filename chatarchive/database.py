from __future__ import annotations
import fcntl, os, sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = '''
CREATE TABLE sources(source TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL, synced_at TEXT, status TEXT, details TEXT NOT NULL DEFAULT '{}');
CREATE TABLE groups(source TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'group', connection TEXT NOT NULL DEFAULT '', enabled INTEGER, in_chat INTEGER, last_sync TEXT, message_count INTEGER NOT NULL DEFAULT 0, participant_count INTEGER NOT NULL DEFAULT 0, first_ts INTEGER, last_ts INTEGER, PRIMARY KEY(source,id));
CREATE TABLE messages(source TEXT NOT NULL, id TEXT NOT NULL, group_id TEXT NOT NULL, ts INTEGER, sender_id TEXT NOT NULL DEFAULT '', sender_name TEXT NOT NULL DEFAULT '', type TEXT NOT NULL DEFAULT 'unknown', text TEXT NOT NULL DEFAULT '', deleted INTEGER NOT NULL DEFAULT 0, parent_id TEXT, media_state TEXT NOT NULL DEFAULT '', raw TEXT NOT NULL DEFAULT '{}', media_sha256 TEXT, media_name TEXT NOT NULL DEFAULT '', media_mime TEXT NOT NULL DEFAULT '', media_bytes INTEGER, first_seen TEXT, PRIMARY KEY(source,id));
CREATE INDEX messages_group_time ON messages(source,group_id,ts DESC,id DESC);
CREATE INDEX messages_time ON messages(ts DESC,source,id DESC);
CREATE INDEX messages_source_type ON messages(source,type,ts DESC);
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
'''

# Columns added after 0.4.0-preview.1; older snapshots are upgraded in place before a merge.
MESSAGE_COLUMNS={'raw':"TEXT NOT NULL DEFAULT '{}'",'media_sha256':'TEXT','media_name':"TEXT NOT NULL DEFAULT ''",'media_mime':"TEXT NOT NULL DEFAULT ''",'media_bytes':'INTEGER','first_seen':'TEXT'}

def upgrade(con):
    present={r[1] for r in con.execute('PRAGMA table_info(messages)')}
    for name,definition in MESSAGE_COLUMNS.items():
        if name not in present:con.execute(f'ALTER TABLE messages ADD COLUMN {name} {definition}')

@contextmanager
def read_db(path):
    p=Path(path).resolve()
    con=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=10)
    con.row_factory=sqlite3.Row
    try:
        con.execute('PRAGMA query_only=ON')
        con.execute('BEGIN')
        yield con
    finally: con.close()

def private_dir(path):
    Path(path).mkdir(parents=True,exist_ok=True,mode=0o700)

@contextmanager
def index_lock(directory):
    private_dir(directory)
    with (Path(directory)/'index.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another index writer is running; retry after it finishes') from None
        yield

def finalize(con):
    # An existing message also creates a catalogue row if the upstream roster lost it.
    con.execute("INSERT OR IGNORE INTO groups(source,id) SELECT source,group_id FROM messages GROUP BY source,group_id")
    con.execute('''UPDATE groups SET (message_count,participant_count,first_ts,last_ts)=(SELECT COUNT(*),COUNT(DISTINCT NULLIF(sender_id,'')),MIN(ts),MAX(ts) FROM messages WHERE source=groups.source AND group_id=groups.id)''')
    con.commit()
