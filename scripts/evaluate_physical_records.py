"""Predeclared public-bench frequency-consistency probe, not classifier accuracy.

Records: first CWRU record of each of three fault types in record index order.
First one-second window; Hann; envelope 500..5000 Hz; strongest 20 local maxima
above 20 Hz, picked WITHOUT giving fault frequencies to the peak picker.
Support criterion: >=2 of the first 4 expected harmonics independently match
one of those maxima within max(2 Hz, 3%). Parameters are not tuned per record.
"""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import vibration.bootstrap
import numpy as np
from scipy.signal import find_peaks
from vibration import AnalysisConfig,SignalBlock,VibrationAnalyzer
from vibration.datasets import DatasetCatalog
from vibration.bearings import Bearings

def main():
    catalog=DatasetCatalog(); bearings=Bearings(); results=[]
    for fault,component in [('inner_race','BPFI'),('outer_race','BPFO'),('rolling_element','2BSF')]:
        row=next(r for r in catalog.rows if r['dataset']=='CWRU' and r['fault']==fault)
        samples,meta=catalog.load(row['id']); fs=meta['sample_rate_hz']
        c=AnalysisConfig().for_source(fs,samples.shape[1],len(samples)/fs,meta['unit'],meta['rpm'],None)
        # No bearing/fault target is passed into the analyzer in this probe.
        r=VibrationAnalyzer(c).analyze(SignalBlock(samples[:round(fs)],fs,unit=c.unit))
        env=r.payload['envelope_spectrum']; f=env['x']; a=env['y']; df=f[1]-f[0]
        peaks,_=find_peaks(a); peaks=peaks[f[peaks]>=20]
        peaks=peaks[np.argsort(a[peaks])[-20:][::-1]]
        target=bearings.frequencies(meta['bearing_id'],meta['rpm'])[component]
        matches=[]; used=set()
        for h in range(1,5):
            expected=target*h; tolerance=max(2*df,.03*expected)
            eligible=[int(i) for i in peaks if int(i) not in used and abs(f[i]-expected)<=tolerance]
            selected=min(eligible,key=lambda i:abs(f[i]-expected)) if eligible else None
            if selected is not None: used.add(selected)
            matches.append({'harmonic':h,'expected_hz':expected,'observed_hz':float(f[selected]) if selected is not None else None,
                            'tolerance_hz':tolerance,'matched':selected is not None})
        matched=sum(x['matched'] for x in matches)
        results.append({'record':row['id'],'ground_truth_fault':fault,'evaluated_frequency':component,
                        'rpm':meta['rpm'],'bearing_id':meta['bearing_id'],'unit':meta['unit'],
                        'top_peaks_hz':[float(f[i]) for i in peaks],'matches':matches,
                        'matched_harmonics':matched,'criterion_met':matched>=2})
    report={'protocol':__doc__,'records':results,'criterion_met':sum(x['criterion_met'] for x in results),
            'total':len(results),'limitations':'Three selected one-second public test-rig windows. No normal controls, statistical diagnosis accuracy, field sensor calibration or wear-rate/RUL validation.'}
    out=ROOT/'output/physics_verification/public_bench_observations.json'
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))

if __name__=='__main__': main()
