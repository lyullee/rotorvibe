"""Reproducible six-category verification. Synthetic probes are explicitly labelled.

Run with the project Python. No training and no changes to original datasets.
"""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import os
os.environ['VIBRATION_RUNTIME_HOME']=str(ROOT/'output/verification/runtime')
import vibration.bootstrap
import json, time, traceback, warnings, importlib.util
from datetime import datetime, timezone
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
from vibration import (AnalysisConfig, SignalBlock, VibrationAnalyzer, BearingGeometry,
                       BearingMap, BaselineStage, AlarmStage)
from vibration.dsp import spectrum
from vibration.adapters import from_process_batch, to_process_batch, condition_evidence

OUT=ROOT/'output/verification'; OUT.mkdir(parents=True,exist_ok=True)
CHECKS=[]
def check(category,name,fn):
    begin=time.perf_counter()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',RuntimeWarning)
            detail=fn()
        row={'category':category,'name':name,'status':'pass','detail':detail}
    except Exception:
        row={'category':category,'name':name,'status':'fail','traceback':traceback.format_exc()}
    row['elapsed_seconds']=time.perf_counter()-begin; CHECKS.append(row)
    print(f"{row['status'].upper()} [{category}] {name}",flush=True)
    if row['status']=='fail': print(row['traceback'],flush=True)

def rejects(fn):
    try: fn()
    except ValueError: return 'ValueError'
    raise AssertionError('Invalid input was accepted.')

def near(actual,expected,rtol=1e-9,atol=1e-12):
    np.testing.assert_allclose(actual,expected,rtol=rtol,atol=atol)
    return {'actual':float(actual),'expected':float(expected),'rtol':rtol,'atol':atol}

FS=12000
def wave(amplitude=2,n=FS,freq=100,fs=FS):
    return amplitude*np.sin(2*np.pi*freq*np.arange(n)/fs)
def cfg(**kwargs): return replace(AnalysisConfig(unit='m/s^2',window='boxcar'),**kwargs)
def result(amplitude=2,config=None,**kwargs):
    c=config or cfg()
    kwargs.setdefault('unit','V' if c.input_representation=='volts' else c.unit)
    return VibrationAnalyzer(c).analyze(SignalBlock(wave(amplitude,n=round(c.sample_rate_hz*c.window_seconds),fs=c.sample_rate_hz),c.sample_rate_hz,**kwargs))

def input_checks():
    for name,kw in [('zero_fs',{'sample_rate_hz':0}),('nan_fs',{'sample_rate_hz':float('nan')}),
                    ('missing_unit',{'unit':None}),('wrong_unit',{'unit':'mm/s'}),
                    ('nyquist_band',{'envelope_high_hz':6000}),('negative_rpm',{'rpm':-1}),
                    ('nan_gain_numpy',{'conditioner_gain':np.float32('nan')}),
                    ('boolean_channels',{'channels':True}),('string_fs',{'sample_rate_hz':'12000'}),
                    ('voltage_without_calibration',{'input_representation':'volts'}),
                    ('bad_sensitivity',{'sensitivity_mv_per_g':[0]}),('hop_longer_than_window',{'hop_seconds':2})]:
        check('input',name,lambda kw=kw:rejects(lambda:cfg(**kw).validate()))
    for name,fn in [
        ('unknown_setting',lambda:AnalysisConfig.create({'typo':1})),
        ('wrong_channel_count',lambda:VibrationAnalyzer(cfg()).analyze(SignalBlock(np.ones((FS,2)),FS,unit='m/s^2'))),
        ('mismatched_unit',lambda:result(unit='g')),
        ('wrong_window_length',lambda:VibrationAnalyzer(cfg()).analyze(SignalBlock(wave(n=1000),FS,unit='m/s^2'))),
        ('wrong_mask_length',lambda:SignalBlock(wave(),FS,valid=np.ones(2))),
        ('wrong_rpm_trace_length',lambda:SignalBlock(wave(),FS,rpm=np.ones(2))),
        ('missing_bearing_provider',lambda:result(config=cfg(bearing_id='unknown',rpm=1800)))]:
        check('input',name,lambda fn=fn:rejects(fn))
    def unknown_units():
        r=result(config=cfg(unit='unknown'))
        assert r.valid and r.metrics['velocity_rms_mm_s'] is None
        return 'Unknown unit stays explicit; absolute velocity unavailable.'
    check('input','unknown_unit_no_absolute_velocity',unknown_units)
    def invalid_signal():
        a=wave(); a[50]=np.nan
        r=VibrationAnalyzer(cfg()).analyze(SignalBlock(a,FS,unit='m/s^2'))
        assert not r.valid and not r.metrics
        return r.to_dict(include_features=False)
    check('input','nan_sample_not_healthy',invalid_signal)

