"""Prospective new-file fault-only holdout; no tuning or overwrite after opening."""
import sys,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import vibration.bootstrap
import numpy as np
from scipy.io import loadmat
from vibration import ConditionedDiagnostic
from vibration.fault_discrimination import FaultDiscriminator
from scripts.develop_fault_discrimination import DATA,OLD,OUT,SCOPE,rows,load,write,sha
from scripts.check_uos_overlap import overlap

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def now(): return datetime.now(timezone.utc).isoformat()
def rawsha(a): return hashlib.sha256(np.asarray(a,dtype='<f8').tobytes()).hexdigest()

def summary(items,key):
    classes=['looseness','misalignment','unbalance']; conf={c:{p:0 for p in classes+['unknown','normal','hold']} for c in classes}; per={}
    for r in items:
        p=r[key]; label=p['label'] or ('unknown' if p['status']=='anomaly_unknown' else 'hold')
        conf[r['truth']][label]+=1
        row=per.setdefault(r['recording'],dict(truth=r['truth'],windows=0,correct=0,predictions={}))
        row['windows']+=1; row['correct']+=int(label==r['truth']); row['predictions'][label]=row['predictions'].get(label,0)+1
    for row in per.values():
        best=max(row['predictions'].values()); winners=[c for c,v in row['predictions'].items() if v==best]
        row['plurality_correct']=len(winners)==1 and winners[0]==row['truth']
    f1=[]
    for c in classes:
        tp=conf[c][c]; fn=sum(conf[c].values())-tp; fp=sum(conf[o][c] for o in classes if o!=c); f1.append(2*tp/max(1,2*tp+fp+fn))
    return dict(windows=len(items),recordings=len(per),correct=sum(conf[c][c] for c in classes),accuracy=sum(conf[c][c] for c in classes)/len(items),macro_f1=float(np.mean(f1)),
        confusion=conf,per_recording=per,recording_plurality_correct=sum(r['plurality_correct'] for r in per.values()),
        abstentions=sum(conf[c]['unknown']+conf[c]['hold'] for c in classes))

def diagnose():
    old=read(ROOT/'output/condition_improvement/matched_frozen.json'); olditems=[json.loads(s) for s in (ROOT/'output/condition_improvement/new_final_predictions.jsonl').read_text(encoding='utf-8').splitlines()]
    result={}
    for row in olditems:
        if row['truth']=='normal': continue
        p=row['prediction']; matches=p.get('relative_matches',[])
        if not matches: continue
        winner=min(matches,key=lambda m:m['distance']); limit=old['class_limits'][old['classes'].index(winner['label'])]
        entry=result.setdefault(row['recording_id'],dict(truth=row['truth'],windows=0,rejected=0,nearest_class_correct_without_rejection=0,nearest_distance=[],nearest_limit=[]))
        entry['windows']+=1; entry['rejected']+=int(p['status']=='anomaly_unknown'); entry['nearest_class_correct_without_rejection']+=int(winner['label']==row['truth'])
        entry['nearest_distance'].append(winner['distance']); entry['nearest_limit'].append(limit)
    for r in result.values():
        r['median_nearest_distance']=float(np.median(r.pop('nearest_distance'))); r['median_nearest_class_limit']=float(np.median(r.pop('nearest_limit')))
    write(OUT/'previous_failure_diagnosis.json',dict(previous_opened_test_is_now_development=True,selected_features=len(old['selected_indices']),
        selected_names=[old['feature_names'][i] for i in old['selected_indices']],per_recording=result,
        limitations='Distance and margin identify model failure mechanisms, not a uniquely identified physical root cause. No shaft phase/axial channels available.'))

