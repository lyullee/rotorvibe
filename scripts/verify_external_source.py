"""Fixed two-stage recipe on source acquisitions; never read 1200RPM arrays here.

Models are adapted to the new apparatus using its own normal/source training
records. This is acquisition holdout validation, not zero-shot machine transfer.
"""
import sys,json,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import vibration.bootstrap
import numpy as np
from vibration.independent_data import IndependentRotorCatalog,CROSS_CHANNELS
from vibration.rotor_features import rotor_features
from vibration.two_stage import fit_two_stage,TwoStageDiagnostic
OUT=ROOT/'output/two_stage'; DATA=ROOT/'data/normal_independent'


def extract(catalog,rows,role):
    path=OUT/f'cross_speed_{role}_features.npz'
    if path.exists():
        with np.load(path,allow_pickle=False) as z: return {k:z[k] for k in z.files}
    def one(row):
        a,meta=catalog.load(row['id']); f=rotor_features(a,25600,meta['rpm'],channel_names=meta['channel_names'])
        return f.values,meta['reference_label'],meta['group_id'],meta['rpm'],row['id'],f.names
    with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(one,rows))
    d={'x':np.vstack([r[0] for r in results]),'y':np.asarray([r[1] for r in results]),'groups':np.asarray([r[2] for r in results]),
       'rpm':np.asarray([r[3] for r in results]),'ids':np.asarray([r[4] for r in results]),'names':np.asarray(results[0][5])}
    np.savez_compressed(path,**d); return d


def main():
    OUT.mkdir(parents=True,exist_ok=True); catalog=IndependentRotorCatalog(DATA)
    train=extract(catalog,catalog.rows(role='source_train'),'train'); profiles={}; metadata={}
    # Recipe chosen on exposed Brito data, held constant for both source speeds.
    for rpm in (600,900):
        speed=train['rpm']==rpm; normal=speed&(train['y']=='normal'); normal_groups=sorted(set(train['groups'][normal].tolist()))
        calibration_groups=normal_groups[-2:]; calibration=normal&np.isin(train['groups'],calibration_groups); fit=normal&~calibration
        faults=speed&(train['y']!='normal')
        scope={'asset_id':'CrossSpeed2026Bench','condition_id':f'speed_{rpm}','unit':'unknown','channel_names':list(CROSS_CHANNELS),
               'sample_rate_hz':25600,'window_samples':25600,'rpm_range':[rpm*.95,rpm*1.05]}
        p=fit_two_stage(train['x'][fit],train['groups'][fit],train['x'][calibration],train['groups'][calibration],
            train['x'][faults],train['y'][faults],train['groups'][faults],feature_names=train['names'].tolist(),scope=scope,mode='relative')
        raw=json.dumps(p,ensure_ascii=False,sort_keys=True).encode(); (OUT/f'cross_speed_{rpm}_frozen.json').write_bytes(raw)
        profiles[rpm]=TwoStageDiagnostic(p); metadata[str(rpm)]={'sha256':hashlib.sha256(raw).hexdigest(),
            'normal_reference_acquisitions':len(set(train['groups'][fit])),'normal_calibration_acquisitions':len(calibration_groups),
            'normal_reference_windows':int(fit.sum()),'normal_calibration_windows':int(calibration.sum()),'fault_training_windows':int(faults.sum())}
    # No validation features enter normal fitting, calibration or fault fitting.
    validation=extract(catalog,catalog.rows(role='source_validation'),'validation')
    assert not set(train['groups'])&set(validation['groups']) and not set(train['ids'])&set(validation['ids'])
    guesses=[]; statuses=[]; truth=[]; per={}
    for row in catalog.rows(role='source_validation'):
        # Raw-array API is the production entry point, not a test-only classifier.
        a,meta=catalog.load(row['id']); model=profiles[meta['rpm']]
        result=model.analyze(a,25600,meta['rpm'],scope=meta,channel_names=CROSS_CHANNELS)
        guesses.append(result['label']); statuses.append(result['status']); truth.append(meta['reference_label'])
        entry=per.setdefault(meta['group_id'],{'truth':meta['reference_label'],'windows':0,'statuses':{},'correct':0})
        entry['windows']+=1; entry['correct']+=int(result['label']==meta['reference_label']); entry['statuses'][result['status']]=entry['statuses'].get(result['status'],0)+1
    y=np.asarray(truth); guesses=np.asarray(guesses,dtype=object); statuses=np.asarray(statuses); normal=y=='normal'; faults=~normal
    anomaly=np.isin(statuses,['fault_candidate','anomaly_unknown']); decisive=np.isin(statuses,['normal','fault_candidate'])
    report={'protocol':'New apparatus, own source training + normal calibration; provider acquisition-disjoint source_validation. Fixed relative feature recipe, not tuned on these predictions.',
        'profiles':metadata,'validation_windows':len(y),'validation_acquisitions':len(per),'normal_windows':int(normal.sum()),'fault_windows':int(faults.sum()),
        'normal_false_alarm_rate':float(anomaly[normal].mean()),'normal_acceptance_rate':float(np.mean(statuses[normal]=='normal')),
        'normal_hold_rate':float(np.mean(statuses[normal]=='hold')),'fault_detection_rate':float(anomaly[faults].mean()),
        'fault_miss_as_normal_rate':float(np.mean(statuses[faults]=='normal')),'fault_hold_rate':float(np.mean(statuses[faults]=='hold')),
        'correct_fault_type_rate_all_faults':float(np.mean(guesses[faults]==y[faults])),
        'overall_label_accuracy_holds_wrong':float(np.mean(guesses==y)),'decision_coverage':float(decisive.mean()),
        'conditional_decision_accuracy':float(np.mean(guesses[decisive]==y[decisive])) if decisive.any() else None,
        'status_counts':{s:int(np.sum(statuses==s)) for s in sorted(set(statuses.tolist()))},'per_acquisition':per,
        'reserved_1200rpm_arrays_opened':(DATA/'metadata/reserved_access.jsonl').exists(),
        'reserved_1200rpm_used_in_this_source_validation':False,'operational_use':False,
        'normal_calibration_caution':'Only two acquisitions per speed; window thresholds are not independent field guarantees.'}
    (OUT/'external_source_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='per_acquisition'},ensure_ascii=False),flush=True)

if __name__=='__main__': main()
