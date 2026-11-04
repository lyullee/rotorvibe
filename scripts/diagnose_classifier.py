"""Read-only post-test diagnostics. Never changes the frozen model or split."""
import sys,json,sqlite3,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import vibration.bootstrap
import numpy as np
from vibration.classifier import GaussianClassifier


def main():
    out=ROOT/'output/classifier_improvement'; raw=(out/'frozen_model.json').read_bytes(); p=json.loads(raw)
    model=GaussianClassifier(p)
    with np.load(out/'test_stride1_v2.npz',allow_pickle=False) as z: test={k:z[k] for k in z.files}
    with np.load(out/'train_stride1_v2.npz',allow_pickle=False) as z: train={k:z[k] for k in z.files}
    with np.load(out/'validation_stride1_v2.npz',allow_pickle=False) as z: val={k:z[k] for k in z.files}
    assert not set(test['ids'])&set(train['ids']) and not set(test['ids'])&set(val['ids'])
    assert not set(test['groups'])&set(train['groups']) and not set(test['groups'])&set(val['groups'])
    db=sqlite3.connect(f"file:{(ROOT/'output/release_verification/model_runtime/vibration.sqlite3').as_posix()}?mode=ro",uri=True)
    try: old=json.loads(db.execute("SELECT payload FROM documents WHERE kind='classifier' AND name='release-verification-only'").fetchone()[0])
    finally: db.close()
    z=(test['x']-np.asarray(old['center']))/np.asarray(old['scale']); mu=np.asarray(old['centroids']); var=np.asarray(old['variances'])
    squared=np.mean((z[:,None,:]-mu)**2/var,axis=2)
    corrected=squared+np.mean(np.log(var),axis=1)
    labels=np.asarray(old['classes'])
    result={'model_sha256':hashlib.sha256(raw).hexdigest(),'data_overlap':'no records or physical trials overlap',
            'split_trials':{'train':sorted(set(train['groups'].tolist())),'validation':sorted(set(val['groups'].tolist())),'test':sorted(set(test['groups'].tolist()))},
            'old_parameters_formula_only_counterfactual_no_refitting':{'without_logdet_forced_accuracy':float(np.mean(labels[squared.argmin(1)]==test['y'])),
              'with_logdet_forced_accuracy':float(np.mean(labels[corrected.argmin(1)]==test['y'])),
              'note':'No unknown rejection here; read-only causal formula ablation, not a second tuned test.'},
            'old_class_mean_log_variance':dict(zip(old['classes'],np.mean(np.log(var),axis=1).tolist())),
            'normal_trial_distribution':[]}
    for data,role in ((train,'train'),(val,'validation'),(test,'test')):
        mask=data['y']=='normal'
        for trial in sorted(set(data['groups'][mask].tolist())):
            x=data['x'][data['groups']==trial]; costs,distances=model.scores(x)
            shift=(x.mean(axis=0)-np.asarray(p['center']))/np.asarray(p['scale'])-np.asarray(p['centroids'])[p['classes'].index('normal')]
            top=np.argsort(np.abs(shift))[-5:][::-1]
            result['normal_trial_distribution'].append({'trial':trial,'role':role,
                'mean_AC_RMS_raw_units':np.exp(x[:,[0,7,14,21]]).mean(axis=0).tolist(),
                'mean_cost_by_class':dict(zip(p['classes'],costs.mean(axis=0).tolist())),
                'largest_mean_shifts_from_normal_training_center':[{'feature':str(data['names'][i]),'global_standard_deviations':float(shift[i])} for i in top]})
    (out/'diagnosis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
