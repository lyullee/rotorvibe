"""Prospectively freeze a pooled source-only qualification model, then open 1200RPM.

Existing 600/900 RPM production-domain profiles are never widened or overwritten.
This is a new experimental cross-speed qualification configuration of the same
two-stage API. No target normal observations calibrate its normal reference.
"""
import argparse,hashlib,json,sys,time
from datetime import datetime,timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import vibration.bootstrap
import numpy as np
from vibration.independent_data import IndependentRotorCatalog,CROSS_CHANNELS
from vibration.rotor_features import rotor_features
from vibration.two_stage import fit_two_stage,TwoStageDiagnostic
OUT=ROOT/'output/final_cross_speed'; DATA=ROOT/'data/normal_independent'
CODE=('vibration/rotor_features.py','vibration/two_stage.py','vibration/classifier.py',
      'vibration/independent_data.py','scripts/verify_final_cross_speed.py')


def now(): return datetime.now(timezone.utc).isoformat()
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_text(encoding='utf-8'))
def write(path,value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def physical_scope(meta):
    # This declared operating family pools shaft speed. It never reads fault labels,
    # acquisition identity or filenames to change features, normalization or decisions.
    return {'asset_id':meta['asset_id'],'condition_id':'steady_cross_speed_qualification','unit':meta['unit']}


def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'protocol.json').exists() or (DATA/'metadata/reserved_access.jsonl').exists():
        raise RuntimeError('Protocol already frozen or target already accessed; do not overwrite/tune this experiment.')
    catalog=IndependentRotorCatalog(DATA); rows=catalog.rows(role='source_train'); targets=catalog.rows(role='reserved_target_test')
    previous={speed:read(ROOT/f'output/two_stage/cross_speed_{speed}_frozen.json') for speed in (600,900)}
    original_hashes={str(speed):sha(ROOT/f'output/two_stage/cross_speed_{speed}_frozen.json') for speed in previous}
    cal_groups=set(group for p in previous.values() for group in p['normal_calibration_groups'])
    # Exact original source-only group allocation and numerical recipe; no search.
    def one(row):
        a,meta=catalog.load(row['id']); f=rotor_features(a,25600,meta['rpm'],channel_names=CROSS_CHANNELS)
        return f.values,meta['reference_label'],meta['group_id'],meta['rpm'],f.names
    with ThreadPoolExecutor(max_workers=3) as pool: extracted=list(pool.map(one,rows))
    x=np.vstack([v[0] for v in extracted]); y=np.asarray([v[1] for v in extracted]); groups=np.asarray([v[2] for v in extracted])
    speeds=sorted({v[3] for v in extracted}); assert speeds==[600,900]
    normal=y=='normal'; calibration=normal&np.isin(groups,list(cal_groups)); fit=normal&~calibration; faults=~normal
    train_ids={row['id'] for row in rows}; target_ids={row['id'] for row in targets}
    source_groups=set(groups.tolist()); target_groups={row['group_id'] for row in targets}
    assert not train_ids&target_ids and not source_groups&target_groups
    val_rows=catalog.rows(role='source_validation')
    assert not target_groups&{r['group_id'] for r in val_rows}
    assert not {r['signal_sha256'] for r in targets}&{r['signal_sha256'] for r in rows+val_rows}
    scope={'asset_id':'CrossSpeed2026Bench','condition_id':'steady_cross_speed_qualification','unit':'unknown',
        'channel_names':list(CROSS_CHANNELS),'sample_rate_hz':25600,'window_samples':25600,'rpm_range':[570,1260]}
    profile=fit_two_stage(x[fit],groups[fit],x[calibration],groups[calibration],x[faults],y[faults],groups[faults],
        feature_names=extracted[0][4],scope=scope,mode='relative',normal_quantile=.80,anomaly_quantile=.99,min_margin=.10)
    profile.update(name='CrossSpeed source 600+900 to unseen 1200 qualification',training_speeds_rpm=speeds,
        qualification_speed_rpm=1200,scope_status='provisional qualification domain; 1200RPM is not validated before this test',
        evaluation='Source-only pooled normal reference/calibration/fault fit. No target data used. operational_use=False.')
    raw=json.dumps(profile,ensure_ascii=False,sort_keys=True).encode(); (OUT/'frozen_model.json').write_bytes(raw)
    protocol={'frozen_utc':now(),'model_sha256':sha(OUT/'frozen_model.json'),'code_sha256':{p:sha(ROOT/p) for p in CODE},
        'candidate':'new pooled cross-speed qualification profile; existing per-speed models unchanged',
        'existing_profile_sha256':original_hashes,'source_train_windows':len(rows),'normal_fit_windows':int(fit.sum()),
        'normal_calibration_windows':int(calibration.sum()),'normal_calibration_groups':sorted(cal_groups),
        'fault_fit_windows':int(faults.sum()),'observed_training_speeds_rpm':speeds,'test_speed_rpm':1200,
        'target_windows':len(targets),'target_acquisitions':len(target_groups),
        'target_sample_ids_sha256':hashlib.sha256('\n'.join(sorted(target_ids)).encode()).hexdigest(),
        'source_manifest_sha256':sha(DATA/'raw/cross_speed/dataset_manifest.csv'),
        'source_partition_sha256':sha(DATA/'raw/cross_speed/recording_disjoint_partitions.csv'),
        'physical_context_rule':'All records retain actual asset/unit/layout/fs/RPM; condition_id maps to declared steady cross-speed family without reading fault labels.',
        'recipe':{'mode':'relative','normal_quantile':.80,'anomaly_quantile':.99,'min_margin':.10,'variance_floor':.25},
        'acceptance':'Exploratory qualification; no user-specified operational acceptance thresholds. Report all holds/errors as non-correct.',
        'metrics':['normal false alarms + normal holds','fault detection + missed-as-normal + fault holds',
                   'fault type accuracy','overall accuracy with abstentions wrong','decision coverage + conditional accuracy',
                   'macro F1','acquisition majority and any-false-alarm rates'],
        'no_target_normal_adaptation':True,'operational_use':False,'status':'frozen_before_target_numeric_access'}
    write(OUT/'protocol.json',protocol)
    print('FROZEN',protocol['model_sha256'],'source train',len(rows),'target arrays not opened',flush=True)


