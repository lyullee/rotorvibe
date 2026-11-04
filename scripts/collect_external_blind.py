"""New test-only data: UOS tapered-bearing domain and independent UFRJ rig.

Only metadata is inspected before the complete manifest and models are frozen.
No new recording is eligible for fitting, tuning or calibration.
"""
import sys,json,re,hashlib,subprocess,shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data/external_blind'; OUT=ROOT/'output/external_blind'; CURL=shutil.which('curl') or 'curl'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def get(url,name):
    path=DATA/'sources'/name; path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists(): subprocess.run([CURL,'-fLsS','--retry','2','--max-time','60',url,'-o',str(path)],check=True)
    return path.read_text(encoding='utf-8')

def prepare():
    if (OUT/'protocol.json').exists(): raise RuntimeError('Already frozen; do not replace manifest/models')
    jobs=[]; dataset='2cygy6y4rk'; version=1
    folders=json.loads(get(f'https://data.mendeley.com/public-api/datasets/{dataset}/folders/{version}','uos30204_folders.json'))
    rate=next(r['id'] for r in folders if r['name']=='SamplingRate_16000')
    for folder in folders:
        if folder.get('parent_id')!=rate: continue
        rpm=int(folder['name'].split('_')[-1]); files=json.loads(get(f'https://data.mendeley.com/public-api/datasets/{dataset}/files?folder_id={folder["id"]}&version={version}',f'uos30204_{rpm}.json'))
        for row in files:
            if not re.fullmatch(r'(H|L|M[123]|U[123])_H_16_30204_\d+\.mat',row['filename']): continue
            condition=row['filename'].split('_')[0]
            if condition!='H' and rpm!=1200: continue
            detail=row['content_details']; label='normal' if condition=='H' else 'looseness' if condition=='L' else 'unbalance' if condition[0]=='U' else 'misalignment'
            jobs.append(dict(id='uos30204:'+row['filename'],path='raw/uos30204/'+row['filename'],source=f'https://data.mendeley.com/datasets/{dataset}/1',
                url=detail['download_url'],provider_sha256=detail['sha256_hash'],bytes=row['size'],fs=16000,rpm=rpm,label=label,unit='g',
                asset_id='UOS_30204_TEST_ONLY',rig='UOS_AST_bearing_transfer',channel='bearing_radial',column=0,format='mat',role='test_only',license='CC-BY-4.0'))
    assert len(jobs)==13 and sum(r['label']=='normal' for r in jobs)==6
    base='https://www02.smt.ufrj.br/~offshore/mfs/database/mafaulda/'
    configurations=[('normal','normal'),('imbalance/6g','unbalance'),('imbalance/20g','unbalance'),('imbalance/35g','unbalance'),
        ('horizontal-misalignment/1.0mm','misalignment'),('horizontal-misalignment/2.0mm','misalignment')]
    for folder,label in configurations:
        html=get(base+folder+'/', 'mafaulda_'+folder.replace('/','_')+'.html')
        entries=[(name,int(size)) for name,size in re.findall(r'href="([0-9.]+\.csv)">[^<]+</a>[^\n]*?\s(\d+)\s*(?:\n|$)',html)]
        eligible=[e for e in entries if 590<=float(e[0][:-4])*60<=1620]
        assert eligible,(folder,'No directory metadata')
        selected=eligible if label=='normal' else sorted({min(eligible,key=lambda e:abs(float(e[0][:-4])*60-target)) for target in (800,1200,1600)})
        for name,size in selected:
            jobs.append(dict(id='mafaulda:'+folder+'/'+name,path='raw/mafaulda/'+folder+'/'+name,source='https://www02.smt.ufrj.br/~offshore/mfs/page_01.html',
                url=base+folder+'/'+name,bytes=size,fs=50000,rpm=float(name[:-4])*60,label=label,unit='unknown',asset_id='UFRJ_MAFAULDA_ABVT',
                rig='UFRJ_ABVT_independent',channel='underhang_radial',column=2,format='csv',role='test_only',license='No explicit license on official page; local research only, excluded from source export'))
    OUT.mkdir(parents=True,exist_ok=True); write(DATA/'plan.json',jobs)
    for source,name in [(ROOT/'output/fault_discrimination/frozen.json','fault_frozen.json'),(ROOT/'output/fault_discrimination/baseline_frozen.json','normal_gate_frozen.json')]:
        (OUT/name).write_bytes(source.read_bytes())
    protocol=dict(frozen_utc=datetime.now(timezone.utc).isoformat(),test_only=True,fit_tune_calibration_forbidden=True,
        model_sha256={name:sha(OUT/name) for name in ['fault_frozen.json','normal_gate_frozen.json']},
        code_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'vibration').rglob('*.py')},plan_sha256=sha(DATA/'plan.json'),
        records=len(jobs),selection='UOS30204: all6 healthy speeds and7faults1200 at16k. MAFAULDA: all healthy nominal590..1620RPM, faults nearest800/1200/1600 for prespecified5severities. Vertical0.51mm directory returned403 before any waveform decoding; excluded that family before freeze.',
        windows='Nonoverlapping2seconds, first4seconds per5second MAFAULDA file; all80seconds UOS.',
        rpm_source='Nominal metadata only; never infer speed from fault vibration or adjust to nearest supported normal RPM.',
        primary='Unmodified public API with REAL asset/unit/channel identity. Scope holds count wrong for fault-type recall; report coverage and normal acceptance separately.',
        shadow='Offline fixed-weight numerical stress only: suppress asset identity check with explicit audit flags; never deploy. No learned reference/scale/threshold updates.',
        shadow_units='UOS30204 physical g. MAFAULDA native CSV amplitude unit not explicit in official page: fixed factors1 and10 as TWO declared unit-sensitivity scenarios; do not choose better or claim physical FPR.',
        unsupported='Report unavailable RPM/units/rate/layout and abstentions; never round RPM to a reference or treat hold as normal.',
        independence='UFRJ ABVT is a different institution/rig than UOS AST. UOS30204 is new bearing domain on same rig, NOT another independent bench.',
        normal_new_to_model=True,looseness_external_bench_available=False,operational_use=False)
    write(OUT/'protocol.json',protocol)
    print('FROZEN',len(jobs),'test-only original records',sum(r['bytes'] for r in jobs),'bytes; arrays not decoded',flush=True)

