import hashlib,sqlite3,time
from chatarchive.security import AccessStore

def test_token_lifecycle(tmp_path):
 s=AccessStore(tmp_path/'access.sqlite3');new=s.create('test',['feishu'],['feishu:g1'],days=1)
 assert s.authenticate(new['token']).groups==('feishu:g1',)
 with s.connect() as c:
  r=c.execute('SELECT * FROM tokens').fetchone();assert new['token'] not in str(tuple(r));assert r['hash']==hashlib.sha256(new['token'].encode()).hexdigest()
 assert 'hash' not in s.list()[0]
 s.revoke(new['id'],'admin');assert s.authenticate(new['token']) is None
 expired=s.create('expired',['wecom'])
 with s.connect() as c:c.execute('UPDATE tokens SET expires_at=? WHERE id=?',(int(time.time())-1,expired['id']))
 assert s.authenticate(expired['token']) is None
