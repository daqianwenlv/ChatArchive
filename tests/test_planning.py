import datetime as dt
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from chatarchive.ai import ModelUnavailable
from chatarchive.planning import DraftStore, DraftInput, ConfirmInput, summarize
from chatarchive.tasks import TaskStore, TaskInput, Rule, WorkStep, Workflow, report, export_run
from chatarchive.query import Queries
from chatarchive.server import create_app


def config(**kwargs):
    return TaskInput(name='协作报告', rule=Rule(groups=[{'source':'feishu','id':'g1'}], window='complete_days', days=30),
        workflow=Workflow(objective='先整理原文，再统计各群消息', steps=[WorkStep(kind='records',title='整理记录'),WorkStep(kind='group',title='汇总群消息')]), **kwargs)


class FakeModel:
    def __init__(self, answer=None): self.answer=answer;self.payload=None
    def status(self): return {'ready':True,'model':'test-only'}
    def complete(self, system, payload): self.payload=payload;return self.answer


def stores(archive, model=None):
    tasks=TaskStore(archive/'tasks.sqlite3',Queries(archive/'archive.sqlite3'))
    return tasks,DraftStore(tasks,model)


def test_draft_never_executes_until_idempotent_confirmation(archive):
    tasks,drafts=stores(archive)
    draft=drafts.propose(DraftInput(request='先整理后统计',config=config()),'admin')
    assert tasks.list()==[] and tasks.runs()['total']==0 and draft['status']=='ready'
    with pytest.raises(ValueError):drafts.confirm(draft['id'],ConfirmInput(revision=2),'admin')
    result=drafts.confirm(draft['id'],ConfirmInput(revision=1),'admin')
    assert drafts.confirm(draft['id'],ConfirmInput(revision=1),'admin')==result
    assert len(tasks.list())==1 and tasks.runs()['total']==1
    tasks.tick()
    run=tasks.run(result['run_id'])
    assert run['status']=='succeeded'
    assert [s['kind'] for s in run['steps']]==['records','group']
    assert all(s['status']=='succeeded' for s in run['steps'])
    assert [s['step']['kind'] for s in run['result']['sections']]==['records','group']
    assert '群名' in export_run(run,'csv',1)[0]
    assert run['config']['plan_version']==1


def test_versions_old_results_and_latest_success_survive_change_failure(archive):
    tasks,drafts=stores(archive)
    draft=drafts.propose(DraftInput(config=config()),'admin')
    confirmed=drafts.confirm(draft['id'],ConfirmInput(revision=1),'admin')
    tasks.tick()
    task=tasks.get(confirmed['task_id'])
    modified=config();modified.name='每日协作';modified.rule.days=1
    pending=drafts.propose(DraftInput(task_id=task['id'],config=modified),'admin')
    assert tasks.get(task['id'])['name']=='协作报告'
    update=drafts.confirm(pending['id'],ConfirmInput(revision=1),'admin')
    assert tasks.get(task['id'])['version']==2
    assert tasks.run(confirmed['run_id'])['config']['plan_version']==1
    with sqlite3.connect(archive/'archive.sqlite3') as db:db.execute("DELETE FROM groups WHERE id='g1'")
    tasks.tick()
    assert tasks.run(update['run_id'])['status']=='failed'
    assert tasks.latest_success(task['id'])['id']==confirmed['run_id']
    assert len(tasks.versions(task['id']))==2
    assert tasks.run(update['run_id'])['steps'][0]['status']=='failed'


def test_concurrent_plan_edit_requires_fresh_review(archive):
    tasks,drafts=stores(archive)
    task=tasks.save(config(),'admin')
    first=drafts.propose(DraftInput(config=config(),task_id=task['id']),'admin')
    second=drafts.propose(DraftInput(config=config(),task_id=task['id']),'admin')
    drafts.confirm(first['id'],ConfirmInput(revision=1,run_now=False),'admin')
    with pytest.raises(ValueError,match='已被修改'):
        drafts.confirm(second['id'],ConfirmInput(revision=1,run_now=False),'admin')
    assert tasks.get(task['id'])['version']==2


