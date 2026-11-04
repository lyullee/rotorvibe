"""Download licensed primary datasets, verify checksums, preserve target-speed holdout."""
import json,hashlib,subprocess,time,zipfile,shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[1]/'data/normal_independent'
CURL=shutil.which('curl') or 'curl'


def metadata(url,name):
    path=ROOT/'sources'/name; path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        subprocess.run([CURL,'-fLsS','--retry','2','--max-time','60','-o',str(path),url],check=True)
    return json.loads(path.read_text(encoding='utf-8'))


def discover():
    metadata('https://zenodo.org/api/records/14388093','marra_record.json')
    folders=metadata('https://data.mendeley.com/public-api/datasets/y8mv28hjwb/folders/1','cross_speed_folders.json')
    outer=next(row for row in folders if row['name']=='SRO-Cross-Speed-Dataset')
    inner=next(row for row in folders if row['name']=='data' and row.get('parent_id')==outer['id'])
    for folder,name in ((outer,'cross_speed_rootfiles.json'),(inner,'cross_speed_archives.json')):
        metadata(f'https://data.mendeley.com/public-api/datasets/y8mv28hjwb/files?folder_id={folder["id"]}&version=1',name)


def field_template():
    template={'purpose':'Collect actual-machine confirmed normal references, separate normal calibration and untouched field tests.',
        'required_fields':['asset_id','acquisition_id','start_time_UTC','role','condition_id','rpm_or_tachometer','load',
            'sample_rate_hz','window_samples','channel_names_and_axes','unit','sensor_model_and_serial',
            'calibration_id_and_sensitivity','sensor_installation_id','mounting_method','normal_condition_confirmation'],
        'roles':['normal_reference_fit','normal_threshold_calibration','independent_field_test'],
        'rules':['Keep all windows from one acquisition in one role.','Use independently confirmed healthy operation, never model-generated normal labels.',
            'Include relevant different starts/days/installations and log speed/load.','Freeze features, normal thresholds, model and alarm policy before opening field tests.',
            'Report false alarms, missed faults, wrong fault types and abstentions together.'],
        'public_data_limits':'Public normal signals do not certify the intended machine, sensor calibration or mounting.'}
    (ROOT/'metadata/field_normal_collection_template.json').write_text(json.dumps(template,ensure_ascii=False,indent=2),encoding='utf-8')


def digest(path,algorithm='sha256'):
    h=hashlib.new(algorithm)
    with path.open('rb') as f:
        while block:=f.read(1024*1024): h.update(block)
    return h.hexdigest()


def download(job):
    result=dict(job); path=ROOT/job['path']; path.parent.mkdir(parents=True,exist_ok=True)
    try:
        expected=job['checksum'].split(':',1)
        if not path.exists() or digest(path,expected[0])!=expected[1]:
            part=path.with_suffix(path.suffix+'.part')
            command=[CURL,'-fLsS','--retry','2','--connect-timeout','20','--max-time','120','--speed-limit','1024','--speed-time','30']
            if job['dataset']=='Marra2024':
                # The archive server serves bounded range requests promptly; whole responses stall.
                size=job['provider_bytes']; chunk=1024*1024; segment=part.with_suffix('.segment')
                start=part.stat().st_size if part.exists() else 0
                with part.open('ab') as stream:
                    for offset in range(start,size,chunk):
                        end=min(offset+chunk,size)-1
                        subprocess.run(command+['--range',f'{offset}-{end}','-o',str(segment),job['url']],check=True)
                        block=segment.read_bytes()
                        if len(block)!=end-offset+1: raise ValueError('Range response size differs.')
                        stream.write(block); stream.flush()
                        if (offset-start)//chunk%40==0: print('PROGRESS',path.name,end+1,'/',size,flush=True)
            else:
                subprocess.run(command+['-o',str(part),job['url']],check=True)
            if digest(part,expected[0])!=expected[1]: raise ValueError('Provider checksum mismatch')
            part.replace(path)
            if job['dataset']=='Marra2024': segment.unlink(missing_ok=True)
        result.update(status='downloaded',bytes=path.stat().st_size,sha256=digest(path))
        if path.suffix=='.zip':
            with zipfile.ZipFile(path) as archive:
                # Inventory/header and CRC only. Reserved MATLAB arrays are not decoded or scored.
                bad=archive.testzip()
                if bad: raise ValueError('ZIP CRC failure')
                result['archive_members']=len([p for p in archive.namelist() if not p.endswith('/')])
                if job['role']!='reserved_target_test':
                    result['member_examples']=archive.namelist()[:5]
        print('OK',job['path'],result['bytes'],job['role'],flush=True)
    except Exception as error:
        result.update(status='failed',error=str(error)); print('FAILED',job['path'],str(error),flush=True)
    return result


def main():
    (ROOT/'metadata').mkdir(parents=True,exist_ok=True); discover(); field_template(); jobs=[]
    z=json.loads((ROOT/'sources/marra_record.json').read_text(encoding='utf-8'))
    if z['metadata'].get('license',{}).get('id')!='cc-by-4.0': raise ValueError('Unexpected primary-source license; review metadata.')
    for file in z['files']:
        jobs.append(dict(dataset='Marra2024',doi='10.5281/zenodo.14388093',license='CC-BY-4.0',
            path='raw/marra/'+file['key'],url='https://zenodo.org/records/14388093/files/'+file['key']+'?download=1',checksum=file['checksum'],provider_bytes=file['size'],
            role='development_reference',source='https://zenodo.org/records/14388093'))
    for name in ('cross_speed_rootfiles.json','cross_speed_archives.json'):
        for file in json.loads((ROOT/'sources'/name).read_text(encoding='utf-8')):
            info=file['content_details']; filename=file['filename']
            role='reserved_target_test' if '1200rpm.zip' in filename else ('development_source' if filename.endswith('.zip') else 'protocol_metadata')
            jobs.append(dict(dataset='CrossSpeed2026',doi='10.17632/y8mv28hjwb.1',license='CC-BY-4.0',
                path='raw/cross_speed/'+filename,url=info['download_url'],checksum='sha256:'+info['sha256_hash'],
                role=role,source='https://data.mendeley.com/datasets/y8mv28hjwb/1'))
    jobs.sort(key=lambda job: (job['dataset']=='Marra2024',job['path']))
    (ROOT/'metadata/download_plan.json').write_text(json.dumps(jobs,ensure_ascii=False,indent=2),encoding='utf-8')
    protocol={'created':'2026-11-04','development':['Brito existing 20 trials (all previously exposed)','Marra2024 (new independent source for development/reference)',
        'CrossSpeed2026 600/900 RPM source domains; follow acquisition-disjoint provider partitions'],
        'reserved_test':'CrossSpeed2026 all 1200 RPM archives; no feature decoding, normalization, fitting, parameter selection or scoring in this collection step',
        'normal_calibration':'Only known-normal source/calibration recordings; never infer normality from target-test labels.',
        'independence':'CrossSpeed is a different apparatus/provider from Brito. Adjacent seconds share original_file and must remain grouped.',
        'limits':'Public lab data do not replace calibration/normal baselines on the intended field machine. No looseness class in CrossSpeed.'}
    (ROOT/'metadata/reserved_test_protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8')
    results=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for future in as_completed([pool.submit(download,job) for job in jobs]):
            results.append(future.result())
            (ROOT/'metadata/download_manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(r['status']=='downloaded' for r in results),'Some downloads failed; inspect manifest.'
    print('COMPLETE',len(results),sum(r['bytes'] for r in results),flush=True)

if __name__=='__main__': main()