def prepare():
    if (OUT/'final_protocol.json').exists() or (OUT/'final_access.jsonl').exists(): raise RuntimeError('Experiment already frozen/opened')
    d=read(OUT/'development.json'); assert d['new_final_used'] is False
    assert sha(OUT/'candidate.json')==d['model_sha256']
    assert d['selected']['macro_f1']>=.5,'Development gate: not better than chance-like subtype behavior'
    source=rows(); sourcehash={r['filename']:rawsha(load(r)) for r in source}
    target=[r for r in read(DATA/'plan.json') if r['role']=='final_test']; assert len(target)==7
    assert not set(sourcehash)&{r['filename'] for r in target}
    assert len(set(sourcehash.values()))==len(sourcehash),'Duplicate source raw recording'
    (OUT/'frozen.json').write_bytes((OUT/'candidate.json').read_bytes())
    (OUT/'baseline_frozen.json').write_bytes((ROOT/'output/condition_improvement/matched_frozen.json').read_bytes())
    code=list((ROOT/'vibration').rglob('*.py'))+[Path(__file__),ROOT/'scripts/check_uos_overlap.py']
    protocol=dict(frozen_utc=now(),model_sha256=sha(OUT/'frozen.json'),baseline_sha256=sha(OUT/'baseline_frozen.json'),
        code_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in code},plan_sha256=sha(DATA/'plan.json'),source_raw_sha256=sourcehash,
        target_files=[r['filename'] for r in target],new_fault_recordings=7,new_fault_windows=560,normal_test_recordings=0,
        comparison='Paired old baseline vs new gated type head on identical new fault windows; abstentions/misses count wrong.',
        fit_scope='Same apparatus, same severities, both source rates, including previously exposed16k1200. New8k1200 faults excluded from all training/tuning.',
        independence='Original-file/sample-rate holdout, not independent reassembly or field rig. Exact raw and high-frequency-noise overlap screen against matched16k sources, cutoff0.98.',
        selection='12 candidates, whole-speed1000/1400 validation with BOTH rates held at each speed, mean macroF1. Final refit all77 fault source files.',
        no_final_test_adaptation=True,operational_use=False)
    write(OUT/'final_protocol.json',protocol); print('FROZEN',protocol['model_sha256'],flush=True)

def run():
    if (OUT/'final_access.jsonl').exists() or (OUT/'final_results.json').exists(): raise RuntimeError('Already opened; no overwrite/re-tuning')
    p=read(OUT/'final_protocol.json'); assert sha(OUT/'frozen.json')==p['model_sha256'] and sha(OUT/'baseline_frozen.json')==p['baseline_sha256']
    assert sha(DATA/'plan.json')==p['plan_sha256']; assert all(sha(ROOT/k)==v for k,v in p['code_sha256'].items())
    model=FaultDiscriminator(read(OUT/'frozen.json')); baseline=ConditionedDiagnostic(read(OUT/'baseline_frozen.json'))
    targets=[r for r in read(DATA/'plan.json') if r['role']=='final_test']; items=[]; rawhash={}; overlaps={}
    write(OUT/'execution.json',dict(status='running',started_utc=now(),model_sha256=p['model_sha256']))
    with (OUT/'final_access.jsonl').open('x',encoding='utf-8') as ledger, (OUT/'final_predictions.jsonl').open('x',encoding='utf-8') as predictions:
        for row in targets:
            path=DATA/row['filename']; assert sha(path)==row['sha256']
            ledger.write(json.dumps(dict(recording=row['filename'],utc=now(),model_sha256=p['model_sha256']))+'\n'); ledger.flush()
            a=loadmat(path,variable_names=['Data'])['Data'].ravel(); assert len(a)==1280000 and np.isfinite(a).all()
            digest=rawsha(a); assert digest not in p['source_raw_sha256'].values() and digest not in rawhash.values(); rawhash[row['filename']]=digest
            paired=row['filename'].replace('_8_6204_','_16_6204_'); b=loadmat(OLD/'raw/uos6204'/paired,variable_names=['Data'])['Data'].ravel()
            overlaps[row['filename']]=overlap(a,b)
            assert overlaps[row['filename']]['passes_nonduplicate_screen'],'Possible acquisition overlap: stop and invalidate independence'
            for start in range(0,len(a),16000):
                block=a[start:start+16000]; gate=baseline.analyze(block,8000,1200,scope=SCOPE,channel_names=['radial_vibration'])
                subtype=model.analyze(block,8000,1200,scope=SCOPE)
                gated=subtype if gate.get('anomaly') is True else gate
                item=dict(recording=row['filename'],start_seconds=start/8000,truth=row['label'],baseline=gate,new_type_given_fault=subtype,new_gated=gated,model_sha256=p['model_sha256'])
                predictions.write(json.dumps(item,ensure_ascii=False,allow_nan=False)+'\n'); predictions.flush(); items.append(item)
            print('TEST',row['filename'],sum(r['new_gated']['label']==r['truth'] for r in items if r['recording']==row['filename']),'/80',flush=True)
    assert len(items)==560 and len(rawhash)==7
    report=dict(model_sha256=p['model_sha256'],baseline=summary(items,'baseline'),new_type_given_fault=summary(items,'new_type_given_fault'),new_gated=summary(items,'new_gated'),
        paired_correctness=dict(both_correct=sum(r['baseline']['label']==r['truth'] and r['new_gated']['label']==r['truth'] for r in items),
            corrected=sum(r['baseline']['label']!=r['truth'] and r['new_gated']['label']==r['truth'] for r in items),
            regressed=sum(r['baseline']['label']==r['truth'] and r['new_gated']['label']!=r['truth'] for r in items)),
        raw_signal_sha256=rawhash,alternate_rate_noise_overlap=overlaps,normal_test_recordings=0,no_post_test_tuning=True,operational_use=False,
        limits=['Seven fault acquisitions only, one looseness and three severity acquisitions per other class; windows correlated.',
            'Same apparatus, original-file/sample-rate holdout with matched source severities; independent reassembly not established.',
            'No fresh normal test: cannot claim a new overall four-class accuracy or normal false-alarm rate.'])
    assert all(sha(ROOT/k)==v for k,v in p['code_sha256'].items()); assert sha(OUT/'frozen.json')==p['model_sha256']
    write(OUT/'final_results.json',report); write(OUT/'execution.json',dict(status='complete',finished_utc=now(),model_sha256=p['model_sha256'],results_sha256=sha(OUT/'final_results.json'),predictions_sha256=sha(OUT/'final_predictions.jsonl'),no_post_test_tuning=True))
    print('FINAL',report['baseline']['accuracy'],report['new_gated']['accuracy'],report['new_type_given_fault']['accuracy'],flush=True)

