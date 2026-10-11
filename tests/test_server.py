import pytest
from fastapi.testclient import TestClient
from chatarchive.server import create_app

@pytest.fixture
def client(archive):
 app=create_app(archive,trust_proxy=False,admin_token='a'*40,base_url='http://testserver')
 with TestClient(app) as c:yield c

def test_auth_and_key_administration(client):
 assert client.get('/api/messages').status_code==401
 assert client.get('/api/messages',headers={'X-Auth-Role':'admin','X-Auth-Oid':'spoof'}).status_code==401
 admin={'Authorization':'Bearer '+'a'*40}
 assert client.post('/api/keys',headers=admin,json={'name':'invalid','sources':['feishu'],'groups':['wecom:wr001']}).status_code==400
 r=client.post('/api/keys',headers=admin,json={'name':'scoped','sources':['feishu'],'groups':['feishu:g1']});assert r.status_code==200
 token=r.json()['token'];h={'Authorization':'Bearer '+token}
 assert client.get('/api/messages',headers=h).json()['total']==2
 assert client.get('/api/message?source=feishu&message_id=m2',headers=h).status_code==404
 assert client.get('/api/keys',headers=h).status_code==403
 assert client.post('/api/keys',headers=admin|{'Origin':'https://evil.example'},json={'name':'bad','sources':['feishu']}).status_code==403
 client.delete('/api/keys/'+r.json()['id'],headers=admin)
 assert client.get('/api/messages',headers=h).status_code==401

def test_mcp_tools_are_scoped_and_revocable(client):
 token=client.app.state.store.create('MCP test',['feishu'],['feishu:g1'])
 headers={'Authorization':'Bearer '+token['token'],'Accept':'application/json, text/event-stream'}
 assert client.post('/mcp/',json={'jsonrpc':'2.0','id':1,'method':'tools/list'}).status_code==401
 init=client.post('/mcp/',headers=headers,json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'tests','version':'1'}}})
 assert init.status_code==200,init.text
 r=client.post('/mcp/',headers=headers,json={'jsonrpc':'2.0','id':2,'method':'tools/list'})
 assert r.status_code==200,r.text
 assert len(r.json()['result']['tools'])==5
 r=client.post('/mcp/',headers=headers,json={'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'search_messages','arguments':{}}})
 assert r.status_code==200,r.text
 data=r.json()['result'];assert not data.get('isError'),data
 assert data['structuredContent']['total']==2
 r=client.post('/mcp/',headers=headers,json={'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'get_message','arguments':{'source':'feishu','message_id':'m2'}}})
 assert r.json()['result']['isError']
 client.app.state.store.revoke(token['id'],'test')
 assert client.post('/mcp/',headers=headers,json={'jsonrpc':'2.0','id':5,'method':'tools/list'}).status_code==401

def test_static_assets_cannot_select_server_files(client):
 r=client.get('/app.js?name=/etc/passwd')
 assert r.status_code==200
 assert "'use strict'" in r.text and 'root:x:' not in r.text
 assert client.get('/access.sqlite3').status_code==404

def test_integration_reports_actual_sdk_tools(client):
 r=client.get('/api/integration',headers={'Authorization':'Bearer '+'a'*40})
 assert r.status_code==200
 d=r.json();assert len(d['tools'])==5 and d['endpoint'].endswith('/mcp/')
 assert all('inputSchema' in t and 'ctx' not in t['inputSchema'].get('properties',{}) for t in d['tools'])
