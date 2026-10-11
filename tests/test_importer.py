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
