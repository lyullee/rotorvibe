"""Asset-scoped normal reference -> fault candidates -> explicit abstention.

Calibration uses separate, confirmed-normal acquisition groups. Quantiles are
empirical window thresholds, NOT confidence bounds for independent field trials.
"""
import copy
from numbers import Real,Integral
import numpy as np
from .classifier import fit_gaussian,GaussianClassifier
from .rotor_features import rotor_features,ROTOR_SCHEMA,NORMAL_CHANGE_SCHEMA,feature_indices

ALGORITHM='normal_gate_then_fault_candidates.v1'


def _matrix(values):
    a=np.asarray(values,dtype=float)
    if a.ndim!=2 or not a.shape[0] or not a.shape[1] or not np.isfinite(a).all() or np.max(np.abs(a))>1e100:
        raise ValueError('Finite nonempty feature matrix required.')
    return a


def _scope(scope):
    s=copy.deepcopy(dict(scope)); required=('asset_id','condition_id','unit','channel_names','sample_rate_hz','window_samples','rpm_range')
    if any(key not in s for key in required): raise ValueError('Complete asset/condition/unit/layout/fs/RPM scope required.')
    if not all(isinstance(s[k],str) and s[k] for k in ('asset_id','condition_id','unit')): raise ValueError('Invalid scope identity.')
    channels=s['channel_names']
    if not isinstance(channels,(list,tuple)) or not channels or not all(isinstance(c,str) and c for c in channels) or len(set(channels))!=len(channels): raise ValueError('Invalid channel layout.')
    if not isinstance(s['rpm_range'],(list,tuple,np.ndarray)) or any(isinstance(v,(bool,np.bool_)) or not isinstance(v,Real) for v in s['rpm_range']): raise ValueError('Invalid RPM range.')
    band=np.asarray(s['rpm_range'],dtype=float)
    if band.shape!=(2,) or not np.isfinite(band).all() or not 0<band[0]<=band[1]: raise ValueError('Invalid RPM range.')
    if isinstance(s['sample_rate_hz'],(bool,np.bool_)) or not isinstance(s['sample_rate_hz'],Real) or not np.isfinite(s['sample_rate_hz']) or s['sample_rate_hz']<=0: raise ValueError('Invalid sample rate.')
    if isinstance(s['window_samples'],(bool,np.bool_)) or not isinstance(s['window_samples'],Integral) or s['window_samples']<256: raise ValueError('Invalid window sample count.')
    s['sample_rate_hz']=float(s['sample_rate_hz']); s['window_samples']=int(s['window_samples'])
    for key in ('calibration_id','sensor_installation_id'):
        if key in s and (not isinstance(s[key],str) or not s[key]): raise ValueError('Invalid calibration/installation identity.')
    s['channel_names']=list(channels); s['rpm_range']=band.tolist()
    return s


