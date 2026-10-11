#!/usr/bin/env python3
"""Check distribution contents and credential patterns; not a substitute for security review."""
import argparse,ast,hashlib,json,re,stat,zipfile
from pathlib import Path
from release_files import source_files

ROOT=Path(__file__).resolve().parents[1]
RULES={
    'private key':r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
    'GitHub credential':r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b',
    'cloud access key':r'\bAKIA[A-Z0-9]{16}\b',
    'ChatArchive access key':r'\bca_[A-Za-z0-9_-]{40,}\b',
    'developer home path':r'/Users/[A-Za-z0-9_.-]+/',
    'private SSH path':r'/root/\.ssh/[A-Za-z0-9_.-]+',
}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--deny-file',type=Path,help='Optional local JSON containing values that must never occur in the release; values are not printed')
    args=p.parse_args()
    manifest=json.loads((ROOT/'release/manifest.json').read_text())
    bundle=ROOT/'release'/manifest['file']
    if hashlib.sha256(bundle.read_bytes()).hexdigest()!=manifest['sha256']:
        raise SystemExit('Release checksum does not match manifest')
    deny=[]
    if args.deny_file:
        def collect(value):
            if isinstance(value,dict):
                for item in value.values():collect(item)
            elif isinstance(value,list):
                for item in value:collect(item)
            elif isinstance(value,str) and len(value)>=12:deny.append(value)
        collect(json.loads(args.deny_file.read_text()))
    expected={'ChatArchive/'+f for f in source_files(ROOT)};errors=[]
    with zipfile.ZipFile(bundle) as z:
        names=z.namelist()
        if set(names)!=expected or len(names)!=len(expected):errors.append('File inventory differs from the allowlist')
        for item in z.infolist():
            if stat.S_ISLNK(item.external_attr>>16) or item.file_size>2*1024*1024:
                errors.append(item.filename+': symlink or oversized source file')
            raw=z.read(item)
            if item.filename.endswith('.jpg'):
                if not raw.startswith(b'\xff\xd8\xff'):errors.append(item.filename+': invalid JPEG')
                continue
            data=raw.decode('utf-8')
            for label,pattern in RULES.items():
                if re.search(pattern,data):errors.append(item.filename+': '+label)
            if any(secret in data for secret in deny):errors.append(item.filename+': prohibited private value')
            if item.filename.endswith('.py'):ast.parse(data,filename=item.filename)
            if item.filename.endswith('.jsonl'):
                for line in data.splitlines():
                    record=json.loads(line)
                    if not str(record.get('id','')).startswith('demo-'):errors.append(item.filename+': non-demo sample ID')
    if errors:raise SystemExit('\n'.join(errors))
    print(json.dumps({'ok':True,'version':manifest['version'],'files':len(expected),'private_values_checked':bool(deny),'checks':['allowlist','archive SHA-256','credential patterns','Python syntax','synthetic sample IDs']}))

if __name__=='__main__':main()
