"""Persistent, local statistics jobs. Rules are data, never executable prompts."""
from __future__ import annotations

import csv
import datetime as dt
import fcntl
import io
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .database import private_dir, read_db
from .query import NAMES, like
from .security import Principal


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class GroupRef(Input):
    source: Literal['feishu', 'wecom', 'wechat', 'dingtalk']
    id: str = Field(min_length=1, max_length=512)


class Rule(Input):
    groups: list[GroupRef] = Field(min_length=1, max_length=50)
    keyword: str = Field(default='', max_length=160)
    message_type: str = Field(default='', max_length=32, pattern=r'^[a-z_]*$')
    days: int = Field(default=7, ge=1, le=366)
    window: Literal['rolling', 'complete_days'] = 'complete_days'
    dimension: Literal['group', 'day', 'sender', 'type', 'records'] = 'group'
    timezone: str = 'Asia/Shanghai'

    @field_validator('timezone')
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError('请选择有效的 IANA 时区') from None
        return value


class Schedule(Input):
    frequency: Literal['manual', 'daily', 'weekly', 'monthly'] = 'weekly'
    time: str = Field(default='09:00', pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    weekday: int = Field(default=0, ge=0, le=6)
    monthday: int = Field(default=1, ge=1, le=28)


class TaskInput(Input):
    name: str = Field(min_length=1, max_length=80)
    rule: Rule
    schedule: Schedule = Field(default_factory=Schedule)
    output: Literal['csv', 'markdown', 'json'] = 'csv'
    enabled: bool = True

    @field_validator('name')
    @classmethod
    def valid_name(cls, value):
        if not value.strip():
            raise ValueError('任务名称不能为空')
        return value.strip()


class CommandInput(Input):
    rule: Rule
    name: str = Field(default='即时统计', min_length=1, max_length=80)
    output: Literal['csv', 'markdown', 'json'] = 'csv'


def next_run(schedule, timezone, after):
    """Strictly future wall-clock occurrence. Skip nonexistent DST times."""
    if schedule.frequency == 'manual':
        return None
    zone = ZoneInfo(timezone)
    start = dt.datetime.fromtimestamp(after, zone).date()
    hour, minute = map(int, schedule.time.split(':'))
    for offset in range(370):
        day = start + dt.timedelta(days=offset)
        if schedule.frequency == 'weekly' and day.weekday() != schedule.weekday:
            continue
        if schedule.frequency == 'monthly' and day.day != schedule.monthday:
            continue
        local = dt.datetime.combine(day, dt.time(hour, minute), zone)
        stamp = local.timestamp()
        # On a fall-back day use only the first occurrence, never run twice.
        if stamp > after and dt.datetime.fromtimestamp(stamp, zone) == local:
            return int(stamp)
    raise ValueError('无法计算下次运行时间')


def report(queries, rule, at):
    """All SQL runs against one consistent archive snapshot, with a time budget."""
    zone = ZoneInfo(rule.timezone)
    end = dt.datetime.fromtimestamp(at, zone)
    if rule.window == 'complete_days':
        end = end.replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - dt.timedelta(days=rule.days)
    groups = list(dict.fromkeys((g.source, g.id) for g in rule.groups))
    where = '(' + ' OR '.join('(m.source=? AND m.group_id=?)' for _ in groups) + ')'
    args = [v for group in groups for v in group]
    if rule.keyword:
        where += " AND m.text LIKE ? ESCAPE '\\'"
        args.append(like(rule.keyword))
    if rule.message_type:
        where += ' AND m.type=?'
        args.append(rule.message_type)
    selected_where, selected_args = where, args.copy()
    where += ' AND m.ts>=? AND m.ts<? AND m.deleted=0'
    args += [int(start.timestamp()*1000), int(end.timestamp()*1000)]
    if not queries.path.is_file():
        raise FileNotFoundError('Archive is not initialized')
    with read_db(queries.path) as db:
        deadline = time.monotonic() + 45
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        db.create_function('task_day', 1, lambda ts: dt.datetime.fromtimestamp(ts/1000, zone).date().isoformat())
        refs = []
        for source, gid in groups:
            row = db.execute("SELECT name,kind FROM groups WHERE source=? AND id=?", (source, gid)).fetchone()
            if row is None or row['kind'] != 'group':
                raise ValueError('所选群已不在当前索引中，请重新选择')
            refs.append({'source': source, 'id': gid, 'name': row['name'] or gid})
        totals = dict(db.execute(f'''SELECT COUNT(*) messages,
            COUNT(DISTINCT source||char(0)||group_id) active_groups,
            COUNT(DISTINCT CASE WHEN sender_id!='' THEN source||char(0)||sender_id END) participants
            FROM messages m WHERE {where}''', args).fetchone())
        undated = db.execute(f'SELECT COUNT(*) FROM messages m WHERE {selected_where} AND m.ts IS NULL AND m.deleted=0', selected_args).fetchone()[0]
        joined = f'FROM messages m JOIN groups g ON g.source=m.source AND g.id=m.group_id WHERE {where}'
        rows = []
        columns = []
        dimensions = {
            'group': ("m.source source,m.group_id group_id,COALESCE(NULLIF(g.name,''),m.group_id) group_name", 'm.source,m.group_id', [('source','来源'),('group_id','群编号'),('group_name','群名')]),
            'day': ('task_day(m.ts) day', 'day', [('day','日期')]),
            'sender': ("m.source source,m.sender_id sender_id,COALESCE(NULLIF(MAX(m.sender_name),''),NULLIF(m.sender_id,''),'未知发送者') sender", 'm.source,m.sender_id', [('source','来源'),('sender_id','发送者编号'),('sender','发送者')]),
            'type': ('m.type type', 'm.type', [('type','消息类型')]),
        }
        if rule.dimension in dimensions:
            select, by, columns = dimensions[rule.dimension]
            order = 'day' if rule.dimension == 'day' else 'messages DESC,'+by
            rows = [dict(r) for r in db.execute(f'SELECT {select},COUNT(*) messages {joined} GROUP BY {by} ORDER BY {order} LIMIT 2001', args)]
            columns = columns + [('messages','消息数')]
            if rule.dimension == 'group':
                present = {(r['source'], r['group_id']) for r in rows}
                rows += [{'source': g['source'], 'group_id': g['id'], 'group_name': g['name'], 'messages': 0} for g in refs if (g['source'], g['id']) not in present]
        evidence = [dict(r) for r in db.execute(f'''SELECT m.source,m.id,m.group_id,
            COALESCE(NULLIF(g.name,''),m.group_id) group_name,m.sender_id,
            COALESCE(NULLIF(m.sender_name,''),NULLIF(m.sender_id,''),'未知发送者') sender,
            m.ts,m.type,SUBSTR(m.text,1,2000) text,LENGTH(m.text)>2000 text_truncated {joined}
            ORDER BY m.ts DESC,m.source,m.id LIMIT ?''', args+[2001 if rule.dimension == 'records' else 100])]
        for row in evidence:
            row['sent_at'] = dt.datetime.fromtimestamp(row.pop('ts')/1000, zone).isoformat(timespec='seconds')
        if rule.dimension == 'records':
            rows = evidence
            columns = [('source','来源'),('group_id','群编号'),('group_name','群名'),('id','消息 ID'),('sent_at','时间'),('sender_id','发送者编号'),('sender','发送者'),('type','消息类型'),('text','正文摘录'),('text_truncated','正文是否截断')]
        meta = dict(db.execute('SELECT key,value FROM metadata'))
    return {'rule': rule.model_dump(), 'groups': refs, 'range': {'start': start.isoformat(timespec='seconds'), 'end_exclusive': end.isoformat(timespec='seconds')},
            'indexed_at': meta.get('indexed_at'), 'totals': totals, 'undated_excluded': undated,
            'columns': [{'key': k, 'label': v} for k, v in columns], 'rows': rows[:2000],
            'truncated': len(rows)>2000, 'evidence': evidence[:100], 'generated_at': at,
            'notes': '按已归档消息统计，排除已撤回和无时间记录；附件仅统计消息元数据。表格最多 2000 行，原文依据为最近 100 条，每条摘录最多 2000 字。'}


SCHEMA = '''
CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, config TEXT NOT NULL, creator TEXT NOT NULL,
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, enabled INTEGER NOT NULL, next_run INTEGER);
CREATE TABLE IF NOT EXISTS task_runs(id TEXT PRIMARY KEY, task_id TEXT, name TEXT NOT NULL, config TEXT NOT NULL,
 actor TEXT NOT NULL, trigger TEXT NOT NULL, scheduled_at INTEGER NOT NULL, created_at INTEGER NOT NULL,
 started_at INTEGER, finished_at INTEGER, status TEXT NOT NULL, error TEXT, result TEXT);
CREATE INDEX IF NOT EXISTS task_runs_task ON task_runs(task_id,created_at DESC);
CREATE INDEX IF NOT EXISTS task_runs_status ON task_runs(status,created_at);
'''


class TaskStore:
    def __init__(self, path, queries):
        self.path, self.queries = Path(path), queries
        private_dir(self.path.parent)
        with self.db() as db:
            db.executescript(SCHEMA)
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def validate_rule(self, rule):
        for g in rule.groups:
            if self.queries.group(Principal('task-validation', admin=True), g.source, g.id)['kind'] != 'group':
                raise ValueError('任务仅支持群会话')
        if len({(g.source, g.id) for g in rule.groups}) != len(rule.groups):
            raise ValueError('不能重复选择同一个群')

    @staticmethod
    def task_row(row):
        item = dict(row)
        item.update(json.loads(item.pop('config')))
        item['enabled'] = bool(row['enabled'])
        return item

    def list(self):
        with self.db() as db:
            return [self.task_row(r) for r in db.execute('''SELECT t.*,
                (SELECT status FROM task_runs WHERE task_id=t.id ORDER BY created_at DESC,rowid DESC LIMIT 1) last_status,
                (SELECT id FROM task_runs WHERE task_id=t.id ORDER BY created_at DESC,rowid DESC LIMIT 1) last_run_id
                FROM tasks t ORDER BY updated_at DESC,id''')]

    def get(self, task_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        if row is None:
            raise LookupError('任务不存在')
        return self.task_row(row)

    def save(self, body, actor, task_id=None, now=None):
        self.validate_rule(body.rule)
        now = int(time.time()) if now is None else now
        upcoming = next_run(body.schedule, body.rule.timezone, now) if body.enabled else None
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if task_id:
                if not db.execute('SELECT id FROM tasks WHERE id=?', (task_id,)).fetchone():
                    raise LookupError('任务不存在')
                db.execute('UPDATE tasks SET config=?,updated_at=?,enabled=?,next_run=? WHERE id=?', (body.model_dump_json(), now, body.enabled, upcoming, task_id))
            else:
                if db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] >= 200:
                    raise ValueError('任务数量已达 200 个上限')
                task_id = uuid.uuid4().hex
                db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?)', (task_id, body.model_dump_json(), actor, now, now, body.enabled, upcoming))
        return self.get(task_id)

    def set_enabled(self, task_id, enabled):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if row is None:
                raise LookupError('任务不存在')
            config = TaskInput.model_validate_json(row['config'])
            now = int(time.time())
            upcoming = next_run(config.schedule, config.rule.timezone, now) if enabled else None
            db.execute('UPDATE tasks SET enabled=?,next_run=?,updated_at=? WHERE id=?', (enabled, upcoming, now, task_id))
            if not enabled:
                db.execute("UPDATE task_runs SET status='cancelled',finished_at=? WHERE task_id=? AND status='queued' AND trigger='scheduled'", (now, task_id))
        return self.get(task_id)

    @staticmethod
    def insert_run(db, body, actor, trigger, at, task_id=None):
        if db.execute("SELECT COUNT(*) FROM task_runs WHERE status IN ('queued','running')").fetchone()[0] >= 20:
            raise ValueError('执行队列已满，请稍后重试')
        if task_id and db.execute("SELECT id FROM task_runs WHERE task_id=? AND status IN ('queued','running')", (task_id,)).fetchone():
            raise ValueError('此任务正在执行或等待执行')
        run_id = uuid.uuid4().hex
        db.execute('''INSERT INTO task_runs(id,task_id,name,config,actor,trigger,scheduled_at,created_at,status)
            VALUES(?,?,?,?,?,?,?,?, 'queued')''', (run_id, task_id, body.name, body.model_dump_json(), actor, trigger, at, int(time.time())))
        return run_id

    def enqueue(self, body, actor, task_id=None):
        self.validate_rule(body.rule)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            return self.insert_run(db, body, actor, 'manual' if task_id else 'console', int(time.time()), task_id)

    def runs(self, task_id=None, offset=0):
        where, args = ('WHERE task_id=?', [task_id]) if task_id else ('', [])
        with self.db() as db:
            total = db.execute('SELECT COUNT(*) FROM task_runs '+where, args).fetchone()[0]
            rows = [dict(r) for r in db.execute('SELECT id,task_id,name,trigger,created_at,started_at,finished_at,status,error FROM task_runs '+where+' ORDER BY created_at DESC,rowid DESC LIMIT 30 OFFSET ?', args+[offset])]
        return {'items': rows, 'total': total, 'offset': offset, 'has_more': offset+len(rows)<total}

    def run(self, run_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM task_runs WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise LookupError('运行记录不存在')
        item = dict(row)
        item['config'] = json.loads(item['config'])
        item['result'] = json.loads(item['result']) if item['result'] else None
        return item

    def tick(self, now=None):
        """One OS lock owns scheduling and execution, across API workers on this host."""
        now = int(time.time()) if now is None else now
        with (self.path.parent/'task-worker.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute("UPDATE task_runs SET status='failed',error='服务中断，未完成统计；请重新运行',finished_at=? WHERE status='running'", (now,))
                for row in db.execute('SELECT * FROM tasks WHERE enabled=1 AND next_run<=? ORDER BY next_run,id', (now,)).fetchall():
                    body = TaskInput.model_validate_json(row['config'])
                    try:
                        # After downtime, run once for the current window; skip the backlog.
                        self.insert_run(db, body, row['creator'], 'scheduled', now, row['id'])
                    except ValueError:
                        continue
                    db.execute('UPDATE tasks SET next_run=? WHERE id=?', (next_run(body.schedule, body.rule.timezone, now), row['id']))
            for _ in range(5):
                with self.db() as db:
                    db.execute('BEGIN IMMEDIATE')
                    row = db.execute("SELECT * FROM task_runs WHERE status='queued' ORDER BY created_at,rowid LIMIT 1").fetchone()
                    if row is None:
                        break
                    db.execute("UPDATE task_runs SET status='running',started_at=? WHERE id=?", (int(time.time()), row['id']))
                try:
                    rule = Rule.model_validate(json.loads(row['config'])['rule'])
                    result = report(self.queries, rule, row['scheduled_at'])
                    status, error, encoded = 'succeeded', None, json.dumps(result, ensure_ascii=False)
                except Exception as exc:
                    logging.getLogger(__name__).warning('Task run %s failed (%s)', row['id'], type(exc).__name__)
                    status, error, encoded = 'failed', '统计失败：请检查索引、群范围或缩小统计时间后重试', None
                with self.db() as db:
                    db.execute('UPDATE task_runs SET status=?,error=?,result=?,finished_at=? WHERE id=?', (status, error, encoded, int(time.time()), row['id']))


class TaskWorker:
    def __init__(self, store):
        self.store, self.stop_event, self.wake_event = store, threading.Event(), threading.Event()
        self.thread = threading.Thread(target=self.loop, name='chatarchive-tasks', daemon=True)

    def start(self):
        self.thread.start()

    def loop(self):
        while not self.stop_event.is_set():
            self.wake_event.clear()
            try:
                self.store.tick()
            except Exception:
                logging.getLogger(__name__).exception('Task scheduler failed')
            self.wake_event.wait(15)

    def stop(self):
        self.stop_event.set()
        self.wake_event.set()


def export_run(run, format):
    if run['status'] != 'succeeded':
        raise ValueError('此运行尚未生成结果')
    result = run['result']
    if format == 'json':
        return json.dumps(run, ensure_ascii=False, indent=2), 'application/json', 'json'
    columns, rows = result['columns'], result['rows']
    if format == 'csv':
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        def safe(value):
            value = str(value if value is not None else '')
            return "'"+value if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t','\r','\n')) else value
        writer.writerow([c['label'] for c in columns])
        writer.writerows([[safe(row.get(c['key'], '')) for c in columns] for row in rows])
        return '\ufeff'+output.getvalue(), 'text/csv', 'csv'
    if format != 'markdown':
        raise ValueError('不支持的导出格式')
    def md(value):
        import html
        return html.escape(str(value if value is not None else ''), quote=False).replace('\\','\\\\').replace('|','\\|').replace('\n',' ').replace('\r',' ').replace('[','\\[').replace(']','\\]').replace('`','\\`')
    lines = ['# '+md(run['name']), '', '时间范围 / Range: '+result['range']['start']+' → '+result['range']['end_exclusive']+' (exclusive)',
             '索引 / Index: '+str(result['indexed_at']), '', md(result['notes']), '',
             '命中消息 / Matched messages: '+str(result['totals']['messages'])+' · 输出行 / Output rows: '+str(len(rows))+('（已截断 / truncated）' if result['truncated'] else ''), '',
             '| '+' | '.join(c['label'] for c in columns)+' |', '| '+' | '.join('---' for _ in columns)+' |']
    lines += ['| '+' | '.join(md(row.get(c['key'], '')) for c in columns)+' |' for row in rows]
    return '\n'.join(lines)+'\n', 'text/markdown', 'md'
