"""Actual replay worker + registry + storage parity for the new diagnostic."""
import sys,os,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
OUT=ROOT/'output/two_stage'; os.environ['VIBRATION_RUNTIME_HOME']=str(OUT/'service_runtime')
import vibration.bootstrap
import numpy as np
from vibration.server import Application
from vibration.two_stage import TwoStageDiagnostic
from vibration import AnalysisConfig,VibrationAnalyzer,TwoStageStage,SignalBlock
from vibration.independent_data import IndependentRotorCatalog


def main():
    profile=json.loads((OUT/'model_relative.json').read_text(encoding='utf-8')); model=TwoStageDiagnostic(profile)
    app=Application('local-verification'); checks=[]
    try:
        app.storage.save('classifier','two-stage-relative',profile); app.models.load('two-stage-relative')
        for trial in (17,16,19,20):
            record=next(r for r in app.catalog.rows if r['dataset']=='Brito' and app.catalog.records[r['id']][2]['trial_id']==trial)
            a,meta=app.catalog.load(record['id']); app.engine.replay(record['id'],speed=8)
            # Existing service intentionally disables classification on source changes.
            app.engine.configure({'model_enabled':True}); app.engine.replay(record['id'],speed=8)
            deadline=time.monotonic()+10
            while app.engine.latest is None and time.monotonic()<deadline: time.sleep(.02)
            assert app.engine.latest is not None,app.engine.state()
            actual=app.engine.latest['classification']; expected=model.analyze(a,25000,1238,scope=meta,channel_names=meta['channel_names'])
            assert actual==expected,(actual,expected)
            checks.append({'trial':trial,'status':actual['status'],'label':actual['label'],'engine_ms':app.engine.latest['analysis_ms']})
            app.engine.stop()
        c=AnalysisConfig(sample_rate_hz=25000,channels=4,rpm=1238)
        analyzer=VibrationAnalyzer(c,stages={'diagnostic':TwoStageStage(model)})
        block=SignalBlock(a,25000,channels=tuple(meta['channel_names']),rpm=1238,metadata=meta)
        latency=[]
        for _ in range(30):
            start=time.perf_counter(); analyzer.analyze(block); latency.append((time.perf_counter()-start)*1000)
        external=IndependentRotorCatalog(ROOT/'data/normal_independent')
        row=next(r for r in external.rows(role='source_validation',normal_only=True) if r['speed_rpm']=='600')
        a,meta=external.load(row['id'])
        newprofile=json.loads((OUT/'cross_speed_600_frozen.json').read_text(encoding='utf-8')); app.models.use_two_stage(newprofile)
        app.engine.replay(row['id'],speed=8,loaded=(a,meta)); app.engine.configure({'model_enabled':True})
        app.engine.replay(row['id'],speed=8,loaded=(a,meta)); deadline=time.monotonic()+10
        while app.engine.latest is None and time.monotonic()<deadline: time.sleep(.02)
        assert app.engine.latest is not None
        expected=TwoStageDiagnostic(newprofile).analyze(a,25600,600,scope=meta,channel_names=meta['channel_names'])
        assert app.engine.latest['classification']==expected
        report={'status':'pass','replay_worker_storage_parity':checks,'diagnostic_stage_latency_ms':{'p50':float(np.median(latency)),'p95':float(np.quantile(latency,.95))},
                'independent_reader_loaded_replay_parity':{'dataset':'CrossSpeed2026','role':'source_validation','status':expected['status']},
                'scope':'30 local repeated 1s/4ch/25kHz windows; not a hardware real-time guarantee','operational_use':False}
        (OUT/'service_integration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
    finally: app.close()

if __name__=='__main__': main()
