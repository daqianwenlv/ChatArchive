#!/usr/bin/env python3
"""Read-only adapter: emit normalized JSONL to stdout, optionally gzip compressed.
Run on the archive host. No collector imports, credential reads or writes.
"""
import base64,datetime as dt,gzip,hashlib,json,mimetypes,os,sys
from pathlib import Path
ROOT=Path(os.environ.get('CHATARCHIVE_CHATLOG_ROOT','/data/chatlog'))
CONNECTION=os.environ.get('CHATARCHIVE_CONNECTION_LABEL','archive')
MEDIA_ROOT=Path(os.environ.get('CHATARCHIVE_MEDIA_ROOT') or ROOT)
KNOWN=set(filter(None,gzip.decompress(base64.b64decode(os.environ.get('CHATARCHIVE_KNOWN_MEDIA') or 'H4sIAAAAAAAC/wMAAAAAAAAAAAA=')).decode().split('\n')))
MAX_BYTES=int(os.environ.get('CHATARCHIVE_MEDIA_MAX_BYTES',str(512*1024*1024)))
CHUNK=1024*1024

def read(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:return default

def attachment(source,mid,r,media_root):
    """Stream an attachment in base64 parts. Only files inside the configured media root are read."""
    if r.get('media_removed') or not r.get('media_path') or source+':'+mid in KNOWN:return
    base=media_root.resolve();path=(base/str(r['media_path'])).resolve()
    if not path.is_relative_to(base) or not path.is_file() or path.stat().st_size>MAX_BYTES:return
    digest=hashlib.sha256();size=0
    with path.open('rb') as f:
        while chunk:=f.read(CHUNK):
            digest.update(chunk);size+=len(chunk)
            yield {'kind':'media_part','source':source,'message_id':mid,'data':base64.b64encode(chunk).decode()}
    name=str(r.get('file_name') or path.name)
    yield {'kind':'media','source':source,'message_id':mid,'sha256':digest.hexdigest(),'bytes':size,'name':name,'mime':mimetypes.guess_type(name)[0] or ''}

def records(root=ROOT,media_root=None):
    media_root=Path(media_root or (MEDIA_ROOT if root==ROOT else root))
    if not root.is_dir():raise FileNotFoundError('Configured chatlog root is not a directory')
    chats=read(root/'chats.json',{});names=read(root/'names.json',{});state=read(root/'state.json',{})
    revoked=set()
    for p in (root/'meta').rglob('*.json'):
        revoked.update(k for k,v in read(p,{}).items() if isinstance(v,dict) and v.get('deleted'))
    for cid,g in chats.items():
        yield {'kind':'group','source':'feishu','id':cid,'name':g.get('chat_name') or '', 'conversation_kind':'group','connection':CONNECTION,'enabled':g.get('enabled'),'in_chat':g.get('in_chat'),'last_sync':state.get(cid,{}).get('last_run')}
    seen=set();groups=set(chats)
    for source,folder in [('feishu','data'),('wechat','wechat')]:
        for path in sorted((root/folder).rglob('*.jsonl')):
            with path.open(encoding='utf-8') as f:
                for line in f:
                    if not line.endswith('\n') or not line.strip():continue
                    try:r=json.loads(line);mid=str(r['msg_id']);cid=str(r['chat_id']);ts=int(r['ts'])
                    except (ValueError,KeyError,TypeError):raise ValueError('Invalid complete archive record') from None
                    if (source,mid) in seen:continue
                    seen.add((source,mid))
                    if source=='wechat' or cid not in groups:
                        key=(source,cid)
                        if key not in groups:
                            groups.add(key)
                            yield {'kind':'group','source':source,'id':cid,'name':r.get('chat_name') or r.get('project') or '', 'conversation_kind':'private' if source=='wechat' and r.get('chat_kind')=='联系人' else 'group','connection':'import' if source=='wechat' else CONNECTION}
                    sid=str(r.get('speaker_id') or '')
                    yield {'kind':'message','source':source,'id':mid,'group_id':cid,'ts':ts if ts>0 else None,'sender_id':sid,'sender_name':names.get(sid) or r.get('speaker') or '', 'type':r.get('msg_type') or 'unknown','text':str(r.get('text') or ''),'deleted':mid in revoked,'parent_id':r.get('parent_id'),'media_state':'removed' if r.get('media_removed') else 'error' if r.get('media_error') else 'stored' if r.get('media_path') else '','raw':r}
                    yield from attachment(source,mid,r,media_root)

if __name__=='__main__':
    output=gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb')
    for item in records():output.write((json.dumps(item,ensure_ascii=False)+'\n').encode())
    output.close()
