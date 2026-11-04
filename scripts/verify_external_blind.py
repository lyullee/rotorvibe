"""One prospective test-only transfer evaluation. No fitting or data adaptation."""
import sys,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import vibration.bootstrap
import numpy as np
from scipy.io import loadmat
from vibration import ConditionedDiagnostic
from vibration.fault_discrimination import fault_features
from vibration.conditioned import canonical_values
from vibration.rotor_features import rotor_features
from scripts.collect_external_blind import DATA,OUT,sha,write
from scripts.external_blind_metrics import shadow_gate,shadow_fault,summarize

def read(path): return json.loads(path.read_text(encoding='utf-8'))
def now(): return datetime.now(timezone.utc).isoformat()

def check_frozen():
    p=read(OUT/'protocol.json')
    assert sha(DATA/'plan.json')==p['plan_sha256']
    assert all(sha(ROOT/k)==v for k,v in p['code_sha256'].items())
    assert all(sha(OUT/k)==v for k,v in p['model_sha256'].items())
    return p

def prepare():
    if (OUT/'access.jsonl').exists() or (OUT/'evaluation_freeze.json').exists(): raise RuntimeError('Evaluation already frozen/opened')
    check_frozen(); manifest=read(DATA/'manifest.json'); plan=read(DATA/'plan.json')
    assert {r['id'] for r in manifest}=={r['id'] for r in plan} and len(manifest)==43
    prior=read(ROOT/'output/fault_discrimination/final_protocol.json')['source_raw_sha256']
    prior.update(read(ROOT/'output/fault_discrimination/final_results.json')['raw_signal_sha256'])
    files=[Path(__file__),ROOT/'scripts/external_blind_metrics.py',ROOT/'scripts/collect_external_blind.py']
    write(OUT/'evaluation_freeze.json',dict(utc=now(),protocol_sha256=sha(OUT/'protocol.json'),manifest_sha256=sha(DATA/'manifest.json'),
        code_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in files},prior_raw_sha256=prior,normal_arrays_opened=0,new_fault_arrays_opened=0,
        shadow_selection='All predeclared scenarios are reported, no best-scenario selection; no resizing of trained normal speed scope.'))
    print('FROZEN evaluator and complete43-file manifest; no arrays opened')

def aggregate(items):
    result={}
    for rig in sorted({r['rig'] for r in items}):
        by=[r for r in items if r['rig']==rig]; keys=sorted(set.intersection(*[set(r['evaluations']) for r in by]))
        result[rig]={key:summarize([dict(r,**{key:r['evaluations'][key]}) for r in by],key) for key in keys}
    return result

