"""Observe callback copy cost and Python-traced memory; not an RT or RSS guarantee."""
import argparse,json,platform,sys,time,tracemalloc
from pathlib import Path
import numpy as np


def run(*,installed=False):
    root=Path(__file__).resolve().parents[1]
    if not installed: sys.path.insert(0,str(root))
    import rotorvibe
    from rotorvibe import AnalysisConfig,SignalBlock,VibrationAnalyzer
    if installed and Path(rotorvibe.__file__).resolve().is_relative_to(root): raise ValueError('Installed package required.')
    fs=12000; t=np.arange(fs)/fs
    values=np.column_stack([np.sin(2*np.pi*(100+i*10)*t) for i in range(4)])
    block=SignalBlock(values,fs,unit='g'); config=AnalysisConfig(channels=4,unit='g')
    rows=[]
    for callbacks in (False,True):
        def stage(r): return {'rms':r.metrics['rms']}
        def sink(r): r.payload['metrics']['rms']=999
        analyzer=VibrationAnalyzer(config,stages={str(i):stage for i in range(4)} if callbacks else None,
                                  sinks=(sink,)*3 if callbacks else ())
        timings=[]; tracemalloc.start()
        for _ in range(24):
            begin=time.perf_counter(); result=analyzer.analyze(block); timings.append(time.perf_counter()-begin)
            assert result.metrics['rms']<999
        _,peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
        rows.append({'stage_count':4 if callbacks else 0,'sink_count':3 if callbacks else 0,
                     'processing_p95_s':float(np.quantile(timings,.95)),'peak_python_traced_bytes':peak,
                     'iterations':24,'all_mutations_isolated':True})
    return {'version':rotorvibe.__version__,'python':platform.python_version(),'platform':platform.system(),
            'sample_rate_hz':fs,'channels':4,'window_s':1,'cases':rows,'hard_realtime_guarantee':False,
            'memory_scope':'tracemalloc, not whole-process RSS; measured on this host'}


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--installed',action='store_true'); p.add_argument('--output'); args=p.parse_args()
    result=run(installed=args.installed); content=json.dumps(result,indent=2)+'\n'
    if args.output: Path(args.output).write_text(content,encoding='utf8')
    print(content)
