"""Freeze improved matched-condition model, then score whole untouched UOS files.

1200RPM healthy8kHz is an explicitly declared reference. The eight16kHz/1200
original files are excluded from all fitting, normalization and candidate choice.
This tests new recordings with a calibrated normal reference, NOT zero-shot speed.
"""
import sys,json,hashlib,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import vibration.bootstrap
import numpy as np
from vibration import ConditionedDiagnostic
from vibration.condition_data import UosRotorCatalog
from scripts.check_uos_overlap import overlap
OUT=ROOT/'output/condition_improvement'; DATA=ROOT/'data/condition_improvement'


def read(path): return json.loads(path.read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,obj): path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def now(): return datetime.now(timezone.utc).isoformat()
def raw_sha(a): return hashlib.sha256(np.asarray(a,dtype='<f8').tobytes()).hexdigest()


def prepare():
    if (DATA/'metadata/new_test_access.jsonl').exists() or (OUT/'new_final_protocol.json').exists(): raise RuntimeError('New test already opened or protocol frozen; no overwrite.')
    development=read(OUT/'matched_development.json'); assert development['source_sanity_gate_pass']
    candidate=OUT/'matched_candidate.json'; assert sha(candidate)==development['candidate_sha256']
    assert all(r['passes_nonduplicate_screen'] for r in read(DATA/'metadata/source_sampling_overlap_check.json').values())
    catalog=UosRotorCatalog(DATA); sources=[r for r in catalog.rows() if r['role']!='reserved_new_test']; targets=catalog.rows('reserved_new_test')
    assert len(sources)==46 and len(targets)==8
    source_ids={r['recording_id'] for r in sources}; assert not source_ids&{r['recording_id'] for r in targets}
    hashes={}
    for row in sources:
        a,meta=catalog.load(row['id']); digest=raw_sha(a)
        if digest in hashes.values(): raise ValueError('Duplicate raw source recordings; review independent groups.')
        hashes[row['id']]=digest
    (OUT/'matched_frozen.json').write_bytes(candidate.read_bytes())
    code_files=list((ROOT/'vibration').rglob('*.py'))+[ROOT/'scripts/verify_conditioned_final.py',ROOT/'scripts/check_uos_overlap.py']
    protocol={'frozen_utc':now(),'model_sha256':sha(OUT/'matched_frozen.json'),'source_selection_sha256':sha(OUT/'matched_development.json'),
        'code_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in code_files},
        'record_plan_sha256':sha(DATA/'metadata/record_plan.json'),'matched_normal_plan_sha256':sha(DATA/'metadata/matched_normal_plan.json'),
        'source_recordings':len(sources),'source_raw_signal_sha256':hashes,
        'target_recording_ids':sorted(r['id'] for r in targets),'target_recordings':8,'target_windows':320,
        'raw_test_sampling_hz':16000,'raw_window_seconds':2,'canonical_analysis_hz':4000,
        'training_normal_reference':'Six8kHz healthy acquisitions including1200RPM, plus four16kHz non-test healthy acquisitions.',
        'normal_calibration':'16kHz800RPM healthy acquisition only; no16kHz1200 normal adaptation.',
        'source_validation_for_selection':'Entire16kHz1000RPM recordings; already development data; not the new final test.',
        'qualification_scope':'New original-recording/sample-rate holdout at matched nominalRPM, not an unobserved-speed or uncalibrated-machine claim.',
        'independence_condition':'No raw duplicates; compare healthy1200 sampling-domain noise overlap against fixed0.98 screen. No claim of independent reassembly.',
        'target_never_used_for_fit_or_tuning':True,'operational_use':False}
    write(OUT/'new_final_protocol.json',protocol)
    print('FROZEN',protocol['model_sha256'],'46source recordings; eight new test files still closed',flush=True)


