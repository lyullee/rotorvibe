"""Collect previously unused 8kHz fault acquisitions, preassign whole test files."""
import sys,json,re,subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
from collect_condition_data import ROOT as OLD,get_json,sha,CURL
DATA=ROOT/'data/fault_discrimination'

def main():
    DATA.mkdir(parents=True,exist_ok=True); jobs=[]
    folders=get_json('https://data.mendeley.com/public-api/datasets/53vtnjy6c6/folders/1','uos_folders.json')
    parent=next(f['id'] for f in folders if f['name']=='SamplingRate_8000')
    for folder in folders:
        if folder.get('parent_id')!=parent: continue
        rpm=int(folder['name'].split('_')[-1])
        rows=get_json(f'https://data.mendeley.com/public-api/datasets/53vtnjy6c6/files?folder_id={folder["id"]}&version=1',f'uos_8k_{rpm}_files.json')
        for row in rows:
            if not re.fullmatch(r'(L|U[123]|M[123])_H_8_6204_\d+\.mat',row['filename']): continue
            condition=row['filename'].split('_')[0]; detail=row['content_details']
            jobs.append(dict(filename=row['filename'],rpm=rpm,sample_rate_hz=8000,unit='g',
                label='looseness' if condition=='L' else 'unbalance' if condition[0]=='U' else 'misalignment',
                severity=condition,role='final_test' if rpm==1200 else 'development',
                url=detail['download_url'],sha256=detail['sha256_hash'],bytes=row['size']))
    assert len(jobs)==42 and sum(r['role']=='final_test' for r in jobs)==7
    plan=DATA/'plan.json'
    if plan.exists(): assert json.loads(plan.read_text(encoding='utf-8'))==jobs
    else: plan.write_text(json.dumps(jobs,indent=2),encoding='utf-8')
    def download(row):
        path=DATA/row['filename']
        assert not (OLD/'raw/uos6204'/row['filename']).exists(),'Previously collected file is not new'
        if not path.exists():
            part=path.with_suffix('.part')
            subprocess.run([CURL,'-fLsS','--retry','3','--max-time','240',row['url'],'-o',str(part)],check=True)
            assert sha(part)==row['sha256']; part.replace(path)
        assert sha(path)==row['sha256']; print('OK',row['filename'],row['role'],flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool: list(pool.map(download,jobs))
    (DATA/'manifest.json').write_text(json.dumps({'files':len(jobs),'bytes':sum(r['bytes'] for r in jobs),'checksums':'all verified',
        'source':'https://data.mendeley.com/datasets/53vtnjy6c6/1','license':'CC-BY-4.0','final_test_opened':False,
        'test_scope':'Seven new fault recordings only; healthy8k records already used, no new healthy holdout. No independent installation IDs.'},indent=2),encoding='utf-8')
if __name__=='__main__': main()