def download():
    protocol=json.loads((OUT/'protocol.json').read_text(encoding='utf-8')); assert sha(DATA/'plan.json')==protocol['plan_sha256']
    jobs=json.loads((DATA/'plan.json').read_text(encoding='utf-8'))
    def one(row):
        path=DATA/row['path']; path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            part=path.with_suffix(path.suffix+'.part'); subprocess.run([CURL,'-fLsS','--retry','3','--connect-timeout','20','--max-time','240',row['url'],'-o',str(part)],check=True)
            assert part.stat().st_size==row['bytes'],row['id']
            if row.get('provider_sha256'): assert sha(part)==row['provider_sha256']
            part.replace(path)
        assert path.stat().st_size==row['bytes']; digest=sha(path)
        if row.get('provider_sha256'): assert digest==row['provider_sha256']
        print('COLLECTED',row['id'],flush=True); return dict(id=row['id'],bytes=path.stat().st_size,local_sha256=digest,provider_sha256=row.get('provider_sha256'),unit=row['unit'],role='test_only')
    with ThreadPoolExecutor(max_workers=4) as pool: manifest=list(pool.map(one,jobs))
    write(DATA/'manifest.json',manifest); print('COMPLETE',len(manifest),'arrays not decoded',flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('phase',choices=['prepare','download']); a=p.parse_args(); prepare() if a.phase=='prepare' else download()
