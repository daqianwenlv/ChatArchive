from __future__ import annotations
import contextvars, hashlib, json, secrets, sqlite3, time
from dataclasses import dataclass
from pathlib import Path
from .database import private_dir

SOURCES=('feishu','wecom','wechat','dingtalk')
PERMISSIONS=('groups:read','messages:read','analysis:read')

@dataclass(frozen=True)
class Principal:
    id: str
    admin: bool = False
    sources: tuple = SOURCES
    groups: tuple | None = None
    permissions: tuple = PERMISSIONS
    def require(self, permission):
        if not self.admin and permission not in self.permissions: raise PermissionError('没有此项查询权限')
    def sql_scope(self, alias='m'):
        if not self.sources: return '0',[]
        clause=f"{alias}.source IN ({','.join('?' for _ in self.sources)})"
        params=list(self.sources)
        if self.groups is not None:
            if not self.groups: return '0',[]
            clause+=f" AND ({alias}.source || ':' || {alias}.group_id) IN ({','.join('?' for _ in self.groups)})"
            params+=list(self.groups)
        return clause,params

CURRENT=contextvars.ContextVar('chatarchive_principal',default=None)

def current():
    p=CURRENT.get()
    if p is None: raise PermissionError('需要有效的访问密钥')
    return p

class AccessStore:
    def __init__(self,path):
        self.path=Path(path);private_dir(self.path.parent)
        with self.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS tokens(id TEXT PRIMARY KEY,name TEXT NOT NULL,hash TEXT NOT NULL UNIQUE,prefix TEXT NOT NULL,sources TEXT NOT NULL,groups_json TEXT,permissions TEXT NOT NULL,created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,revoked_at INTEGER,last_used INTEGER);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at INTEGER NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,object TEXT NOT NULL DEFAULT '',result TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS audit_at ON audit(at);''')
        self.path.chmod(0o600)
    def connect(self):
        c=sqlite3.connect(self.path,timeout=10);c.row_factory=sqlite3.Row;return c
    def create(self,name,sources,groups=None,permissions=PERMISSIONS,days=30,actor='admin'):
        name=name.strip()
        if not 1<=len(name)<=80: raise ValueError('名称长度为 1–80 个字符')
        if not sources or not set(sources)<=set(SOURCES): raise ValueError('请选择有效的数据源')
        if not permissions or not set(permissions)<=set(PERMISSIONS): raise ValueError('请选择有效权限')
        if not 1<=days<=90: raise ValueError('有效期须在 1–90 天内')
        if groups is not None and (not groups or len(groups)>500 or any(not isinstance(g,str) or g.split(':',1)[0] not in sources for g in groups)): raise ValueError('群范围与数据源不匹配')
        token='ca_'+secrets.token_urlsafe(32); now=int(time.time()); key_id=secrets.token_hex(8)
        with self.connect() as c:
            c.execute('INSERT INTO tokens(id,name,hash,prefix,sources,groups_json,permissions,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?)',(key_id,name,hashlib.sha256(token.encode()).hexdigest(),token[:10],json.dumps(sorted(set(sources))),None if groups is None else json.dumps(sorted(set(groups))),json.dumps(sorted(set(permissions))),now,now+days*86400))
        self.audit(actor,'key.create',key_id,'ok')
        return {'id':key_id,'token':token,'expires_at':now+days*86400}
    def authenticate(self,token):
        if not token or len(token)>256: return None
        now=int(time.time())
        with self.connect() as c:
            row=c.execute('SELECT * FROM tokens WHERE hash=? AND revoked_at IS NULL AND expires_at>?',(hashlib.sha256(token.encode()).hexdigest(),now)).fetchone()
            if row is None: return None
            if not row['last_used'] or now-row['last_used']>=60: c.execute('UPDATE tokens SET last_used=? WHERE id=?',(now,row['id']))
        return Principal(row['id'],sources=tuple(json.loads(row['sources'])),groups=None if row['groups_json'] is None else tuple(json.loads(row['groups_json'])),permissions=tuple(json.loads(row['permissions'])))
    def list(self):
        with self.connect() as c: rows=c.execute('SELECT id,name,prefix,sources,groups_json,permissions,created_at,expires_at,revoked_at,last_used FROM tokens ORDER BY created_at DESC').fetchall()
        return [dict(r)|{'sources':json.loads(r['sources']),'groups':json.loads(r['groups_json']) if r['groups_json'] else None,'permissions':json.loads(r['permissions'])} for r in rows]
    def revoke(self,key_id,actor):
        with self.connect() as c:
            result=c.execute('UPDATE tokens SET revoked_at=? WHERE id=? AND revoked_at IS NULL',(int(time.time()),key_id))
        self.audit(actor,'key.revoke',key_id,'ok' if result.rowcount else 'unchanged')
    def audit(self,actor,action,obj='',result='ok'):
        with self.connect() as c:
            c.execute('INSERT INTO audit(at,actor,action,object,result) VALUES(?,?,?,?,?)',(int(time.time()),actor,action,obj[:180],result))
            c.execute('DELETE FROM audit WHERE at<?',(int(time.time())-90*86400,))
    def recent_audit(self):
        with self.connect() as c:return [dict(r) for r in c.execute('SELECT at,actor,action,object,result FROM audit ORDER BY id DESC LIMIT 50')]
