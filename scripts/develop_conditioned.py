"""Development only: exposed SRO1200, plus UOS source files excluding all new1200."""
import json,sys,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import vibration.bootstrap
import numpy as np
from vibration.condition_data import ExposedCrossSpeedDevelopment,UosRotorCatalog
from vibration.rotor_features import rotor_features,RotorFeatures
from vibration.conditioned import fit_conditioned,ConditionedDiagnostic
OUT=ROOT/'output/condition_improvement'; OUT.mkdir(parents=True,exist_ok=True)


def cached(name,records,loader,fs,n):
    path=OUT/f'{name}.npz'
    if path.exists():
        with np.load(path,allow_pickle=False) as z: return {k:z[k] for k in z.files}
    def one(record):
        a,meta=loader(record['id']); x=[]
        for offset in range(0,len(a)-n+1,n):
            f=rotor_features(a[offset:offset+n],fs,meta['rpm'],channel_names=meta['channel_names']); x.append(f.values)
        group=meta.get('group_id',meta.get('recording_id'))
        print('features',name,record['id'],len(x),flush=True)
        return np.vstack(x),meta['reference_label'],group,meta['rpm'],f.names,meta['channel_names'],record['id']
    with ThreadPoolExecutor(max_workers=3) as pool: pieces=list(pool.map(one,records))
    result={'x':np.vstack([p[0] for p in pieces]),'y':np.concatenate([np.repeat(p[1],len(p[0])) for p in pieces]),
        'groups':np.concatenate([np.repeat(p[2],len(p[0])) for p in pieces]),'rpm':np.concatenate([np.repeat(p[3],len(p[0])) for p in pieces]),
        'ids':np.concatenate([np.repeat(p[6],len(p[0])) for p in pieces]),'names':np.asarray(pieces[0][4]),'channels':np.asarray(pieces[0][5])}
    np.savez_compressed(path,**result); return result


def measure(p,d,mask,fs,n):
    model=ConditionedDiagnostic(p); y=d['y'][mask]; guesses=[]; status=[]; per={}
    for x,rpm,truth,g in zip(d['x'][mask],d['rpm'][mask],y,d['groups'][mask]):
        result=model.predict(RotorFeatures(tuple(d['names']),x,fs,float(rpm),tuple(d['channels']),n),scope=p['scope'])
        guesses.append(result['label']); status.append(result['status'])
        entry=per.setdefault(str(g),{'truth':str(truth),'windows':0,'correct':0,'status':{}})
        entry['windows']+=1; entry['correct']+=int(result['label']==truth); entry['status'][result['status']]=entry['status'].get(result['status'],0)+1
    guesses=np.asarray(guesses,dtype=object); status=np.asarray(status); normal=y=='normal'; faults=~normal
    f1=[]
    for label in sorted(set(y.tolist())):
        tp=np.sum((guesses==label)&(y==label)); fp=np.sum((guesses==label)&(y!=label)); fn=np.sum((guesses!=label)&(y==label)); f1.append(float(2*tp/max(2*tp+fp+fn,1)))
    anomaly=np.isin(status,['fault_candidate','anomaly_unknown']); decisive=np.isin(status,['normal','fault_candidate'])
    return {'windows':len(y),'recordings':len(per),'normal_windows':int(normal.sum()),'fault_windows':int(faults.sum()),
        'normal_false_alarm_rate':float(anomaly[normal].mean()),'normal_acceptance_rate':float(np.mean(status[normal]=='normal')),
        'normal_hold_rate':float(np.mean(status[normal]=='hold')),'fault_detection_rate':float(anomaly[faults].mean()),
        'fault_miss_as_normal_rate':float(np.mean(status[faults]=='normal')),'fault_hold_rate':float(np.mean(status[faults]=='hold')),
        'correct_fault_type_rate':float(np.mean(guesses[faults]==y[faults])),'accuracy_holds_wrong':float(np.mean(guesses==y)),
        'macro_f1':float(np.mean(f1)),'decision_coverage':float(decisive.mean()),'per_recording':per}


def fit(d,reference,calibration,faults,scope,mode,interpolate,uncertainty):
    return fit_conditioned(d['x'][reference],d['rpm'][reference],d['groups'][reference],d['x'][calibration],d['rpm'][calibration],d['groups'][calibration],
        d['x'][faults],d['rpm'][faults],d['y'][faults],d['groups'][faults],feature_names=d['names'].tolist(),scope=scope,mode=mode,
        interpolate=interpolate,max_rpm_gap=800.,interpolation_uncertainty=uncertainty,min_margin=.1)


