"""Actual source recording -> normal bank -> core stage/registry/replay worker parity."""
import os,sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
OUT=ROOT/'output/condition_improvement'; os.environ['VIBRATION_RUNTIME_HOME']=str(OUT/'api_runtime')
import vibration.bootstrap
from vibration import ConditionedDiagnostic,ConditionedStage,VibrationAnalyzer,SignalBlock,AnalysisConfig
from vibration.condition_data import UosRotorCatalog
from vibration.server import Application
from vibration.stages import ClassifierStage


def main():
    p=json.loads((OUT/'matched_frozen.json').read_text(encoding='utf-8')); model=ConditionedDiagnostic(p)
    catalog=UosRotorCatalog(ROOT/'data/condition_improvement'); app=Application('local-verification'); checked=[]
    try:
        app.storage.save('classifier','conditioned-bank',p); app.models.load('conditioned-bank')
        for record_id in ('uos:H_H_16_6204_1000.mat','uos:U2_H_16_6204_1000.mat'):
            a,meta=catalog.load(record_id); a=a[:32000]; meta={**meta,'duration_seconds':2.,'id':record_id+'#source_window0'}
            c=AnalysisConfig(sample_rate_hz=16000,channels=1,window_seconds=2,unit='g',rpm=1000,model_enabled=True)
            analyzer=VibrationAnalyzer(c,stages={'conditioned':ConditionedStage(model),'registry':ClassifierStage(app.models)})
            result=analyzer.analyze(SignalBlock(a,16000,unit='g',channels=tuple(meta['channel_names']),rpm=1000,metadata=meta))
            expected=model.analyze(a,16000,1000,scope=meta,channel_names=meta['channel_names'])
            assert result.payload['conditioned']==result.payload['registry']==expected
            app.engine.replay(meta['id'],speed=8,loaded=(a,meta)); app.engine.configure({'model_enabled':True,'window_seconds':2})
            app.engine.replay(meta['id'],speed=8,loaded=(a,meta)); deadline=time.monotonic()+10
            while app.engine.latest is None and time.monotonic()<deadline: time.sleep(.02)
            assert app.engine.latest is not None and app.engine.latest['classification']==expected
            checked.append({'recording_id':record_id,'status':expected['status'],'label':expected['label']}); app.engine.stop()
        report={'status':'pass','raw_rates_to_common_band_core_registry_storage_replay_parity':checked,
            'new_test_recordings_reopened':0,'operational_use':False}
        (OUT/'api_integration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
    finally: app.close()

if __name__=='__main__': main()