def audit():
    p=read(OUT/'final_protocol.json'); r=read(OUT/'final_results.json'); execution=read(OUT/'execution.json')
    assert execution['status']=='complete'; assert sha(OUT/'frozen.json')==p['model_sha256']; assert sha(OUT/'baseline_frozen.json')==p['baseline_sha256']
    assert all(sha(ROOT/k)==v for k,v in p['code_sha256'].items()); assert sha(DATA/'plan.json')==p['plan_sha256']
    assert sha(OUT/'final_results.json')==execution['results_sha256']; assert sha(OUT/'final_predictions.jsonl')==execution['predictions_sha256']
    items=[json.loads(s) for s in (OUT/'final_predictions.jsonl').read_text(encoding='utf-8').splitlines()]
    access=[json.loads(s) for s in (OUT/'final_access.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(access)==7 and {a['recording'] for a in access}==set(p['target_files']) and all(a['model_sha256']==p['model_sha256'] for a in access)
    assert len(items)==560 and len({(i['recording'],i['start_seconds']) for i in items})==560
    assert {i['recording'] for i in items}==set(p['target_files'])
    for filename in p['target_files']: assert {i['start_seconds'] for i in items if i['recording']==filename}==set(range(0,160,2))
    for key in ('baseline','new_type_given_fault','new_gated'): assert summary(items,key)==r[key]
    assert all(x['passes_nonduplicate_screen'] for x in r['alternate_rate_noise_overlap'].values())
    assert not set(r['raw_signal_sha256'].values())&set(p['source_raw_sha256'].values())
    write(OUT/'audit.json',dict(status='pass',frozen_model_code_plan_unchanged=True,original_recordings=7,windows=560,access_rows=7,
        metrics_recount_match=True,no_exact_or_screened_noise_duplicates=True,no_test_reopening=True,no_post_test_tuning=True,operational_use=False))
    print('PASS audit:7 untouched original files,560 nonoverlap windows, paired results, frozen hashes')

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('phase',choices=['diagnose','prepare','test','audit']); args=parser.parse_args()
    {'diagnose':diagnose,'prepare':prepare,'test':run,'audit':audit}[args.phase]()