def metrics(records):
    truth=np.asarray([r['truth'] for r in records]); labels=np.asarray([r['prediction'].get('label') for r in records],dtype=object)
    status=np.asarray([r['prediction']['status'] for r in records]); normal=truth=='normal'; fault=~normal
    anomaly=np.isin(status,['fault_candidate','anomaly_unknown']); decisive=np.isin(status,['normal','fault_candidate'])
    per={}; confusion={}; f1=[]; classes=('normal','misalignment','unbalance')
    for row in records:
        p=row['prediction']; guessed=p.get('label') or p['status']; label=row['truth']; group=row['group_id']
        confusion.setdefault(label,{}).setdefault(guessed,0); confusion[label][guessed]+=1
        entry=per.setdefault(group,{'truth':label,'windows':0,'correct':0,'predictions':{},'anomaly_windows':0})
        assert entry['truth']==label
        entry['windows']+=1; entry['correct']+=int(p.get('label')==label); entry['anomaly_windows']+=int(p['status'] in ('fault_candidate','anomaly_unknown'))
        entry['predictions'][guessed]=entry['predictions'].get(guessed,0)+1
    for entry in per.values():
        maximum=max(entry['predictions'].values()); winners=[key for key,n in entry['predictions'].items() if n==maximum]
        entry['majority_label']=winners[0] if len(winners)==1 and winners[0] in classes else None
    for label in classes:
        tp=int(np.sum((truth==label)&(labels==label))); fp=int(np.sum((truth!=label)&(labels==label))); fn=int(np.sum((truth==label)&(labels!=label)))
        f1.append(2*tp/max(2*tp+fp+fn,1))
    normal_groups=[r for r in per.values() if r['truth']=='normal']; fault_groups=[r for r in per.values() if r['truth']!='normal']
    return {'windows':len(records),'acquisitions':len(per),'normal_windows':int(normal.sum()),'fault_windows':int(fault.sum()),
        'normal_false_alarm_windows':int(anomaly[normal].sum()),'normal_false_alarm_rate':float(anomaly[normal].mean()),
        'normal_correct_windows':int(np.sum(labels[normal]=='normal')),'normal_hold_windows':int(np.sum(status[normal]=='hold')),
        'normal_acceptance_rate':float(np.mean(status[normal]=='normal')),'normal_hold_rate':float(np.mean(status[normal]=='hold')),
        'fault_detection_windows':int(anomaly[fault].sum()),'fault_detection_rate':float(anomaly[fault].mean()),
        'fault_missed_as_normal_windows':int(np.sum(status[fault]=='normal')),'fault_hold_windows':int(np.sum(status[fault]=='hold')),
        'correct_fault_type_windows':int(np.sum(labels[fault]==truth[fault])),'correct_fault_type_rate_all_faults':float(np.mean(labels[fault]==truth[fault])),
        'correct_windows':int(np.sum(labels==truth)),'overall_accuracy_holds_wrong':float(np.mean(labels==truth)),
        'decision_coverage':float(decisive.mean()),'conditional_decision_accuracy':float(np.mean(labels[decisive]==truth[decisive])) if decisive.any() else None,
        'macro_f1':float(np.mean(f1)),'status_counts':{s:int(np.sum(status==s)) for s in sorted(set(status.tolist()))},
        'confusion':confusion,'acquisition_majority_correct':sum(r['majority_label']==r['truth'] for r in per.values()),
        'normal_acquisitions':len(normal_groups),'normal_acquisitions_any_false_alarm':sum(r['anomaly_windows']>0 for r in normal_groups),
        'fault_acquisitions':len(fault_groups),'fault_acquisitions_no_detections':sum(r['anomaly_windows']==0 for r in fault_groups),
        'per_acquisition':per,'error_windows':sum(r['prediction']['status']=='quality_hold' for r in records)}


