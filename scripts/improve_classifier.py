"""Develop on original train/validation trials; freeze before one final test pass.

The old test score was already published: this is a training-independent repeat
benchmark, NOT a newly collected blind external-machine experiment.
"""
import os,sys,json,hashlib,time,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
OUT=ROOT/'output/classifier_improvement'; OUT.mkdir(parents=True,exist_ok=True)
os.environ['VIBRATION_RUNTIME_HOME']=str(OUT/'runtime')
import vibration.bootstrap
import numpy as np
from vibration.datasets import DatasetCatalog
from vibration.dsp import channel_features
from vibration.classifier import fit_gaussian,GaussianClassifier


def extract(catalog,split,stride):
    path=OUT/f'{split}_stride{stride}_v2.npz'
    if path.exists():
        with np.load(path,allow_pickle=False) as z: return {k:z[k] for k in z.files}
    x=[]; y=[]; groups=[]; ids=[]
    rows=[r for r in catalog.rows if r['dataset']=='Brito' and catalog.records[r['id']][2]['suggested_split']==split]
    by_trial={}
    for row in rows: by_trial.setdefault(catalog.records[row['id']][2]['trial_id'],[]).append(row)
    for trial,records in sorted(by_trial.items()):
        for row in records[::stride]:
            a,meta=catalog.load(row['id']); names,v=channel_features(a,25000)
            x.append(v); y.append(catalog.records[row['id']][2]['fault']); groups.append(trial); ids.append(row['id'])
        print('features',split,'trial',trial,'windows',len(x),flush=True)
    result={'x':np.asarray(x),'y':np.asarray(y),'groups':np.asarray(groups),'ids':np.asarray(ids),'names':np.asarray(names)}
    np.savez_compressed(path,**result); return result


def metrics(truth,predicted,groups):
    truth=np.asarray(truth); predicted=np.asarray(predicted); groups=np.asarray(groups)
    labels=sorted(set(truth.tolist())); per={}; matrix={}; f1=[]
    for label in labels:
        matrix[label]={p:int(np.sum((truth==label)&(predicted==p))) for p in sorted(set(predicted.tolist()))}
        tp=np.sum((truth==label)&(predicted==label)); fp=np.sum((truth!=label)&(predicted==label)); fn=np.sum((truth==label)&(predicted!=label))
        f1.append(float(2*tp/max(2*tp+fp+fn,1)))
    for group in sorted(set(groups.tolist())):
        mask=groups==group; per[str(group)]={'truth':str(truth[mask][0]),'windows':int(mask.sum()),'correct':int(np.sum(predicted[mask]==truth[mask])),
            'majority_prediction':str(max(labels,key=lambda label:np.sum(predicted[mask]==label)))}
    return {'windows':len(truth),'independent_trials':len(per),'window_accuracy':float(np.mean(truth==predicted)),
            'macro_f1':float(np.mean(f1)),'confusion':matrix,'per_trial':per,
            'trial_majority_accuracy':float(np.mean([r['truth']==r['majority_prediction'] for r in per.values()]))}


def predict(p,x):
    return GaussianClassifier(p).predict_many(x)


def old_centroid(train,query,logdet=False):
    x=train['x'][:,:28]; q=query['x'][:,:28]; y=train['y']; center=np.median(x,axis=0); scale=np.maximum(np.std(x,axis=0),.1)
    z=(x-center)/scale; q=(q-center)/scale; classes=sorted(set(y.tolist())); costs=[]
    for label in classes:
        c=z[y==label]; mu=c.mean(axis=0); var=np.maximum(c.var(axis=0),.25)
        costs.append(np.mean((q-mu)**2/var,axis=1)+(np.mean(np.log(var)) if logdet else 0))
    return np.asarray(classes)[np.argmin(costs,axis=0)]


