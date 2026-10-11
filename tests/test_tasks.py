import datetime as dt
import json
import sqlite3
import threading
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from chatarchive.maintenance import backup, restore
from chatarchive.query import Queries
from chatarchive.server import create_app
from chatarchive.tasks import Rule, Schedule, TaskInput, CommandInput, TaskStore, next_run, report, export_run


def at(value):
    return int(dt.datetime.fromisoformat(value).timestamp())


def rule(**kw):
    return Rule(groups=[{'source':'feishu','id':'g1'},{'source':'wecom','id':'wr001'}], **kw)


def test_multigroup_report_filters_and_evidence(archive):
    q = Queries(archive/'archive.sqlite3')
    result = report(q, rule(), at('2026-10-12T09:00:00+08:00'))
    assert result['totals'] == {'messages':3,'active_groups':2,'participants':3}
    assert result['undated_excluded'] == 1
    assert {m['id'] for m in result['evidence']} == {'m0','m1','m3'}
    assert {r['messages'] for r in result['rows']} == {2,1}
    assert result['range']['end_exclusive'] == '2026-10-12T00:00:00+08:00'
    filtered = report(q, rule(keyword='100%', dimension='records'), at('2026-10-12T09:00:00+08:00'))
    assert filtered['totals']['messages'] == 1 and filtered['rows'][0]['id'] == 'm1'
    assert report(q, rule(keyword='_'), at('2026-10-12T09:00:00+08:00'))['totals']['messages'] == 0
    assert report(q, rule(message_type='file'), at('2026-10-12T09:00:00+08:00'))['rows'][0]['messages'] == 0


def test_time_boundaries_identities_and_revoked(archive):
    q = Queries(archive/'archive.sqlite3')
    end = at('2026-10-11T09:00:00+08:00')
    assert report(q, rule(days=1), end)['totals']['messages'] == 1
    assert report(q, rule(days=1, window='rolling'), end)['totals']['messages'] == 3
    people = report(q, rule(dimension='sender'), end+86400)['rows']
    assert len(people) == 3  # Same display name must never merge identities.
    with sqlite3.connect(archive/'archive.sqlite3') as db:
        db.execute("UPDATE messages SET deleted=1 WHERE id='m1'")
    assert report(q, rule(), end+86400)['totals']['messages'] == 2


def test_schedule_timezone_dst_and_monthly():
    sunday = at('2026-10-11T09:00:00+08:00')
    assert next_run(Schedule(), 'Asia/Shanghai', sunday) == at('2026-10-12T09:00:00+08:00')
    assert next_run(Schedule(frequency='daily'), 'Asia/Singapore', sunday) == sunday+86400
    assert next_run(Schedule(frequency='manual'), 'UTC', sunday) is None
    assert next_run(Schedule(frequency='monthly',monthday=28), 'UTC', at('2026-02-28T09:00:00+00:00')) == at('2026-03-28T09:00:00+00:00')
    # 02:30 does not exist on the spring-forward day in New York.
    assert next_run(Schedule(frequency='daily',time='02:30'), 'America/New_York', at('2026-03-08T00:00:00-05:00')) == at('2026-03-09T02:30:00-04:00')
    # Do not run a second time when the local clock falls back.
    assert next_run(Schedule(frequency='daily',time='01:30'), 'America/New_York', at('2026-11-01T01:31:00-04:00')) == at('2026-11-02T01:30:00-05:00')
    with pytest.raises(ValueError): rule(timezone='bad/timezone')


def test_durable_runs_pause_resume_and_recovery(archive):
    store = TaskStore(archive/'tasks.sqlite3', Queries(archive/'archive.sqlite3'))
    now = at('2026-10-12T09:00:00+08:00')
    task = store.save(TaskInput(name='每周统计',rule=rule()), 'admin', now=now-1)
    store.tick(now=now+86400*3)  # Catch up once, not once per missed day.
    first = store.runs(task['id'])['items'][0]
    assert first['status'] == 'succeeded'
    store.tick(now=now+86400*3)
    assert store.runs(task['id'])['total'] == 1
    before = store.run(first['id'])['result']
    task = store.set_enabled(task['id'], False)
    assert task['next_run'] is None and not task['enabled']
    run_id = store.enqueue(TaskInput(name='手动执行',rule=rule()), 'admin', task['id'])
    with pytest.raises(ValueError,match='正在执行'):
        store.enqueue(TaskInput(name='重复',rule=rule()), 'admin', task['id'])
    with store.db() as db:
        db.execute("UPDATE task_runs SET status='running' WHERE id=?", (run_id,))
    TaskStore(store.path, store.queries).tick(now=now)
    assert store.run(run_id)['status'] == 'failed'
    assert store.run(first['id'])['result'] == before
    assert store.set_enabled(task['id'], True)['next_run']


def test_worker_lock_prevents_duplicate_execution(archive, monkeypatch):
    import chatarchive.tasks as module
    store = TaskStore(archive/'tasks.sqlite3', Queries(archive/'archive.sqlite3'))
    run_id = store.enqueue(CommandInput(rule=rule()), 'admin')
    entered, release = threading.Event(), threading.Event()
    calls = []
    original = module.report
    def blocked(*args):
        calls.append(1); entered.set(); assert release.wait(5)
        return original(*args)
    monkeypatch.setattr(module, 'report', blocked)
    first = threading.Thread(target=store.tick)
    first.start()
    try:
        assert entered.wait(5)
        TaskStore(store.path, store.queries).tick()
        assert store.run(run_id)['status'] == 'running'
    finally:
        release.set(); first.join(5)
    assert len(calls) == 1 and store.run(run_id)['status'] == 'succeeded'


