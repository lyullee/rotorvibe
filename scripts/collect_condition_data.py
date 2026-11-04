"""New primary-source UOS records; whole 1200RPM recordings reserved before decoding."""
import hashlib,json,re,shutil,subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[1]/'data/condition_improvement'
CURL=shutil.which('curl') or 'curl'


def get_json(url,name):
    path=ROOT/'sources'/name; path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists(): subprocess.run([CURL,'-fLsS','--retry','2','--max-time','60',url,'-o',str(path)],check=True)
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while b:=f.read(1024*1024): h.update(b)
    return h.hexdigest()


def main():
    (ROOT/'metadata').mkdir(parents=True,exist_ok=True)
    folders=get_json('https://data.mendeley.com/public-api/datasets/53vtnjy6c6/folders/1','uos_folders.json')
    rate=next(f for f in folders if f['name']=='SamplingRate_16000'); jobs=[]
    for folder in folders:
        if folder.get('parent_id')!=rate['id']: continue
        rpm=int(folder['name'].split('_')[-1])
        files=get_json(f'https://data.mendeley.com/public-api/datasets/53vtnjy6c6/files?folder_id={folder["id"]}&version=1',f'uos_{rpm}_files.json')
        for row in files:
            if not re.fullmatch(r'(H|L|M[123]|U[123])_H_16_6204_\d+\.mat',row['filename']): continue
            condition=row['filename'].split('_')[0]; label='normal' if condition=='H' else 'looseness' if condition=='L' else 'misalignment' if condition.startswith('M') else 'unbalance'
            role='reserved_new_test' if rpm==1200 else ('normal_calibration' if rpm==800 and label=='normal' else 'development')
            detail=row['content_details']
            jobs.append({'id':'uos:'+row['filename'],'filename':row['filename'],'path':f'raw/uos6204/{row["filename"]}',
                'rpm':rpm,'sample_rate_hz':16000,'unit':'g','bearing':'MOCHU 6204','condition':condition,'reference_label':label,
                'role':role,'recording_id':row['filename'],'provider_sha256':detail['sha256_hash'],'provider_bytes':row['size'],
                'url':detail['download_url'],'source':'https://data.mendeley.com/datasets/53vtnjy6c6/1','doi':'10.17632/53vtnjy6c6.1','license':'CC-BY-4.0'})
    assert len(jobs)==48 and sum(j['role']=='reserved_new_test' for j in jobs)==8
    plan=ROOT/'metadata/record_plan.json'
    if plan.exists():
        previous=json.loads(plan.read_text(encoding='utf-8'))
        assert [(r['id'],r['role']) for r in previous]==[(r['id'],r['role']) for r in jobs],'Do not change established recording roles.'
    else: plan.write_text(json.dumps(jobs,ensure_ascii=False,indent=2),encoding='utf-8')
    protocol={'source':'UOS subset 1, version 1, 16kHz only; avoid mixing alternate-rate views as independent records',
        'development_speeds':[600,800,1000,1400,1600],'new_final_test_speed':1200,'new_final_test_recordings':8,
        'normal_fit_speeds':[600,1000,1400,1600],'normal_calibration_speed':800,
        'whole_recording_separation':True,'test_arrays_not_decoded_at_collection':True,
        'independence_limit':'Original MAT recording holdout, one recording per condition/speed. Reassembly independence not documented; not field-machine validation.',
        'unit_provenance':'Provider states Data field in g; calibration certificates not provided',
        'no_new_test_tuning':True,'previous_CrossSpeed1200':'Exposed development data only; never advertised as a new blind test again.'}
    (ROOT/'metadata/new_test_protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8')
    def download(job):
        result=dict(job); path=ROOT/job['path']; path.parent.mkdir(parents=True,exist_ok=True)
        try:
            if not path.exists() or sha(path)!=job['provider_sha256']:
                part=path.with_suffix('.mat.part')
                subprocess.run([CURL,'-fLsS','--retry','2','--max-time','180','--connect-timeout','20',job['url'],'-o',str(part)],check=True)
                if sha(part)!=job['provider_sha256']: raise ValueError('Provider checksum mismatch')
                part.replace(path)
            result.update(status='downloaded',bytes=path.stat().st_size,sha256=sha(path))
            print('OK',job['filename'],job['role'],flush=True)
        except Exception as e: result.update(status='failed',error=str(e)); print('FAILED',job['filename'],str(e),flush=True)
        return result
    results=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(download,j) for j in jobs]):
            results.append(future.result())
            (ROOT/'metadata/download_manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(r['status']=='downloaded' for r in results),'Incomplete collection; inspect manifest.'
    print('COMPLETE',len(results),sum(r['bytes'] for r in results),'bytes; test numeric arrays remain closed',flush=True)

if __name__=='__main__': main()