def fit_two_stage(normal_fit,normal_fit_groups,normal_calibration,calibration_groups,
                  faults,fault_labels,fault_groups,*,feature_names,scope,mode='relative',
                  normal_quantile=.80,anomaly_quantile=.99,min_margin=.10):
    train=_matrix(normal_fit); calibration=_matrix(normal_calibration); fx=_matrix(faults)
    names=list(feature_names); context=_scope(scope)
    if len(names)!=train.shape[1] or len(set(names))!=len(names) or calibration.shape[1]!=train.shape[1] or fx.shape[1]!=train.shape[1]:
        raise ValueError('Feature schemas differ.')
    tg=np.asarray(normal_fit_groups); cg=np.asarray(calibration_groups); fg=np.asarray(fault_groups); labels=np.asarray(fault_labels)
    if any(g.ndim!=1 or len(g)!=len(x) for g,x in ((tg,train),(cg,calibration),(fg,fx))) or labels.ndim!=1 or len(labels)!=len(fx): raise ValueError('Group/label lengths differ.')
    if set(tg.tolist())&set(cg.tolist()) or (set(tg.tolist())|set(cg.tolist()))&set(fg.tolist()): raise ValueError('Fit/calibration/fault acquisition groups must be disjoint.')
    if any(str(label).casefold() in ('normal','healthy','정상') for label in labels): raise ValueError('Fault stage must exclude normal labels.')
    if not (np.isfinite(normal_quantile) and np.isfinite(anomaly_quantile) and 0<normal_quantile<anomaly_quantile<1) or not np.isfinite(min_margin) or min_margin<0:
        raise ValueError('Invalid gate/margin settings.')
    selected=feature_indices(names,mode); t=train[:,selected]; c=calibration[:,selected]
    # Group centers give each normal acquisition equal representation.
    centers=np.array([np.median(t[tg==g],axis=0) for g in sorted(set(tg.tolist()))])
    center=np.median(centers,axis=0)
    scale=np.maximum(np.median(np.abs(t-center),axis=0)*1.4826,.1)
    scores=np.sqrt(np.mean(((c-center)/scale)**2,axis=1))
    upper=float(max(1.,np.quantile(scores,anomaly_quantile)))
    lower=float(min(upper,np.quantile(scores,normal_quantile)))
    fault_model=fit_gaussian((fx[:,selected]-center)/scale,labels,fg,feature_schema=NORMAL_CHANGE_SCHEMA)
    fault_model['feature_names']=[names[i] for i in selected]
    profile={'algorithm':ALGORITHM,'feature_schema':ROTOR_SCHEMA,'feature_names':names,'selected_indices':selected,
        'mode':mode,'scope':context,'normal_change_schema':NORMAL_CHANGE_SCHEMA,'normal_center':center.tolist(),'normal_scale':scale.tolist(),
        'normal_accept_limit':lower,'anomaly_limit':upper,'min_fault_margin':float(min_margin),'fault_model':fault_model,
        'normal_fit_groups':sorted(set(tg.tolist())),'normal_calibration_groups':sorted(set(cg.tolist())),
        'fault_training_groups':sorted(set(fg.tolist())),
        'name':'Two-stage '+mode,
        'summary':{'status':'experimental_two_stage','mode':mode,'normal_fit_windows':len(train),
            'normal_calibration_windows':len(calibration),'fault_fit_windows':len(fx),
            'normal_calibration_acquisitions':len(set(cg.tolist())),'classes':fault_model['classes']},
        'calibration':{'normal_windows':len(c),'independent_acquisitions':len(set(cg.tolist())),
            'normal_quantile':normal_quantile,'anomaly_quantile':anomaly_quantile,
            'method':'empirical window quantiles; consecutive windows correlated; no field false-alarm guarantee'},
        'operational_use':False}
    TwoStageDiagnostic(profile)
    return profile


