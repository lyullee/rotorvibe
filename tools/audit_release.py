"""Fail closed if raw/private files or normative lookup modules enter a release."""
import argparse,ast,json,re,tarfile,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES={'.pdf','.npy','.npz','.mat','.csv','.lvm','.db','.sqlite','.sqlite3','.pem','.key'}
PRIVATE_ISO={'industrial.py','shaft.py','turbine.py','gas_turbine.py','reciprocating.py','pump.py','compressor.py','wind.py','hydro.py','sources.json'}
SECRET=re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{32,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')

def check(name,data):
    path=Path(name); parts=path.parts
    if path.suffix.lower() in FORBIDDEN_SUFFIXES or any(p in ('data','runtime','upstream') for p in parts): raise ValueError('Restricted content: '+name)
    if 'iso' in parts and path.name in PRIVATE_ISO: raise ValueError('Normative route must remain private: '+name)
    if path.suffix in {'.py','.json','.jsonl','.md','.rst','.txt','.yml','.cff','.toml'} or path.name in {'LICENSE','NOTICE','MANIFEST.in'}:
        text=data.decode('utf-8-sig')
        if SECRET.search(text): raise ValueError('Credential pattern: '+name)
        if re.search(r'[A-Z]:[\\/](?:Users|C드라이브)',text): raise ValueError('Personal absolute path: '+name)
        if path.suffix=='.py': ast.parse(text,filename=name)

def audit_tree():
    count=0
    for p in ROOT.rglob('*'):
        if not p.is_file() or any(t in ('.git','__pycache__','build','dist') or t.endswith('.egg-info') for t in p.relative_to(ROOT).parts): continue
        check(p.relative_to(ROOT).as_posix(),p.read_bytes()); count+=1
    assert (ROOT/'LICENSE').read_text(encoding='utf-8').startswith('MIT License')
    assert not list((ROOT/'vibration/iso').glob('*.json'))
    return count

def audit_dist(folder):
    rows=[]
    for p in Path(folder).iterdir():
        if p.suffix=='.whl':
            with zipfile.ZipFile(p) as archive:
                for name in archive.namelist():
                    if not name.endswith('/'): check(name,archive.read(name))
        elif p.name.endswith('.tar.gz'):
            with tarfile.open(p) as archive:
                for member in archive.getmembers():
                    if member.isfile(): check(member.name,archive.extractfile(member).read())
        else: continue
        rows.append(p.name)
    assert any(n.endswith('.whl') for n in rows) and any(n.endswith('.tar.gz') for n in rows)
    return rows

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--dist'); args=parser.parse_args()
    result={'status':'pass','source_files_audited':audit_tree(),'normative_tables':'excluded','raw_data':'excluded','credentials_and_personal_paths':'no pattern findings'}
    if args.dist: result['distributions']=audit_dist(args.dist)
    print(json.dumps(result,indent=2))