def run():
    if (OUT/'access.jsonl').exists() or (OUT/'results.json').exists(): raise RuntimeError('Already opened; no overwrite/re-tuning')
    p=check_frozen(); e=read(OUT/'evaluation_freeze.json')
    assert sha(OUT/'protocol.json')==e['protocol_sha256']; assert sha(DATA/'manifest.json')==e['manifest_sha256']
    assert all(sha(ROOT/k)==v for k,v in e['code_sha256'].items())
    manifest={r['id']:r for r in read(DATA/'manifest.json')}; normal=read(OUT/'normal_gate_frozen.json'); fault=read(OUT/'fault_frozen.json'); gate=ConditionedDiagnostic(normal)
    plan=read(DATA/'plan.json'); items=[]; rawhash={}
    write(OUT/'execution.json',dict(status='running',utc=now(),model_sha256=p['model_sha256']))
    with (OUT/'access.jsonl').open('x',encoding='utf-8') as ledger,(OUT/'predictions.jsonl').open('x',encoding='utf-8') as stream:
        for row in plan:
            path=DATA/row['path']; assert sha(path)==manifest[row['id']]['local_sha256']
            ledger.write(json.dumps(dict(id=row['id'],utc=now(),role='test_only',model_sha256=p['model_sha256']))+'\n'); ledger.flush()
            if row['format']=='mat':
                a=loadmat(path,variable_names=['Data'])['Data'].ravel(); assert len(a)==1280000
            else:
                a=np.loadtxt(path,delimiter=',',usecols=(row['column'],)); assert len(a)==250000
            assert np.isfinite(a).all()
            digest=hashlib.sha256(np.asarray(a,dtype='<f8').tobytes()).hexdigest()
            assert digest not in e['prior_raw_sha256'].values() and digest not in rawhash.values(),'Duplicate prior/new recording'
            rawhash[row['id']]=digest; fs=row['fs']; size=fs*2
            for start in range(0,len(a)-size+1,size):
                block=a[start:start+size]; scope=dict(asset_id=row['asset_id'],condition_id='external_untouched_test',unit=row['unit'])
                actual=gate.analyze(block,fs,row['rpm'],scope=scope,channel_names=[row['channel']])
                evaluations={'strict_api':actual}
                factors=[1.] if row['unit']=='g' else [1.,10.]
                for factor in factors:
                    x=block*factor; common=canonical_values(x,fs,4000)
                    rotor=rotor_features(common,4000,row['rpm'],channel_names=['radial_vibration'])
                    assert list(rotor.names)==normal['feature_names']
                    normal_result=shadow_gate(rotor.values,row['rpm'],normal)
                    names,features=fault_features(x,fs,row['rpm']); assert list(names)==fault['names']
                    type_result=shadow_fault(features,row['rpm'],fault)
                    key='shadow_physical_g' if row['unit']=='g' else f'shadow_native_factor_{factor:g}_unit_unverified'
                    evaluations[key]=type_result if normal_result.get('anomaly') is True else normal_result
                    evaluations[key+'_gate']=normal_result
                    # Conditional fault-subtype head does NOT classify healthy state; only record it for actual fault labels.
                    if row['label']!='normal': evaluations[key+'_type_given_fault']=type_result
                item=dict(recording=row['id'],rig=row['rig'],truth=row['label'],start_seconds=start/fs,rpm_nominal=row['rpm'],
                    actual_asset_id=row['asset_id'],actual_channel=row['channel'],actual_unit=row['unit'],evaluations=evaluations,model_sha256=p['model_sha256'])
                stream.write(json.dumps(item,ensure_ascii=False,allow_nan=False)+'\n'); stream.flush(); items.append(item)
            print('TEST',row['id'],(len(a)//size),'windows',flush=True)
    assert len(rawhash)==43 and len(items)==580
    # Aggregate head-only fault results separately because healthy samples must not enter that metric.
    metrics=aggregate(items); conditional={}
    for rig in sorted({i['rig'] for i in items}):
        subset=[i for i in items if i['rig']==rig and i['truth']!='normal']
        keys=sorted(set.intersection(*[set(i['evaluations']) for i in subset]))
        conditional[rig]={key:summarize([dict(i,**{key:i['evaluations'][key]}) for i in subset],key) for key in keys if key.endswith('_type_given_fault')}
    check_frozen(); assert all(sha(ROOT/k)==v for k,v in e['code_sha256'].items())
    report=dict(status='complete',test_only=True,model_sha256=p['model_sha256'],new_original_recordings=43,new_windows=580,
        raw_signal_sha256=rawhash,by_domain=metrics,conditional_fault_head=conditional,training_or_tuning_on_new_data=False,
        interpretation='Strict API all holds is lack of supported-domain coverage, NOT demonstrated zero false-alarm performance. Shadow bypass is offline numerical stress, not production validation.',
        mafaulda_unit_warning='Native CSV amplitude unit not explicit on official page. Both fixed scenarios are exploratory sensitivity checks, not calibrated physical FPR claims.',
        no_independent_looseness_on_ufrj=True,operational_use=False)
    write(OUT/'results.json',report); write(OUT/'execution.json',dict(status='complete',finished_utc=now(),results_sha256=sha(OUT/'results.json'),
        predictions_sha256=sha(OUT/'predictions.jsonl'),no_fit_tune_calibration=True,no_model_or_inference_code_change=True))
    for rig,values in metrics.items():
        for key,r in values.items():
            if key.endswith('_gate'): continue
            print(rig,key,'normal',r['normal_false_anomalies'],'/',r['normal_windows'],'normal decided',r['normal_decision_windows'],'fault correct',r['fault_type_correct'],'/',r['fault_windows'],flush=True)
    for rig,values in conditional.items():
        for key,r in values.items(): print(rig,key,r['fault_type_correct'],'/',r['fault_windows'],flush=True)

def audit():
    p=check_frozen(); e=read(OUT/'evaluation_freeze.json'); report=read(OUT/'results.json'); execution=read(OUT/'execution.json')
    assert execution['status']=='complete'; assert sha(OUT/'results.json')==execution['results_sha256']; assert sha(OUT/'predictions.jsonl')==execution['predictions_sha256']
    assert sha(OUT/'protocol.json')==e['protocol_sha256'] and sha(DATA/'manifest.json')==e['manifest_sha256']
    assert all(sha(ROOT/k)==v for k,v in e['code_sha256'].items())
    items=[json.loads(s) for s in (OUT/'predictions.jsonl').read_text(encoding='utf-8').splitlines()]
    access=[json.loads(s) for s in (OUT/'access.jsonl').read_text(encoding='utf-8').splitlines()]; plan=read(DATA/'plan.json')
    assert len(access)==43 and len({r['id'] for r in access})==43 and {r['id'] for r in access}=={r['id'] for r in plan}
    assert all(r['model_sha256']==p['model_sha256'] for r in access+items)
    assert len(items)==580 and len({(r['recording'],r['start_seconds']) for r in items})==580
    for row in plan:
        expected=set(range(0,80,2)) if row['format']=='mat' else {0,2}
        assert {r['start_seconds'] for r in items if r['recording']==row['id']}==expected
    assert aggregate(items)==report['by_domain']
    for rig,metrics in report['conditional_fault_head'].items():
        subset=[i for i in items if i['rig']==rig and i['truth']!='normal']
        for key,r in metrics.items(): assert summarize([dict(i,**{key:i['evaluations'][key]}) for i in subset],key)==r
    assert not set(report['raw_signal_sha256'].values())&set(e['prior_raw_sha256'].values())
    assert len(set(report['raw_signal_sha256'].values()))==43
    assert not report['training_or_tuning_on_new_data']
    write(OUT/'audit.json',dict(status='pass',frozen_models_and_inference_code_unchanged=True,test_only_original_recordings=43,windows=580,
        access_rows=43,no_exact_prior_or_target_duplicates=True,metrics_recount_match=True,no_new_fit_tune_calibration=True,no_test_reopening=True,operational_use=False))
    print('PASS independent recount,43 original-file accesses,580 unique windows,frozen inference/models,no target adaptation')

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('phase',choices=['prepare','test','audit']); args=parser.parse_args()
    {'prepare':prepare,'test':run,'audit':audit}[args.phase]()
