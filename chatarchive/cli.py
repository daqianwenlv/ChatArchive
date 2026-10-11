"""Portable commands for a standalone installation. Production credentials are not bundled."""
from __future__ import annotations
import argparse,datetime as dt,json,os,secrets,sqlite3,tempfile
from pathlib import Path
from .database import SCHEMA,finalize,private_dir,index_lock
from .importer import insert,import_wecom
from .security import AccessStore

NAMES={'feishu':'飞书','wecom':'企业微信','wechat':'微信','dingtalk':'钉钉'}
def main():
 p=argparse.ArgumentParser(prog='chatarchive');p.add_argument('--data',type=Path,default=Path(os.environ.get('CHATARCHIVE_DATA','var')))
 sub=p.add_subparsers(dest='command',required=True)
 sub.add_parser('init',help='Create an empty private index')
 ingest=sub.add_parser('import-jsonl',help='Merge normalized group/message JSONL');ingest.add_argument('file',type=Path)
 wc=sub.add_parser('import-wecom',help='Read an existing WeCom archive database');wc.add_argument('file',type=Path)
 key=sub.add_parser('create-key',help='Create a scoped read key; token goes to a private output file');key.add_argument('--name',required=True);key.add_argument('--source',action='append',required=True,choices=NAMES);key.add_argument('--group',action='append');key.add_argument('--days',type=int,default=30);key.add_argument('--output',type=Path,required=True)
 args=p.parse_args();private_dir(args.data);target=args.data/'archive.sqlite3'
 if args.command=='create-key':
  result=AccessStore(args.data/'access.sqlite3').create(args.name,args.source,args.group,days=args.days,actor='local-cli')
  fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'w') as out:out.write(result['token']+'\n')
  print(json.dumps({'id':result['id'],'expires_at':result['expires_at'],'token_file':str(args.output)}));return
 with index_lock(args.data):
  import_records(args,target)

def import_records(args,target):
 if args.command=='init' and target.exists():raise SystemExit('Index already exists; nothing changed.')
 fd,temp=tempfile.mkstemp(prefix='.import-',suffix='.sqlite3',dir=args.data);os.close(fd);con=sqlite3.connect(temp)
 try:
  if target.exists():
   old=sqlite3.connect(target.resolve().as_uri()+'?mode=ro',uri=True);old.backup(con);old.close()
  else:
   con.executescript(SCHEMA)
   con.executemany('INSERT INTO sources VALUES(?,?,?,?,?,?)',[(s,name,'unconfigured',None,'not_connected','{}') for s,name in NAMES.items()])
  seen=set()
  if args.command=='import-jsonl':
   with args.file.open(encoding='utf-8') as f:
    for line in f:
     if not line.strip():continue
     r=json.loads(line)
     if r.get('source') not in NAMES or not r.get('id'):raise ValueError('Invalid source or ID')
     if r.get('kind')=='message' and not r.get('group_id'):raise ValueError('Missing group_id')
     insert(con,r);seen.add(r['source'])
  elif args.command=='import-wecom':import_wecom(con,args.file);seen.add('wecom')
  stamp=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
  for s in seen:con.execute("UPDATE sources SET mode='import',status='imported',synced_at=? WHERE source=?",(stamp,s))
  con.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('indexed_at',stamp));finalize(con);con.close();con=None;os.chmod(temp,0o600);os.replace(temp,target)
  print(json.dumps({'ok':True,'index':str(target),'sources':sorted(seen)}))
 finally:
  if con:con.close()
  if os.path.exists(temp):os.unlink(temp)

if __name__=='__main__':
 try:main()
 except (ValueError,OSError,RuntimeError,sqlite3.Error) as exc:
  raise SystemExit('Command failed: '+str(exc)) from None
