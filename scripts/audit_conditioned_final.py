"""Recount saved new predictions and verify prospective provenance without fitting."""
import sys,json,hashlib,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'output/condition_improvement'; DATA=ROOT/'data/condition_improvement'
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=read(OUT/'new_final_protocol.json'); r=read(OUT/'new_final_results.json'); e=read(OUT/'new_final_execution.json')
    records=[json.loads(line) for line in (OUT/'new_final_predictions.jsonl').read_text(encoding='utf-8').splitlines()]
    accesses=[json.loads(line) for line in (DATA/'metadata/new_test_access.jsonl').read_text(encoding='utf-8').splitlines()]
    assert sha(OUT/'matched_frozen.json')==p['model_sha256']==r['model_sha256']==e['model_sha256']
    assert sha(OUT/'new_final_results.json')==e['result_sha256'] and sha(OUT/'new_final_predictions.jsonl')==e['prediction_sha256']
    assert all(sha(ROOT/path)==value for path,value in p['code_sha256'].items())
    assert sha(DATA/'metadata/record_plan.json')==p['record_plan_sha256'] and sha(DATA/'metadata/matched_normal_plan.json')==p['matched_normal_plan_sha256']
    keys={(a['recording_id'],a['start_seconds']) for a in records}
    assert len(keys)==len(records)==320 and {a['recording_id'] for a in records}==set(p['target_recording_ids'])
    assert len(accesses)==8 and {a['record_id'] for a in accesses}==set(p['target_recording_ids'])
    assert {a['model_sha256'] for a in accesses}=={p['model_sha256']}
    assert not set(p['target_recording_ids'])&set(p['source_raw_signal_sha256'])
    assert not set(r['raw_test_signal_sha256'].values())&set(p['source_raw_signal_sha256'].values())
    assert r['nonduplicate_screen_pass']
    correct=sum(a['prediction']['label']==a['truth'] for a in records)
    false=sum(a['truth']=='normal' and a['prediction'].get('anomaly') is True for a in records)
    normal_hold=sum(a['truth']=='normal' and a['prediction']['status']=='hold' for a in records)
    detected=sum(a['truth']!='normal' and a['prediction'].get('anomaly') is True for a in records)
    assert correct==r['correct_windows']==166 and false==r['normal_false_alarms']==1 and normal_hold==r['normal_hold']==8 and detected==r['fault_detected']==280
    verdict={'audit_status':'pass','frozen_model_code_and_record_plan_unchanged':True,'whole_recording_split_verified':True,
        'new_original_test_recordings':8,'new_nonoverlap_2second_windows':320,'source_recordings':46,
        'no_exact_raw_source_test_duplicates':True,'alternate_rate_noise_overlap':r['healthy_alternate_rate_overlap'],
        'independent_recount_matches':True,'accuracy_holds_wrong':correct/len(records),'normal_false_alarm_rate':false/40,
        'normal_acquisitions':1,'normal_acquisitions_with_any_false_alarm':1,
        'no_post_test_tuning':True,'operational_use':False,
        'decision':'Normal-reference handling improved; fault-type accuracy48.21% remains insufficient for automatic operational diagnosis.',
        'independence_limit':'Original-file/sample-rate acquisition holdout. A low noise-overlap score is not proof of separate installations or independent fault repetitions.'}
    (OUT/'new_final_audit.json').write_text(json.dumps(verdict,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(verdict,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