def formula_checks():
    check('formula','sine_rms',lambda:near(result().metrics['rms'],2/np.sqrt(2)))
    check('formula','sine_peak',lambda:near(result().metrics['peak'],2))
    check('formula','sine_crest',lambda:near(result().metrics['crest_factor'],np.sqrt(2)))
    check('formula','sine_kurtosis',lambda:near(result().metrics['kurtosis'],1.5))
    def dc():
        a=wave()+3; r=VibrationAnalyzer(cfg()).analyze(SignalBlock(a,FS,unit='m/s^2'))
        near(r.metrics['mean'],3); near(r.metrics['rms_raw'],np.sqrt(11)); near(r.metrics['rms'],np.sqrt(2))
        return {'mean':r.metrics['mean'],'raw_rms':r.metrics['rms_raw']}
    check('formula','dc_and_ac_separation',dc)
    for window in ('boxcar','hann','hamming'):
        def fft(window=window):
            f,a,p=spectrum(wave(),FS,window)
            near(f[np.argmax(a)],100); near(a.max(),2); near(p.sum()*(f[1]-f[0]),2)
            return {'peak_hz':float(f[np.argmax(a)]),'amplitude':float(a.max()),'integrated_psd':float(p.sum())}
        check('formula','fft_and_psd_'+window,fft)
    def nyquist():
        f,a,p=spectrum(3*(-1.)**np.arange(1024),1024,'boxcar')
        near(a[-1],3); near(p.sum(),9)
        f,a,p=spectrum(np.cos(2*np.pi*100*np.arange(1025)/1025),1025,'boxcar')
        near(a.max(),1)
        return 'Even Nyquist and odd-length one-sided scaling checked.'
    check('formula','fft_even_odd_edges',nyquist)
    check('formula','velocity_psd_integration',lambda:near(result().metrics['velocity_rms_mm_s'],2/np.sqrt(2)/(2*np.pi*100)*1000))
    def bearing():
        actual=BearingGeometry(8,10,50).frequencies(1800)
        expected={'BPFI':144,'BPFO':96,'FTF':12,'BSF':72,'2BSF':144}
        for key,value in expected.items(): near(actual[key],value)
        return actual
    check('formula','bearing_hand_calculation',bearing)
    def voltage():
        c=cfg(input_representation='volts',sensitivity_mv_per_g=[100],conditioner_gain=2,unit='g')
        r=result(.4,config=c)
        return near(r.metrics['rms'],np.sqrt(2))
    check('formula','volts_to_g',voltage)
    def envelope():
        t=np.arange(FS)/FS; a=(1+.4*np.cos(2*np.pi*100*t))*np.cos(2*np.pi*2000*t)
        r=VibrationAnalyzer(cfg()).analyze(SignalBlock(a,FS,unit='m/s^2'))
        s=r.payload['envelope_spectrum']; peak=float(s['x'][np.argmax(s['y'])])
        near(peak,100); return {'envelope_peak_hz':peak}
    check('formula','am_envelope_frequency',envelope)

def extreme_checks():
    for amp in (1e-12,1e-6,1e6,1e12):
        def scale(amp=amp):
            r=result(amp); assert r.valid
            near(r.metrics['rms'],amp/np.sqrt(2),atol=amp*1e-9)
            near(r.metrics['kurtosis'],1.5); near(r.metrics['crest_factor'],np.sqrt(2))
            json.dumps(r.to_dict(),allow_nan=False)
            return {'amplitude':amp,'kurtosis':r.metrics['kurtosis']}
        check('extreme','scale_'+str(amp),scale)
    for name,amp in [('zero',0),('subnormal',1e-200),('too_large',1e13)]:
        def invalid(amp=amp):
            r=result(amp); assert not r.valid; json.dumps(r.to_dict(),allow_nan=False)
            return r.payload
        check('extreme',name+'_explicit_invalid',invalid)
    check('extreme','very_high_rpm',lambda:rejects(lambda:SignalBlock(wave(),FS,rpm=1e308)))
    def minimum():
        c=cfg(sample_rate_hz=100,window_seconds=2.56,hop_seconds=.02,envelope_low_hz=5,envelope_high_hz=40,velocity_low_hz=1,velocity_high_hz=40)
        a=np.sin(2*np.pi*10*np.arange(256)/100)
        r=VibrationAnalyzer(c).analyze(SignalBlock(a,100,unit='m/s^2'))
        assert r.valid; return len(r.payload['spectrum']['x'])
    check('extreme','minimum_fs_and_window',minimum)
    def calibration():
        r=result(config=cfg(input_representation='volts',sensitivity_mv_per_g=[1e-300]))
        assert not r.valid; return r.payload
    check('extreme','tiny_calibration_sensitivity',calibration)

