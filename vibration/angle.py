"""Experimental angle-domain features with explicit measured speed and anti-aliasing.

Fixed-speed morphology profiles are not reused or converted. New angle profiles
require independent fitting/calibration and measured-data qualification.
"""
from dataclasses import dataclass
from collections.abc import Mapping
from numbers import Real
import copy
import numpy as np
from scipy.signal import butter,sosfiltfilt
from .dsp import spectrum
from .fault_discrimination import fit_fault_discriminator,FaultDiscriminator
from .acquisition import check_acquisition

ANGLE_SCHEMA='vibration.angle_features.v1'
ANGLE_ALGORITHM='vibration.angle_fault.v1'


def _channels(scope):
    if not isinstance(scope,Mapping) or scope.get('rpm_source') not in ('tachometer','encoder'):
        raise ValueError('Measured speed source required')
    channels=scope.get('channel_names')
    if (not isinstance(channels,(list,tuple)) or not 1<=len(channels)<=16
        or any(not isinstance(n,str) or not n.strip() for n in channels) or len(set(channels))!=len(channels)):
        raise ValueError('Unique ordered channel names required')
    return channels


def angle_resample(values,sample_rate_hz,rpm_trace,*,samples_per_revolution=256,revolutions=16):
    a=np.asarray(values,dtype=float)
    if a.ndim==1: a=a[:,None]
    rpm=np.asarray(rpm_trace,dtype=float)
    if np.asarray(rpm_trace).dtype.kind=='b': raise ValueError('RPM must not be boolean')
    if (a.ndim!=2 or not 256<=len(a)<=2_000_000 or not 1<=a.shape[1]<=16 or not np.isfinite(a).all() or np.any(np.abs(a)>1e12)
        or rpm.shape!=(len(a),) or not np.isfinite(rpm).all() or np.any(rpm<=0) or np.any(rpm>1e6)):
        raise ValueError('Finite waveform and positive per-sample RPM trace required')
    if isinstance(sample_rate_hz,(bool,np.bool_)) or not isinstance(sample_rate_hz,Real) or not np.isfinite(sample_rate_hz) or not 100<=sample_rate_hz<=200000:
        raise ValueError('Finite sampling rate in 100..200000 Hz required')
    if (isinstance(samples_per_revolution,bool) or not isinstance(samples_per_revolution,int) or not 64<=samples_per_revolution<=4096
        or isinstance(revolutions,bool) or not isinstance(revolutions,int) or not 8<=revolutions<=1024
        or samples_per_revolution*revolutions*a.shape[1]>8_000_000):
        raise ValueError('Bounded integer angular grid required')
    phase=np.r_[0,np.cumsum((rpm[:-1]+rpm[1:])/(120*sample_rate_hz))]
    if phase[-1]<revolutions: raise ValueError('Insufficient measured revolutions')
    # A conservative time-domain low-pass before angular decimation. Refuse
    # speed ranges where retaining 10X conflicts with anti-alias protection.
    cutoff=.4*min(sample_rate_hz,samples_per_revolution*float(rpm.min())/60)
    if 10*float(rpm.max())/60>=.7*cutoff: raise ValueError('Insufficient angular sampling/bandwidth for speed range')
    filtered=sosfiltfilt(butter(8,cutoff,fs=sample_rate_hz,output='sos'),a,axis=0)
    theta=phase[-1]-revolutions+np.arange(samples_per_revolution*revolutions)/samples_per_revolution
    angular=np.column_stack([np.interp(theta,phase,filtered[:,ch]) for ch in range(a.shape[1])])
    angular.setflags(write=False)
    return angular,{'schema':ANGLE_SCHEMA,'samples_per_revolution':samples_per_revolution,'revolutions':revolutions,
                    'rpm_min':float(rpm.min()),'rpm_max':float(rpm.max()),'rpm_mean':float(rpm.mean()),
                    'anti_alias_cutoff_hz':float(cutoff),'trace_source':'caller_measured','operational_use':False}


@dataclass(frozen=True)
class AngleFeatures:
    names: tuple
    values: np.ndarray
    metadata: dict
    schema: str = ANGLE_SCHEMA


def angle_features(values,sample_rate_hz,rpm_trace,*,samples_per_revolution=256,revolutions=16):
    angular,metadata=angle_resample(values,sample_rate_hz,rpm_trace,
                                  samples_per_revolution=samples_per_revolution,revolutions=revolutions)
    names=[]; features=[]
    for ch in range(angular.shape[1]):
        x=angular[:,ch]-angular[:,ch].mean(); rms=float(np.sqrt(np.mean(x*x)))
        if rms<=1e-15: raise ValueError('Flat angular channel')
        order,_,power=spectrum(x,samples_per_revolution)
        total=power.sum(); normalized=x/rms
        values=[np.log(rms),np.log(np.max(np.abs(normalized))),np.log(np.mean(normalized**4))]
        names.extend(f'ch{ch+1}_{name}' for name in ('log_rms','log_crest','log_kurtosis'))
        for target in np.arange(.5,10.01,.5):
            names.append(f'ch{ch+1}_order_{target:g}X')
            values.append(np.log(max(float(power[np.abs(order-target)<=1.5/revolutions].sum()/total),1e-12)))
        features.extend(values)
    vector=np.asarray(features)
    if not np.isfinite(vector).all(): raise ValueError('Nonfinite angle features')
    vector.setflags(write=False)
    return AngleFeatures(tuple(names),vector,metadata)


