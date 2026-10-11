from __future__ import annotations
import argparse,datetime as dt,fcntl,gzip,json,os,sqlite3,subprocess,tempfile
from pathlib import Path
from .database import SCHEMA,finalize,private_dir


def insert(con,r):
    if r['kind']=='group':
        con.execute('INSERT OR REPLACE INTO groups(source,id,name,kind,connection,enabled,in_chat,last_sync) VALUES(?,?,?,?,?,?,?,?)',(r['source'],r['id'],r.get('name') or '',r.get('conversation_kind','group'),r.get('connection',''),r.get('enabled'),r.get('in_chat'),r.get('last_sync')))
    elif r['kind']=='message':
        r=dict(r);r['type']={'media':'video','audio':'voice'}.get(r.get('type'),r.get('type','unknown'))
        con.execute('INSERT OR IGNORE INTO messages(source,id,group_id,ts,sender_id,sender_name,type,text,deleted,parent_id,media_state) VALUES(?,?,?,?,?,?,?,?,?,?,?)',tuple(r.get(k,default) for k,default in [('source',''),('id',''),('group_id',''),('ts',None),('sender_id',''),('sender_name',''),('type','unknown'),('text',''),('deleted',False),('parent_id',None),('media_state','')]))
    else:raise ValueError('Unknown import record')


def wecom_text(row):
    kind=row.get('msgtype') or row.get('msg_type') or 'unknown'
    payload=row.get(kind,{})
    if isinstance(payload,str):return payload
    if kind=='text':return str(payload.get('content') or '')
    if kind=='mixed':return '\n'.join(str(x.get('content') or '') for x in payload.get('item',[]) if x.get('type')=='text')
    if kind=='file':return '[文件] '+str(payload.get('filename') or '')
    if kind=='link':return '\n'.join(str(payload.get(k) or '') for k in ('title','description','link_url')).strip()
    if kind=='location':return '[位置] '+str(payload.get('address') or '')
    if kind=='card':return '[名片] '+str(payload.get('user_name') or '')
    return {'image':'[图片]','voice':'[语音]','video':'[视频]','revoke':'[撤回提示]','emotion':'[表情]','chatrecord':'[聊天记录]','weapp':'[小程序]'}.get(kind,'['+kind+']')


def import_wecom(con,path):
    source=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=20);source.row_factory=sqlite3.Row
    try:
        source.execute('BEGIN');groups=set()
        for row in source.execute('SELECT f.*,p.plaintext FROM message_facts f JOIN plaintext_messages p ON p.seq=f.seq ORDER BY f.seq'):
            raw=json.loads(row['plaintext']);gid=row['room_id'] or 'private:'+str(row['sender'] or 'unknown')
            if gid not in groups:
                insert(con,{'kind':'group','source':'wecom','id':gid,'name':'','conversation_kind':'group' if row['room_id'] else 'private','connection':'archive','enabled':True,'in_chat':None});groups.add(gid)
            insert(con,{'kind':'message','source':'wecom','id':row['msgid'],'group_id':gid,'ts':row['msg_time'],'sender_id':row['sender'] or '', 'sender_name':'','type':row['msgtype'] or 'unknown','text':wecom_text(raw),'deleted':False,'media_state':'not_downloaded' if row['msgtype'] in ('image','file','voice','video') else ''})
        return dict(source.execute('SELECT name,value FROM cursor_state'))
    finally:source.close()


def export_program(root,connection='archive'):
    """Pass deployment settings as Python string literals, never shell fragments."""
    settings='import os\n'
    settings+='os.environ["CHATARCHIVE_CHATLOG_ROOT"]='+repr(str(root))+'\n'
    settings+='os.environ["CHATARCHIVE_CONNECTION_LABEL"]='+repr(connection)+'\n'
    return settings.encode()+(Path(__file__).resolve().parents[1]/'scripts/export_chatlog.py').read_bytes()


