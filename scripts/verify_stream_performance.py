"""Synthetic-data throughput/memory observation, not a real-time guarantee."""
import sys,json,time,tracemalloc,gc
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import vibration.bootstrap
import numpy as np
from vibration import AnalysisConfig,SignalBlock,VibrationAnalyzer

def main():
    results=[]
    for fs,channels in ((12000,1),(25600,4)):
        c=AnalysisConfig(sample_rate_hz=fs,channels=channels,unit='m/s^2')
        analyzer=VibrationAnalyzer(c); timings=[]; windows=0; midpoint=0
        for i in range(120):
            t=i+np.arange(fs)/fs
            a=(np.sin(2*np.pi*100*t)+.1*np.cos(2*np.pi*1300*t))[:,None].repeat(channels,axis=1)
            started=time.perf_counter(); rows=analyzer.push(SignalBlock(a,fs,unit='m/s^2',start_time_s=i,sequence=i))
            timings.append((time.perf_counter()-started)*1000/max(1,len(rows))); windows+=len(rows)
            assert len(analyzer._a)<round(fs*c.window_seconds)
            for row in rows:
                assert row.valid and np.isfinite(row.features).all()
                np.testing.assert_allclose(row.metrics['rms'],np.sqrt(.505),rtol=1e-9)
        # Measure allocations separately so the tracer does not distort latency.
        analyzer.reset(); tracemalloc.start()
        for i in range(20):
            t=i+np.arange(fs)/fs
            a=(np.sin(2*np.pi*100*t)+.1*np.cos(2*np.pi*1300*t))[:,None].repeat(channels,axis=1)
            rows=analyzer.push(SignalBlock(a,fs,unit='m/s^2',start_time_s=i,sequence=i))
            if i==9: gc.collect(); midpoint=tracemalloc.get_traced_memory()[0]
        gc.collect(); current,peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
        assert windows==477
        assert current-midpoint<4*1024*1024,'Unexpected continuing memory growth in fixed-size stream.'
        results.append({'sample_rate_hz':fs,'channels':channels,'data_seconds':120,'windows':windows,
            'per_window_p50_ms':float(np.quantile(timings,.5)),'per_window_p95_ms':float(np.quantile(timings,.95)),
            'per_window_max_ms':max(timings),'tracemalloc_peak_MiB':peak/1024**2,'second_half_memory_growth_MiB':(current-midpoint)/1024**2,
            'memory_observation_seconds':20,'p95_below_250ms_hop':bool(np.quantile(timings,.95)<250),
            'note':'Latency measured without allocation tracing; memory measured in a separate 20s stream. Synthetic steady input, local Windows run, not hardware real-time certification.'})
    out=ROOT/'output/release_verification'; out.mkdir(parents=True,exist_ok=True)
    (out/'stream_performance.json').write_text(json.dumps({'status':'pass','profiles':results},indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))

if __name__=='__main__': main()