class TwoStageDiagnostic:
    def __init__(self,profile):
        p=copy.deepcopy(profile)
        if p.get('algorithm')!=ALGORITHM or p.get('feature_schema')!=ROTOR_SCHEMA: raise ValueError('Unsupported two-stage profile.')
        self.profile=p; self.scope=_scope(p['scope']); self.names=tuple(p['feature_names'])
        self.indices=np.asarray(p['selected_indices'],dtype=int); self.center=np.asarray(p['normal_center'],dtype=float); self.scale=np.asarray(p['normal_scale'],dtype=float)
        if self.indices.ndim!=1 or not len(self.indices) or len(set(self.indices.tolist()))!=len(self.indices) or np.any(self.indices<0) or np.any(self.indices>=len(self.names)):
            raise ValueError('Invalid selected feature indices.')
        if self.center.shape!=self.indices.shape or self.scale.shape!=self.indices.shape or not np.isfinite(self.center).all() or not np.isfinite(self.scale).all() or np.any(self.scale<=0): raise ValueError('Invalid normal reference.')
        limits=[p['normal_accept_limit'],p['anomaly_limit'],p['min_fault_margin']]
        if not np.isfinite(limits).all() or not 0<=limits[0]<=limits[1] or limits[1]<=0 or limits[2]<0: raise ValueError('Invalid gate thresholds.')
        self.fault=GaussianClassifier(p['fault_model'])
        if self.fault.center.shape!=self.center.shape: raise ValueError('Fault/reference feature dimensions differ.')

    def _domain_reason(self,features,scope):
        current=dict(scope)
        identities=('asset_id','condition_id','unit')+tuple(k for k in ('calibration_id','sensor_installation_id') if k in self.scope)
        if any(current.get(key)!=self.scope[key] for key in identities):
            return 'normal_reference_scope_mismatch'
        if list(features.channel_names)!=self.scope['channel_names'] or features.sample_rate_hz!=self.scope['sample_rate_hz'] or features.sample_count!=self.scope['window_samples'] or not self.scope['rpm_range'][0]<=features.rpm<=self.scope['rpm_range'][1]:
            return 'outside_layout_sampling_or_speed_domain'
        return None

    def relative_features(self,features,*,scope):
        """Return selected names + read-only normal-scaled changes for other Python modules."""
        reason=self._domain_reason(features,scope)
        if reason: raise ValueError(reason)
        if features.schema!=ROTOR_SCHEMA or tuple(features.names)!=self.names: raise ValueError('Rotor feature schema mismatch.')
        v=np.asarray(features.values,dtype=float)
        if v.shape!=(len(self.names),) or not np.isfinite(v).all() or np.max(np.abs(v))>1e100: raise ValueError('Invalid diagnostic features.')
        relative=(v[self.indices]-self.center)/self.scale
        relative.setflags(write=False)
        return tuple(self.names[i] for i in self.indices),relative

    def predict(self,features,*,scope):
        base={'operational_use':False,'feature_schema':ROTOR_SCHEMA}
        reason=self._domain_reason(features,scope)
        if reason: return {**base,'status':'hold','label':None,'reason':reason}
        _,relative=self.relative_features(features,scope=scope)
        score=float(np.sqrt(np.mean(relative**2)))
        top=np.argsort(np.abs(relative))[-5:][::-1]
        base.update(normal_score=score,normal_accept_limit=self.profile['normal_accept_limit'],anomaly_limit=self.profile['anomaly_limit'],
                    deviations=[{'feature':self.names[self.indices[i]],'normal_scaled_change':float(relative[i])} for i in top])
        if score<=self.profile['normal_accept_limit']:
            return {**base,'status':'normal','label':'normal','anomaly':False,'reason':'within_confirmed_normal_reference'}
        if score<=self.profile['anomaly_limit']:
            return {**base,'status':'hold','label':None,'anomaly':None,'reason':'normal_gate_borderline'}
        prediction=self.fault.predict(relative); costs,_=self.fault.scores(relative); ordered=np.sort(costs)
        margin=float(ordered[1]-ordered[0]); base.update(anomaly=True,fault_margin=margin,relative_matches=prediction['relative_matches'])
        if prediction['status']=='unknown' or margin<self.profile['min_fault_margin']:
            return {**base,'status':'anomaly_unknown','label':None,'reason':'fault_evidence_insufficient'}
        return {**base,'status':'fault_candidate','label':prediction['label'],'reason':'normal_departure_and_separated_fault_match'}

    def analyze(self,values,sample_rate_hz,rpm,*,scope,channel_names=None):
        if rpm is None: return {'status':'hold','label':None,'reason':'rpm_required','operational_use':False}
        try: features=rotor_features(values,sample_rate_hz,rpm,channel_names=channel_names)
        except ValueError as error:
            if str(error).startswith('Insufficient duration/bandwidth'):
                return {'status':'hold','label':None,'reason':'insufficient_order_resolution_or_bandwidth','operational_use':False}
            raise
        return self.predict(features,scope=scope)


class TwoStageStage:
    """Use in VibrationAnalyzer(stages={'diagnostic': TwoStageStage(model)})."""
    def __init__(self,model): self.model=model

    def __call__(self,result):
        if not result.valid: return {'status':'quality_hold','label':None,'operational_use':False}
        raise RuntimeError('TwoStageStage requires the raw-window stage hook.')

    def analyze_window(self,result,values):
        if not result.valid: return self(result)
        if result.payload.get('rpm_variation_ratio',0.)>.03:
            return {'status':'hold','label':None,'reason':'variable_speed_requires_angle_domain_features','operational_use':False}
        source=result.metadata.get('source',{}); config=result.metadata['measurement']
        scope={k:source.get(k) for k in ('asset_id','condition_id')}; scope['unit']=config['unit']
        for key in ('calibration_id','sensor_installation_id'):
            if key in source: scope[key]=source[key]
        return self.model.analyze(values,config['sample_rate_hz'],result.payload.get('rpm'),scope=scope,channel_names=result.channels)
