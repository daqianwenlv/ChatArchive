import time
import pytest
from fastapi.testclient import TestClient
from chatarchive.accounts import Accounts, IDLE_SECONDS, digest, LoginLimited
from chatarchive.server import create_app

INITIAL = 'Initial-testing-password-2026'
CHANGED = 'Changed-testing-password-2026'


@pytest.fixture
def client(archive):
    app = create_app(archive, trust_proxy=False, admin_token='', base_url='https://testserver')
    app.state.accounts.create('owner', INITIAL)
    with TestClient(app, base_url='https://testserver', headers={'Origin':'https://testserver'}) as c:
        yield c


def login(client, password=INITIAL):
    return client.post('/api/session', json={'username':'owner','password':password})


def test_initial_password_gate_rotation_and_logout(client):
    assert login(client, 'wrong').status_code == 401
    r = login(client)
    assert r.json()['must_change_password']
    cookie = r.headers['set-cookie']
    assert all(x in cookie for x in ['HttpOnly','Secure','SameSite=lax'])
    initial_session = client.cookies.get('chatarchive_session')
    assert client.get('/api/me').json()['username'] == 'owner'
    for path in ['/api/sources','/api/groups','/api/keys','/api/analysis','/api/message']:
        assert client.get(path).json()['code'] == 'password_change_required'
    assert client.post('/api/password', json={'current_password':'wrong','new_password':CHANGED}).status_code == 400
    assert client.post('/api/password', json={'current_password':INITIAL,'new_password':CHANGED}).status_code == 200
    current = client.cookies.get('chatarchive_session')
    assert current != initial_session
    assert client.app.state.accounts.session(initial_session) is None
    assert client.get('/api/messages').json()['total'] == 5
    assert client.get('/api/me').json()['must_change_password'] is False
    # Passwords and opaque session secrets must never be stored verbatim.
    raw = client.app.state.accounts.path.read_bytes()
    assert all(value.encode() not in raw for value in [INITIAL,CHANGED,current,initial_session])
    assert client.delete('/api/session').status_code == 200
    assert client.app.state.accounts.session(current) is None
    assert client.get('/api/messages').status_code == 401
    assert login(client).status_code == 401
    assert login(client, CHANGED).status_code == 200


def test_csrf_validation_and_machine_boundary(client):
    payload = {'username':'owner','password':INITIAL}
    assert client.post('/api/session', headers={'Origin':'https://evil.example'}, json=payload).status_code == 403
    client.headers.pop('Origin')
    assert client.post('/api/session', json=payload).status_code == 403
    client.headers['Origin']='https://testserver'
    assert login(client).status_code == 200
    assert client.get('/api/me',headers={'X-ChatArchive-Machine':'1'}).status_code == 401
    assert client.post('/mcp/', json={'jsonrpc':'2.0','id':1,'method':'tools/list'}).status_code == 401
    assert client.post('/api/session',headers={'X-ChatArchive-Machine':'1'},json=payload).status_code == 403
    assert client.get('/api/sso',headers={'X-Auth-Oid':'spoof','X-Auth-Role':'admin'}).status_code == 403
    bad = client.post('/api/password',json={'current_password':INITIAL,'new_password':'tiny-secret'})
    # Invalid input errors must not echo submitted credentials.
    assert bad.status_code == 400 and INITIAL not in bad.text and 'tiny-secret' not in bad.text
    client.headers.pop('Origin')
    assert client.delete('/api/session').status_code == 403


def test_login_limit_persists_and_expiry_disable_reset(tmp_path):
    accounts = Accounts(tmp_path/'accounts.sqlite3')
    uid = accounts.create('owner', INITIAL, must_change=False)
    for _ in range(10):
        assert accounts.login('nobody','wrong','ip1') is None
    with pytest.raises(LoginLimited):
        Accounts(accounts.path).login('nobody','wrong','ip2')
    token = accounts.login('owner', INITIAL, 'ip3')
    with accounts.connect() as c:
        c.execute('UPDATE sessions SET last_seen=? WHERE hash=?',(int(time.time())-IDLE_SECONDS,digest(token)))
    assert accounts.session(token) is None
    token = accounts.login('owner', INITIAL, 'ip3')
    with accounts.connect() as c:
        c.execute('UPDATE sessions SET expires_at=0 WHERE hash=?',(digest(token),))
    assert accounts.session(token) is None
    token = accounts.login('owner', INITIAL, 'ip3')
    accounts.reset('owner', CHANGED)
    assert accounts.session(token) is None
    assert accounts.login('owner', INITIAL, 'ip3') is None
    token = accounts.login('owner', CHANGED, 'ip3')
    assert accounts.session(token)['must_change_password']
    with accounts.connect() as c:
        c.execute('UPDATE users SET disabled=1 WHERE id=?',(uid,))
    assert accounts.session(token) is None
    assert accounts.login('owner', CHANGED, 'ip3') is None


def test_password_change_revokes_other_devices(client):
    accounts = client.app.state.accounts
    other = accounts.login('owner', INITIAL, 'other-device')
    login(client)
    assert client.post('/api/password',json={'current_password':INITIAL,'new_password':CHANGED}).status_code == 200
    assert accounts.session(other) is None


def test_trusted_feishu_exchange_and_logout(archive):
    app = create_app(archive,trust_proxy=True,admin_token='',base_url='https://testserver/ChatArchive')
    # Proxy passes the path without its deployment prefix, like production nginx.
    with TestClient(app,base_url='https://testserver',client=('127.0.0.1',1234)) as client:
        headers={'X-Auth-Oid':'feishu-admin','X-Auth-Role':'admin'}
        r=client.get('/api/sso',headers=headers,follow_redirects=False)
        assert r.status_code == 303
        assert r.headers['location'] == 'https://testserver/ChatArchive/'
        assert 'Path=/ChatArchive/' in r.headers['set-cookie']
        token=client.cookies.get('chatarchive_session')
        account=app.state.accounts.session(token)
        assert account['authentication'] == 'feishu' and account['principal'].admin
        app.state.accounts.logout(token)
        assert app.state.accounts.session(token) is None
