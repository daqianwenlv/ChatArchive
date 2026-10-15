import base64,gzip,hashlib,json,sqlite3,subprocess,sys,zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from chatarchive.database import SCHEMA,finalize
from chatarchive.importer import export_program,insert
from chatarchive.maintenance import backup,doctor,restore
from chatarchive.media import MediaStore,media_path
from chatarchive.query import Queries
from chatarchive.server import create_app

PNG=b'\x89PNG\r\n\x1a\n'+b'fictional image'*100


def chatlog(tmp_path):
    root=tmp_path/'chatlog';(root/'data').mkdir(parents=True);(root/'files').mkdir()
    (root/'files/plan.png').write_bytes(PNG)
    (tmp_path/'secret.key').write_text('collector credential')
    (root/'chats.json').write_text(json.dumps({'g1':{'chat_name':'虚构群'}}))
    lines=[{'msg_id':'q1','chat_id':'g1','ts':1,'text':'原始问题','mentions':['u2']},
           {'msg_id':'a1','chat_id':'g1','ts':2,'text':'[图片]','msg_type':'image','parent_id':'q1','media_path':'files/plan.png'},
           {'msg_id':'x1','chat_id':'g1','ts':3,'text':'越界','msg_type':'file','media_path':'../secret.key'}]
    (root/'data/events.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in lines))
    return root


def export(root,known=()):
    result=subprocess.run([sys.executable,'-'],input=export_program(root,known_media=known),capture_output=True)
    assert result.returncode==0,result.stderr
    return [json.loads(line) for line in gzip.decompress(result.stdout).splitlines()]


def test_export_keeps_raw_records_and_streams_attachments_inside_root(tmp_path):
    rows=export(chatlog(tmp_path))
    messages={r['id']:r for r in rows if r['kind']=='message'}
    assert messages['q1']['raw']['mentions']==['u2']
    final=[r for r in rows if r['kind']=='media']
    assert [r['message_id'] for r in final]==['a1']
    assert final[0]['sha256']==hashlib.sha256(PNG).hexdigest() and final[0]['mime']=='image/png'
    data=b''.join(base64.b64decode(r['data']) for r in rows if r['kind']=='media_part')
    assert data==PNG
    # A path outside the media root is never read.
    assert b'collector credential' not in json.dumps(rows).encode()
    assert not any(r['kind'].startswith('media') for r in export(chatlog(tmp_path/'again'),['feishu:a1']))


def test_import_archives_attachment_and_keeps_history(tmp_path):
    rows=export(chatlog(tmp_path))
    c=sqlite3.connect(tmp_path/'archive.sqlite3');c.executescript(SCHEMA);media=MediaStore(tmp_path/'media')
    for r in rows:insert(c,r,media)
    finalize(c)
    digest=hashlib.sha256(PNG).hexdigest()
    assert media_path(tmp_path/'media',digest).read_bytes()==PNG
    assert c.execute("SELECT media_state,media_sha256,media_name FROM messages WHERE id='a1'").fetchone()==('archived',digest,'plan.png')
    # A later export that blanks or drops content does not erase what is archived.
    insert(c,{'kind':'message','source':'feishu','id':'q1','group_id':'g1','text':'','deleted':True,'media_state':'stored'},media)
    insert(c,{'kind':'message','source':'feishu','id':'a1','group_id':'g1','text':'[图片]','media_state':'removed'},media)
    insert(c,{'kind':'group','source':'feishu','id':'g1','name':''},media)
    assert c.execute("SELECT text,deleted,json_extract(raw,'$.mentions[0]') FROM messages WHERE id='q1'").fetchone()==('原始问题',1,'u2')
    assert c.execute("SELECT media_state FROM messages WHERE id='a1'").fetchone()[0]=='archived'
    assert c.execute("SELECT name FROM groups WHERE id='g1'").fetchone()[0]=='虚构群'
    c.close()


def test_checksum_mismatch_publishes_nothing(tmp_path):
    c=sqlite3.connect(':memory:');c.executescript(SCHEMA);media=MediaStore(tmp_path/'media')
    insert(c,{'kind':'message','source':'feishu','id':'m','group_id':'g'},media)
    insert(c,{'kind':'media_part','source':'feishu','message_id':'m','data':base64.b64encode(b'abc').decode()},media)
    with pytest.raises(ValueError,match='checksum'):
        insert(c,{'kind':'media','source':'feishu','message_id':'m','sha256':'0'*64,'bytes':3},media)
    assert not list((tmp_path/'media').rglob('*'))


def test_cli_import_upgrades_old_index_and_stores_media(tmp_path):
    data=tmp_path/'data';data.mkdir()
    old=sqlite3.connect(data/'archive.sqlite3')
    old.executescript(SCHEMA.replace(", raw TEXT NOT NULL DEFAULT '{}', media_sha256 TEXT, media_name TEXT NOT NULL DEFAULT '', media_mime TEXT NOT NULL DEFAULT '', media_bytes INTEGER, first_seen TEXT",''))
    old.execute("INSERT INTO messages(source,id,group_id,text) VALUES('feishu','old','g1','旧记录')");old.commit();old.close()
    file=tmp_path/'in.jsonl'
    file.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in export(chatlog(tmp_path))))
    r=subprocess.run([sys.executable,'-m','chatarchive.cli','--data',str(data),'import-jsonl',str(file)],capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    with sqlite3.connect(data/'archive.sqlite3') as c:
        assert c.execute("SELECT COUNT(*) FROM messages WHERE id IN ('old','q1','a1')").fetchone()[0]==3
        assert c.execute("SELECT media_state FROM messages WHERE id='a1'").fetchone()[0]=='archived'
    assert media_path(data/'media',hashlib.sha256(PNG).hexdigest()).is_file()


@pytest.fixture
def stored(archive):
    digest=hashlib.sha256(PNG).hexdigest();path=media_path(archive/'media',digest)
    path.parent.mkdir(parents=True);path.write_bytes(PNG)
    with sqlite3.connect(archive/'archive.sqlite3') as c:
        c.execute("UPDATE messages SET parent_id='m0',media_sha256=?,media_name='plan.png',media_mime='image/png',media_bytes=?,media_state='archived',raw='{\"k\":1}' WHERE id='m1'",(digest,len(PNG)))
        c.execute("UPDATE messages SET parent_id='m2' WHERE id='m0'")
    return archive


def test_message_detail_quote_and_scoped_download(stored,owner,restricted):
    item=Queries(stored/'archive.sqlite3').message(owner,'feishu','m1')
    assert item['raw']=={'k':1} and item['parent']['text']=='发布版本，完成测试' and item['media_available']
    # The quoted message is outside this key's group scope and is not revealed.
    assert Queries(stored/'archive.sqlite3').message(restricted,'feishu','m0')['parent'] is None
    app=create_app(stored,trust_proxy=False,admin_token='a'*40,base_url='http://testserver')
    with TestClient(app) as client:
        admin={'Authorization':'Bearer '+'a'*40}
        r=client.get('/api/media?source=feishu&message_id=m1',headers=admin)
        assert r.status_code==200 and r.content==PNG and r.headers['content-type']=='image/png'
        assert client.get('/api/media?source=feishu&message_id=m0',headers=admin).status_code==404
        assert 'raw' not in client.get('/api/messages',headers=admin).json()['items'][0]
        token=client.app.state.store.create('other group',['feishu'],['feishu:g2'])['token']
        assert client.get('/api/media?source=feishu&message_id=m1',headers={'Authorization':'Bearer '+token}).status_code==404


def test_backup_restore_includes_verified_media(stored,tmp_path):
    bundle=tmp_path/'snap.zip'
    assert backup(stored,bundle)['media']=={'files':1,'bytes':len(PNG)}
    target=tmp_path/'restored';result=restore(bundle,target)
    assert result['media']['files']==1 and doctor(target)['ok']
    assert media_path(target/'media',hashlib.sha256(PNG).hexdigest()).read_bytes()==PNG
    # A swapped attachment fails verification and nothing is published.
    with zipfile.ZipFile(bundle) as z:entries={n:z.read(n) for n in z.namelist()}
    name=next(n for n in entries if n.startswith('media/'));entries[name]=b'tampered'
    bad=tmp_path/'bad.zip'
    with zipfile.ZipFile(bad,'w') as z:
        for n,v in entries.items():z.writestr(n,v)
    with pytest.raises(ValueError,match='checksum'):restore(bad,tmp_path/'bad-target')
    assert not any(p.is_file() for p in (tmp_path/'bad-target').rglob('*'))


def test_doctor_reports_missing_attachments(stored):
    media_path(stored/'media',hashlib.sha256(PNG).hexdigest()).unlink()
    report=doctor(stored)
    assert not report['ok'] and report['media']['missing']==1