def fit_angle_fault_discriminator(x,labels,rpms,groups,*,names,scope,samples_per_revolution=256,revolutions=16,margin=.03):
    channels=_channels(scope)
    # Validate extraction settings without creating a new implicit feature grid.
    if (isinstance(samples_per_revolution,bool) or not isinstance(samples_per_revolution,int) or not 64<=samples_per_revolution<=4096
        or isinstance(revolutions,bool) or not isinstance(revolutions,int) or not 8<=revolutions<=1024):
        raise ValueError('Invalid angle settings')
    expected=[]
    if samples_per_revolution*revolutions*len(channels)>8_000_000: raise ValueError('Angular grid exceeds memory limit')
    for ch in range(len(channels)):
        expected.extend(f'ch{ch+1}_{n}' for n in ('log_rms','log_crest','log_kurtosis'))
        expected.extend(f'ch{ch+1}_order_{o:g}X' for o in np.arange(.5,10.01,.5))
    if list(names)!=expected: raise ValueError('Angle feature schema mismatch')
    model=fit_fault_discriminator(x,labels,rpms,groups,names=names,scope=scope,mode='morphology',rpm_penalty=0.,margin=margin)
    return {'algorithm':ANGLE_ALGORITHM,'feature_schema':ANGLE_SCHEMA,'samples_per_revolution':samples_per_revolution,
            'revolutions':revolutions,'model':model,'operational_use':False}


class AngleFaultDiscriminator:
    def __init__(self,profile):
        p=copy.deepcopy(profile)
        if p.get('algorithm')!=ANGLE_ALGORITHM or p.get('feature_schema')!=ANGLE_SCHEMA or p.get('operational_use') is not False:
            raise ValueError('New angle profile required; fixed-speed profiles cannot be reused')
        self.profile=p; self.model=FaultDiscriminator(p['model'])
        scope=self.model.scope
        channels=_channels(scope)
        expected=[]
        for ch in range(len(channels)):
            expected.extend(f'ch{ch+1}_{n}' for n in ('log_rms','log_crest','log_kurtosis'))
            expected.extend(f'ch{ch+1}_order_{o:g}X' for o in np.arange(.5,10.01,.5))
        if self.model.profile['names']!=expected: raise ValueError('Angle schema mismatch')
        for key,lo,hi in (('samples_per_revolution',64,4096),('revolutions',8,1024)):
            if isinstance(p[key],bool) or not isinstance(p[key],int) or not lo<=p[key]<=hi: raise ValueError('Invalid angle grid')
        if p['samples_per_revolution']*p['revolutions']*len(channels)>8_000_000: raise ValueError('Angular grid exceeds memory limit')

    def analyze(self,values,sample_rate_hz,rpm_trace,*,scope):
        if not isinstance(scope,Mapping):
            return dict(status='hold',label=None,reason='fault_scope_missing_or_invalid',operational_use=False)
        if scope.get('rpm_source') not in ('tachometer','encoder'):
            return dict(status='hold',label=None,reason='measured_rpm_trace_required',operational_use=False)
        rpm=np.asarray(rpm_trace,dtype=float)
        if rpm.ndim!=1 or not len(rpm) or not np.isfinite(rpm).all() or np.any((rpm<590)|(rpm>1620)):
            return dict(status='hold',label=None,reason='outside_speed_scope',operational_use=False)
        a=np.asarray(values)
        if a.ndim==1: a=a[:,None]
        if a.ndim!=2 or not len(a): raise ValueError('Nonempty waveform required')
        if len(scope.get('channel_names',[]))!=a.shape[1]:
            return dict(status='hold',label=None,reason='outside_channel_layout',operational_use=False)
        f=angle_features(values,sample_rate_hz,rpm, samples_per_revolution=self.profile['samples_per_revolution'],revolutions=self.profile['revolutions'])
        result=self.model.predict(f.values,float(rpm.mean()),scope=scope)
        result.update(feature_schema=ANGLE_SCHEMA,angle_measurement=f.metadata)
        return result


class AngleFaultStage:
    def __init__(self,model,*,gate_key='reference',experimental_enabled=False):
        if not isinstance(experimental_enabled,bool): raise ValueError('Explicit experiment switch required')
        self.model=model; self.gate_key=gate_key; self.enabled=experimental_enabled

    def analyze_window(self,result,values):
        hold=lambda reason:dict(status='hold',label=None,reason=reason,operational_use=False)
        if not self.enabled: return hold('angle_experiment_not_enabled')
        if not result.valid or result.payload.get(self.gate_key,{}).get('anomaly') is not True: return hold('confirmed_anomaly_gate_required')
        quality=check_acquisition(result,require_measured_rpm=True)
        if quality['status']!='accepted': return hold(quality['reason'])
        source=result.metadata['source']; config=result.metadata['measurement']
        cutoff=.4*min(config['sample_rate_hz'],self.model.profile['samples_per_revolution']*float(result.rpm_trace.min())/60)
        if check_acquisition(result,required_band_hz=(float(result.rpm_trace.min())/120,cutoff))['status']!='accepted':
            return hold('angular_sensor_band_insufficient')
        scope={**source,'unit':config['unit'],'rpm_source':source['acquisition']['rpm_source'],'channel_names':list(result.channels)}
        decision=self.model.analyze(values,config['sample_rate_hz'],result.rpm_trace,scope=scope)
        if decision['status'] in ('fault_candidate','anomaly_unknown'):
            decision.update(anomaly=True,anomaly_source=self.gate_key)
        return decision

    def __call__(self,result): raise RuntimeError('Use raw-window stage hook')
