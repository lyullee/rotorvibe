"""Read-only provenance, independent counts and post-test distribution diagnostics.

Reads saved predictions/metadata only. Does not re-open signals, fit parameters,
change thresholds or tune against target outcomes.
"""
import hashlib,json,sys,statistics,collections,zipfile
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import vibration.bootstrap
import numpy as np
from vibration.independent_data import IndependentRotorCatalog
OUT=ROOT/'output/final_cross_speed'; DATA=ROOT/'data/normal_independent'


def read(path): return json.loads(path.read_text(encoding='utf-8'))
def lines(path): return [json.loads(row) for row in path.read_text(encoding='utf-8').splitlines()]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=read(OUT/'protocol.json'); report=read(OUT/'final_test.json'); execution=read(OUT/'execution.json')
    model=read(OUT/'frozen_model.json'); predictions=lines(OUT/'target_predictions.jsonl'); source=lines(OUT/'source_validation_predictions.jsonl')
    catalog=IndependentRotorCatalog(DATA); rows=catalog.rows(role='reserved_target_test'); audit=lines(DATA/'metadata/reserved_access.jsonl')
    expected_ids={r['id'] for r in rows}; observed={r['sample_id'] for r in predictions}
    assert len(predictions)==len(observed)==len(expected_ids)==1178 and observed==expected_ids
    assert len(audit)==1178 and {r['record_id'] for r in audit}==expected_ids
    assert {r['frozen_model_sha256'] for r in audit}=={p['model_sha256']}
    assert sha(OUT/'frozen_model.json')==p['model_sha256']==report['model_sha256']
    assert sha(OUT/'protocol.json')==execution['protocol_sha256']==report['protocol_sha256']
    assert sha(OUT/'final_test.json')==execution['results_sha256']
    assert sha(OUT/'target_predictions.jsonl')==execution['target_predictions_sha256']
    assert all(sha(ROOT/path)==value for path,value in p['code_sha256'].items())
    assert all(sha(ROOT/f'output/two_stage/cross_speed_{speed}_frozen.json')==value for speed,value in p['existing_profile_sha256'].items())
    assert sha(DATA/'raw/cross_speed/dataset_manifest.csv')==p['source_manifest_sha256']
    assert sha(DATA/'raw/cross_speed/recording_disjoint_partitions.csv')==p['source_partition_sha256']
    evidence=read(OUT/'pretest_package_evidence.json'); package=read(OUT/'pretest_package_smoke.json')
    assert sha(OUT/'pretest_runtime_wheel.whl')==evidence['sha256']==package['sha256']
    assert datetime.fromisoformat(evidence['original_artifact_mtime_utc'])<datetime.fromisoformat(p['frozen_utc'])
    with zipfile.ZipFile(OUT/'pretest_runtime_wheel.whl') as wheel:
        assert hashlib.sha256(wheel.read('vibration/dsp.py')).hexdigest()==sha(ROOT/'vibration/dsp.py')
    source_ids={r['id'] for role in ('source_train','source_validation') for r in catalog.rows(role=role)}
    source_groups={r['group_id'] for role in ('source_train','source_validation') for r in catalog.rows(role=role)}
    assert not expected_ids&source_ids and not {r['group_id'] for r in rows}&source_groups
    assert {r['group_id'] for r in predictions}=={r['group_id'] for r in rows}
    for entry in predictions:
        primary=catalog.records[entry['sample_id']]; truth={'imbalance':'unbalance'}.get(primary['condition'],primary['condition'])
        assert entry['truth']==truth and entry['group_id']==primary['group_id'] and entry['model_sha256']==p['model_sha256']
    correct=sum(r['prediction'].get('label')==r['truth'] for r in predictions)
    normal=[r for r in predictions if r['truth']=='normal']; fault=[r for r in predictions if r['truth']!='normal']
    false=sum(r['prediction'].get('anomaly') is True for r in normal)
    anomaly=sum(r['prediction'].get('anomaly') is True for r in fault)
    counts=collections.Counter(r['prediction']['status'] for r in predictions)
    assert correct==report['target_1200rpm']['correct_windows']==130
    assert false==report['target_1200rpm']['normal_false_alarm_windows']==399
    assert anomaly==report['target_1200rpm']['fault_detection_windows']==779
    assert dict(counts)==report['target_1200rpm']['status_counts']
    source_normal=[r['prediction']['normal_score'] for r in source if r['truth']=='normal']
    target_normal=[r['prediction']['normal_score'] for r in normal]
    limits=dict(zip(model['fault_model']['classes'],model['fault_model']['distance_limits']))
    distance_reject=0; margin_reject=0; both=0; features=collections.Counter()
    for entry in predictions:
        prediction=entry['prediction']
        if entry['truth']=='normal': features.update(r['feature'] for r in prediction.get('deviations',[]))
        if prediction['status']=='anomaly_unknown':
            nearest=min(prediction['relative_matches'],key=lambda r:r['negative_log_density_per_feature'])
            d=nearest['distance']>limits[nearest['label']]; m=prediction['fault_margin']<model['min_fault_margin']
            distance_reject+=int(d); margin_reject+=int(m); both+=int(d and m)
    def stats(values): return {'min':min(values),'median':statistics.median(values),'p95':float(np.quantile(values,.95)),'max':max(values)}
    result={'audit_status':'pass','predictive_qualification':'failed','all_1178_predictions_accounted_for':True,
        'independent_recount_matches':True,'source_target_record_and_acquisition_overlap':False,
        'frozen_model_code_manifest_checksums_unchanged':True,'original_per_speed_profiles_unchanged':True,
        'DSP_matches_verified_pretest_package':True,'pretest_package_sha256':evidence['sha256'],
        'target_records_read_once':True,'normal_accept_limit':model['normal_accept_limit'],'anomaly_limit':model['anomaly_limit'],
        'source_validation_normal_scores':stats(source_normal),'target_1200_normal_scores':stats(target_normal),
        'unknown_diagnosis_rejections':{'distance_limit':distance_reject,'small_margin':margin_reject,'both':both,'total':counts['anomaly_unknown']},
        'normal_top5_deviation_feature_occurrences':features.most_common(10),
        'interpretation':'All target normal scores exceed the fixed normal anomaly limit. Relative/order features did not remove speed-domain shift. This does not identify a unique physical cause.',
        'policy':'Do not deploy pooled cross-speed candidate or tune/retest on this opened target. Per-speed models remain scoped to 600/900RPM; new acquisition normal references and a fresh final split are needed.',
        'operational_use':False}
    (OUT/'audit_and_diagnosis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
