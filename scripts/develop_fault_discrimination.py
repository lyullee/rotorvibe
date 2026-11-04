"""Development on previously exposed records + new non1200 8kHz faults only."""
import sys,json,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import vibration.bootstrap
import numpy as np
from scipy.io import loadmat
from vibration.fault_discrimination import fault_features,fit_fault_discriminator,FaultDiscriminator
DATA=ROOT/'data/fault_discrimination'; OLD=ROOT/'data/condition_improvement'; OUT=ROOT/'output/fault_discrimination'
SCOPE={'asset_id':'UOS_MOCHU6204','condition_id':'steady_bearing_healthy','unit':'g'}

def write(path,obj): path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def rows():
    old=json.loads((OLD/'metadata/record_plan.json').read_text(encoding='utf-8'))+json.loads((OLD/'metadata/matched_normal_plan.json').read_text(encoding='utf-8'))
    result=[dict(filename=r['filename'],path=str(OLD/r['path']),label=r['reference_label'],rpm=r['rpm'],fs=r['sample_rate_hz'],sha256=r['provider_sha256'],role='exposed_development') for r in old]
    for r in json.loads((DATA/'plan.json').read_text(encoding='utf-8')):
        if r['role']=='final_test': continue
        result.append(dict(filename=r['filename'],path=str(DATA/r['filename']),label=r['label'],rpm=r['rpm'],fs=8000,sha256=r['sha256'],role='development'))
    return result

def load(row):
    if row.get('role')=='final_test': raise RuntimeError('No final-test decoding in development')
    assert sha(Path(row['path']))==row['sha256']
    x=loadmat(row['path'],variable_names=['Data'])['Data'].ravel()
    if len(x)!=1280000 or not np.isfinite(x).all(): raise ValueError('Invalid original waveform')
    return x

def extract():
    OUT.mkdir(parents=True,exist_ok=True); cache=OUT/'source.npz'
    if cache.exists():
        with np.load(cache,allow_pickle=False) as z: return {k:z[k] for k in z.files}
    source=rows(); assert len(source)==89
    def one(row):
        a=load(row); step=row['fs']*2; features=[]
        for start in range(0,len(a),step):
            names,x=fault_features(a[start:start+step],row['fs'],row['rpm']); features.append(x)
        print('features',row['filename'],len(features),flush=True)
        return np.vstack(features),row,names
    with ThreadPoolExecutor(max_workers=4) as pool: records=list(pool.map(one,source))
    d={'x':np.vstack([v[0] for v in records]),'names':np.asarray(records[0][2])}
    for key,field in [('y','label'),('rpm','rpm'),('fs','fs'),('groups','filename')]: d[key]=np.concatenate([np.repeat(r[field],len(x)) for x,r,_ in records])
    np.savez_compressed(cache,**d); write(OUT/'source_records.json',source)
    return d

def measure(model,d,mask):
    predictions=[model.predict(x,r,scope=SCOPE) for x,r in zip(d['x'][mask],d['rpm'][mask])]
    labels=d['y'][mask]; classes=['looseness','misalignment','unbalance']; confusion={c:{p:0 for p in classes+['unknown']} for c in classes}
    for y,p in zip(labels,predictions): confusion[str(y)][p['label'] or 'unknown']+=1
    f1=[]
    for c in classes:
        tp=confusion[c][c]; fn=sum(confusion[c].values())-tp; fp=sum(confusion[o][c] for o in classes if o!=c)
        f1.append(2*tp/max(1,2*tp+fp+fn))
    return dict(windows=len(labels),recordings=len(set(d['groups'][mask])),accuracy=sum(confusion[c][c] for c in classes)/len(labels),macro_f1=float(np.mean(f1)),confusion=confusion)

def main():
    if (OUT/'final_access.jsonl').exists(): raise RuntimeError('Final opened; do not retune this experiment')
    d=extract(); fault=d['y']!='normal'; candidates=[]
    # Both acquisition rates at held speeds remain whole-file validation; no alternate-rate pair leaks that speed.
    folds=[1000,1400]
    for mode in ['orders','morphology']:
        for penalty in [0.,1.,4.]:
            for margin in [0.,.05]:
                results=[]
                for speed in folds:
                    train=fault&(d['rpm']!=speed); validation=fault&(d['rpm']==speed)
                    p=fit_fault_discriminator(d['x'][train],d['y'][train],d['rpm'][train],d['groups'][train],names=d['names'].tolist(),scope=SCOPE,mode=mode,rpm_penalty=penalty,margin=margin)
                    results.append(measure(FaultDiscriminator(p),d,validation))
                candidate=dict(mode=mode,rpm_penalty=penalty,margin=margin,folds=results,macro_f1=float(np.mean([r['macro_f1'] for r in results])))
                candidates.append(candidate); print('candidate',mode,penalty,margin,candidate['macro_f1'],flush=True)
    best=max(candidates,key=lambda c:c['macro_f1'])
    p=fit_fault_discriminator(d['x'][fault],d['y'][fault],d['rpm'][fault],d['groups'][fault],names=d['names'].tolist(),scope=SCOPE,**{k:best[k] for k in ('mode','rpm_penalty','margin')})
    write(OUT/'candidate.json',p); write(OUT/'development.json',dict(candidates=candidates,selected=best,source_recordings=len(set(d['groups'])),fault_recordings=len(set(d['groups'][fault])),
        new_final_used=False,old_final_now_development=True,model_sha256=sha(OUT/'candidate.json'),scope='Fault subtype conditional on anomaly; no healthy inference by this model.'))
    print('SELECTED',best,flush=True)
if __name__=='__main__': main()
