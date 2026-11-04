"""Measured-speed rotor features: harmonic power, directional ratios, absolute levels."""
from dataclasses import dataclass
from itertools import combinations
import numpy as np
from .dsp import channel_features,spectrum

ROTOR_SCHEMA='vibration.rotor_features.v1'
NORMAL_CHANGE_SCHEMA='vibration.rotor_normal_changes.v1'
ORDERS=(.5,1.,2.,3.,4.,5.,6.,8.,10.)


@dataclass(frozen=True)
class RotorFeatures:
    names: tuple
    values: np.ndarray
    sample_rate_hz: float
    rpm: float
    channel_names: tuple
    sample_count: int=0
    schema: str=ROTOR_SCHEMA


def rotor_features(values,sample_rate_hz,rpm,*,channel_names=None):
    """Requires RPM supplied independently of fault labels; no peak-based speed guessing.

    Band half-width is max(1.5 FFT bins, 3% shaft frequency). Bands that cannot
    resolve adjacent requested orders or exceed Nyquist are rejected.
    """
    a=np.asarray(values,dtype=float)
    if a.ndim==1: a=a[:,None]
    if a.ndim!=2 or len(a)<256 or a.shape[1]<1 or not np.isfinite(a).all() or np.max(np.abs(a))>1e12:
        raise ValueError('Finite N x C rotor samples are required.')
    if isinstance(sample_rate_hz,(bool,np.bool_)) or not np.isfinite(sample_rate_hz) or sample_rate_hz<=0:
        raise ValueError('Positive finite sample rate required.')
    if rpm is None or isinstance(rpm,(bool,np.bool_)) or not np.isscalar(rpm) or not np.isfinite(rpm) or rpm<=0:
        raise ValueError('Positive independently supplied RPM is required.')
    channels=tuple(channel_names if channel_names is not None else [f'ch{i+1}' for i in range(a.shape[1])])
    if len(channels)!=a.shape[1] or len(set(channels))!=len(channels) or not all(isinstance(c,str) and c for c in channels):
        raise ValueError('Unique channel names must match columns.')
    fr=rpm/60; df=sample_rate_hz/len(a); half=max(1.5*df,.03*fr)
    spacing=min(np.diff(ORDERS))*fr
    if 2*half>=spacing or ORDERS[-1]*fr+half>=sample_rate_hz/2:
        raise ValueError('Insufficient duration/bandwidth to resolve requested rotor orders.')
    names,legacy=channel_features(a,sample_rate_hz); out=legacy.tolist(); logs=[]; rms=[]
    for ch in range(a.shape[1]):
        x=a[:,ch]-a[:,ch].mean(); r=float(np.sqrt(np.mean(x*x)))
        if r<=1e-15: raise ValueError('Flat channel cannot supply rotor ratios.')
        rms.append(np.log(r)); f,_,psd=spectrum(x,sample_rate_hz); total=max(float(psd.sum()),1e-30)
        log=[]
        for order in ORDERS:
            energy=float(psd[np.abs(f-order*fr)<=half].sum())/total
            log.append(np.log(max(energy,1e-12)))
            names.append(f'ch{ch+1}_log_order_power_{order:g}X'); out.append(log[-1])
        logs.append(log)
        for i,order in enumerate(ORDERS):
            if order==1: continue
            names.append(f'ch{ch+1}_log_order_ratio_{order:g}X_to_1X'); out.append(log[i]-log[1])
    for first,second in combinations(range(a.shape[1]),2):
        names.append(f'ch{first+1}_to_ch{second+1}_log_rms_ratio'); out.append(rms[first]-rms[second])
        for i,order in enumerate(ORDERS):
            names.append(f'ch{first+1}_to_ch{second+1}_log_order_fraction_ratio_{order:g}X')
            out.append(logs[first][i]-logs[second][i])
    array=np.asarray(out,dtype=float)
    if not np.isfinite(array).all(): raise ValueError('Nonfinite rotor features.')
    array.setflags(write=False)
    return RotorFeatures(tuple(names),array,float(sample_rate_hz),float(rpm),channels,len(a))


def feature_indices(names,mode='combined'):
    """Explicit ablation groups; no label/trial/name-derived adaptive selection."""
    if mode=='legacy': selected=[i for i,n in enumerate(names) if '_order_' not in n and '_to_ch' not in n]
    elif mode=='relative': selected=[i for i,n in enumerate(names) if '_order_' in n or '_to_ch' in n]
    elif mode=='combined': selected=list(range(len(names)))
    else: raise ValueError('Unknown rotor feature mode.')
    if not selected: raise ValueError('Feature selection is empty.')
    return selected


extract_rotor_features=rotor_features