def test_model_gets_directory_not_messages_and_cannot_change_selected_scope(archive):
    model=FakeModel({'config':config().model_dump(),'questions':[],'notes':[]})
    tasks,drafts=stores(archive,model)
    draft=drafts.propose(DraftInput(request='整理这个群',groups=[{'source':'feishu','id':'g2'}]),'admin')
    assert draft['status']=='error'
    assert '发布版本' not in json.dumps(model.payload,ensure_ascii=False)
    assert len(model.payload['supplied_groups'])==1
    assert tasks.list()==[]


def test_clarification_cannot_be_confirmed_and_missing_model_retains_request(archive):
    tasks,drafts=stores(archive,FakeModel({'config':None,'questions':['选择哪个产品群？'],'notes':[]}))
    draft=drafts.propose(DraftInput(request='整理产品群'),'admin')
    assert draft['status']=='needs_input'
    with pytest.raises(ValueError):drafts.confirm(draft['id'],ConfirmInput(revision=1),'admin')
    drafts.model=FakeModel()
    drafts.model.complete=lambda *a: (_ for _ in ()).throw(ModelUnavailable('模型未配置'))
    revised=drafts.propose(DraftInput(request='保留这句话',revision=1), 'admin', draft['id'])
    assert revised['status']=='error' and revised['request']=='保留这句话'
    assert revised['revision']==2 and not tasks.list()


def test_calendar_windows_are_not_rolling_seven_days(archive):
    q=Queries(archive/'archive.sqlite3')
    at=dt.datetime.fromisoformat('2026-10-14T09:00:00+08:00').timestamp()
    weekly=report(q,config().rule.model_copy(update={'window':'previous_week'}),at)
    assert weekly['range']['start']=='2026-10-05T00:00:00+08:00'
    assert weekly['range']['end_exclusive']=='2026-10-12T00:00:00+08:00'
    monthly=report(q,config().rule.model_copy(update={'window':'previous_month'}),at)
    assert monthly['range']['start']=='2026-09-01T00:00:00+08:00'
    assert monthly['range']['end_exclusive']=='2026-10-01T00:00:00+08:00'


def test_ai_findings_require_real_citations(archive):
    data=report(Queries(archive/'archive.sqlite3'),config().rule,dt.datetime.fromisoformat('2026-10-12T09:00:00+08:00').timestamp())
    model=FakeModel({'title':'进展','findings':[{'text':'完成测试','kind':'fact','citations':[{'source':'feishu','id':'invented'}]}]})
    with pytest.raises(ValueError,match='无法核对'):summarize('整理进展',data,model)
    model.answer['findings'][0]['citations'][0]['id']=data['evidence'][0]['id']
    result=summarize('整理进展',data,model)
    assert result['sampled']==len(data['evidence'])


def test_confirm_rolls_back_if_queue_full(archive):
    tasks,drafts=stores(archive)
    with tasks.db() as db:
        for _ in range(20):tasks.insert_run(db,config(),'admin','console',0)
    d=drafts.propose(DraftInput(config=config()),'admin')
    with pytest.raises(ValueError,match='队列已满'):drafts.confirm(d['id'],ConfirmInput(revision=1),'admin')
    assert tasks.list()==[] and drafts.get(d['id'])['status']=='ready'


