"""Validate development-source arrays and metadata; never decode reserved target arrays."""
import sys,json,csv,collections,zipfile,argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import vibration.bootstrap
import numpy as np
from vibration.independent_data import IndependentRotorCatalog
from vibration.rotor_features import rotor_features
DATA=ROOT/'data/normal_independent'; META=DATA/'metadata'; META.mkdir(parents=True,exist_ok=True)


def cross():
    catalog=IndependentRotorCatalog(DATA); rows=catalog.rows(); by_role=collections.Counter(r['role'] for r in rows)
    sets={role:{r['group_id'] for r in rows if r['role']==role} for role in by_role}
    assert not sets['source_train']&sets['source_validation'] and not sets['source_train']&sets['reserved_target_test'] and not sets['source_validation']&sets['reserved_target_test']
    hashes={role:{r['signal_sha256'] for r in rows if r['role']==role} for role in by_role}
    assert not hashes['source_train']&hashes['source_validation'] and not hashes['source_train']&hashes['reserved_target_test'] and not hashes['source_validation']&hashes['reserved_target_test']
    targets=catalog.rows(role='reserved_target_test'); audit=META/'reserved_access.jsonl'
    history=audit.read_text(encoding='utf-8').splitlines() if audit.exists() else []
    try: catalog.load(targets[0]['id'])
    except PermissionError: pass
    else: raise AssertionError('Reserved target load must fail.')
    assert (audit.read_text(encoding='utf-8').splitlines() if audit.exists() else [])==history
    sources=[r for r in rows if r['role']!='reserved_target_test']; checked=0; first={}; normal=collections.Counter(); rms={}
    def one(row):
        a,meta=catalog.load(row['id']); return row,meta,np.sqrt(np.mean((a-a.mean(axis=0))**2,axis=0))
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(one,row) for row in sources]):
            row,meta,ac=future.result(); checked+=1
            if row['condition']=='normal':
                normal[str(meta['rpm'])]+=1; rms.setdefault(str(meta['rpm']),[]).append(ac)
                first.setdefault(str(meta['rpm']),row['id'])
            if checked%500==0: print('source MAT validated',checked,'/',len(sources),flush=True)
    (DATA/'ready').mkdir(exist_ok=True)
    for speed,record_id in first.items():
        a,meta=catalog.load(record_id); f=rotor_features(a,25600,meta['rpm'],channel_names=meta['channel_names'])
        np.savez_compressed(DATA/f'ready/cross_speed_normal_{speed}_example.npz',vibration=a,sample_rate_hz=25600,rpm=meta['rpm'],unit=np.asarray('unknown'),channel_names=np.asarray(meta['channel_names']),acquisition_id=meta['acquisition_id'])
        assert len(f.names)==156 and np.isfinite(f.values).all()
    result={'status':'pass','source_arrays_validated':checked,'all_source_shapes':[25600,4],'source_acquisitions':{k:len(v) for k,v in sets.items() if k!='reserved_target_test'},
        'normal_source_windows_by_rpm':dict(normal),'normal_source_acquisitions':len({r['group_id'] for r in sources if r['condition']=='normal'}),
        'source_normal_median_AC_RMS_raw_units':{speed:np.median(values,axis=0).tolist() for speed,values in rms.items()},
        'roles':dict(by_role),'reserved_target_acquisitions':len(sets['reserved_target_test']),
        'reserved_target_normal_windows':len([r for r in targets if r['condition']=='normal']),
        'reserved_arrays_decoded':bool(history),'reserved_numeric_arrays_read_in_this_collection_validation':False,
        'reserved_prior_access_log_entries':len(history),'reserved_access_blocked_without_explicit_model_hash':True,'cross_role_duplicate_signal_hashes':0,
        'source_labels_are_metadata_only':True,'amplitude_unit':'unknown; do not apply absolute ISO thresholds',
        'split':'provider MS_600_900_to_1200 fold 0, acquisition-disjoint',
        'scope':'Collection + numerical integrity, not external model accuracy.'}
    (META/'cross_speed_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)


def marra():
    catalog=IndependentRotorCatalog(DATA); rows=catalog.marra_members(); by_archive=collections.defaultdict(list)
    for row in rows: by_archive[row['archive']].append(row['member'])
    assert len(by_archive)==6 and all(len(members)==200 for members in by_archive.values()),{k:len(v) for k,v in by_archive.items()}
    samples=[]
    for archive,members in sorted(by_archive.items()):
        # Sort and inspect one acquisition in each frequency directory, not adjacent windows.
        folders={}
        for member in sorted(members): folders.setdefault(str(Path(member).parent),member)
        candidates=list(folders.values())
        if len(candidates)==1: candidates=[sorted(members)[i] for i in (0,50,100,150)]
        for member in candidates:
            a,meta=catalog.load_marra(archive,member)
            f=rotor_features(a,6000,meta['rpm'],channel_names=meta['channel_names'])
            samples.append({'archive':archive,'member':member,'shape':list(a.shape),'rpm_from_trigger':meta['rpm'],
                'trigger_jitter_ratio':meta['trigger_jitter_ratio'],'features':len(f.names),'reference_label':meta['reference_label']})
            if archive=='Baseline.zip':
                np.savez_compressed(DATA/f'ready/marra_normal_{round(meta["rpm"])}rpm_example.npz',vibration=a,sample_rate_hz=6000,rpm=meta['rpm'],unit=np.asarray('unknown'),channel_names=np.asarray(meta['channel_names']))
        print('LVM samples validated',archive,len(candidates),flush=True)
    result={'status':'pass','records_inventory':len(rows),'normal_records':len(by_archive['Baseline.zip']),
            'per_archive':{key:len(value) for key,value in by_archive.items()},'waveform_QA':'frequency-directory samples only; provider checksums and ZIP CRC cover full archives',
            'sampled_arrays_validated':len(samples),'samples':samples,'unit':'unknown; raw acceleration scale not calibrated here',
            'independence':'Separate apparatus from Brito; reassembly/acquisition independence not fully documented by provider.'}
    (META/'marra_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS Marra collection and representative waveform/trigger validation',flush=True)


def marra_normal():
    catalog=IndependentRotorCatalog(DATA); rows=[r for r in catalog.marra_members() if r['archive']=='Baseline.zip']
    checked=[]; failed=[]
    def one(row):
        a,meta=catalog.load_marra(row['archive'],row['member'])
        return {'member':row['member'],'samples':len(a),'rpm':meta['rpm'],'trigger_jitter_ratio':meta['trigger_jitter_ratio']}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(one,row):row for row in rows}
        for future in as_completed(futures):
            try: checked.append(future.result())
            except Exception as error: failed.append({'member':futures[future]['member'],'reason':str(error)})
            if (len(checked)+len(failed))%50==0: print('normal LVM validated',len(checked),'failures',len(failed),flush=True)
    report={'status':'pass' if len(checked)==200 and not failed else 'review','normal_records':len(rows),'normal_arrays_validated':len(checked),
            'failed':failed,'shape':[36000,4],'sample_rate_hz':6000,'records':checked,
            'scope':'All normal raw acceleration arrays and optical-trigger stationarity; no field normality certificate.'}
    (META/'marra_normal_full_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Normal Marra full check:',report['status'],len(checked),'/',len(rows),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('dataset',choices=('cross','marra','marra_normal')); args=parser.parse_args()
    {'cross':cross,'marra':marra,'marra_normal':marra_normal}[args.dataset]()
