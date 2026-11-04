# Numerical conventions: demeaned AC metrics, window-gain-corrected one-sided FFT,
# window-energy-normalized PSD, and explicit band-limited integration.
# Display compaction is separate from quantitative raw-window stage inputs.

import numpy as np
from scipy import signal

G0=9.80665


def spectrum(x, fs, window='hann'):
    x=np.asarray(x,dtype=float)
    w=signal.get_window(window,len(x),fftbins=True)
    z=np.fft.rfft((x-x.mean())*w)
    factors=np.full(len(z),2.0); factors[0]=1
    if len(x)%2==0: factors[-1]=1
    amp=np.abs(z)/w.sum()*factors
    psd=np.abs(z)**2/(fs*np.sum(w*w))*factors
    return np.fft.rfftfreq(len(x),1/fs),amp,psd


def compact_spectrum(f, a, maximum=1800, *, native=False):
    if native: return {'x':f,'y':a}
    if len(f)<=maximum:
        return {'x':f.tolist(),'y':a.tolist()}
    edges=np.linspace(0,len(f),maximum+1,dtype=int)
    indices=[lo+int(np.argmax(a[lo:hi])) for lo,hi in zip(edges[:-1],edges[1:]) if hi>lo]
    return {'x':f[indices].tolist(),'y':a[indices].tolist()}