def develop():
    if (OUT/'final_test.json').exists():
        raise RuntimeError('The final test has been opened. Do not tune or overwrite this experiment; acquire a fresh protocol/data split.')
    catalog=DatasetCatalog(); train=extract(catalog,'train',7); val=extract(catalog,'validation',7)
    report={'protocol':'Original trial groups fixed. Train-only 3-fold grouped CV, validation selection; test features not accessed.',
            'validation_old_centroid':metrics(val['y'],old_centroid(train,val),val['groups']),
            'validation_logdet_corrected':metrics(val['y'],old_centroid(train,val,True),val['groups']),'candidates':[]}
    # Each fold leaves an entire physical experiment out for every class.
    classes=sorted(set(train['y'].tolist())); folds=[]
    for fold in range(3):
        held=[sorted(set(train['groups'][train['y']==label].tolist()))[fold] for label in classes]
        folds.append(np.isin(train['groups'],held))
    for floor in (.05,.25,1.):
        cv=[]
        for held in folds:
            p=fit_gaussian(train['x'][~held],train['y'][~held],train['groups'][~held],variance_floor=floor)
            cv.extend((predict(p,train['x'][held])==train['y'][held]).tolist())
        p=fit_gaussian(train['x'],train['y'],train['groups'],variance_floor=floor)
        score=metrics(val['y'],predict(p,val['x']),val['groups'])
        entry={'variance_floor':floor,'group_cv_accuracy':float(np.mean(cv)),'validation':score}
        report['candidates'].append(entry)
        print('candidate',floor,'CV',np.mean(cv),'validation',score['window_accuracy'],flush=True)
    best=max(report['candidates'],key=lambda r:(r['validation']['macro_f1'],r['group_cv_accuracy']))
    report['selected']={k:best[k] for k in ('variance_floor','group_cv_accuracy')}
    # Refit selected parameters on ALL original training windows only.
    full=extract(catalog,'train',1)
    profile=fit_gaussian(full['x'],full['y'],full['groups'],variance_floor=best['variance_floor'])
    profile.update(feature_names=full['names'].tolist(),name='Brito Gaussian v3',created=time.strftime('%Y-%m-%d'),
        summary={'records':len(full['x']),'trials':len(set(full['groups'])),'dataset':'Brito','status':'development_validated','classes':classes},
        domain={'dataset':'Brito','channels':4,'sample_rate_hz':25000,'samples':25000,'unit':'unknown'},
        evaluation='Training-trial-independent benchmark pending. No field operational approval.')
    fullval=extract(catalog,'validation',1)
    report['selected_full_validation']=metrics(fullval['y'],predict(profile,fullval['x']),fullval['groups'])
    raw=json.dumps(profile,ensure_ascii=False,sort_keys=True).encode(); (OUT/'frozen_model.json').write_bytes(raw)
    report['frozen_sha256']=hashlib.sha256(raw).hexdigest(); report['training_trials']=profile['training_trials']
    report['validation_trials']=sorted(set(fullval['groups'].tolist()))
    report['limitations']='Previously published old test score is known; this is not a fresh blind test. Consecutive windows correlated.'
    (OUT/'development.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


def final():
    report=json.loads((OUT/'development.json').read_text(encoding='utf-8')); raw=(OUT/'frozen_model.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==report['frozen_sha256']; p=json.loads(raw)
    if (OUT/'final_test.json').exists(): raise RuntimeError('Final test already run. Preserve it; do not tune against it.')
    catalog=DatasetCatalog(); test=extract(catalog,'test',1)
    assert not set(test['groups'])&set(p['training_trials'])
    assert not set(test['groups'])&set(report['validation_trials'])
    result=metrics(test['y'],predict(p,test['x']),test['groups'])
    result.update(model_sha256=report['frozen_sha256'],test_trials=sorted(set(test['groups'].tolist())),
                  training_overlap=False,validation_overlap=False,operational_use=False,
                  limitation=report['limitations'])
    (OUT/'final_test.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('phase',choices=('develop','final')); args=parser.parse_args()
    develop() if args.phase=='develop' else final()
