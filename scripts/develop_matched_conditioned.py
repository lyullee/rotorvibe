"""Use additional matched-speed healthy records; new16k/1200 files remain closed."""
import sys,json,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import vibration.bootstrap
import numpy as np
from vibration.condition_data import UosRotorCatalog
from vibration.conditioned import canonical_values,fit_conditioned
from vibration.rotor_features import rotor_features
from scripts.develop_conditioned import measure
OUT=ROOT/'output/condition_improvement'; DATA=ROOT/'data/condition_improvement'


def extract(catalog):
    path=OUT/'uos_common_band_source.npz'
    if path.exists():
        with np.load(path,allow_pickle=False) as z: return {k:z[k] for k in z.files}
    rows=[r for r in catalog.rows() if r['role']!='reserved_new_test']
    def one(row):
        a,meta=catalog.load(row['id']); fs=meta['sample_rate_hz']; n=fs*2; vectors=[]
        for start in range(0,len(a)-n+1,n):
            values=canonical_values(a[start:start+n],fs,4000)
            f=rotor_features(values,4000,meta['rpm'],channel_names=meta['channel_names']); vectors.append(f.values)
        print('common band source',row['id'],len(vectors),flush=True)
        return np.vstack(vectors),meta['reference_label'],meta['recording_id'],meta['rpm'],fs,row['id'],f.names
    with ThreadPoolExecutor(max_workers=3) as pool: records=list(pool.map(one,rows))
    d={'x':np.vstack([r[0] for r in records]),'y':np.concatenate([np.repeat(r[1],len(r[0])) for r in records]),
       'groups':np.concatenate([np.repeat(r[2],len(r[0])) for r in records]),'rpm':np.concatenate([np.repeat(r[3],len(r[0])) for r in records]),
       'raw_fs':np.concatenate([np.repeat(r[4],len(r[0])) for r in records]),'ids':np.concatenate([np.repeat(r[5],len(r[0])) for r in records]),
       'names':np.asarray(records[0][6]),'channels':np.asarray(['radial_vibration'])}
    assert len(set(d['ids']))==46 and not any('H_H_16_6204_1200' in s for s in d['ids'])
    np.savez_compressed(path,**d); return d


def fit(d,reference,calibration,faults,scope,mode,margin):
    p=fit_conditioned(d['x'][reference],d['rpm'][reference],d['groups'][reference],
        d['x'][calibration],d['rpm'][calibration],d['groups'][calibration],d['x'][faults],d['rpm'][faults],d['y'][faults],d['groups'][faults],
        feature_names=d['names'].tolist(),scope=scope,mode=mode,interpolate=False,min_margin=margin)
    p.update(canonical_sample_rate_hz=4000,permitted_input_rates=[4000,8000,16000],source_normal_rates=[8000,16000],
        sampling_note='Anti-aliased common4kHz band before all features; source and target original recordings remain separate.')
    return p


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (DATA/'metadata/new_test_access.jsonl').exists(): raise RuntimeError('Final test already opened; development is closed for this experiment.')
    catalog=UosRotorCatalog(DATA); d=extract(catalog); normal=d['y']=='normal'; fs=d['raw_fs']; rpm=d['rpm']
    scope={'asset_id':'UOS_MOCHU6204','condition_id':'steady_bearing_healthy','unit':'g','channel_names':['radial_vibration'],
        'sample_rate_hz':4000,'window_samples':8000,'rpm_range':[594,1616]}
    reference=(normal&(fs==8000))|(normal&(fs==16000)&np.isin(rpm,[600,1400,1600]))
    calibration=normal&(fs==16000)&(rpm==800); faults=(~normal)&(rpm!=1000); validation=(fs==16000)&(rpm==1000)
    report={'protocol':'Matched-speed normal8kHz original records + declared source16kHz records; source1000 recording validation; final16k1200 closed.',
        'new_test_arrays_used':False,'candidate_count':6,'candidates':[],'source_normal_recordings':11,
        'common_analysis_rate_hz':4000,'new_test_recordings':8,'independence_audit_required':True,
        'source_sanity_gate':'normal FPR <=5%, normal acceptance >=50%, fault detection >=50%, decision coverage >=50%; not a field acceptance standard'}
    for mode in ('relative','orders','levels_orders'):
        for margin in (.1,0.):
            p=fit(d,reference,calibration,faults,scope,mode,margin); r=measure(p,d,validation,4000,8000)
            entry={'mode':mode,'margin':margin,'validation':r}; report['candidates'].append(entry)
            print('matched source',mode,margin,r['macro_f1'],r['normal_false_alarm_rate'],r['fault_detection_rate'],r['accuracy_holds_wrong'],flush=True)
    feasible=[r for r in report['candidates'] if r['validation']['normal_false_alarm_rate']<=.05 and r['validation']['normal_acceptance_rate']>=.5 and r['validation']['fault_detection_rate']>=.5 and r['validation']['decision_coverage']>=.5]
    best=max(feasible or report['candidates'],key=lambda r:(r['validation']['macro_f1'],r['validation']['decision_coverage']))
    report['source_sanity_gate_pass']=bool(feasible); report['selected']={k:best[k] for k in ('mode','margin')}
    p=fit(d,normal&~calibration,calibration,~normal,scope,best['mode'],best['margin'])
    raw=json.dumps(p,ensure_ascii=False,sort_keys=True).encode(); (OUT/'matched_candidate.json').write_bytes(raw)
    report['candidate_sha256']=hashlib.sha256(raw).hexdigest()
    (OUT/'matched_development.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    assert not (DATA/'metadata/new_test_access.jsonl').exists()
    print('SOURCE SANITY GATE',bool(feasible),'new test still closed',flush=True)

if __name__=='__main__': main()
