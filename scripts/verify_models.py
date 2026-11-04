"""Full local Brito split evaluation plus FEMTO causal-prefix integrity check.

Requires separately collected local datasets. Validation/test records never fit
or tune the model. Window accuracy is descriptive, not independent-trial accuracy.
"""
import sys,os,json,time,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
OUT=ROOT/'output/release_verification'; OUT.mkdir(parents=True,exist_ok=True)
os.environ['VIBRATION_RUNTIME_HOME']=str(OUT/'model_runtime')
import vibration.bootstrap
import numpy as np
from vibration.datasets import DatasetCatalog
from vibration.storage import Storage
from vibration.models import ModelRegistry,LifeEstimator
from vibration.config import AnalysisConfig
from vibration.dsp import channel_features

def main():
    catalog=DatasetCatalog(); storage=Storage(); registry=ModelRegistry(storage,catalog)
    started=time.perf_counter(); name='release-verification-only'
    try:
        registry.train(name); previous=-1; deadline=time.monotonic()+900
        while registry.job['status']=='running':
            if time.monotonic()>deadline: raise TimeoutError('Model fitting exceeded 15-minute verification limit.')
            n=registry.job.get('completed',0)
            if n//1000!=previous: print('training',n,'/',registry.job.get('total'),flush=True); previous=n//1000
            time.sleep(.1)
        if registry.job['status']!='complete': raise RuntimeError(registry.job)
        registry.load(name); profile=registry.active
        assert len(profile['training_trials'])==12
        result={'training':profile['summary'],'training_trials':profile['training_trials'],'splits':{},'tuning_on_heldout':False}
        config=AnalysisConfig(sample_rate_hz=25000,channels=4,unit='unknown',model_enabled=True).validate()
        for split in ('validation','test'):
            rows=[r for r in catalog.rows if r['dataset']=='Brito' and catalog.records[r['id']][2]['suggested_split']==split]
            trials=sorted({catalog.records[r['id']][2]['trial_id'] for r in rows})
            assert not set(trials)&set(profile['training_trials'])
            confusion={}; per_trial={}; correct=0; unknown=0
            for i,row in enumerate(rows):
                a,meta=catalog.load(row['id']); names,v=channel_features(a,25000)
                prediction=registry.classify(v,config,meta); truth=catalog.records[row['id']][2]['fault']; predicted=prediction['label']
                trial=catalog.records[row['id']][2]['trial_id']; entry=per_trial.setdefault(str(trial),{'truth':truth,'windows':0,'correct':0})
                entry['windows']+=1; entry['correct']+=int(predicted==truth)
                confusion.setdefault(truth,{})[predicted]=confusion.setdefault(truth,{}).get(predicted,0)+1
                correct+=int(predicted==truth); unknown+=int(prediction['status']=='unknown')
                assert all(np.isfinite(x['weight']) for x in prediction['relative_matches'])
                if (i+1)%500==0: print(split,i+1,'/',len(rows),flush=True)
            result['splits'][split]={'windows':len(rows),'independent_trials':len(trials),'trial_ids':trials,
                'correct_windows':correct,'unknown_windows':unknown,'window_accuracy':correct/len(rows),
                'confusion':confusion,'per_trial':per_trial,'statistical_limitation':'Overlapping/consecutive windows from a single trial are correlated.'}
        estimator=LifeEstimator(catalog)
        assert len(estimator.references)==6
        heldout_id=next(id for id,row in catalog.lives.items() if row['role']!='training_complete_life' and row['snapshot_count']>100)
        row=catalog.lives[heldout_id]; index=min(500,row['snapshot_count']-1)
        _,source=catalog.load(heldout_id,index); before=estimator.estimate(source)
        saved=row['nominal_rms_series'][index+1:]
        row['nominal_rms_series'][index+1:]=[[1e9,1e9] for _ in saved]
        try:
            _,same_prefix=catalog.load(heldout_id,index); after=estimator.estimate(same_prefix)
            assert before==after,'Held-out future leaked into online prediction.'
        finally: row['nominal_rms_series'][index+1:]=saved
        assert all(r['reference_bearing']!=source['record_id'] for r in before.get('references',[]))
        result['FEMTO_causality']={'status':'pass','reference_training_lives':6,'heldout':heldout_id,
            'observed_snapshots':index+1,'future_perturbation_invariant':True,'prediction':before,
            'scope':'Causality/integration only, not RUL accuracy calibration.'}
        result['seconds']=time.perf_counter()-started
        (OUT/'model_evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'validation_accuracy':result['splits']['validation']['window_accuracy'],
            'test_accuracy':result['splits']['test']['window_accuracy'],'seconds':result['seconds'],'FEMTO_causality':'pass'}),flush=True)
    finally: registry.close(); storage.close()

if __name__=='__main__': main()
