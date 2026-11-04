"""Retrain through the production registry, then verify the frozen benchmark snapshot."""
import os,sys,json,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
OUT=ROOT/'output/classifier_improvement'
os.environ['VIBRATION_RUNTIME_HOME']=str(OUT/'production_runtime')
import vibration.bootstrap
import numpy as np
from vibration import VibrationAnalyzer,SignalBlock,AnalysisConfig,GaussianClassifier
from vibration.datasets import DatasetCatalog
from vibration.models import ModelRegistry
from vibration.storage import Storage
from vibration.stages import ClassifierStage


def main():
    frozen=json.loads((OUT/'frozen_model.json').read_text(encoding='utf-8'))
    final=json.loads((OUT/'final_test.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((OUT/'frozen_model.json').read_bytes()).hexdigest()==final['model_sha256']
    catalog=DatasetCatalog(); storage=Storage(); registry=ModelRegistry(storage,catalog)
    try:
        registry.train('Brito Gaussian v3 verified'); deadline=time.monotonic()+900; previous=-1
        while registry.job['status']=='running':
            if time.monotonic()>deadline: raise TimeoutError('Production training timeout.')
            count=registry.job.get('completed',0)
            if count//1000!=previous: print('production training',count,flush=True); previous=count//1000
            time.sleep(.1)
        assert registry.job['status']=='complete',registry.job
        registry.load('Brito Gaussian v3 verified'); actual=registry.active
        assert actual['training_trials']==frozen['training_trials']
        for key in ('center','scale','centroids','variances','distance_limits'):
            np.testing.assert_allclose(actual[key],frozen[key],rtol=1e-12,atol=1e-12)
        actual['summary']['status']='independent_training_trial_tested'
        actual['summary']['benchmark']={k:final[k] for k in ('windows','independent_trials','window_accuracy','macro_f1','trial_majority_accuracy')}
        actual['summary']['benchmark']['model_parameter_match']='frozen snapshot verified'
        actual['summary']['benchmark']['operational_use']=False
        storage.save('classifier',actual['name'],actual); registry.load(actual['name'])
        config=AnalysisConfig(sample_rate_hz=25000,channels=4,model_enabled=True)
        analyzer=VibrationAnalyzer(config,stages={'classification':ClassifierStage(registry)})
        pure=GaussianClassifier(frozen); checked=[]
        with np.load(OUT/'test_stride1_v2.npz',allow_pickle=False) as data:
            batch=pure.predict_many(data['x'])
            for i,(v,record_id) in enumerate(zip(data['x'],data['ids'])):
                predicted=registry.classify(v,config,{'dataset':'Brito','fault':'not a feature'})
                assert predicted['label']==batch[i]
            for group in final['test_trials']:
                index=int(np.flatnonzero(data['groups']==group)[0]); record_id=str(data['ids'][index])
                a,meta=catalog.load(record_id); meta['source_label']='intentionally incorrect'
                result=analyzer.analyze(SignalBlock(a,25000,metadata=meta))
                assert result.payload['classification']['label']==batch[index]
                checked.append({'trial':group,'raw_pipeline_label':str(batch[index])})
        result={'status':'pass','production_training_records':actual['summary']['records'],
                'training_parameters_match_frozen':True,'registry_predictions_match_all_test_windows':len(batch),
                'raw_signal_pipeline':checked,'runtime':'output/classifier_improvement/production_runtime',
                'operational_use':False}
        actual['frozen_benchmark_model_sha256']=final['model_sha256']
        actual['evaluation']='Original trial holdout repeat benchmark; old test score previously known. No operational approval. Normal test recall 0/420.'
        (OUT/'evaluated_model.json').write_text(json.dumps(actual,ensure_ascii=False,indent=2),encoding='utf-8')
        (OUT/'integration.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False),flush=True)
    finally: registry.close(); storage.close()

if __name__=='__main__': main()