def run():
    protocol=read(OUT/'new_final_protocol.json'); model_path=OUT/'matched_frozen.json'
    if (OUT/'new_final_results.json').exists() or (OUT/'new_final_predictions.jsonl').exists(): raise RuntimeError('Final experiment already opened; do not overwrite or tune.')
    if (DATA/'metadata/new_test_access.jsonl').exists(): raise RuntimeError('Unexpected prior access to the new final records.')
    assert sha(model_path)==protocol['model_sha256']
    assert all(sha(ROOT/path)==value for path,value in protocol['code_sha256'].items())
    assert sha(DATA/'metadata/record_plan.json')==protocol['record_plan_sha256']
    assert sha(DATA/'metadata/matched_normal_plan.json')==protocol['matched_normal_plan_sha256']
    model=ConditionedDiagnostic(read(model_path)); catalog=UosRotorCatalog(DATA); records=[]; per={}; overlap_result=None; data_hashes={}
    started=time.perf_counter(); write(OUT/'new_final_execution.json',{'started_utc':now(),'model_sha256':protocol['model_sha256'],'status':'running'})
    with (OUT/'new_final_predictions.jsonl').open('x',encoding='utf-8') as stream:
        for row in catalog.rows('reserved_new_test'):
            a,meta=catalog.load(row['id'],frozen_model_sha256=protocol['model_sha256']); digest=raw_sha(a)
            if digest in protocol['source_raw_signal_sha256'].values() or digest in data_hashes.values(): raise ValueError('New test raw recording duplicates a source/other test record.')
            data_hashes[row['id']]=digest
            if meta['reference_label']=='normal':
                reference,_=catalog.load('uos:H_H_8_6204_1200.mat'); overlap_result=overlap(reference,a)
            truth=meta['reference_label']; entry={'truth':truth,'windows':0,'correct':0,'predictions':{},'anomaly_windows':0}
            for start in range(0,len(a)-32000+1,32000):
                result=model.analyze(a[start:start+32000],16000,1200,scope=meta,channel_names=meta['channel_names'])
                item={'recording_id':row['id'],'start_seconds':start/16000,'truth':truth,'prediction':result,'model_sha256':protocol['model_sha256']}
                stream.write(json.dumps(item,ensure_ascii=False,allow_nan=False)+'\n'); stream.flush(); records.append(item)
                guessed=result['label'] or result['status']; entry['windows']+=1; entry['correct']+=int(result['label']==truth)
                entry['predictions'][guessed]=entry['predictions'].get(guessed,0)+1; entry['anomaly_windows']+=int(result.get('anomaly') is True)
            per[row['id']]=entry
            print('new final',row['filename'],entry['correct'],'/',entry['windows'],entry['predictions'],flush=True)
    assert len(records)==320 and len(per)==8
    truth=np.asarray([r['truth'] for r in records]); labels=np.asarray([r['prediction']['label'] for r in records],dtype=object); status=np.asarray([r['prediction']['status'] for r in records])
    normal=truth=='normal'; fault=~normal; anomaly=np.isin(status,['fault_candidate','anomaly_unknown']); decisive=np.isin(status,['normal','fault_candidate'])
    confusion={}; f1=[]
    for label in sorted(set(truth.tolist())):
        confusion[label]={}
        for item in records:
            if item['truth']==label:
                guess=item['prediction']['label'] or item['prediction']['status']; confusion[label][guess]=confusion[label].get(guess,0)+1
        tp=np.sum((truth==label)&(labels==label)); fp=np.sum((truth!=label)&(labels==label)); fn=np.sum((truth==label)&(labels!=label)); f1.append(float(2*tp/max(2*tp+fp+fn,1)))
    for entry in per.values():
        maximum=max(entry['predictions'].values()); winners=[k for k,v in entry['predictions'].items() if v==maximum]
        entry['majority_label']=winners[0] if len(winners)==1 and winners[0] in set(truth) else None
    independent=bool(overlap_result and overlap_result['passes_nonduplicate_screen'])
    report={'model_sha256':protocol['model_sha256'],'protocol_sha256':sha(OUT/'new_final_protocol.json'),
        'new_recordings':8,'new_windows':320,'normal_windows':int(normal.sum()),'fault_windows':int(fault.sum()),
        'normal_correct':int(np.sum(labels[normal]=='normal')),'normal_false_alarms':int(anomaly[normal].sum()),'normal_false_alarm_rate':float(anomaly[normal].mean()),
        'normal_hold':int(np.sum(status[normal]=='hold')),'fault_detected':int(anomaly[fault].sum()),'fault_detection_rate':float(anomaly[fault].mean()),
        'fault_missed_as_normal':int(np.sum(status[fault]=='normal')),'fault_hold':int(np.sum(status[fault]=='hold')),
        'fault_type_correct':int(np.sum(labels[fault]==truth[fault])),'fault_type_accuracy_all_fault_windows':float(np.mean(labels[fault]==truth[fault])),
        'correct_windows':int(np.sum(labels==truth)),'accuracy_holds_wrong':float(np.mean(labels==truth)),
        'decision_coverage':float(decisive.mean()),'conditional_accuracy':float(np.mean(labels[decisive]==truth[decisive])) if decisive.any() else None,'macro_f1':float(np.mean(f1)),
        'recording_majority_correct':sum(e['majority_label']==e['truth'] for e in per.values()),'per_recording':per,'confusion':confusion,
        'healthy_alternate_rate_overlap':overlap_result,'nonduplicate_screen_pass':independent,'raw_test_signal_sha256':data_hashes,
        'target_normal_used_for_fitting':False,'target_used_for_model_selection':False,'no_post_test_tuning':True,
        'qualification_scope':protocol['qualification_scope'],'limitations':['Only eight original test recordings, including ONE healthy acquisition.',
            'Provider says collected at two rates; noise-overlap screen is not proof of independent reassembly.','Same apparatus with own normal reference; not field-machine transfer.'],
        'operational_use':False,'elapsed_seconds':time.perf_counter()-started}
    assert sha(model_path)==protocol['model_sha256']
    write(OUT/'new_final_results.json',report)
    execution={'finished_utc':now(),'status':'complete' if independent else 'independence_screen_failed',
        'model_sha256':protocol['model_sha256'],'result_sha256':sha(OUT/'new_final_results.json'),'prediction_sha256':sha(OUT/'new_final_predictions.jsonl'),
        'new_test_arrays_opened':8,'new_windows':320,'no_post_test_tuning':True}
    write(OUT/'new_final_execution.json',execution); write(DATA/'metadata/new_final_execution.json',execution)
    print(json.dumps({k:v for k,v in report.items() if k not in ('per_recording','raw_test_signal_sha256')},ensure_ascii=False),flush=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('phase',choices=('prepare','test')); args=parser.parse_args()
    prepare() if args.phase=='prepare' else run()
