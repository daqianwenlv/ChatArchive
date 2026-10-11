#!/usr/bin/env python3
"""Build the explicit source allowlist; never package live archives or internal notes."""
from pathlib import Path
import ast,hashlib,json,stat,zipfile
from release_files import source_files

ROOT=Path(__file__).resolve().parents[1]
VERSION=next(ast.literal_eval(node.value) for node in ast.parse((ROOT/'chatarchive/__init__.py').read_text()).body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__version__' for t in node.targets))
FILES=source_files(ROOT)
OUT=ROOT/'release';OUT.mkdir(exist_ok=True)
path=OUT/f'ChatArchive-{VERSION}-source.zip'
with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as bundle:
    for name in FILES:
        if any(x in Path(name).parts for x in ['internal','var','site','.venv']) or (ROOT/name).is_symlink():
            raise ValueError('Disallowed source file: '+name)
        if Path(name).suffix in ['.sqlite3','.db','.key','.pem']:
            raise ValueError('Disallowed source file type: '+name)
        # Stable timestamps and modes make archives reproducible from the same source.
        info=zipfile.ZipInfo('ChatArchive/'+name,date_time=(2026,1,1,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(stat.S_IFREG|0o644)<<16
        bundle.writestr(info,(ROOT/name).read_bytes())
report={'file':path.name,'version':VERSION,'files':len(FILES),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'maturity':'query-preview','includes_real_chat_data':False}
(OUT/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
(OUT/'SHA256SUMS').write_text(report['sha256']+'  '+path.name+'\n')
print(json.dumps(report))