def connection_checks():
    def stream():
        c=cfg(); a=wave(n=36000); analyzer=VibrationAnalyzer(c); rows=[]
        start=0
        for seq,size in enumerate((137,4173,219,8000,23471)):
            rows+=analyzer.push(SignalBlock(a[start:start+size],FS,unit=c.unit,start_time_s=start/FS,sequence=seq,episode_id='e1',metadata={'asset':'A'})); start+=size
        assert len(rows)==9
        direct=VibrationAnalyzer(c)
        for i,r in enumerate(rows):
            near(r.metrics['rms'],direct.analyze(SignalBlock(a[i*3000:i*3000+12000],FS,unit=c.unit)).metrics['rms'])
            near(r.start_time_s,i*.25)
            assert r.episode_id=='e1' and r.metadata['source']['asset']=='A'
        return {'windows':len(rows),'starts':[r.start_time_s for r in rows]}
    check('connection','chunked_vs_direct_and_identifiers',stream)
    for boundary in ('time','episode','sequence'):
        def gap(boundary=boundary):
            a=VibrationAnalyzer(cfg()); a.push(SignalBlock(wave(n=6000),FS,unit='m/s^2',sequence=0))
            opts={'start_time_s':.5,'episode_id':'default','sequence':1}
            opts.update({'time':{'start_time_s':2},'episode':{'episode_id':'new'},'sequence':{'sequence':5}}[boundary])
            assert a.push(SignalBlock(wave(n=6000),FS,unit='m/s^2',**opts))==[]
            return 'Partial pre-boundary samples discarded.'
        check('connection','boundary_'+boundary,gap)
    def dependency_chain():
        received=[]
        a=VibrationAnalyzer(cfg(),stages={'first':lambda r:{'asset':'machine-A','value':r.metrics['rms']},
                                        'second':lambda r:{'upstream':r.payload['first']['value']}},sinks=(received.append,))
        r=a.analyze(SignalBlock(wave(),FS,unit='m/s^2'))
        assert received[0] is r; near(r.payload['second']['upstream'],np.sqrt(2))
        return condition_evidence(r,asset_id='machine-A')['asset_id']
    check('connection','stages_sink_and_asset_evidence',dependency_chain)
    def source_contract():
        path=ROOT/'docs/integration/upstream/contracts.py.source.txt'
        spec=importlib.util.spec_from_loader('verified_upstream_contract',loader=None)
        module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module
        exec(compile(path.read_text(encoding='utf-8'),str(path),'exec'),module.__dict__)
        module.__path__=[]; sys.modules['process_monitoring']=module
        c=cfg(); a=VibrationAnalyzer(c)
        rows=a.push(SignalBlock(wave(n=18000),FS,unit=c.unit,clock_id='daq',episode_id='A'))
        b=to_process_batch(rows)
        assert b.values.shape==(3,7) and b.valid.shape==b.values.shape and b.metadata['clock_id']=='daq'
        raw=module.SignalBatch(np.arange(FS)/FS,wave()[:,None],('acc',),units=('m/s^2',))
        restored=from_process_batch(raw,sample_rate_hz=FS,clock_id='daq')
        near(VibrationAnalyzer(c).analyze(restored).metrics['rms'],np.sqrt(2))
        bad=replace(raw,time_s=np.arange(FS)/FS*2)
        rejects(lambda:from_process_batch(bad,sample_rate_hz=FS,clock_id='daq'))
        return {'upstream_commit':'79b4cf52a0acd0d0cbd3addbe82c3d98d6385e5a','feature_shape':list(b.values.shape),'scope':'Actual upstream SignalBatch contract snapshot; not full Monitor pipeline.'}
    check('connection','actual_upstream_signalbatch_contract',source_contract)

