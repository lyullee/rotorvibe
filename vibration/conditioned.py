# Experimental normal-reference bank; fitting, calibration and fault recordings differ.
# Default inference does not extrapolate unobserved speeds or reuse another asset ID.
# Common-band resampling is specific to this profile, not the full bearing DSP path.

"""Conditioned normal-reference bank with bounded interpolation and recording prototypes.

No reference extrapolation. Calibration recordings never fit reference centers or
fault prototypes. All scores are empirical; operational_use remains False.
"""
import copy
import numpy as np
from scipy.signal import resample_poly
from math import gcd
from .two_stage import _scope
from .rotor_features import rotor_features,ROTOR_SCHEMA

ALGORITHM='speed_conditioned_normal_bank.v1'


def canonical_values(values,source_rate,target_rate=4000):
    """Anti-aliased common-band conversion; never treat 8k and16k Nyquists as equal."""
    if isinstance(source_rate,(bool,np.bool_)) or isinstance(target_rate,(bool,np.bool_)) or not np.isfinite([source_rate,target_rate]).all() or int(source_rate)!=source_rate or int(target_rate)!=target_rate or not 0<target_rate<=source_rate:
        raise ValueError('Positive integer rates with target <= source required.')
    a=np.asarray(values,dtype=float)
    if a.ndim==1: a=a[:,None]
    if a.ndim!=2 or not len(a) or not np.isfinite(a).all() or np.max(np.abs(a))>1e12: raise ValueError('Invalid resampling input.')
    divisor=gcd(int(source_rate),int(target_rate))
    return resample_poly(a,int(target_rate)//divisor,int(source_rate)//divisor,axis=0)


def selected_features(names,mode):
    if mode=='levels_orders': rows=[i for i,n in enumerate(names) if n.endswith('_log_rms') or '_log_order_power_' in n]
    elif mode=='orders': rows=[i for i,n in enumerate(names) if '_log_order_power_' in n]
    elif mode=='relative': rows=[i for i,n in enumerate(names) if '_order_' in n or '_to_ch' in n]
    else: raise ValueError('Unknown conditioned feature mode.')
    if not rows: raise ValueError('No selected features.')
    return rows


def matrix(values):
    a=np.asarray(values,dtype=float)
    if a.ndim!=2 or not a.shape[0] or not a.shape[1] or not np.isfinite(a).all() or np.max(np.abs(a))>1e100: raise ValueError('Invalid feature matrix.')
    return a


def reference_at(references,rpm,*,interpolate,max_gap,uncertainty):
    if not np.isfinite(rpm) or rpm<=0: raise ValueError('Positive finite RPM required.')
    speeds=np.asarray([r['rpm'] for r in references],dtype=float)
    index=int(np.argmin(np.abs(speeds-rpm))); near=references[index]
    if abs(speeds[index]-rpm)<=max(2.,.01*speeds[index]):
        return np.asarray(near['center']),np.asarray(near['scale']),{'mode':'matched','lower_rpm':float(speeds[index]),'upper_rpm':float(speeds[index])}
    if not interpolate or rpm<speeds[0] or rpm>speeds[-1]: return None
    hi=int(np.searchsorted(speeds,rpm)); lo=hi-1
    if speeds[hi]-speeds[lo]>max_gap: return None
    weight=float(np.log(rpm/speeds[lo])/np.log(speeds[hi]/speeds[lo]))
    a=references[lo]; b=references[hi]; ca=np.asarray(a['center']); cb=np.asarray(b['center'])
    center=(1-weight)*ca+weight*cb
    variance=(1-weight)*np.asarray(a['scale'])**2+weight*np.asarray(b['scale'])**2
    # Explicit bracket uncertainty; it does not guarantee behavior near a resonance.
    extra=uncertainty*weight*(1-weight)*np.abs(cb-ca)
    scale=np.sqrt(variance+extra**2)
    return center,scale,{'mode':'interpolated_qualification','lower_rpm':float(speeds[lo]),'upper_rpm':float(speeds[hi]),'weight':weight}


def fit_conditioned(normal,normal_rpm,normal_groups,calibration,calibration_rpm,calibration_groups,
                    faults,fault_rpm,fault_labels,fault_groups,*,feature_names,scope,mode='levels_orders',
                    interpolate=False,max_rpm_gap=800.,interpolation_uncertainty=1.,min_margin=.10):
    n=matrix(normal); c=matrix(calibration); f=matrix(faults); names=list(feature_names); scope=_scope(scope)
    if n.shape[1]!=len(names) or c.shape[1]!=len(names) or f.shape[1]!=len(names): raise ValueError('Feature dimensions differ.')
    ng=np.asarray(normal_groups); cg=np.asarray(calibration_groups); fg=np.asarray(fault_groups); y=np.asarray(fault_labels)
    nr=np.asarray(normal_rpm,dtype=float); cr=np.asarray(calibration_rpm,dtype=float); fr=np.asarray(fault_rpm,dtype=float)
    for a,rows in ((ng,n),(cg,c),(fg,f),(nr,n),(cr,c),(fr,f),(y,f)):
        if a.ndim!=1 or len(a)!=len(rows): raise ValueError('Recording/feature lengths differ.')
    if any(not np.isfinite(a).all() or np.any(a<=0) for a in (nr,cr,fr)): raise ValueError('Invalid training RPM.')
    if set(ng)&set(cg) or (set(ng)|set(cg))&set(fg): raise ValueError('Reference, calibration and fault recordings must be separate.')
    if 'normal' in set(y) or len(set(y))<2: raise ValueError('At least two fault classes, excluding normal, are required.')
    if not isinstance(interpolate,bool) or not np.isfinite([max_rpm_gap,interpolation_uncertainty,min_margin]).all() or max_rpm_gap<=0 or interpolation_uncertainty<0 or min_margin<0: raise ValueError('Invalid interpolation/margin settings.')
    for group in set(ng):
        if len(set(nr[ng==group]))!=1: raise ValueError('A normal recording must have one speed.')
    chosen=selected_features(names,mode); references=[]
    for rpm in sorted(set(nr.tolist())):
        mask=nr==rpm; block=n[mask][:,chosen]; groups=ng[mask]
        centers=np.asarray([np.median(block[groups==g],axis=0) for g in sorted(set(groups.tolist()))])
        center=np.median(centers,axis=0); scale=np.maximum(1.4826*np.median(np.abs(block-center),axis=0),.15)
        references.append({'rpm':rpm,'center':center.tolist(),'scale':scale.tolist(),'recordings':sorted(set(groups.tolist()))})
    def changes(values,rpms):
        result=[]
        for v,rpm in zip(values,rpms):
            ref=reference_at(references,rpm,interpolate=interpolate,max_gap=max_rpm_gap,uncertainty=interpolation_uncertainty)
            if ref is None: raise ValueError('No supported normal reference for a calibration/training speed.')
            result.append((v[chosen]-ref[0])/ref[1])
        return np.vstack(result)
    cz=changes(c,cr); scores=np.sqrt(np.mean(cz**2,axis=1)); z=changes(f,fr)
    global_scale=np.maximum(np.std(z,axis=0),1.)
    prototypes=[]; prototype_labels=[]; prototype_groups=[]
    for group in sorted(set(fg.tolist())):
        mask=fg==group
        if len(set(y[mask]))!=1: raise ValueError('Fault recording has mixed labels.')
        prototypes.append(np.median(z[mask]/global_scale,axis=0)); prototype_labels.append(str(y[mask][0])); prototype_groups.append(group)
    prototypes=np.asarray(prototypes); classes=sorted(set(prototype_labels)); labels=np.asarray(prototype_labels); limits=[]
    for label in classes:
        distances=[]
        for v,group in zip(z[y==label]/global_scale,fg[y==label]):
            mask=(labels==label)&(np.asarray(prototype_groups)!=group)
            if not mask.any(): raise ValueError('Each fault class needs multiple independent training recordings.')
            distances.append(float(np.sqrt(np.mean((prototypes[mask]-v)**2,axis=1)).min()))
        limits.append(float(max(1.,np.quantile(distances,.995)*1.25)))
    profile={'algorithm':ALGORITHM,'feature_schema':ROTOR_SCHEMA,'feature_names':names,'selected_indices':chosen,'mode':mode,'scope':scope,
        'references':references,'interpolate':interpolate,'max_rpm_gap':float(max_rpm_gap),'interpolation_uncertainty':float(interpolation_uncertainty),
        'normal_accept_limit':float(min(max(1.,np.quantile(scores,.99)),np.quantile(scores,.8))),
        'anomaly_limit':float(max(1.,np.quantile(scores,.99))),'min_margin':float(min_margin),
        'fault_scale':global_scale.tolist(),'fault_prototypes':prototypes.tolist(),'prototype_labels':prototype_labels,
        'prototype_groups':prototype_groups,'classes':classes,'class_limits':limits,
        'normal_fit_groups':sorted(set(ng.tolist())),'normal_calibration_groups':sorted(set(cg.tolist())),'fault_fit_groups':sorted(set(fg.tolist())),
        'name':'Conditioned '+mode,'summary':{'status':'experimental_conditioned','classes':classes,'reference_speeds':sorted(set(nr.tolist())),
            'normal_fit_recordings':len(set(ng)),'normal_calibration_recordings':len(set(cg)),'fault_fit_recordings':len(set(fg))},
        'calibration':'empirical window quantiles; correlated windows; no field error guarantee','operational_use':False}
    ConditionedDiagnostic(profile)
    return profile


class ConditionedDiagnostic:
    def __init__(self,profile):
        p=copy.deepcopy(profile)
        if p.get('algorithm')!=ALGORITHM or p.get('feature_schema')!=ROTOR_SCHEMA: raise ValueError('Unsupported conditioned profile.')
        self.profile=p; self.scope=_scope(p['scope']); self.names=tuple(p['feature_names']); self.indices=np.asarray(p['selected_indices'])
        if self.indices.ndim!=1 or self.indices.dtype.kind not in 'iu' or not len(self.indices) or len(set(self.indices.tolist()))!=len(self.indices) or np.any(self.indices<0) or np.any(self.indices>=len(self.names)): raise ValueError('Invalid feature indices.')
        d=len(self.indices); references=p['references']; speeds=[]
        for ref in references:
            speeds.append(ref['rpm']); a=np.asarray(ref['center']); b=np.asarray(ref['scale'])
            if a.shape!=(d,) or b.shape!=(d,) or not np.isfinite(a).all() or not np.isfinite(b).all() or np.any(b<=0): raise ValueError('Invalid normal reference.')
        if not speeds or not np.isfinite(speeds).all() or min(speeds)<=0 or speeds!=sorted(set(speeds)): raise ValueError('Invalid reference speeds.')
        self.scale=np.asarray(p['fault_scale']); self.prototypes=np.asarray(p['fault_prototypes']); self.labels=np.asarray(p['prototype_labels']); self.classes=tuple(p['classes'])
        self.limits=np.asarray(p['class_limits'])
        if self.scale.shape!=(d,) or self.prototypes.shape!=(len(self.labels),d) or len(self.classes)<2 or self.limits.shape!=(len(self.classes),): raise ValueError('Invalid prototype dimensions.')
        if len(set(self.classes))!=len(self.classes) or set(self.labels)!=set(self.classes) or not isinstance(p['interpolate'],bool): raise ValueError('Invalid prototype classes/interpolation mode.')
        if not all(np.isfinite(a).all() for a in (self.scale,self.prototypes,self.limits)) or np.any(self.scale<=0) or np.any(self.limits<=0): raise ValueError('Nonfinite/nonpositive prototype parameters.')
        numbers=[p['normal_accept_limit'],p['anomaly_limit'],p['min_margin'],p['max_rpm_gap'],p['interpolation_uncertainty']]
        if not np.isfinite(numbers).all() or not 0<=numbers[0]<=numbers[1] or numbers[1]<=0 or min(numbers[2:])<0 or numbers[3]<=0: raise ValueError('Invalid gate parameters.')
        if 'canonical_sample_rate_hz' in p:
            if p['canonical_sample_rate_hz']!=self.scope['sample_rate_hz'] or not isinstance(p.get('permitted_input_rates'),list) or not p['permitted_input_rates'] or any(isinstance(r,bool) or not isinstance(r,(int,float)) or not np.isfinite(r) or r<p['canonical_sample_rate_hz'] for r in p['permitted_input_rates']): raise ValueError('Invalid canonical input-rate contract.')

    def predict(self,features,*,scope):
        base={'operational_use':False,'feature_schema':ROTOR_SCHEMA}
        keys=('asset_id','condition_id','unit')+tuple(k for k in ('calibration_id','sensor_installation_id') if k in self.scope)
        if any(scope.get(k)!=self.scope[k] for k in keys): return {**base,'status':'hold','label':None,'reason':'normal_reference_scope_mismatch'}
        if list(features.channel_names)!=self.scope['channel_names'] or features.sample_rate_hz!=self.scope['sample_rate_hz'] or features.sample_count!=self.scope['window_samples']:
            return {**base,'status':'hold','label':None,'reason':'outside_layout_sampling_or_window_domain'}
        if not self.scope['rpm_range'][0]<=features.rpm<=self.scope['rpm_range'][1]:
            return {**base,'status':'hold','label':None,'reason':'outside_speed_scope'}
        ref=reference_at(self.profile['references'],features.rpm,interpolate=self.profile['interpolate'],max_gap=self.profile['max_rpm_gap'],uncertainty=self.profile['interpolation_uncertainty'])
        if ref is None: return {**base,'status':'hold','label':None,'reason':'normal_reference_speed_unavailable'}
        if features.schema!=ROTOR_SCHEMA or tuple(features.names)!=self.names: raise ValueError('Feature schema mismatch.')
        v=np.asarray(features.values,dtype=float)
        if v.shape!=(len(self.names),) or not np.isfinite(v).all() or np.max(np.abs(v))>1e100: raise ValueError('Invalid diagnostic feature values.')
        z=(v[self.indices]-ref[0])/ref[1]; score=float(np.sqrt(np.mean(z*z)))
        base.update(normal_score=score,normal_accept_limit=self.profile['normal_accept_limit'],anomaly_limit=self.profile['anomaly_limit'],reference=ref[2])
        if score<=self.profile['normal_accept_limit']: return {**base,'status':'normal','label':'normal','anomaly':False}
        if score<=self.profile['anomaly_limit']: return {**base,'status':'hold','label':None,'anomaly':None,'reason':'normal_gate_borderline'}
        distances=np.sqrt(np.mean((self.prototypes-z/self.scale)**2,axis=1))
        by_class=np.asarray([distances[self.labels==c].min() for c in self.classes]); winner=int(by_class.argmin())
        weights=np.exp(-np.minimum(by_class-by_class.min(),100)); weights/=weights.sum()
        margin=float(np.sort(by_class)[1]-by_class[winner])
        base.update(anomaly=True,fault_margin=margin,relative_matches=[{'label':c,'distance':float(d),'weight':float(w)} for c,d,w in zip(self.classes,by_class,weights)])
        if by_class[winner]>self.limits[winner] or margin<self.profile['min_margin'] or margin<=1e-12:
            return {**base,'status':'anomaly_unknown','label':None,'reason':'fault_evidence_insufficient'}
        return {**base,'status':'fault_candidate','label':self.classes[winner]}

    def analyze(self,values,sample_rate_hz,rpm,*,scope,channel_names=None):
        if rpm is None: return {'status':'hold','label':None,'reason':'rpm_required','operational_use':False}
        if 'canonical_sample_rate_hz' in self.profile:
            target=self.profile['canonical_sample_rate_hz']
            if sample_rate_hz not in self.profile['permitted_input_rates']:
                return {'status':'hold','label':None,'reason':'unsupported_input_sampling_rate','operational_use':False}
            if len(values)!=round(self.scope['window_samples']/self.scope['sample_rate_hz']*sample_rate_hz):
                return {'status':'hold','label':None,'reason':'outside_window_duration','operational_use':False}
            values=canonical_values(values,sample_rate_hz,target); sample_rate_hz=target
        return self.predict(rotor_features(values,sample_rate_hz,rpm,channel_names=channel_names),scope=scope)


class ConditionedStage:
    def __init__(self,model): self.model=model
    def __call__(self,result):
        if not result.valid: return {'status':'quality_hold','label':None,'operational_use':False}
        raise RuntimeError('ConditionedStage requires the raw-window hook.')
    def analyze_window(self,result,values):
        if not result.valid: return self(result)
        if result.payload.get('rpm_variation_ratio',0)>.03: return {'status':'hold','label':None,'reason':'variable_speed_requires_angle_domain_features','operational_use':False}
        source=result.metadata.get('source',{}); config=result.metadata['measurement']
        scope={**source,'unit':config['unit']}
        return self.model.analyze(values,config['sample_rate_hz'],result.payload.get('rpm'),scope=scope,channel_names=result.channels)
