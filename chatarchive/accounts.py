"""Local accounts and revocable browser sessions; no public registration."""
from __future__ import annotations
import argparse, getpass, hashlib, hmac, os, re, secrets, sqlite3, sys, time
from pathlib import Path
from .database import private_dir
from .security import Principal

SESSION_SECONDS = 8 * 3600
IDLE_SECONDS = 3600


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt=None):
    # OWASP's 32 MiB scrypt configuration. Salt and work factors are versioned.
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768,
                           r=8, p=3, maxmem=64 * 1024 * 1024, dklen=32)
    return 'scrypt$32768$8$3$' + salt + '$' + value.hex()


def password_matches(password, encoded):
    if not encoded or not encoded.startswith('scrypt$32768$8$3$'):
        return False
    return hmac.compare_digest(password_hash(password, encoded.split('$')[4]), encoded)


def validate_password(password):
    if not 15 <= len(password) <= 128:
        raise ValueError('密码须为 15–128 个字符，可以使用一句便于记忆的话')


class LoginLimited(Exception):
    pass


class Accounts:
    def __init__(self, path):
        self.path = Path(path)
        private_dir(self.path.parent)
        with self.connect() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL, external_id TEXT UNIQUE,
                    must_change INTEGER NOT NULL DEFAULT 1,
                    disabled INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
                    last_seen INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
                CREATE TABLE IF NOT EXISTS login_limits (
                    key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires_at INTEGER NOT NULL);
            ''')
        self.path.chmod(0o600)
        self.dummy_hash = password_hash(secrets.token_urlsafe(32))

    def connect(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def create(self, username, password, *, must_change=True):
        username = username.strip().lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,47}', username):
            raise ValueError('账号须为 3–48 位字母、数字、点、下划线或连字符')
        validate_password(password)
        encoded = password_hash(password)
        uid = secrets.token_hex(16)
        with self.connect() as c:
            c.execute('INSERT INTO users(id,username,password,must_change,created_at) VALUES(?,?,?,?,?)',
                      (uid, username, encoded, int(must_change), int(time.time())))
        return uid

    def limit(self, username, address, action='login'):
        now = int(time.time())
        keys = [(action + ':user:' + digest(username), 10, 900),
                (action + ':ip:' + digest(address), 30, 900), (action + ':global', 100, 60)]
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM login_limits WHERE expires_at<=?', (now,))
            for key, maximum, window in keys:
                row = c.execute('SELECT count FROM login_limits WHERE key=?', (key,)).fetchone()
                if row and row['count'] >= maximum:
                    raise LoginLimited()
            for key, maximum, window in keys:
                c.execute('INSERT INTO login_limits VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1',
                          (key, now + window))

    def _issue(self, c, uid):
        now = int(time.time())
        token = secrets.token_urlsafe(32)
        c.execute('DELETE FROM sessions WHERE expires_at<=? OR last_seen<=?', (now, now-IDLE_SECONDS))
        c.execute('INSERT INTO sessions VALUES(?,?,?,?,?)', (digest(token), uid, now, now+SESSION_SECONDS, now))
        return token

    def login(self, username, password, address, previous=''):
        username = username.strip().lower()
        self.limit(username, address)
        with self.connect() as c:
            row = c.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        valid = password_matches(password, row['password'] if row and row['password'] else self.dummy_hash)
        if not row or not valid or row['disabled'] or row['external_id']:
            return None
        with self.connect() as c:
            # A concurrent reset/disable must invalidate this in-flight login too.
            c.execute('BEGIN IMMEDIATE')
            fresh = c.execute('SELECT password,disabled FROM users WHERE id=?', (row['id'],)).fetchone()
            if fresh['disabled'] or fresh['password'] != row['password']:
                return None
            c.execute('DELETE FROM login_limits WHERE key=?', ('login:user:'+digest(username),))
            c.execute('DELETE FROM sessions WHERE hash=?', (digest(previous),))
            return self._issue(c, row['id'])

    def external_login(self, subject, previous=''):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM users WHERE external_id=?', (subject,)).fetchone()
            if row and row['disabled']:
                raise PermissionError('此账号已停用')
            uid = row['id'] if row else secrets.token_hex(16)
            if not row:
                c.execute('INSERT INTO users(id,username,password,external_id,must_change,created_at) VALUES(?,?,?,?,0,?)',
                          (uid, 'feishu-'+digest(subject)[:24], '', subject, int(time.time())))
            c.execute('DELETE FROM sessions WHERE hash=?', (digest(previous),))
            return self._issue(c, uid)

    def session(self, token):
        if not token or len(token) > 256:
            return None
        now = int(time.time())
        with self.connect() as c:
            row = c.execute('''SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
                               WHERE s.hash=? AND s.expires_at>? AND s.last_seen>? AND u.disabled=0''',
                            (digest(token), now, now-IDLE_SECONDS)).fetchone()
            if row:
                c.execute('UPDATE sessions SET last_seen=? WHERE hash=? AND last_seen<?', (now, digest(token), now-60))
        if not row:
            return None
        return {'principal': Principal('user:'+row['id'], admin=True),
                'username': '飞书管理员' if row['external_id'] else row['username'],
                'must_change_password': bool(row['must_change']),
                'authentication': 'feishu' if row['external_id'] else 'password'}

    def logout(self, token):
        with self.connect() as c:
            c.execute('DELETE FROM sessions WHERE hash=?', (digest(token),))

    def change_password(self, token, current, new, address):
        session = self.session(token)
        if not session or session['authentication'] != 'password':
            raise PermissionError('请使用账号密码登录后修改')
        self.limit(session['username'], address, 'password')
        validate_password(new)
        if hmac.compare_digest(current.encode(), new.encode()):
            raise ValueError('新密码不能与当前密码相同')
        uid = session['principal'].id.removeprefix('user:')
        with self.connect() as c:
            row = c.execute('SELECT password FROM users WHERE id=?', (uid,)).fetchone()
        if not password_matches(current, row['password']):
            raise ValueError('当前密码不正确')
        encoded = password_hash(new)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            now = int(time.time())
            active = c.execute('SELECT 1 FROM sessions WHERE hash=? AND expires_at>? AND last_seen>?',
                               (digest(token), now, now-IDLE_SECONDS)).fetchone()
            if not active:
                raise PermissionError('登录已失效，请重新登录')
            changed = c.execute('UPDATE users SET password=?,must_change=0 WHERE id=? AND password=? AND disabled=0',
                                (encoded, uid, row['password']))
            if not changed.rowcount:
                raise PermissionError('账号已更新，请重新登录')
            c.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
            return self._issue(c, uid)

    def reset(self, username, password):
        validate_password(password)
        encoded = password_hash(password)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT id FROM users WHERE username=? AND external_id IS NULL', (username.lower(),)).fetchone()
            if not row:
                raise ValueError('账号不存在')
            c.execute('UPDATE users SET password=?,must_change=1 WHERE id=?', (encoded, row['id']))
            c.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
            c.execute('DELETE FROM login_limits WHERE key=?', ('login:user:'+digest(username.lower()),))


def main():
    parser = argparse.ArgumentParser(description='Manage local administrator accounts on this server')
    parser.add_argument('command', choices=['create', 'reset', 'disable'])
    parser.add_argument('username')
    parser.add_argument('--data', default=os.environ.get('CHATARCHIVE_DATA', './var'))
    parser.add_argument('--password-stdin', action='store_true', help='Read one password line from redirected stdin; never pass secrets in argv')
    args = parser.parse_args()
    accounts = Accounts(Path(args.data)/'accounts.sqlite3')
    if args.command == 'disable':
        with accounts.connect() as c:
            row = c.execute('SELECT id FROM users WHERE username=?', (args.username.lower(),)).fetchone()
            if not row:
                raise SystemExit('Account does not exist')
            c.execute('UPDATE users SET disabled=1 WHERE id=?', (row['id'],))
            c.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
    else:
        if args.password_stdin:
            if sys.stdin.isatty():
                raise SystemExit('--password-stdin requires redirected input')
            password = sys.stdin.readline(1024).rstrip('\r\n')
        else:
            password = getpass.getpass('Initial password (15–128 characters): ')
            if password != getpass.getpass('Confirm password: '):
                raise SystemExit('Passwords do not match')
        if args.command == 'create':
            accounts.create(args.username, password)
        else:
            accounts.reset(args.username, password)
    print('Account updated. No password has been printed or saved in plaintext.')


if __name__ == '__main__':
    try:
        main()
    except sqlite3.IntegrityError:
        raise SystemExit('Account already exists; use reset to change its password') from None
    except (ValueError, OSError) as exc:
        raise SystemExit('Account update failed: '+str(exc)) from None
