"""Compare fixed feature ablations on exposed Brito development data only.

New 1200-RPM external test archives are NEVER opened by this script.
"""
import os,sys,json,time,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
OUT=ROOT/'output/two_stage'; OUT.mkdir(parents=True,exist_ok=True)
os.environ['VIBRATION_RUNTIME_HOME']=str(OUT/'runtime')
import vibration.bootstrap
import numpy as np
from vibration import VibrationAnalyzer,SignalBlock,AnalysisConfig,TwoStageStage
from vibration.rotor_features import rotor_features,RotorFeatures
from vibration.two_stage import fit_two_stage,TwoStageDiagnostic
from vibration.datasets import DatasetCatalog


def extract(catalog):
    path=OUT/'brito_rotor_full.npz'
    if path.exists():
        with np.load(path,allow_pickle=False) as z: return {k:z[k] for k in z.files}
    groups={}
    for r in catalog.rows:
        if r['dataset']=='Brito': groups.setdefault(catalog.records[r['id']][2]['trial_id'],[]).append(r)
    def one(trial,rows):
        x=[]; labels=[]; ids=[]
        for row in rows:
            values,meta=catalog.load(row['id'])
            features=rotor_features(values,25000,1238,channel_names=meta['channel_names'])
            x.append(features.values); labels.append(catalog.records[row['id']][2]['fault']); ids.append(row['id'])
        print('extracted trial',trial,'windows',len(x),flush=True)
        return trial,np.asarray(x),labels,ids,features.names,features.channel_names
    pieces=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(one,t,rows) for t,rows in sorted(groups.items())]): pieces.append(future.result())
    pieces.sort(key=lambda r:r[0])
    result={'x':np.vstack([p[1] for p in pieces]),'groups':np.concatenate([np.repeat(p[0],len(p[1])) for p in pieces]),
        'y':np.concatenate([p[2] for p in pieces]),'ids':np.concatenate([p[3] for p in pieces]),
        'names':np.asarray(pieces[0][4]),'channels':np.asarray(pieces[0][5])}
    np.savez_compressed(path,**result); return result


def measure(model,data,mask,scope):
    labels=data['y'][mask]; statuses=[]; guesses=[]; anomalies=[]; per={}
    for v,truth,group in zip(data['x'][mask],labels,data['groups'][mask]):
        result=model.predict(RotorFeatures(tuple(data['names']),v,25000,1238,tuple(data['channels']),25000),scope=scope)
        statuses.append(result['status']); guesses.append(result['label']); anomalies.append(result.get('anomaly') is True)
        entry=per.setdefault(str(group),{'truth':str(truth),'windows':0,'statuses':{},'correct':0})
        entry['windows']+=1; entry['correct']+=int(result['label']==truth)
        entry['statuses'][result['status']]=entry['statuses'].get(result['status'],0)+1
    normal=labels=='normal'; fault=~normal; statuses=np.asarray(statuses); guesses=np.asarray(guesses,dtype=object); anomalies=np.asarray(anomalies)
    decisive=np.isin(statuses,['normal','fault_candidate'])
    return {'windows':len(labels),'independent_trials':len(per),'normal_windows':int(normal.sum()),'fault_windows':int(fault.sum()),
        'normal_false_alarm_rate':float(anomalies[normal].mean()) if normal.any() else None,
        'normal_acceptance_rate':float(np.mean(statuses[normal]=='normal')) if normal.any() else None,
        'normal_hold_rate':float(np.mean(statuses[normal]=='hold')) if normal.any() else None,
        'fault_detection_rate':float(anomalies[fault].mean()),
        'fault_miss_as_normal_rate':float(np.mean(statuses[fault]=='normal')),
        'fault_hold_rate':float(np.mean(statuses[fault]=='hold')),
        'correct_fault_type_rate_all_fault_windows':float(np.mean(guesses[fault]==labels[fault])),
        'overall_label_accuracy_holds_wrong':float(np.mean(guesses==labels)),
        'decision_coverage':float(decisive.mean()),'conditional_decision_accuracy':float(np.mean(guesses[decisive]==labels[decisive])) if decisive.any() else None,
        'status_counts':{s:int(np.sum(statuses==s)) for s in sorted(set(statuses.tolist()))},'per_trial':per}


def main():
    started=time.perf_counter(); catalog=DatasetCatalog(); d=extract(catalog); g=d['groups']; y=d['y']; x=d['x']
    fit=np.isin(g,[1,3,6]); calibration=g==9; faultfit=np.isin(g,[2,4,5,7,8,10,11,12,15]); evaluation=np.isin(g,[13,14,16,17,18,19,20])
    assert not set(g[fit|calibration|faultfit])&set(g[evaluation])
    scope={'asset_id':'BritoBench','condition_id':'nominal_1238rpm','unit':'unknown','channel_names':d['channels'].tolist(),
           'sample_rate_hz':25000,'window_samples':25000,'rpm_range':[1176.1,1299.9]}
    report={'protocol':'All Brito records are exposed development data. New CrossSpeed1200 data reserved, not opened.',
        'normal_fit_trials':[1,3,6],'normal_calibration_trials':[9],'fault_fit_trials':[2,4,5,7,8,10,11,12,15],
        'development_evaluation_trials':[13,14,16,17,18,19,20],'modes':{},'feature_count':len(d['names']),
        'calibration_limitation':'Only ONE normal calibration experiment, 420 correlated windows; no independent false-alarm guarantee.',
        'operational_use':False}
    for mode in ('legacy','relative','combined'):
        p=fit_two_stage(x[fit],g[fit],x[calibration],g[calibration],x[faultfit],y[faultfit],g[faultfit],feature_names=d['names'].tolist(),scope=scope,mode=mode)
        raw=json.dumps(p,ensure_ascii=False,sort_keys=True).encode(); (OUT/f'model_{mode}.json').write_bytes(raw)
        model=TwoStageDiagnostic(p)
        result=measure(model,d,evaluation,scope); result['original_exposed_test_subset']=measure(model,d,np.isin(g,[16,17,19,20]),scope)
        result['selected_feature_count']=len(p['selected_indices']); result['sha256']=hashlib.sha256(raw).hexdigest()
        report['modes'][mode]=result
        # Full raw-array -> window hook -> stage parity, no label metadata required.
        index=int(np.flatnonzero(g==17)[0]); values,meta=catalog.load(str(d['ids'][index]))
        config=AnalysisConfig(sample_rate_hz=25000,channels=4,rpm=1238)
        analyzer=VibrationAnalyzer(config,stages={'diagnostic':TwoStageStage(model)})
        observed=analyzer.analyze(SignalBlock(values,25000,channels=tuple(d['channels']),rpm=1238,metadata={'asset_id':scope['asset_id'],'condition_id':scope['condition_id']}))
        expected=model.analyze(values,25000,1238,scope=scope,channel_names=d['channels'])
        assert observed.payload['diagnostic']==expected
        print(mode,json.dumps({k:result[k] for k in ('normal_false_alarm_rate','fault_detection_rate','overall_label_accuracy_holds_wrong','decision_coverage')}),flush=True)
    report['seconds']=time.perf_counter()-started
    (OUT/'development_comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS development ablation + raw pipeline parity. No fresh external-test score asserted.',flush=True)

if __name__=='__main__': main()
