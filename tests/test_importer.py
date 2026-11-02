import json,sqlite3,subprocess,sys
from pathlib import Path
from chatarchive.database import SCHEMA,finalize
from chatarchive.importer import insert

def test_normalization_and_dedup(tmp_path):
 c=sqlite3.connect(tmp_path/'index.sqlite3');c.executescript(SCHEMA)
 item={'kind':'message','source':'feishu','id':'m','group_id':'g','type':'media','text':'[视频]','ts':1}
 insert(c,item);insert(c,item);finalize(c)
 assert c.execute('SELECT COUNT(*),MAX(type) FROM messages').fetchone()==(1,'video')
 assert c.execute('SELECT message_count FROM groups').fetchone()[0]==1
 c.close()

def test_portable_import_failure_preserves_index(tmp_path):
 data=tmp_path/'data'
 def run(*args):return subprocess.run([sys.executable,'-m','chatarchive.cli','--data',str(data),*args],capture_output=True,text=True)
 assert run('init').returncode==0
 good=Path(__file__).resolve().parents[1]/'examples/sample.jsonl'
 assert run('import-jsonl',str(good)).returncode==0
 before=(data/'archive.sqlite3').read_bytes()
 bad=tmp_path/'bad.jsonl';bad.write_text('{"source":"invalid"}\n')
 assert run('import-jsonl',str(bad)).returncode!=0
 assert (data/'archive.sqlite3').read_bytes()==before

def wecom_db(path,messages):
 c=sqlite3.connect(path)
 c.executescript('CREATE TABLE message_facts(seq INTEGER PRIMARY KEY,msgid TEXT,room_id TEXT,sender TEXT,msg_time INTEGER,msgtype TEXT,is_group INTEGER);CREATE TABLE plaintext_messages(seq INTEGER PRIMARY KEY,msgid TEXT,plaintext BLOB);CREATE TABLE cursor_state(name TEXT PRIMARY KEY,value TEXT)')
 for seq,(mid,kind,body) in enumerate(messages,1):
  c.execute('INSERT INTO message_facts VALUES(?,?,?,?,?,?,1)',(seq,mid,'r1','u1',seq,kind))
  c.execute('INSERT INTO plaintext_messages VALUES(?,?,?)',(seq,mid,json.dumps({'msgid':mid,'msgtype':kind,kind:body})))
 c.commit();c.close()

def test_wecom_enrichment_adds_originals_quotes_and_names(tmp_path):
 from chatarchive.importer import import_wecom
 wecom_db(tmp_path/'wecom.sqlite3',[('img','image',{'sdkfileid':'x'}),('old','image',{'sdkfileid':'y'}),('re','text',{'content':'「甲：[图片]」\n- - - - - - - -\n收到'})])
 e=sqlite3.connect(tmp_path/'enrich.sqlite3')
 e.executescript('CREATE TABLE media(msgid TEXT PRIMARY KEY,state TEXT,sha256 TEXT,bytes INTEGER,mime TEXT,name TEXT,text TEXT,info TEXT);CREATE TABLE quotes(msgid TEXT PRIMARY KEY,parent_msgid TEXT);CREATE TABLE names(kind TEXT,id TEXT,name TEXT,PRIMARY KEY(kind,id))')
 e.execute("INSERT INTO media VALUES('img','ok',?,3,'image/png','img.png','[图片] 虚构的海报','{\"kind\":\"贴片或设计稿\"}')",('a'*64,))
 e.execute("INSERT INTO media(msgid,state) VALUES('old','expired')")
 e.execute("INSERT INTO quotes VALUES('re','img')")
 e.executemany('INSERT INTO names VALUES(?,?,?)',[('room','r1','虚构客户群'),('user','u1','甲')]);e.commit();e.close()
 c=sqlite3.connect(tmp_path/'index.sqlite3');c.executescript(SCHEMA)
 state=import_wecom(c,tmp_path/'wecom.sqlite3',enrichment=tmp_path/'enrich.sqlite3');finalize(c)
 assert state['group_names_available']
 assert c.execute("SELECT name FROM groups WHERE id='r1'").fetchone()[0]=='虚构客户群'
 assert c.execute("SELECT text,media_state,media_sha256,media_mime,sender_name,json_extract(raw,'$.enrichment.kind') FROM messages WHERE id='img'").fetchone()==('[图片] 虚构的海报','archived','a'*64,'image/png','甲','贴片或设计稿')
 assert c.execute("SELECT media_state,media_sha256 FROM messages WHERE id='old'").fetchone()==('expired',None)
 assert c.execute("SELECT parent_id FROM messages WHERE id='re'").fetchone()[0]=='img'
 # Without the companion database the import behaves as before.
 c2=sqlite3.connect(':memory:');c2.executescript(SCHEMA)
 assert not import_wecom(c2,tmp_path/'wecom.sqlite3')['group_names_available']
 assert c2.execute("SELECT media_state,parent_id FROM messages WHERE id='img'").fetchone()==('not_downloaded',None)
