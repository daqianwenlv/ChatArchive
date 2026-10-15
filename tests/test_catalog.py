import json,sqlite3,time
import pytest
from fastapi.testclient import TestClient
from chatarchive.catalog import CatalogStore,CategoriesInput,LabelInput,PROPOSE_PROMPT,CLASSIFY_PROMPT
from chatarchive.importer import insert
from chatarchive.database import finalize
from chatarchive.maintenance import backup,restore
from chatarchive.server import create_app


class FakeModel:
    def __init__(self):self.calls=[]
    def status(self):return {'ready':True,'model':'fake','message':''}
    def complete(self,system,payload):
        self.calls.append((system,payload))
        if system==PROPOSE_PROMPT:
            return {'categories':[{'name':'产品研发','description':'版本与发布','keywords':['发布'],'groups':[g['key'] for g in payload['groups'] if g['key']!='wecom:wr001']},
                                  {'name':'客户服务','description':'企微客户沟通','keywords':['客户'],'groups':['wecom:wr001','unknown:x']}]}
        if system==CLASSIFY_PROMPT:
            out=[]
            for g in payload['groups']:
                out.append({'group':g['key'],'category':'客户服务','tags':['企微','这是一个超过十二个字符的标签名称'],'confidence':1.4,'reason':'客户沟通',
                            'evidence':[e['ref'] for e in g['excerpts']][:1]+['e999']})
            return {'results':out}
        raise AssertionError(system)


@pytest.fixture
def store(archive):
    return CatalogStore(archive/'catalog.sqlite3',archive/'archive.sqlite3',FakeModel())


def test_numbers_are_permanent_and_follow_first_message(store,archive):
    store.number_groups()
    with store.db() as db:
        seqs={r['group_id']:r['seq'] for r in db.execute('SELECT group_id,seq FROM group_labels')}
    assert seqs=={'g1':1,'g2':2,'wr001':3,'g3':4}
    c=sqlite3.connect(archive/'archive.sqlite3')
    insert(c,{'kind':'message','source':'feishu','id':'early','group_id':'g0','ts':1,'text':'更早的群'});finalize(c);c.close()
    assert store.number_groups()==1
    assert store.label('feishu','g1')['seq']==1 and store.label('feishu','g0')['seq']==5


def test_proposal_then_rule_and_ai_classification_respects_locks(store):
    job=store.start('propose','tests',background=False)
    assert job['status']=='succeeded',job
    names=[c['name'] for c in job['result']['categories']]
    assert names==['产品研发','客户服务']
    assert job['result']['categories'][1]['examples']==[{'source':'wecom','id':'wr001','name':'wr001','seq':3}]
    cats=store.save_categories(CategoriesInput(categories=[{'name':'产品研发','keywords':['产品']},{'name':'客户服务','keywords':['客户']}]))
    store.set_label(LabelInput(source='feishu',group_id='g2',category_id=cats[0]['id'],tags=['手工']),'admin')
    job=store.start('classify','tests',background=False,mode='all')
    assert job['status']=='succeeded',job
    g1=store.label('feishu','g1');g2=store.label('feishu','g2');wr=store.label('wecom','wr001');g3=store.label('feishu','g3')
    # 群名「产品讨论」命中识别词，不调用 AI。
    assert (g1['category'],g1['origin'])==('产品研发','rule')
    assert (g2['category'],g2['origin'],g2['tags'],g2['locked'])==('产品研发','manual',['手工'],True)
    assert (wr['category'],wr['origin'],wr['tags'],wr['confidence'])==('客户服务','ai',['企微'],1.0)
    assert wr['evidence'] and set(wr['evidence'])<={'m3','undated'}
    assert g3['classified_at'] is None  # 无消息且群名未命中：等有消息后再判断。
    classified=[p for s,p in store.model.calls if s==CLASSIFY_PROMPT]
    assert [g['key'] for p in classified for g in p['groups']]==['wecom:wr001']
    # Removing a category releases its groups, including manual locks.
    store.save_categories(CategoriesInput(categories=[{'id':cats[1]['id'],'name':'客户'}]))
    assert store.label('feishu','g2')['category_id'] is None and not store.label('feishu','g2')['locked']
    assert store.label('wecom','wr001')['category']=='客户'


def test_auto_classifies_only_when_needed(store):
    assert store.auto() is None  # 尚无分类
    store.save_categories(CategoriesInput(categories=[{'name':'产品研发','keywords':['产品']}]))
    assert store.auto()['status']=='succeeded'
    calls=len(store.model.calls)
    assert store.auto() is None and len(store.model.calls)==calls


def test_api_lists_numbers_categories_and_filters(archive):
    app=create_app(archive,trust_proxy=False,admin_token='a'*40,base_url='http://testserver',scheduler=False)
    admin={'Authorization':'Bearer '+'a'*40}
    with TestClient(app) as client:
        client.app.state.catalog.model=FakeModel()
        r=client.post('/api/catalog/proposals',headers=admin);assert r.status_code==202
        job=r.json()
        for _ in range(100):
            job=client.get('/api/catalog/jobs/'+job['id'],headers=admin).json()
            if job['status']!='running':break
            time.sleep(0.05)
        assert job['status']=='succeeded'
        cats=client.put('/api/catalog/categories',headers=admin,json={'categories':[{'name':c['name'],'keywords':c['keywords']} for c in job['result']['categories']]}).json()['categories']
        r=client.put('/api/catalog/group',headers=admin,json={'source':'feishu','group_id':'g1','category_id':cats[1]['id'],'tags':['重点']})
        assert r.json()['category']=='客户服务'
        data=client.get('/api/groups',headers=admin,params={'category':cats[1]['id']}).json()
        assert [(g['id'],g['seq'],g['tags'],g['label_locked']) for g in data['items']]==[('g1',1,['重点'],True)]
        assert [c['name'] for c in data['categories']]==['产品研发','客户服务']
        assert [g['id'] for g in client.get('/api/groups',headers=admin,params={'q':'#3'}).json()['items']]==['wr001']
        assert client.get('/api/group',headers=admin,params={'source':'feishu','group_id':'g1'}).json()['category']=='客户服务'
        token=client.app.state.store.create('reader',['feishu'],['feishu:g1'])['token'];h={'Authorization':'Bearer '+token}
        assert client.get('/api/catalog',headers=h).status_code==403
        assert client.get('/api/catalog/group',headers=h,params={'source':'feishu','group_id':'g1'}).json()['seq']==1
        assert client.get('/api/catalog/group',headers=h,params={'source':'feishu','group_id':'g2'}).status_code==404
        assert client.put('/api/catalog/group',headers=h,json={'source':'feishu','group_id':'g1','category_id':None}).status_code==403
        assert client.put('/api/catalog/categories',headers=admin,json={'categories':[{'name':'重复'},{'name':'重复'}]}).status_code==400
        assert client.get('/catalog.js').status_code==200


def test_catalog_is_backed_up(store,tmp_path):
    store.save_categories(CategoriesInput(categories=[{'name':'产品研发'}]));store.number_groups()
    bundle=tmp_path/'s.zip';backup(store.path.parent,bundle)
    target=tmp_path/'r';restore(bundle,target)
    with sqlite3.connect(target/'catalog.sqlite3') as c:
        assert c.execute('SELECT name FROM categories').fetchall()==[('产品研发',)]
        assert c.execute('SELECT COUNT(*) FROM group_labels').fetchone()[0]==4
