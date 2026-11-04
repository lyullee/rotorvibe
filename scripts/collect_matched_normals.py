"""Additional physically matched-RPM healthy acquisitions from the primary 8kHz domain.

These are declared source references, never the reserved 16kHz/1200 recordings.
Provider paper: DOI 10.1016/j.dib.2024.110940. Original-file independence must be
audited against alternate-rate overlap; do not assume independent installations.
"""
import sys,json,re,subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
from collect_condition_data import ROOT as DATA,get_json,sha,CURL


def main():
    folders=get_json('https://data.mendeley.com/public-api/datasets/53vtnjy6c6/folders/1','uos_folders.json')
    rate=next(f for f in folders if f['name']=='SamplingRate_8000'); jobs=[]
    for folder in folders:
        if folder.get('parent_id')!=rate['id']: continue
        rpm=int(folder['name'].split('_')[-1]); files=get_json(f'https://data.mendeley.com/public-api/datasets/53vtnjy6c6/files?folder_id={folder["id"]}&version=1',f'uos_8k_{rpm}_files.json')
        row=next(r for r in files if r['filename']==f'H_H_8_6204_{rpm}.mat'); detail=row['content_details']
        jobs.append({'id':'uos:'+row['filename'],'filename':row['filename'],'path':'raw/uos6204/'+row['filename'],
            'rpm':rpm,'sample_rate_hz':8000,'unit':'g','bearing':'MOCHU 6204','condition':'H','reference_label':'normal',
            'role':'matched_normal_reference','recording_id':row['filename'],'provider_sha256':detail['sha256_hash'],'provider_bytes':row['size'],
            'url':detail['download_url'],'source':'https://data.mendeley.com/datasets/53vtnjy6c6/1','doi':'10.17632/53vtnjy6c6.1','license':'CC-BY-4.0'})
    path=DATA/'metadata/matched_normal_plan.json'
    path.write_text(json.dumps(jobs,ensure_ascii=False,indent=2),encoding='utf-8')
    def download(job):
        p=DATA/job['path']; result=dict(job)
        if not p.exists() or sha(p)!=job['provider_sha256']:
            part=p.with_suffix('.mat.part'); subprocess.run([CURL,'-fLsS','--retry','2','--max-time','180',job['url'],'-o',str(part)],check=True)
            if sha(part)!=job['provider_sha256']: raise ValueError('Checksum mismatch')
            part.replace(p)
        result.update(status='downloaded',sha256=sha(p),bytes=p.stat().st_size)
        print('OK matched normal',job['filename'],flush=True); return result
    with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(download,jobs))
    (DATA/'metadata/matched_normal_manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    protocol=json.loads((DATA/'metadata/new_test_protocol.json').read_text(encoding='utf-8'))
    (DATA/'metadata/initial_interpolation_protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8')
    protocol.update(source_normal_addition='Six 8kHz/160s healthy original files, 600..1600RPM, matched-RPM reference only',
        common_analysis_sampling_hz=4000,independence_audit='Original MAT file grouping; check resampled/noise overlap before reporting. Provider does not identify reassembly sessions.',
        new_test_unchanged='All eight 16kHz/1200RPM files stay closed; no test-window or test-normal fitting.')
    (DATA/'metadata/new_test_protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8')
    print('COMPLETE six additional normal files',sum(r['bytes'] for r in results),flush=True)

if __name__=='__main__': main()
