import gzip,json,subprocess,sys
from chatarchive.importer import export_program


def test_bridge_configuration_and_literal_paths(tmp_path):
    # Quotes and shell syntax are literal path characters, not commands.
    root=tmp_path/"archive ' $(not-a-command)";root.mkdir()
    (root/'chats.json').write_text(json.dumps({'g1':{'chat_name':'虚构群'}}))
    (root/'data').mkdir()
    (root/'data/events.jsonl').write_text(json.dumps({'msg_id':'demo-message','chat_id':'g1','ts':1,'text':'虚构记录'})+'\n')
    label="demo ' connection"
    result=subprocess.run([sys.executable,'-'],input=export_program(root,label),capture_output=True)
    assert result.returncode==0
    rows=[json.loads(line) for line in gzip.decompress(result.stdout).splitlines()]
    assert rows[0]['connection']==label
    assert rows[0]['name']=='虚构群'
    assert rows[1]['text']=='虚构记录'


def test_missing_archive_root_is_not_an_empty_success(tmp_path):
    result=subprocess.run([sys.executable,'-'],input=export_program(tmp_path/'missing'),capture_output=True)
    assert result.returncode!=0
    assert b'Configured chatlog root is not a directory' in result.stderr
