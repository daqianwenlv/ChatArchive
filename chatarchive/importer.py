from __future__ import annotations
import argparse,base64,collections,datetime as dt,fcntl,gzip,json,os,sqlite3,subprocess,tempfile
from pathlib import Path
from .database import SCHEMA,finalize,private_dir,upgrade
from .media import MediaStore


def insert(con,r,media=None):
    """Merge one record. Archived content is kept when a later export omits or blanks it."""
    if r['kind']=='group':
        con.execute('''INSERT INTO groups(source,id,name,kind,connection,enabled,in_chat,last_sync) VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(source,id) DO UPDATE SET name=CASE WHEN excluded.name!='' THEN excluded.name ELSE name END,kind=excluded.kind,
            connection=CASE WHEN excluded.connection!='' THEN excluded.connection ELSE connection END,enabled=COALESCE(excluded.enabled,enabled),
            in_chat=COALESCE(excluded.in_chat,in_chat),last_sync=COALESCE(excluded.last_sync,last_sync)''',(r['source'],r['id'],r.get('name') or '',r.get('conversation_kind','group'),r.get('connection',''),r.get('enabled'),r.get('in_chat'),r.get('last_sync')))
    elif r['kind']=='message':
        r=dict(r);r['type']={'media':'video','audio':'voice'}.get(r.get('type'),r.get('type','unknown'))
        raw=json.dumps(r['raw'],ensure_ascii=False,separators=(',',':')) if r.get('raw') is not None else '{}'
        con.execute('''INSERT INTO messages(source,id,group_id,ts,sender_id,sender_name,type,text,deleted,parent_id,media_state,raw,first_seen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            ON CONFLICT(source,id) DO UPDATE SET group_id=excluded.group_id,ts=COALESCE(excluded.ts,ts),
            sender_id=CASE WHEN excluded.sender_id!='' THEN excluded.sender_id ELSE sender_id END,
            sender_name=CASE WHEN excluded.sender_name!='' THEN excluded.sender_name ELSE sender_name END,
            type=CASE WHEN excluded.type!='unknown' THEN excluded.type ELSE type END,
            text=CASE WHEN excluded.text!='' THEN excluded.text ELSE text END,deleted=MAX(deleted,excluded.deleted),
            parent_id=COALESCE(excluded.parent_id,parent_id),
            media_state=CASE WHEN media_sha256 IS NOT NULL THEN 'archived' WHEN excluded.media_state!='' THEN excluded.media_state ELSE media_state END,
            raw=CASE WHEN excluded.raw!='{}' THEN excluded.raw ELSE raw END''',tuple(r.get(k,default) for k,default in [('source',''),('id',''),('group_id',''),('ts',None),('sender_id',''),('sender_name',''),('type','unknown'),('text',''),('deleted',False),('parent_id',None),('media_state','')])+(raw,))
    elif r['kind'] in ('media_part','media'):
        if media is None:raise ValueError('Attachment records need a media directory')
        media.part(r) if r['kind']=='media_part' else media.finish(con,r)
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


def import_wecom(con,path,received=None):
    source=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=20);source.row_factory=sqlite3.Row
    try:
        source.execute('BEGIN');groups=set()
        for row in source.execute('SELECT f.*,p.plaintext FROM message_facts f JOIN plaintext_messages p ON p.seq=f.seq ORDER BY f.seq'):
            raw=json.loads(row['plaintext']);fact={k:row[k] for k in row.keys() if k!='plaintext'};gid=row['room_id'] or 'private:'+str(row['sender'] or 'unknown')
            if gid not in groups:
                insert(con,{'kind':'group','source':'wecom','id':gid,'name':'','conversation_kind':'group' if row['room_id'] else 'private','connection':'archive','enabled':True,'in_chat':None});groups.add(gid)
            insert(con,{'kind':'message','source':'wecom','id':row['msgid'],'group_id':gid,'ts':row['msg_time'],'sender_id':row['sender'] or '', 'sender_name':'','type':row['msgtype'] or 'unknown','text':wecom_text(raw),'deleted':False,'media_state':'not_downloaded' if row['msgtype'] in ('image','file','voice','video') else '','raw':{'fact':fact,'content':raw}})
            if received is not None:received['wecom']+=1
        return dict(source.execute('SELECT name,value FROM cursor_state'))
    finally:source.close()


