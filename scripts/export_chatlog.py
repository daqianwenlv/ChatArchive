#!/usr/bin/env python3
"""Read-only adapter: emit normalized JSONL to stdout, optionally gzip compressed.
Run on the archive host. No collector imports, credential reads or writes.
"""
import datetime as dt,gzip,json,os,sys
from pathlib import Path
ROOT=Path(os.environ.get('CHATARCHIVE_CHATLOG_ROOT','/data/chatlog'))
CONNECTION=os.environ.get('CHATARCHIVE_CONNECTION_LABEL','archive')

def read(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:return default

def records(root=ROOT):
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
                    yield {'kind':'message','source':source,'id':mid,'group_id':cid,'ts':ts if ts>0 else None,'sender_id':sid,'sender_name':names.get(sid) or r.get('speaker') or '', 'type':r.get('msg_type') or 'unknown','text':str(r.get('text') or ''),'deleted':mid in revoked,'parent_id':r.get('parent_id'),'media_state':'removed' if r.get('media_removed') else 'error' if r.get('media_error') else 'stored' if r.get('media_path') else ''}

if __name__=='__main__':
    output=gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb')
    for item in records():output.write((json.dumps(item,ensure_ascii=False)+'\n').encode())
    output.close()