def run():
    protocol=read(OUT/'protocol.json'); model_path=OUT/'frozen_model.json'; fingerprint=sha(model_path)
    if fingerprint!=protocol['model_sha256'] or any(sha(ROOT/path)!=value for path,value in protocol['code_sha256'].items()):
        raise RuntimeError('Frozen model or inference/evaluation code changed; refusing test access.')
    if (OUT/'final_test.json').exists() or (OUT/'target_predictions.jsonl').exists():
        raise RuntimeError('Final test has already been opened. Preserve results; do not tune or overwrite it.')
    for speed,value in protocol['existing_profile_sha256'].items(): assert sha(ROOT/f'output/two_stage/cross_speed_{speed}_frozen.json')==value
    model=TwoStageDiagnostic(read(model_path)); catalog=IndependentRotorCatalog(DATA); started=time.perf_counter()
    execution={'started_utc':now(),'model_sha256':fingerprint,'protocol_sha256':sha(OUT/'protocol.json'),'status':'running',
               'target_was_untouched_before_this_run':not (DATA/'metadata/reserved_access.jsonl').exists()}
    if not execution['target_was_untouched_before_this_run']: raise RuntimeError('Target was previously opened outside this protocol.')
    write(OUT/'execution.json',execution)
    summaries={}
    for role,name in (('source_validation','source_validation'),('reserved_target_test','target')):
        rows=catalog.rows(role=role); records=[]
        with (OUT/f'{name}_predictions.jsonl').open('x',encoding='utf-8') as stream:
            for index,row in enumerate(rows):
                a,meta=catalog.load(row['id'],frozen_model_sha256=fingerprint if role=='reserved_target_test' else None)
                try:
                    prediction=model.analyze(a,meta['sample_rate_hz'],meta['rpm'],scope=physical_scope(meta),channel_names=meta['channel_names'])
                except ValueError as error:
                    prediction={'status':'quality_hold','label':None,'reason':str(error),'operational_use':False}
                entry={'sample_id':row['id'],'group_id':meta['group_id'],'rpm':meta['rpm'],'truth':meta['reference_label'],
                    'prediction':prediction,'model_sha256':fingerprint}
                stream.write(json.dumps(entry,ensure_ascii=False,allow_nan=False)+'\n'); stream.flush(); records.append(entry)
                if (index+1)%200==0: print(name,index+1,'/',len(rows),flush=True)
        summaries[name]=metrics(records)
    report={'model_sha256':fingerprint,'protocol_sha256':sha(OUT/'protocol.json'),'model_kind':protocol['candidate'],
        'source_validation':summaries['source_validation'],'target_1200rpm':summaries['target'],
        'strict_existing_profile_1200_coverage':'Neither prior per-speed scope supports 1200RPM; both would hold. They were not widened.',
        'no_target_training_or_calibration':True,'no_target_tuning':True,'operational_use':False,
        'elapsed_seconds':time.perf_counter()-started,
        'scope':'First numerical opening of 1200RPM after prospective source-only freeze. Different speed on the same CrossSpeed apparatus, not unseen field machinery.'}
    assert sha(model_path)==fingerprint
    write(OUT/'final_test.json',report)
    execution.update(status='complete',finished_utc=now(),target_arrays_opened=summaries['target']['windows'],
        results_sha256=sha(OUT/'final_test.json'),target_predictions_sha256=sha(OUT/'target_predictions.jsonl'))
    write(OUT/'execution.json',execution); write(DATA/'metadata/final_test_execution.json',execution)
    print(json.dumps({k:v for k,v in summaries['target'].items() if k!='per_acquisition'},ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('phase',choices=('prepare','test')); args=parser.parse_args()
    prepare() if args.phase=='prepare' else run()
