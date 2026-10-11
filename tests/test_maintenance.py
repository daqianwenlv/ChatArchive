import hashlib,json,sqlite3,stat,subprocess,sys,zipfile
from pathlib import Path
import pytest
from chatarchive.accounts import Accounts
from chatarchive.maintenance import backup,restore,doctor
from chatarchive.security import AccessStore
from chatarchive.database import index_lock


def test_backup_restore_data_and_invalidate_historical_credentials(archive,tmp_path):
 a=Accounts(archive/'accounts.sqlite3');a.create('admin','Initial-test-password-2026',must_change=False)
 session=a.login('admin','Initial-test-password-2026','tests')
 keys=AccessStore(archive/'access.sqlite3');key=keys.create('client',['feishu'])
 bundle=tmp_path/'snapshot.zip';report=backup(archive,bundle)
 assert report['messages']=={'feishu':3,'wecom':2}
 assert stat.S_IMODE(bundle.stat().st_mode)==0o600
 with pytest.raises(FileExistsError):backup(archive,bundle)
 # Revocation after the snapshot must not be undone by recovery.
 keys.revoke(key['id'],'tests')
 target=tmp_path/'restored';result=restore(bundle,target)
 assert result['credentials_invalidated']
 assert doctor(target)['ok']
 with sqlite3.connect(target/'archive.sqlite3') as restored_db,sqlite3.connect(archive/'archive.sqlite3') as original_db:
  for table in ['messages','groups','sources','metadata']:
   assert restored_db.execute('SELECT * FROM '+table).fetchall()==original_db.execute('SELECT * FROM '+table).fetchall()
 restored=Accounts(target/'accounts.sqlite3')
 assert restored.session(session) is None
 assert restored.login('admin','Initial-test-password-2026','tests') is None
 assert AccessStore(target/'access.sqlite3').authenticate(key['token']) is None
 restored.reset('admin','New-recovery-password-2026')
 assert restored.login('admin','New-recovery-password-2026','tests')
 with pytest.raises(ValueError,match='empty'):restore(bundle,target)
 assert all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in target.glob('*.sqlite3'))


@pytest.mark.parametrize('mode',['tamper','traversal','duplicate','schema'])
def test_reject_invalid_backup_without_partial_restore(archive,tmp_path,mode):
 bundle=tmp_path/'source.zip';backup(archive,bundle)
 with zipfile.ZipFile(bundle) as z:entries={n:z.read(n) for n in z.namelist()}
 if mode=='tamper':entries['archive.sqlite3']+=b'changed'
 if mode=='traversal':entries['../outside.txt']=b'bad'
 if mode=='schema':
  fake=tmp_path/'fake.sqlite3'
  with sqlite3.connect(fake) as db:db.execute('CREATE TABLE wrong(id INTEGER)')
  data=fake.read_bytes();entries['archive.sqlite3']=data
  m=json.loads(entries['manifest.json']);m['files']['archive.sqlite3']={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()};entries['manifest.json']=json.dumps(m).encode()
 bad=tmp_path/'bad.zip'
 with zipfile.ZipFile(bad,'w') as z:
  for name,data in entries.items():z.writestr(name,data)
  if mode=='duplicate':
   with pytest.warns(UserWarning):z.writestr('manifest.json',entries['manifest.json'])
 target=tmp_path/'target'
 with pytest.raises(ValueError):restore(bad,target)
 assert not list(target.iterdir())
 assert not (tmp_path/'outside.txt').exists()


def test_import_rejects_concurrent_writer_and_preserves_archive(archive):
 before=(archive/'archive.sqlite3').read_bytes()
 with index_lock(archive):
  result=subprocess.run([sys.executable,'-m','chatarchive.cli','--data',str(archive),'import-jsonl',str(Path(__file__).resolve().parents[1]/'examples/sample.jsonl')],capture_output=True,text=True)
  assert result.returncode!=0 and 'Another index writer' in result.stderr
 assert (archive/'archive.sqlite3').read_bytes()==before


def test_doctor_detects_missing_or_corrupt_index(tmp_path):
 assert not doctor(tmp_path)['ok']
 (tmp_path/'archive.sqlite3').write_text('invalid SQLite')
 assert not doctor(tmp_path)['ok']


def test_restore_cli_accepts_stdin_and_leaves_existing_target_untouched(archive,tmp_path):
 bundle=tmp_path/'stdin.zip';backup(archive,bundle)
 target=tmp_path/'cli-restored'
 cmd=[sys.executable,'-m','chatarchive.maintenance','--data',str(target),'restore','-']
 result=subprocess.run(cmd,input=bundle.read_bytes(),capture_output=True)
 assert result.returncode==0,result.stderr.decode()
 before=(target/'archive.sqlite3').read_bytes()
 again=subprocess.run(cmd,input=bundle.read_bytes(),capture_output=True)
 assert again.returncode!=0 and b'never overwritten' in again.stderr
 assert (target/'archive.sqlite3').read_bytes()==before