def waveform(x, fs, maximum=1600, *, native=False):
    if native: return {'x':np.arange(len(x))/fs,'y':x.copy()}
    if len(x)<=maximum:
        indices=np.arange(len(x))
    else:
        edges=np.linspace(0,len(x),maximum//2+1,dtype=int)
        indices=[]
        for lo,hi in zip(edges[:-1],edges[1:]):
            block=x[lo:hi]
            if len(block): indices.extend(sorted([lo+int(np.argmin(block)),lo+int(np.argmax(block))]))
        indices=np.asarray(indices,dtype=int)
    return {'x':(indices/fs).tolist(),'y':x[indices].tolist()}


def channel_features(data, fs):
    """Fixed feature contract shared by live inference and optional supervised fitting."""
    a=np.asarray(data,dtype=float)
    if a.ndim==1: a=a[:,None]
    names=[]; values=[]
    for ch in range(a.shape[1]):
        x=a[:,ch]-a[:,ch].mean()
        rms=float(np.sqrt(np.mean(x*x)))
        normalized=x/rms if rms>0 else np.zeros_like(x)
        crest=float(np.max(np.abs(normalized)))
        kurt=float(np.mean(normalized**4))
        f,_,p=spectrum(x,fs)
        total=float(p.sum())
        features=[np.log(max(rms,np.finfo(float).tiny)),np.log(max(crest,1e-12)),min(kurt,1e5)]
        labels=['log_rms','log_crest','kurtosis']
        for lo,hi in [(10,100),(100,500),(500,2000),(2000,10000)]:
            power=float(p[(f>=lo)&(f<min(hi,fs/2))].sum())/total if total>0 else 0
            features.append(np.log(max(power,1e-12))); labels.append(f'log_fraction_{lo}_{hi}')
        names.extend([f'ch{ch+1}_{n}' for n in labels]); values.extend(features)
    return names,np.asarray(values,dtype=float)


def peak_evidence(f, amplitude, target, tolerance_ratio, resolution, *, spacing_hz=None):
    tolerance=max(target*tolerance_ratio,2*resolution)
    if spacing_hz is not None and 2*tolerance>=spacing_hz:
        return {'expected_hz':float(target),'observed_hz':None,'amplitude':None,
                'local_contrast_db':None,'tolerance_hz':float(tolerance),'detected':False,
                'resolvable':False,'reason':'Harmonic search bands overlap at this duration/RPM; use a longer window.'}
    mask=(f>=max(resolution,target-tolerance))&(f<=target+tolerance)
    if not mask.any(): return None
    indices=np.flatnonzero(mask); i=int(indices[np.argmax(amplitude[indices])])
    neighborhood=(f>=max(resolution,target-5*tolerance))&(f<=target+5*tolerance)&(~mask)
    floor=float(np.median(amplitude[neighborhood])) if neighborhood.any() else float(np.median(amplitude[1:]))
    snr=20*np.log10(max(float(amplitude[i]),1e-15)/max(floor,1e-15))
    return {'expected_hz':float(target),'observed_hz':float(f[i]),'amplitude':float(amplitude[i]),
            'local_contrast_db':float(snr),'tolerance_hz':float(tolerance),'detected':bool(snr>=8)}


def analyze(data, config, rpm_trace=None, bearing_frequencies=None, *, native=False):
    a=np.asarray(data,dtype=float)
    if a.ndim==1: a=a[:,None]
    if len(a)<256 or not np.isfinite(a).all() or np.max(np.abs(a))>1e12:
        raise ValueError('분석 창이 부족하거나 비정상 수치가 있습니다.')
    x=a[:,config.channel]; ac=x-x.mean(); fs=config.sample_rate_hz
    f,amp,psd=spectrum(x,fs,config.window)
    resolution=fs/len(x)
    rms=float(np.sqrt(np.mean(ac*ac))); raw_rms=float(np.sqrt(np.mean(x*x)))
    peak=float(np.max(np.abs(ac)))
    normalized=ac/rms if rms>0 else np.zeros_like(ac)
    kurt=float(np.mean(normalized**4))
    sos=signal.butter(4,[config.envelope_low_hz,config.envelope_high_hz],btype='bandpass',fs=fs,output='sos')
    carrier=signal.sosfiltfilt(sos,ac)
    envelope=np.abs(signal.hilbert(carrier))
    ef,ea,ep=spectrum(envelope,fs,config.window)
    bands=[]
    for lo,hi in [(10,100),(100,500),(500,2000),(2000,10000)]:
        end=min(hi,fs/2)
        power=float(psd[(f>=lo)&(f<end)].sum()*resolution) if end>lo else None
        bands.append({'low_hz':lo,'high_hz':end,'power':power})
    velocity=None
    if config.unit in ['g','m/s^2']:
        scale=G0 if config.unit=='g' else 1
        mask=(f>=config.velocity_low_hz)&(f<=config.velocity_high_hz)
        velocity=float(np.sqrt(np.sum(psd[mask]*scale**2/(2*np.pi*f[mask])**2)*resolution)*1000)
    metrics={'rms':rms,'rms_raw':raw_rms,'mean':float(x.mean()),'peak':peak,
             'peak_to_peak':float(x.max()-x.min()),'crest_factor':float(np.max(np.abs(normalized))),
             'kurtosis':kurt,'skewness':float(np.mean(normalized**3)),
             'velocity_rms_mm_s':velocity,'envelope_rms':float(np.sqrt(np.mean((envelope-envelope.mean())**2))),
             'band_power':bands,'unit':config.unit,'definitions':'RMS/peak are AC; rms_raw includes DC; kurtosis is Pearson (Gaussian=3). Velocity is band-limited PSD integration.'}
    rpm=config.rpm
    order=None
    if rpm_trace is not None and len(rpm_trace)==len(x) and np.isfinite(rpm_trace).all() and np.min(rpm_trace)>0:
        rpm=float(np.mean(rpm_trace))
        if config.order_tracking:
            revolutions=np.cumsum(rpm_trace)/(60*fs)
            theta=np.linspace(revolutions[0],revolutions[-1],len(x))
            angular=np.interp(theta,revolutions,ac)
            of,oa,_=spectrum(angular,1/(theta[1]-theta[0]),config.window)
            order=compact_spectrum(of,oa,1000,native=native)
            order['mode']='angle_resampled_from_rpm_trace'
    if order is None and rpm:
        order=compact_spectrum(f/(rpm/60),amp,1000,native=native)
        order['mode']='constant_rpm_reference'
    markers=[]; candidates=[]; limitations=[]
    for label,target in (bearing_frequencies or {}).items():
        harmonics=[]
        for h in range(1,5):
            if target*h>=fs/2: break
            e=peak_evidence(ef,ea,target*h,config.peak_tolerance_ratio,resolution,spacing_hz=target)
            if e:
                e.update(label=label,harmonic=h); harmonics.append(e)
                markers.append(e)
        detected=sum(e['detected'] for e in harmonics)
        if detected>=2:
            candidates.append({'label':{'BPFI':'베어링 내륜','BPFO':'베어링 외륜','BSF':'전동체','2BSF':'전동체 2BSF','FTF':'케이지'}.get(label,label),
                               'kind':'bearing','strength':detected/4,'evidence':harmonics,
                               'assessment':'고조파 일치 후보. 정상 대비 증가와 다른 원인 확인 필요.'})
    rotating=[]
    if rpm:
        for h in range(1,9):
            e=peak_evidence(f,amp,rpm/60*h,config.peak_tolerance_ratio,resolution,spacing_hz=rpm/60)
            if e: e['order']=h; rotating.append(e)
        significant=[e for e in rotating if e['detected']]
        if significant and significant[0]['order']==1:
            candidates.append({'label':'불평형 가능성','kind':'mechanical','strength':0.35,
                               'evidence':significant[:1],'assessment':'1X 성분만으로 확정 불가. 반경 방향·위상·공진 확인 필요.'})
        if any(e['order']==2 for e in significant):
            candidates.append({'label':'정렬불량 가능성','kind':'mechanical','strength':0.35,
                               'evidence':[e for e in significant if e['order']<=2],
                               'assessment':'2X 증거는 비특이적. 축방향·결합부 위상 확인 필요.'})
        if len(significant)>=4:
            candidates.append({'label':'헐거움 가능성','kind':'mechanical','strength':0.45,
                               'evidence':significant,'assessment':'다수 회전 고조파. 접촉·공진·복합 결함과 구분 필요.'})
    if any(e.get('resolvable') is False for e in markers+rotating):
        limitations.append('측정 창이 짧거나 회전수가 낮아 고조파 검색 대역이 겹칩니다. 창 길이를 늘려 재분석하세요.')
    features_names,features=channel_features(a,fs)
    # Uniform PSD bins are retained for a time/frequency heatmap, unlike peak-preserving line charts.
    grid=np.linspace(0,fs/2,384)
    heat=10*np.log10(np.maximum(np.interp(grid,f,psd),1e-20))
    variation=float(np.ptp(rpm_trace)/rpm) if rpm_trace is not None and len(rpm_trace)==len(x) and np.isfinite(rpm_trace).all() and rpm else 0.
    result={'metrics':metrics,'rpm':rpm,'rpm_variation_ratio':variation,'frequency_resolution_hz':resolution,
            'waveform':waveform(x,fs,native=native),'spectrum':compact_spectrum(f,amp,native=native),
            'psd':compact_spectrum(f,psd,native=native),'envelope_spectrum':compact_spectrum(ef,ea,native=native),
            'spectrogram':{'frequencies':grid if native else grid.tolist(),'db':heat if native else heat.tolist()},'order_spectrum':order,
            'bearing_markers':markers,'rotation_markers':rotating,
            'diagnosis':{'candidates':candidates,'status':'candidate_only','limitations':limitations,
                         'note':'주파수 일치는 고장 확정이 아닙니다. 유사한 패턴·복합 결함·설치 영향을 확인하세요.'},
            '_features':features,'_feature_names':features_names}
    return result
