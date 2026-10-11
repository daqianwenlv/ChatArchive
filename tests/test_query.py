import pytest
from chatarchive.query import Queries
from chatarchive.security import Principal

def test_scope_applies_to_all_routes(archive,restricted):
 q=Queries(archive/'archive.sqlite3')
 assert q.groups(restricted)['total']==1
 assert q.messages(restricted)['total']==2
 assert q.analysis(restricted)['totals']['messages']==2
 assert q.source_list(restricted)['sources'][0]['messages']==2
 with pytest.raises(LookupError):q.group(restricted,'feishu','g2')
 with pytest.raises(LookupError):q.message(restricted,'feishu','m2')
 assert q.messages(restricted,source='wecom')['total']==0

def test_unicode_literal_search_and_dates(archive,owner):
 q=Queries(archive/'archive.sqlite3')
 assert q.messages(owner,q='发布')['total']==2
 assert q.messages(owner,q='%')['total']==1
 assert q.messages(owner,source='feishu',group_id='g1',start='2026-10-11',end='2026-10-11')['total']==1
 assert q.messages(owner,source='feishu',group_id='g1',end='2026-10-10')['total']==1
 with pytest.raises(ValueError):q.messages(owner,start='2026-10-15',end='2026-10-11')
 assert q.messages(owner,q="' OR 1=1 --")['total']==0

def test_paging_and_analysis_identity(archive,owner):
 q=Queries(archive/'archive.sqlite3')
 a=q.messages(owner,limit=2);b=q.messages(owner,limit=2,offset=2)
 assert not {x['id'] for x in a['items']} & {x['id'] for x in b['items']}
 r=q.analysis(owner,source='feishu',group_id='g1')
 assert r['totals']['participants']==2
 assert len(r['participants'])==2
 assert sum(x['count'] for x in r['days'])==2
 w=q.analysis(owner,source='wecom');assert w['totals']['undated']==1
 assert q.group(owner,'feishu','g3')['message_count']==0

def test_permissions(archive):
 p=Principal('p',sources=('feishu',),permissions=('groups:read',))
 q=Queries(archive/'archive.sqlite3')
 assert q.groups(p)['total']==3
 with pytest.raises(PermissionError):q.messages(p)
 with pytest.raises(PermissionError):q.analysis(p)

def test_analysis_without_body_permission_has_no_keywords(archive):
 p=Principal('analyst',sources=('feishu',),groups=('feishu:g1',),permissions=('analysis:read',))
 r=Queries(archive/'archive.sqlite3').analysis(p)
 assert r['totals']['messages']==2
 assert r['keywords']==[] and r['keyword_sample']==0