def test_planning_endpoints_admin_only_and_draft_confirmation(archive):
    app=create_app(archive,admin_token='a'*40,scheduler=False)
    with TestClient(app) as client:
        assert client.get('/api/task-planner').status_code==401
        key=app.state.store.create('reader',['feishu'],actor='test')['token']
        client.headers['Authorization']='Bearer '+key
        for path in ['/api/task-planner','/api/task-drafts']:
            assert client.get(path).status_code==403
        assert client.post('/api/task-drafts',json={'config':config().model_dump()}).status_code==403
        client.headers['Authorization']='Bearer '+'a'*40
        response=client.post('/api/task-drafts',json={'config':config().model_dump(),'request':'整理记录'})
        assert response.status_code==201
        draft=response.json()
        approved=client.post('/api/task-drafts/'+draft['id']+'/confirm',json={'revision':1})
        assert approved.status_code==200
        app.state.tasks.tick()
        topic=client.get('/api/tasks/'+approved.json()['task_id']+'/topic').json()
        assert topic['latest_success']['status']=='succeeded'
        assert topic['task']['version']==1
        for asset in ['/workspace.js','/workspace.css']:
            assert client.get(asset).status_code==200
        export=client.get('/api/task-runs/'+approved.json()['run_id']+'/export?format=csv&section=1')
        assert export.status_code==200
        assert client.get('/api/task-runs/'+approved.json()['run_id']+'/export?format=csv&section=5').status_code==400


def test_refinement_preserves_manual_context_and_review_notes(archive):
    edited=config();edited.name='手工调整的名称';edited.workflow.steps.reverse()
    model=FakeModel({'config':edited.model_dump(),'questions':[],'notes':['按已选群生成']} )
    tasks,drafts=stores(archive,model)
    draft=drafts.propose(DraftInput(request='每天统计',context=edited),'admin')
    assert model.payload['current_config']['name']==edited.name
    assert model.payload['current_config']['workflow']['steps'][0]['kind']=='group'
    saved=drafts.propose(DraftInput(request=draft['request'],config=edited,revision=1,review_notes=draft['proposal']['notes']),'admin',draft['id'])
    assert '按已选群生成' in saved['proposal']['notes']
    drafts.archive(saved['id'])
    assert drafts.list()==[] and drafts.get(saved['id'])['status']=='archived'
    with pytest.raises(ValueError):drafts.confirm(saved['id'],ConfirmInput(revision=2),'admin')


def test_plan_confirmation_does_not_resume_concurrently_paused_task(archive):
    tasks,drafts=stores(archive)
    task=tasks.save(config(),'admin')
    pending=drafts.propose(DraftInput(config=config(),task_id=task['id']),'admin')
    tasks.set_enabled(task['id'],False)
    confirmed=drafts.confirm(pending['id'],ConfirmInput(revision=1),'admin')
    assert not tasks.get(task['id'])['enabled']
    assert tasks.get(task['id'])['next_run'] is None
    tasks.tick()
    assert tasks.run(confirmed['run_id'])['status']=='succeeded'
    assert not tasks.get(task['id'])['enabled']


def test_interrupted_run_cancels_unstarted_steps(archive):
    tasks,_=stores(archive)
    run=tasks.enqueue(config(),'admin')
    with tasks.db() as db:
        db.execute("UPDATE task_runs SET status='running' WHERE id=?",(run,))
        db.execute("UPDATE task_run_steps SET status='running' WHERE run_id=? AND ordinal=0",(run,))
    tasks.tick()
    result=tasks.run(run)
    assert result['status']=='failed'
    assert [s['status'] for s in result['steps']]==['failed','cancelled']


def test_range_api_uses_server_calendar_without_reading_groups(archive):
    app=create_app(archive,admin_token='a'*40,scheduler=False)
    with TestClient(app) as client:
        assert client.post('/api/task-range',json={'window':'previous_week'}).status_code==401
        client.headers['Authorization']='Bearer '+'a'*40
        response=client.post('/api/task-range',json={'window':'previous_week','timezone':'Asia/Shanghai'})
        assert response.status_code==200
        start=dt.datetime.fromisoformat(response.json()['start'])
        end=dt.datetime.fromisoformat(response.json()['end_exclusive'])
        assert start.weekday()==0 and start.hour==0 and end-start==dt.timedelta(days=7)
        assert client.post('/api/task-range',json={'timezone':'made_up'}).status_code==400
