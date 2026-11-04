"""Synthetic throughput/queue timing on this machine; not a hard realtime qualification."""
from pathlib import Path
import argparse,json,platform,sys,time
import numpy as np


def run(*,installed=False):
    root=Path(__file__).resolve().parents[1]
    if not installed: sys.path.insert(0,str(root))
    from rotorvibe import AnalysisConfig,SignalBlock,VibrationAnalyzer,RealtimeProcessor
    import rotorvibe
    if installed and Path(rotorvibe.__file__).resolve().is_relative_to(root): raise ValueError('Installed package required')
    results=[]
    for fs,channels in ((4000,1),(12000,1),(12000,4),(48000,4)):
        config=AnalysisConfig(sample_rate_hz=fs,channels=channels,unit='m/s^2',rpm=1200,
            envelope_low_hz=min(500,fs*.1),envelope_high_hz=min(5000,fs*.45),
            velocity_high_hz=min(1000,fs*.4))
        processor=RealtimeProcessor(VibrationAnalyzer(config),max_pending=4,latency_budget_seconds=.25)
        t=np.arange(fs)/fs
        samples=np.column_stack([.2*np.sin(2*np.pi*(20+ch*10)*t) for ch in range(channels)])
        start=time.perf_counter()
        for index in range(24):
            processor.submit(SignalBlock(samples,fs,unit='m/s^2',rpm=1200,start_time_s=index,sequence=index))
            if index%4==3: processor.drain()
        processor.drain(); elapsed=time.perf_counter()-start
        stats=processor.stats(); processor.close()
        results.append({'sample_rate_hz':fs,'channels':channels,'input_seconds':24,'elapsed_wall_seconds':elapsed,
                        'input_to_wall_ratio':24/elapsed,'stats':stats})
    return {'schema':'vibration.benchmark.v1','python':platform.python_version(),'platform':platform.system(),
            'version':rotorvibe.__version__,'cases':results,'input':'synthetic; 4 queued 1-second chunks per burst',
            'qualification':'observed on this machine only, no field or OS scheduling guarantee'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--installed',action='store_true'); parser.add_argument('--output')
    args=parser.parse_args(); result=run(installed=args.installed); content=json.dumps(result,indent=2)+'\n'
    if args.output: Path(args.output).write_text(content,encoding='utf8')
    print(content)