def main():
    data=ROOT/'data/condition_improvement'
    if (data/'metadata/new_test_access.jsonl').exists(): raise RuntimeError('New test already opened. Do not tune this experiment.')
    old=ExposedCrossSpeedDevelopment(ROOT/'data/normal_independent')
    sro=cached('exposed_sro_all',old.rows(),old.load,25600,25600); normal=sro['y']=='normal'
    reference=np.zeros(len(normal),dtype=bool); cal=reference.copy(); faults=reference.copy(); val=reference.copy()
    for speed in (600,900,1200):
        for label in ('normal','misalignment','unbalance'):
            groups=sorted(set(sro['groups'][(sro['rpm']==speed)&(sro['y']==label)].tolist()))
            if label=='normal':
                for g in groups[:11]: reference|=sro['groups']==g
                for g in groups[11:14]: cal|=sro['groups']==g
                for g in groups[14:]: val|=sro['groups']==g
            else:
                for g in groups[:14]: faults|=sro['groups']==g
                for g in groups[14:]: val|=sro['groups']==g
    scope={'asset_id':'CrossSpeed2026Bench','condition_id':'steady','unit':'unknown','channel_names':sro['channels'].tolist(),
        'sample_rate_hz':25600,'window_samples':25600,'rpm_range':[594,1212]}
    report={'SRO_status':'All previously opened data are development; no new independent claim.',
        'SRO_ablations':{},'UOS_source_validation':[],'new_test_used_for_development':False}
    for mode in ('relative','orders','levels_orders'):
        p=fit(sro,reference,cal,faults,scope,mode,False,1.)
        result=measure(p,sro,val,25600,25600); result['known_exposed_1200_only']=measure(p,sro,val&(sro['rpm']==1200),25600,25600)
        report['SRO_ablations'][mode]=result
        (OUT/f'sro_{mode}.json').write_text(json.dumps(p,ensure_ascii=False,sort_keys=True),encoding='utf-8')
        print('SRO',mode,result['macro_f1'],result['known_exposed_1200_only']['normal_false_alarm_rate'],flush=True)
    catalog=UosRotorCatalog(data)
    rows=[r for r in catalog.rows() if r['role']!='reserved_new_test']
    assert all(r['rpm']!=1200 for r in rows)
    uos=cached('uos_source',rows,catalog.load,16000,32000); ng=uos['y']=='normal'; rpm=uos['rpm']
    scope={'asset_id':'UOS_MOCHU6204','condition_id':'steady_bearing_healthy','unit':'g','channel_names':uos['channels'].tolist(),
        'sample_rate_hz':16000,'window_samples':32000,'rpm_range':[594,1616]}
    # Development validation is the entire 1000RPM condition, never the new1200 files.
    rf=ng&np.isin(rpm,[600,1400,1600]); calibration=ng&(rpm==800); faultfit=(~ng)&(rpm!=1000); validation=rpm==1000
    for mode in ('relative','orders','levels_orders'):
        for uncertainty in (0.,1.):
            p=fit(uos,rf,calibration,faultfit,scope,mode,True,uncertainty)
            result=measure(p,uos,validation,16000,32000)
            entry={'mode':mode,'uncertainty':uncertainty,'validation':result}; report['UOS_source_validation'].append(entry)
            print('UOS source only',mode,uncertainty,result['macro_f1'],result['normal_false_alarm_rate'],result['accuracy_holds_wrong'],flush=True)
    best=max(report['UOS_source_validation'],key=lambda r:(r['validation']['macro_f1'],r['validation']['decision_coverage']))
    report['selected']={'mode':best['mode'],'uncertainty':best['uncertainty'],'rule':'source1000RPM macro-F1, then decision coverage; 1200 arrays not decoded'}
    # Final fit uses all source files; calibration800 remains separate from normal refs.
    final=fit(uos,ng&(rpm!=800),ng&(rpm==800),~ng,scope,best['mode'],True,best['uncertainty'])
    raw=json.dumps(final,ensure_ascii=False,sort_keys=True).encode(); (OUT/'uos_candidate.json').write_bytes(raw)
    report['candidate_sha256']=hashlib.sha256(raw).hexdigest()
    (OUT/'development.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    assert not (data/'metadata/new_test_access.jsonl').exists()
    print('Development complete; new1200 test remains closed.',flush=True)

if __name__=='__main__': main()