def test_backups_include_jobs_but_restore_pauses_them(archive,tmp_path):
    store = TaskStore(archive/'tasks.sqlite3', Queries(archive/'archive.sqlite3'))
    task = store.save(TaskInput(name='测试',rule=rule()), 'admin')
    run_id = store.enqueue(CommandInput(rule=rule()), 'admin')
    output = tmp_path/'tasks-backup.zip'; backup(archive, output)
    dest = tmp_path/'restored'; restore(output, dest)
    restored = TaskStore(dest/'tasks.sqlite3', Queries(dest/'archive.sqlite3'))
    assert restored.get(task['id'])['enabled'] is False
    assert restored.run(run_id)['status'] == 'cancelled'


def test_task_api_auth_validation_execution_and_exports(archive):
    app = create_app(archive,admin_token='a'*40,base_url='http://testserver',scheduler=False)
    body = TaskInput(name='跨群周报',rule=rule()).model_dump()
    with TestClient(app) as client:
        assert client.get('/api/tasks').status_code == 401
        key = app.state.store.create(name='reader',sources=['feishu'],groups=['feishu:g1'],actor='test')['token']
        client.headers['Authorization'] = 'Bearer '+key
        for method,url,payload in [('GET','/api/tasks',None),('POST','/api/tasks',body),('GET','/api/task-runs',None),('POST','/api/commands',{'rule':rule().model_dump()})]:
            assert client.request(method,url,json=payload).status_code == 403
        client.headers['Authorization'] = 'Bearer '+'a'*40
        bad = {**body,'rule':{**body['rule'],'groups':[]}}
        assert client.post('/api/tasks',json=bad).status_code == 400
        bad['rule']['groups'] = [{'source':'feishu','id':'does-not-exist'}]
        assert client.post('/api/tasks',json=bad).status_code == 404
        created = client.post('/api/tasks',json=body)
        assert created.status_code == 201
        task_id = created.json()['id']
        run = client.post('/api/tasks/'+task_id+'/run')
        assert run.status_code == 202
        run_id = run.json()['id']
        assert client.get('/api/task-runs/'+run_id+'/export').status_code == 400
        app.state.tasks.tick()
        result = client.get('/api/task-runs/'+run_id).json()
        assert result['status'] == 'succeeded'
        for fmt,content_type in [('csv','text/csv'),('markdown','text/markdown'),('json','application/json')]:
            response = client.get('/api/task-runs/'+run_id+'/export',params={'format':fmt})
            assert response.status_code == 200 and content_type in response.headers['content-type']
            assert 'attachment;' in response.headers['content-disposition']
        body['name']='修订周报'
        assert client.put('/api/tasks/'+task_id,json=body).json()['name']=='修订周报'
        assert client.get('/api/task-runs/'+run_id).json()['name']=='跨群周报'
        assert not client.post('/api/tasks/'+task_id+'/pause').json()['enabled']
        client.headers['Authorization'] = 'Bearer '+key
        for url in ['/api/tasks/'+task_id,'/api/task-runs/'+run_id,'/api/task-runs/'+run_id+'/export']:
            assert client.get(url).status_code == 403


def test_export_escapes_untrusted_text_and_reports_truncation(archive):
    result = report(Queries(archive/'archive.sqlite3'),rule(),at('2026-10-12T09:00:00+08:00'))
    result['rows'][0]['group_name'] = '=HYPERLINK("https://bad.example")'
    run = {'name':'<img src=x>','status':'succeeded','result':result}
    assert "'=HYPERLINK" in export_run(run,'csv')[0]
    assert '<img' not in export_run(run,'markdown')[0]
    assert json.loads(export_run(run,'json')[0])['name'] == run['name']


def test_pending_scheduled_run_cancelled_on_pause(archive):
    store = TaskStore(archive/'tasks.sqlite3', Queries(archive/'archive.sqlite3'))
    body=TaskInput(name='待执行',rule=rule());task=store.save(body,'admin')
    with store.db() as db:
        run_id=store.insert_run(db,body,'admin','scheduled',at('2026-10-12T09:00:00+08:00'),task['id'])
    store.set_enabled(task['id'],False)
    assert store.run(run_id)['status']=='cancelled'


def test_large_record_inventory_keeps_full_count_and_marks_limits(archive):
    with sqlite3.connect(archive/'archive.sqlite3') as db:
        stamp=at('2026-10-10T12:00:00+08:00')*1000
        db.executemany("INSERT INTO messages(source,id,group_id,ts,text,type) VALUES('feishu',?,'g1',?,?,'text')", [(f'bulk-{i}',stamp,'x'*2100) for i in range(2001)])
    result=report(Queries(archive/'archive.sqlite3'),rule(dimension='records'),at('2026-10-12T09:00:00+08:00'))
    assert result['totals']['messages']==2004
    assert len(result['rows'])==2000 and result['truncated']
    assert len(result['evidence'])==100
    assert any(r['text_truncated'] and len(r['text'])==2000 for r in result['rows'])


def test_missing_group_fails_run_without_stalling_queue(archive):
    store=TaskStore(archive/'tasks.sqlite3',Queries(archive/'archive.sqlite3'))
    bad=store.enqueue(CommandInput(rule=rule()),'admin')
    good=store.enqueue(CommandInput(rule=Rule(groups=[{'source':'feishu','id':'g2'}])),'admin')
    with sqlite3.connect(archive/'archive.sqlite3') as db:db.execute("DELETE FROM groups WHERE id='g1'")
    store.tick()
    assert store.run(bad)['status']=='failed'
    assert store.run(good)['status']=='succeeded'
