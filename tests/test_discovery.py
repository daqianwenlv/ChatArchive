import datetime as dt
import pytest
from chatarchive.discovery import interpret, search_groups, keyword_intent
from chatarchive.planning import DraftInput, ConfirmInput, DraftStore
from chatarchive.query import Queries
from chatarchive.tasks import TaskStore

NOW=dt.datetime.fromisoformat('2026-10-12T12:00:00+08:00').timestamp()


def test_keyword_retrieval_finds_content_without_knowing_group_name(archive,owner):
    terms=keyword_intent('每周统计发布相关讨论，整理版本计划').terms
    assert '统计' not in terms and '发布' in terms
    result=search_groups(Queries(archive/'archive.sqlite3'),owner,['发布'],90,NOW)
    assert [g['id'] for g in result['items']]==['g1']
    assert result['items'][0]['matched_messages']==2
    assert result['items'][0]['name_terms']==[]
    assert all('发布' in e['text'] for e in result['items'][0]['evidence'])


def test_discovery_enforces_scope_and_literal_search(archive,restricted):
    query=Queries(archive/'archive.sqlite3')
    assert search_groups(query,restricted,['私密'],90,NOW)['items']==[]
    result=search_groups(query,restricted,['100%'],90,NOW)
    assert result['items'][0]['matched_messages']==1
    assert result['items'][0]['evidence'][0]['id']=='m1'


def test_name_matches_and_time_coverage_are_explicit(archive,owner):
    query=Queries(archive/'archive.sqlite3')
    result=search_groups(query,owner,['未归档'],90,NOW)
    assert result['items'][0]['name_terms']==['未归档']
    assert result['items'][0]['matched_messages']==0
    assert result['items'][0]['evidence']==[]
    assert search_groups(query,owner,['缺少时间'],90,NOW)['items']==[]
    assert search_groups(query,owner,['缺少时间'],None,NOW)['items'][0]['id']=='wr001'


def test_intent_model_receives_only_request_not_archive(archive):
    class Model:
        def status(self):return {'ready':True}
        def complete(self,system,payload):
            assert set(payload)=={'request','schema'}
            return {'objective':'汇总发布讨论','terms':['发布','版本'],'questions':[]}
    result,mode=interpret('整理发布进展',model=Model())
    assert mode=='ai' and result.terms==['发布','版本']


def test_discovery_draft_is_persistent_but_never_executable(archive,monkeypatch):
    monkeypatch.delenv('CHATARCHIVE_AI_BASE_URL',raising=False)
    tasks=TaskStore(archive/'tasks.sqlite3',Queries(archive/'archive.sqlite3'));drafts=DraftStore(tasks)
    draft=drafts.propose(DraftInput(request='整理发布讨论',discover_groups=True,search_days=None),'admin')
    assert draft['status']=='scope_review'
    assert draft['proposal']['discovery']['mode']=='keywords'
    assert any(g['id']=='g1' for g in draft['proposal']['discovery']['items'])
    assert not tasks.list() and tasks.runs()['total']==0
    with pytest.raises(ValueError):drafts.confirm(draft['id'],ConfirmInput(revision=1),'admin')
    assert drafts.get(draft['id'])['proposal']['discovery']==draft['proposal']['discovery']


def test_ambiguous_intent_asks_for_business_subject(archive,owner):
    class Model:
        def status(self):return {'ready':True}
        def complete(self,*args):return {'objective':'定期整理','terms':[],'questions':['需要整理哪个项目或业务主题？']}
    intent,mode=interpret('帮我统计一下',model=Model())
    result=search_groups(Queries(archive/'archive.sqlite3'),owner,intent.terms,90,NOW)
    assert mode=='ai' and intent.questions and result['items']==[]


def test_plan_model_cannot_inject_discovery_candidates(archive):
    class Model:
        def status(self):return {'ready':True}
        def complete(self,*args):return {'discovery':{'items':[{'id':'invented'}]}}
    tasks=TaskStore(archive/'tasks.sqlite3',Queries(archive/'archive.sqlite3'))
    draft=DraftStore(tasks,Model()).propose(DraftInput(request='汇总发布',groups=[{'source':'feishu','id':'g1'}]),'admin')
    assert draft['status']=='error'
    assert draft['proposal']['discovery'] is None
    assert tasks.list()==[]


def test_failed_discovery_keeps_its_stage_for_retry(archive):
    class Model:
        def status(self):return {'ready':True}
        def complete(self,*args):raise ValueError('服务暂时不可用')
    tasks=TaskStore(archive/'tasks.sqlite3',Queries(archive/'archive.sqlite3'))
    drafts=DraftStore(tasks,Model())
    draft=drafts.propose(DraftInput(request='发布',discover_groups=True,groups=[{'source':'feishu','id':'g1'}]),'admin')
    assert draft['status']=='error' and drafts.get(draft['id'])['proposal']['discovery_failed']
    retried=drafts.propose(DraftInput(request='发布',discover_groups=True,search_terms=['发布'],revision=draft['revision']),'admin',draft['id'])
    assert retried['status']=='scope_review'
    assert not retried['proposal']['discovery_failed']
    assert tasks.list()==[]