def build(args):
    private_dir(args.output.parent)
    with (args.output.parent/'index.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        fd,temp=tempfile.mkstemp(prefix='.index-',suffix='.sqlite3',dir=args.output.parent);os.close(fd)
        c=sqlite3.connect(temp)
        try:
            c.executescript(SCHEMA);c.execute('BEGIN')
            # The command is fixed. Credentials remain only on the collector host.
            program=export_program(args.chatlog_root,args.connection_label)
            with tempfile.TemporaryFile() as errors:
                proc=subprocess.Popen(['ssh','-i',args.identity,'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-o','StrictHostKeyChecking=yes',args.host,'python3 -'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors)
                try:
                    proc.stdin.write(program);proc.stdin.close()
                    with gzip.GzipFile(fileobj=proc.stdout,mode='rb') as archive:
                        for line in archive:insert(c,json.loads(line))
                    if proc.wait(timeout=30)!=0:raise RuntimeError('Archive source export failed')
                finally:
                    if proc.poll() is None:proc.kill();proc.wait()
            connection_details={}
            for entry in args.profile:
                label,profile=entry.split('=',1)
                result=subprocess.run(['lark-cli','--profile',profile,'im','+chat-list','--as','bot','--page-all','--page-size','100','--page-limit','100'],capture_output=True,text=True,check=True,timeout=60)
                data=json.loads(result.stdout)
                if not data.get('ok') or not data.get('meta',{}).get('pagination',{}).get('complete'):raise RuntimeError('Incomplete group catalogue')
                for g in data['data']['chats']:
                    cid=g['chat_id'];existing=c.execute('SELECT connection FROM groups WHERE source=? AND id=?',('feishu',cid)).fetchone()
                    if existing:
                        labels=set((existing[0] or '').split(','))|{label}
                        c.execute('UPDATE groups SET connection=? WHERE source=? AND id=?',(','.join(sorted(labels)),'feishu',cid))
                    else:insert(c,{'kind':'group','source':'feishu','id':cid,'name':g.get('name') or '', 'connection':label,'enabled':False,'in_chat':True})
                connection_details[label]={'visible_groups':len(data['data']['chats']),'connected':True}
            wc=import_wecom(c,args.wecom_db)
            stamp=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
            rows=[('feishu','飞书','continuous',stamp,'connected',json.dumps({'connections':connection_details,'interval_seconds':1800})),('wecom','企业微信','continuous',wc.get('last_pull_at'),wc.get('collector_status','unknown'),json.dumps({'interval_seconds':15,'group_names_available':False})),('wechat','微信','import',stamp,'imported','{}'),('dingtalk','钉钉','unconfigured',None,'not_connected','{}')]
            c.executemany('INSERT INTO sources VALUES(?,?,?,?,?,?)',rows)
            c.execute('INSERT INTO metadata VALUES(?,?)',('indexed_at',stamp));finalize(c)
            counts=dict(c.execute('SELECT source,COUNT(*) FROM messages GROUP BY source'));c.close();c=None
            if not counts.get('feishu') or not counts.get('wecom'):raise RuntimeError('Required source is unexpectedly empty')
            os.chmod(temp,0o640);os.replace(temp,args.output)
            print(json.dumps({'ok':True,'indexed_at':stamp,'messages':counts}))
        finally:
            if c:c.close()
            if os.path.exists(temp):os.unlink(temp)


def main():
    p=argparse.ArgumentParser();p.add_argument('--host',required=True);p.add_argument('--identity',required=True);p.add_argument('--wecom-db',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--profile',action='append',default=[])
    p.add_argument('--chatlog-root',type=Path,default=Path(os.environ.get('CHATARCHIVE_CHATLOG_ROOT','/data/chatlog')))
    p.add_argument('--connection-label',default=os.environ.get('CHATARCHIVE_CONNECTION_LABEL','archive'))
    build(p.parse_args())

if __name__=='__main__':main()