def regression_checks():
    def baseline_alarm():
        c=cfg(hop_seconds=1); baseline=BaselineStage(c); baseline.begin('verified_normal',20)
        alarm=AlarmStage(persistence_seconds=0,release_seconds=0)
        a=VibrationAnalyzer(c,stages={'baseline':baseline,'alarm':alarm})
        rows=[]
        for i in range(22): rows+=a.push(SignalBlock(wave(),FS,unit=c.unit,start_time_s=i))
        assert rows[-1].payload['alarm']['level']=='normal'
        profile=baseline.export_profile(); assert profile['summary']['windows']==20
        high=a.push(SignalBlock(wave(200),FS,unit=c.unit,start_time_s=22))[0]
        assert high.payload['alarm']['level']=='danger'
        bad=np.full(FS,np.nan); invalid=a.push(SignalBlock(bad,FS,unit=c.unit,start_time_s=23))[0]
        assert invalid.payload['alarm']['level']=='unavailable' and invalid.payload['alarm']['retained_level']=='danger'
        imported=BaselineStage(c,profile=json.loads(json.dumps(profile)))
        assert imported(high)['status']=='ready'
        incompatible=replace(high,metadata={'measurement':cfg(unit='g').to_dict()})
        assert imported(incompatible)['status']=='incompatible'
        return {'normal':rows[-1].payload['alarm'],'high':high.payload['alarm'],'invalid':invalid.payload['alarm']}
    check('regression','baseline_profile_alarm_invalid_and_reload',baseline_alarm)
    def order():
        r=result(config=cfg(rpm=1800),rpm=np.full(FS,1800.))
        assert r.payload['order_spectrum']['mode']=='angle_resampled_from_rpm_trace'
        s=r.payload['order_spectrum']; near(s['x'][np.argmax(s['y'])],100/30,rtol=.011)
        return r.payload['order_spectrum']['mode']
    check('regression','rpm_trace_order_tracking',order)
    def history():
        from vibration.storage import Storage
        s=Storage(); s.save('verification','profile',{'summary':{'ok':True}})
        assert s.get('verification','profile')['summary']['ok'] is True
        s.db.close(); return 'SQLite document round trip in isolated verification runtime.'
    check('regression','sqlite_documents',history)
    def old_schema():
        c=cfg(); b=BaselineStage(c); b.begin('legacy',20)
        r=result()
        for _ in range(20): b(r)
        p=b.export_profile(); p['signature'].pop('feature_schema')
        assert BaselineStage(c,profile=p)(r)['status']=='incompatible'
        from vibration.models import ModelRegistry
        registry=ModelRegistry(None,None); registry.active={'name':'legacy'}
        assert registry.classify(r.features,cfg(model_enabled=True),{})['status']=='incompatible'
        return 'Pre-fix baseline/model profiles are rejected instead of silently reused.'
    check('regression','old_feature_schema_rejected',old_schema)
    def persistence():
        a=AlarmStage(persistence_seconds=2,release_seconds=3,max_gap_seconds=2)
        base=result()
        def observation(t,score,valid=True):
            return a(replace(base,end_time_s=t,valid=valid,payload={'baseline':{'score':score}}))
        assert observation(1,10)['level']=='unavailable'
        assert observation(2,10)['level']=='unavailable'
        assert observation(3,10)['level']=='danger'
        assert observation(4,0)['level']=='danger'
        assert observation(5,0,False)['retained_level']=='danger'
        assert observation(6,0)['level']=='danger'
        assert observation(7,0)['level']=='danger'
        assert observation(8,0)['level']=='danger'
        assert observation(9,0)['level']=='normal'
        assert observation(20,10)['level']=='normal'
        assert observation(21,10)['level']=='normal'
        assert observation(22,10)['level']=='danger'
        return 'Measured elapsed persistence/recovery; invalid and long gaps interrupt pending transitions.'
    check('regression','alarm_elapsed_persistence_recovery',persistence)
    def varying_speed():
        fs=12000; rpm=1200+1200*np.arange(fs)/fs
        revolutions=np.cumsum(rpm)/(60*fs)
        a=np.cos(2*np.pi*5*revolutions)
        r=VibrationAnalyzer(cfg()).analyze(SignalBlock(a,fs,unit='m/s^2',rpm=rpm))
        s=r.payload['order_spectrum']; i=np.argmax(s['y'])
        near(s['x'][i],5,rtol=.01)
        return {'expected_order':5,'measured_order':float(s['x'][i]),'rpm_start':float(rpm[0]),'rpm_end':float(rpm[-1])}
    check('regression','variable_speed_five_order_resampling',varying_speed)

