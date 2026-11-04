"""High-frequency acquisition-overlap check; no fault model or threshold fitting.

Low cross-correlation does not prove independent installations. High/noise-level
matches invalidate a claim that two sample-rate domains are separate records.
"""
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import vibration.bootstrap
import numpy as np
from scipy import signal
from vibration.conditioned import canonical_values
from vibration.condition_data import UosRotorCatalog


def overlap(a,b):
    a=np.asarray(a).ravel(); b=np.asarray(b).ravel()
    same=np.array_equal(a,b)
    # Match raw-noise detail, not the expected shared periodic rotor harmonics.
    sos=signal.butter(6,[1000,3000],btype='bandpass',fs=8000,output='sos')
    left=signal.sosfiltfilt(sos,a); right=signal.sosfiltfilt(sos,canonical_values(b,16000,8000)[:,0])
    template=right[8000:40000]; template=template-template.mean(); length=len(template)
    energy=np.r_[0,np.cumsum(left*left)]; energies=energy[length:]-energy[:-length]
    corr=signal.fftconvolve(left,template[::-1],mode='valid')/np.sqrt(np.maximum(energies*np.sum(template*template),1e-100))
    peak=float(np.max(np.abs(corr)))
    return {'exact_raw_Data_duplicate':bool(same),'maximum_normalized_noise_overlap':peak,'passes_nonduplicate_screen':not same and peak<.98,
        'limit':.98,'caution':'Screen for duplicated/resampled noise only; independent reassembly is not established.'}


def main():
    data=ROOT/'data/condition_improvement'; catalog=UosRotorCatalog(data); results={}
    for rpm in (600,800,1000,1400,1600):
        a,_=catalog.load(f'uos:H_H_8_6204_{rpm}.mat'); b,_=catalog.load(f'uos:H_H_16_6204_{rpm}.mat')
        results[str(rpm)]=overlap(a,b); print(rpm,results[str(rpm)],flush=True)
    path=data/'metadata/source_sampling_overlap_check.json'; path.write_text(json.dumps(results,indent=2),encoding='utf-8')
    assert all(r['passes_nonduplicate_screen'] for r in results.values()),'Alternate-rate source records may overlap; do not claim independent final validation.'

if __name__=='__main__': main()