def export_program(root,connection='archive',media_root=None,known_media=()):
    """Pass deployment settings as Python string literals, never shell fragments."""
    settings='import os\n'
    settings+='os.environ["CHATARCHIVE_CHATLOG_ROOT"]='+repr(str(root))+'\n'
    settings+='os.environ["CHATARCHIVE_CONNECTION_LABEL"]='+repr(connection)+'\n'
    if media_root is not None:settings+='os.environ["CHATARCHIVE_MEDIA_ROOT"]='+repr(str(media_root))+'\n'
    # Attachments already archived are not transferred again.
    known=base64.b64encode(gzip.compress('\n'.join(known_media).encode())).decode()
    settings+='os.environ["CHATARCHIVE_KNOWN_MEDIA"]='+repr(known)+'\n'
    return settings.encode()+(Path(__file__).resolve().parents[1]/'scripts/export_chatlog.py').read_bytes()


def build(args):
    private_dir(args.output.parent)
    with (args.output.parent/'index.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        fd,temp=tempfile.mkstemp(prefix='.index-',suffix='.sqlite3',dir=args.output.parent);os.close(fd)
        c=sqlite3.connect(temp);media=MediaStore(args.output.parent/'media');received=collections.Counter()
        try:
            # Merge into the previous snapshot: records that later disappear upstream stay archived.
            if args.output.exists():
                old=sqlite3.connect(args.output.resolve().as_uri()+'?mode=ro',uri=True);old.backup(c);old.close();upgrade(c)
            else:c.executescript(SCHEMA)
            known=[s+':'+i for s,i in c.execute('SELECT source,id FROM messages WHERE media_sha256 IS NOT NULL')]
            c.execute('BEGIN')
            # The command is fixed. Credentials remain only on the collector host.
            program=export_program(args.chatlog_root,args.connection_label,args.media_root,known)
            with tempfile.TemporaryFile() as errors:
                proc=subprocess.Popen(['ssh','-i',args.identity,'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-o','StrictHostKeyChecking=yes',args.host,'python3 -'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors)
                try:
                    proc.stdin.write(program);proc.stdin.close()
                    with gzip.GzipFile(fileobj=proc.stdout,mode='rb') as archive:
                        for line in archive:
                            r=json.loads(line);insert(c,r,media)
                            if r['kind']=='message':received[r['source']]+=1
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
            wc=import_wecom(c,args.wecom_db,received)
            stamp=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
            rows=[('feishu','飞书','continuous',stamp,'connected',json.dumps({'connections':connection_details,'interval_seconds':1800})),('wecom','企业微信','continuous',wc.get('last_pull_at'),wc.get('collector_status','unknown'),json.dumps({'interval_seconds':15,'group_names_available':False})),('wechat','微信','import',stamp,'imported','{}'),('dingtalk','钉钉','unconfigured',None,'not_connected','{}')]
            c.executemany('INSERT OR REPLACE INTO sources VALUES(?,?,?,?,?,?)',rows)
            c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('indexed_at',stamp));finalize(c)
            counts=dict(c.execute('SELECT source,COUNT(*) FROM messages GROUP BY source'));c.close();c=None
            if not received['feishu'] or not received['wecom']:raise RuntimeError('Required source is unexpectedly empty')
            os.chmod(temp,0o640);os.replace(temp,args.output)
            print(json.dumps({'ok':True,'indexed_at':stamp,'messages':counts}))
        finally:
            media.close()
            if c:c.close()
            if os.path.exists(temp):os.unlink(temp)


def main():
    p=argparse.ArgumentParser();p.add_argument('--host',required=True);p.add_argument('--identity',required=True);p.add_argument('--wecom-db',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--profile',action='append',default=[])
    p.add_argument('--chatlog-root',type=Path,default=Path(os.environ.get('CHATARCHIVE_CHATLOG_ROOT','/data/chatlog')))
    p.add_argument('--media-root',type=Path,default=os.environ.get('CHATARCHIVE_MEDIA_ROOT') or None,help='Remote attachment directory; defaults to --chatlog-root')
    p.add_argument('--connection-label',default=os.environ.get('CHATARCHIVE_CONNECTION_LABEL','archive'))
    build(p.parse_args())

if __name__=='__main__':main()
