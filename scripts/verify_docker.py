#!/usr/bin/env python3
"""Build and exercise an isolated deployment with synthetic data; remove only our test resources."""
import argparse, asyncio, importlib.util, json, os, secrets, socket, subprocess, sys, tempfile
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('mcp_example',ROOT/'examples/mcp_client.py')
mcp_example=importlib.util.module_from_spec(spec);spec.loader.exec_module(mcp_example)

def run(args,*,env,input=None,timeout=300):
    result=subprocess.run(args,cwd=ROOT,env=env,input=input,capture_output=True,timeout=timeout)
    if result.returncode:
        # All inputs and resources here are generated synthetic test data.
        raise RuntimeError('Command failed: '+str(args[:7])+'\n'+result.stderr.decode(errors='replace')[-4000:])
    return result.stdout


def exercise(url,username,password):
    with httpx.Client(base_url=url,headers={'Origin':url},timeout=30) as c:
        assert c.get('/').status_code==200
        assert c.get('/api/messages').status_code==401
        assert c.get('/api/me',headers={'X-Auth-Oid':'spoof','X-Auth-Role':'admin'}).status_code==401
        assert c.post('/api/session',json={'username':username,'password':password},headers={'Origin':'https://invalid.example'}).status_code==403
        r=c.post('/api/session',json={'username':username,'password':password});assert r.status_code==200,r.status_code
        assert r.json()['must_change_password']
        assert c.get('/api/messages').json()['code']=='password_change_required'
        original=c.cookies.get('chatarchive_session');new=secrets.token_urlsafe(24)
        assert c.post('/api/password',json={'current_password':password,'new_password':new}).status_code==200
        assert httpx.get(url+'/api/me',cookies={'chatarchive_session':original}).status_code==401
        assert c.get('/api/messages').json()['total']==2
        assert c.get('/api/groups').json()['total']==1
        assert c.get('/api/analysis',params={'source':'feishu','group_id':'demo-project'}).json()['totals']['messages']==2
        r=c.post('/api/keys',json={'name':'synthetic-smoke','sources':['feishu'],'groups':['feishu:demo-project'],'days':1});assert r.status_code==200
        key=r.json()
        result=asyncio.run(mcp_example.inspect_endpoint(url+'/mcp/',key['token']))
        assert len(result['tools'])==5
        assert result['sources']['sources'][0]['messages']==2
        assert c.get('/api/keys',headers={'Authorization':'Bearer '+key['token']}).status_code==403
        assert c.delete('/api/session').status_code==200
        assert c.get('/api/messages').status_code==401
        return new,key


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path)
    args=p.parse_args()
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    env=os.environ.copy();url=f'http://127.0.0.1:{port}'
    env.update(CHATARCHIVE_PORT=str(port),CHATARCHIVE_BASE_URL=url,CHATARCHIVE_ADMIN_TOKEN='')
    suffix=secrets.token_hex(5)
    projects=['chatarchive-smoke-'+suffix,'chatarchive-restore-'+suffix]
    compose=lambda project:['docker','compose','-p',project]
    call=lambda project,*cmd,input=None,timeout=300:run(compose(project)+list(cmd),env=env,input=input,timeout=timeout)
    username='smoke_admin';password=secrets.token_urlsafe(24)
    completed=[]
    def phase(name):completed.append(name);print(name,flush=True)
    try:
        call(projects[0],'config','--quiet')
        call(projects[0],'build',timeout=900);phase('Container build passed')
        call(projects[0],'run','--rm','-T','chatarchive','python','-m','chatarchive.cli','init')
        for _ in range(2):call(projects[0],'run','--rm','-T','chatarchive','python','-m','chatarchive.cli','import-jsonl','examples/sample.jsonl')
        call(projects[0],'run','--rm','-T','chatarchive','python','-m','chatarchive.accounts','create',username,'--password-stdin',input=(password+'\n').encode())
        call(projects[0],'up','-d','--wait','--wait-timeout','90');phase('Clean installation and duplicate import passed')
        password,key=exercise(url,username,password);phase('Password login, rotation, scoped HTTP and official MCP client passed')
        call(projects[0],'up','-d','--force-recreate','--wait','--wait-timeout','90')
        with httpx.Client(base_url=url,headers={'Origin':url},timeout=30) as c:
            assert c.post('/api/session',json={'username':username,'password':password}).status_code==200
            assert c.get('/api/messages').json()['total']==2
            call(projects[0],'exec','-T','chatarchive','python','-m','chatarchive.maintenance','backup','/data/smoke-backup.zip')
            snapshot=call(projects[0],'exec','-T','chatarchive','python','-c',"import sys;sys.stdout.buffer.write(open('/data/smoke-backup.zip','rb').read())")
            assert c.delete('/api/keys/'+key['id']).status_code==200
        phase('Container replacement preserves data and accounts; backup passed')
        call(projects[0],'down')
        # The second project creates its own completely separate data volume.
        call(projects[1],'build',timeout=900)
        call(projects[1],'run','--rm','-T','chatarchive','python','-m','chatarchive.maintenance','restore','-',input=snapshot)
        call(projects[1],'up','-d','--wait','--wait-timeout','90')
        assert httpx.get(url+'/api/messages',headers={'Authorization':'Bearer '+key['token']}).status_code==401
        assert httpx.post(url+'/api/session',headers={'Origin':url},json={'username':username,'password':password}).status_code==401
        recovery=secrets.token_urlsafe(24)
        call(projects[1],'exec','-T','chatarchive','python','-m','chatarchive.accounts','reset',username,'--password-stdin',input=(recovery+'\n').encode())
        exercise(url,username,recovery)
        call(projects[1],'exec','-T','chatarchive','python','-m','chatarchive.maintenance','doctor')
        phase('Restore to a new volume, credential invalidation and recovered queries passed')
        call(projects[1],'down')
        call(projects[0],'up','-d','--wait','--wait-timeout','90')
        with httpx.Client(base_url=url,headers={'Origin':url}) as c:
            assert c.post('/api/session',json={'username':username,'password':password}).status_code==200
            assert c.get('/api/messages').json()['total']==2
        phase('Switching back to original volume passed')
        result={'ok':True,'checks':completed,'synthetic_messages':2,'public_registration':False}
        if args.report:args.report.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result))
    finally:
        for project in projects:
            cleanup=subprocess.run(compose(project)+['down','--volumes','--remove-orphans'],cwd=ROOT,env=env,capture_output=True)
            if cleanup.returncode:print('Cleanup needs attention for '+project,file=sys.stderr)

if __name__=='__main__':main()