def end_to_end_checks():
    def real_files():
        from vibration.datasets import DatasetCatalog
        from vibration.bearings import Bearings
        catalog=DatasetCatalog(); observations=[]
        for dataset in ('CWRU','Paderborn','IMS','Brito','KAIST','FEMTO'):
            item=next(r for r in catalog.rows if r['dataset']==dataset)
            a,meta=catalog.load(item['id'])
            fs=meta['sample_rate_hz']
            c=AnalysisConfig().for_source(fs,a.shape[1],len(a)/fs,meta['unit'],meta.get('rpm'),meta.get('bearing_id'))
            n=round(c.window_seconds*fs)
            r=VibrationAnalyzer(c,bearing_provider=Bearings()).analyze(SignalBlock(a[:n],fs,unit=c.unit,metadata=meta))
            assert r.valid and np.isfinite(r.features).all()
            json.dumps(r.to_dict(),allow_nan=False)
            observations.append({'dataset':dataset,'record':item['id'],'shape':list(a.shape),'sample_rate_hz':fs,'unit':c.unit,'rms':r.metrics['rms']})
        return observations
    check('end_to_end','six_real_dataset_readers_to_analysis',real_files)
    def http():
        import threading, urllib.request, urllib.error
        from http.server import ThreadingHTTPServer
        from vibration.server import Application,Handler
        app=Application('verification-token'); server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        server.app=app; server.daemon_threads=True
        worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
        base=f'http://127.0.0.1:{server.server_address[1]}'
        def request(path,payload=None,token='verification-token'):
            req=urllib.request.Request(base+path,data=None if payload is None else json.dumps(payload).encode(),headers={'X-API-Key':token,'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=15) as response:
                body=response.read(); return json.loads(body) if response.headers.get_content_type()=='application/json' else body
        try:
            assert b'<html' in request('/').lower()
            try: request('/api/state',token='wrong')
            except urllib.error.HTTPError as e: assert e.code==401
            else: raise AssertionError('Unauthorized request accepted')
            request('/api/live/start',{'config':cfg().to_dict()})
            request('/api/ingest',{'samples':wave().tolist(),'sample_rate_hz':FS,'unit':'m/s^2','sequence':0})
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                latest=request('/api/latest')
                if latest and latest.get('metrics'): break
                time.sleep(.05)
            else: raise AssertionError('No live analysis frame.')
            near(latest['metrics']['rms'],np.sqrt(2))
            history=request('/api/history?kind=frames&session='+latest['session_id'])
            assert history and history[0]['session_id']==latest['session_id']
            near(history[0]['payload']['metrics']['rms'],np.sqrt(2))
            exported=request('/api/export?session='+latest['session_id'])
            assert exported['frames']
            request('/api/stop',{})
            return {'transport':'loopback HTTP with API key','rms':latest['metrics']['rms'],'session_id':latest['session_id'],'ui_html_served':True}
        finally:
            server.shutdown(); server.server_close(); worker.join(timeout=2)
            app.close()
    check('end_to_end','http_ingest_worker_dsp_sqlite_result',http)

if __name__=='__main__':
    start=datetime.now(timezone.utc).isoformat()
    input_checks(); formula_checks(); extreme_checks(); connection_checks(); regression_checks(); end_to_end_checks()
    report={'started_utc':start,'finished_utc':datetime.now(timezone.utc).isoformat(),
            'python':sys.version,'numpy':np.__version__,'checks':CHECKS,
            'passed':sum(r['status']=='pass' for r in CHECKS),'failed':sum(r['status']=='fail' for r in CHECKS),
            'scope':'Engineering software verification, not field diagnostic accuracy or RUL validation. No classifier training.'}
    (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"RESULT: {report['passed']} passed / {report['failed']} failed",flush=True)
    sys.exit(bool(report['failed']))
