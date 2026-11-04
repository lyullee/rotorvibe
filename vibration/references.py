"""Explicit installation/RPM/load normal references with recording-disjoint calibration."""
from dataclasses import dataclass
from collections.abc import Mapping
import copy,json,math,re
from numbers import Real
import numpy as np
from .acquisition import AcquisitionInfo,check_acquisition
from .config import AnalysisConfig

ALGORITHM='vibration.normal_reference.v1'


def _range(value,name):
    if len(value)!=2 or any(isinstance(v,bool) or not isinstance(v,Real) or not math.isfinite(v) for v in value) or value[0]>value[1]:
        raise ValueError('Finite ordered '+name+' required')
    return list(map(float,value))


def _scope(result):
    source=result.metadata['source']; info=AcquisitionInfo(**source['acquisition']).validate()
    condition=source.get('condition_id'); load_unit=source.get('load_unit')
    if any(not isinstance(s,str) or not s.strip() for s in (condition,load_unit)):
        raise ValueError('condition_id and load_unit required')
    config=AnalysisConfig.create(result.metadata['measurement'])
    signature=config.signature(); signature.pop('load'); signature['hop_seconds']=config.hop_seconds
    value={key:getattr(info,key) for key in ('asset_id','sensor_id','sensor_installation_id','calibration_id','frame')}
    value.update(condition_id=condition,load_unit=load_unit,channels=list(info.channel_names),axes=list(info.axes),signature=signature,
                 sensor_band_hz=list(info.sensor_band_hz),anti_alias_cutoff_hz=info.anti_alias_cutoff_hz,rpm_source=info.rpm_source)
    return json.loads(json.dumps(value,allow_nan=False))


@dataclass(frozen=True)
class NormalRecording:
    record_id: str
    group_id: str
    observations: tuple
    confirmed_normal: bool
    role: str = 'unassigned'
    sha256: str | None = None

    @classmethod
    def from_plan(cls,record,observations,*,confirmed_normal):
        if record.role not in ('normal_fit','normal_calibration') or record.label!='normal':
            raise ValueError('Only planned normal fit/calibration records may enter a reference')
        return cls(record.record_id,json.dumps([record.rig_id,record.acquisition_id]),tuple(observations),
                   confirmed_normal,record.role,record.sha256)


def _vector(result,representation,angle_config):
    if representation=='time': return list(result.feature_names),np.asarray(result.features,dtype=float)
    from .angle import angle_features
    if result.rpm_trace is None: raise ValueError('Measured RPM trace required for angle reference')
    if check_acquisition(result,require_measured_rpm=True)['status']!='accepted': raise ValueError('Measured acquisition required')
    values=result.payload['waveform']['y'] if len(result.channels)==1 else _raw_unavailable()
    if np.asarray(values).shape!=(len(result.rpm_trace),): raise ValueError('Full native waveform required, never display-decimated samples')
    f=angle_features(values,
                     result.metadata['measurement']['sample_rate_hz'],result.rpm_trace,**angle_config)
    if check_acquisition(result,required_band_hz=(f.metadata['rpm_min']/120,f.metadata['anti_alias_cutoff_hz']))['status']!='accepted':
        raise ValueError('Angular sensor band insufficient')
    return list(f.names),f.values


def _raw_unavailable():
    raise ValueError('Angle normal references currently require one channel')


def _eligible(result,scope,rpm_range,load_range,names,representation='time',angle_config=None):
    if not result.valid or check_acquisition(result)['status']!='accepted': raise ValueError('Qualified acquisition required')
    if _scope(result)!=scope: raise ValueError('Reference source differs')
    rpm=result.payload.get('rpm'); load=result.metadata['measurement'].get('load')
    if rpm is None or not rpm_range[0]<=rpm<=rpm_range[1]: raise ValueError('RPM outside declared range')
    if load is None or not load_range[0]<=load<=load_range[1]: raise ValueError('Load outside declared range')
    if representation=='time' and result.payload.get('rpm_variation_ratio',0)>.03: raise ValueError('Fixed-speed normal reference requires <=3% RPM variation')
    if result.rpm_trace is not None and (result.rpm_trace.min()<rpm_range[0] or result.rpm_trace.max()>rpm_range[1]):
        raise ValueError('RPM trace outside declared range')
    actual_names,vector=_vector(result,representation,angle_config or {})
    if actual_names!=names: raise ValueError('Reference feature schema differs')
    if vector.shape!=(len(names),) or not np.isfinite(vector).all() or np.any(np.abs(vector)>1e100): raise ValueError('Invalid features')
    return vector


def fit_normal_reference(fit_records,calibration_records,*,name,rpm_range,load_range,quantile=.99,
                         representation='time',samples_per_revolution=256,revolutions=16):
    """Equal group-weighted center; calibration quantiles use per-record maximum scores.

    At least two original groups per role are required. These are empirical limits,
    not a population error guarantee. Test records are never accepted by this API.
    """
    fit=list(fit_records); calibration=list(calibration_records)
    if representation not in ('time','angle'): raise ValueError('Unknown reference representation')
    angle_config={'samples_per_revolution':samples_per_revolution,'revolutions':revolutions} if representation=='angle' else {}
    if not isinstance(name,str) or not name.strip(): raise ValueError('Reference name required')
    rpm_range=_range(rpm_range,'RPM range'); load_range=_range(load_range,'load range')
    if rpm_range[0]<=0 or isinstance(quantile,bool) or not isinstance(quantile,Real) or not .5<=quantile<1:
        raise ValueError('Positive RPM range and quantile in [.5,1) required')
    for records,role in ((fit,'normal_fit'),(calibration,'normal_calibration')):
        if len(records)<2: raise ValueError('At least two original recordings per role required')
        for record in records:
            if not isinstance(record,NormalRecording) or record.confirmed_normal is not True or not record.observations:
                raise ValueError('Confirmed normal recordings with observations required')
            if record.role!=role: raise ValueError('Reference fit/calibration roles must match the prospective plan')
            if any(not isinstance(s,str) or not s.strip() for s in (record.record_id,record.group_id)):
                raise ValueError('Original record and group identities required')
            if record.sha256 is not None and (not isinstance(record.sha256,str) or re.fullmatch('[0-9a-f]{64}',record.sha256) is None):
                raise ValueError('Recording checksum must be SHA256 hex')
    all_records=fit+calibration
    if len({r.record_id for r in all_records})!=len(all_records) or len({r.group_id for r in all_records})!=len(all_records):
        raise ValueError('Fit/calibration must use distinct original acquisition groups')
    hashes=[r.sha256 for r in all_records if r.sha256 is not None]
    if len(set(hashes))!=len(hashes): raise ValueError('Duplicate raw data cannot count as independent recordings')
    first=fit[0].observations[0]; scope=_scope(first); names,_=_vector(first,representation,angle_config)
    if not names or len(set(names))!=len(names): raise ValueError('Unique feature names required')
    arrays=[np.vstack([_eligible(r,scope,rpm_range,load_range,names,representation,angle_config) for r in record.observations]) for record in all_records]
    representatives=np.vstack([np.median(a,axis=0) for a in arrays[:len(fit)]])
    center=np.median(representatives,axis=0)
    scale=np.maximum(1.4826*np.median(np.abs(representatives-center),axis=0),.15)
    scores=[float(np.sqrt(np.mean(((a-center)/scale)**2,axis=1)).max()) for a in arrays[len(fit):]]
    lower=max(1.,float(np.quantile(scores,.8))); upper=max(lower,float(np.quantile(scores,quantile)))
    return dict(algorithm=ALGORITHM,name=name,scope=scope,feature_names=names,representation=representation,angle_config=angle_config,
        feature_schema='vibration.angle_features.v1' if representation=='angle' else 'vibration.features.v2',center=center.tolist(),scale=scale.tolist(),
        rpm_range=rpm_range,load_range=load_range,normal_accept_limit=lower,anomaly_limit=upper,
        fit_records=[r.record_id for r in fit],calibration_records=[r.record_id for r in calibration],
        fit_groups=[r.group_id for r in fit],calibration_groups=[r.group_id for r in calibration],
        calibration_quantile=float(quantile),calibration_unit='maximum_score_per_original_recording',operational_use=False)


class NormalReferenceBank:
    def __init__(self,profiles=()):
        self._profiles={}
        for profile in profiles: self.register(profile)

    def register(self,profile):
        required={'algorithm','name','feature_names','representation','feature_schema','angle_config','scope',
                  'center','scale','rpm_range','load_range','normal_accept_limit','anomaly_limit',
                  'fit_records','calibration_records','fit_groups','calibration_groups','operational_use'}
        if not isinstance(profile,Mapping) or not required.issubset(profile): raise ValueError('Incomplete normal reference profile')
        p=json.loads(json.dumps(profile,allow_nan=False)); names=p.get('feature_names',[])
        if (p.get('algorithm')!=ALGORITHM or p.get('operational_use') is not False or not isinstance(names,list) or not names
            or any(not isinstance(n,str) or not n.strip() for n in names) or len(set(names))!=len(names)):
            raise ValueError('Unsupported normal reference')
        if not isinstance(p.get('name'),str) or not p['name'].strip(): raise ValueError('Reference name required')
        if p['name'] in self._profiles: raise ValueError('Reference name already registered; replace explicitly')
        if p.get('representation') not in ('time','angle'): raise ValueError('Unknown reference representation')
        expected_schema='vibration.angle_features.v1' if p['representation']=='angle' else 'vibration.features.v2'
        if p.get('feature_schema')!=expected_schema: raise ValueError('Reference feature schema mismatch')
        if p['representation']=='angle':
            settings=p['angle_config']
            if set(settings)!={'samples_per_revolution','revolutions'}: raise ValueError('Angular settings required')
            for key,lo,hi in (('samples_per_revolution',64,4096),('revolutions',8,1024)):
                if isinstance(settings[key],bool) or not isinstance(settings[key],int) or not lo<=settings[key]<=hi: raise ValueError('Invalid angular settings')
        for field in ('center','scale'):
            a=np.asarray(p[field],dtype=float)
            if a.shape!=(len(names),) or not np.isfinite(a).all() or np.any(np.abs(a)>1e100): raise ValueError('Invalid reference arrays')
        if min(p['scale'])<.15: raise ValueError('Invalid reference scale')
        for key in ('rpm_range','load_range'): _range(p[key],key)
        for role in ('fit','calibration'):
            for field in ('groups','records'):
                items=p[role+'_'+field]
                if not isinstance(items,list) or any(not isinstance(s,str) or not s.strip() for s in items): raise ValueError('Original string identities required')
            if len(p[role+'_groups'])<2 or len(set(p[role+'_groups']))!=len(p[role+'_groups']): raise ValueError('Original acquisition groups required')
            if len(p[role+'_records'])!=len(p[role+'_groups']) or len(set(p[role+'_records']))!=len(p[role+'_records']): raise ValueError('Unique source records required')
        if set(p['fit_groups'])&set(p['calibration_groups']): raise ValueError('Calibration leakage')
        if set(p['fit_records'])&set(p['calibration_records']): raise ValueError('Record leakage')
        scope=p.get('scope',{})
        if not isinstance(scope,dict): raise ValueError('Reference scope must be a mapping')
        if any(not isinstance(scope.get(k),str) or not scope[k].strip() for k in
               ('asset_id','sensor_id','sensor_installation_id','calibration_id','condition_id','load_unit','frame')):
            raise ValueError('Reference acquisition scope required')
        if not isinstance(scope.get('signature'),dict) or scope['signature'].get('feature_schema')!='vibration.features.v2':
            raise ValueError('Explicit core measurement signature required')
        AnalysisConfig.create({k:v for k,v in scope['signature'].items() if k!='feature_schema'})
        limits=[p['normal_accept_limit'],p['anomaly_limit']]
        if any(isinstance(v,bool) or not isinstance(v,Real) or not math.isfinite(v) for v in limits) or not 0<limits[0]<=limits[1]: raise ValueError('Invalid normal limits')
        self._profiles[p['name']]=p

    def export(self): return copy.deepcopy(list(self._profiles.values()))

    def clear(self): self._profiles.clear()

    def analyze(self,result,*,representation='time'):
        if representation not in ('time','angle'): raise ValueError('Unknown reference representation')
        quality=check_acquisition(result)
        if quality['status']!='accepted': return dict(status='hold',label=None,reason=quality['reason'],issues=quality['issues'],operational_use=False)
        try: scope=_scope(result)
        except ValueError: return dict(status='hold',label=None,reason='reference_scope_metadata_required',operational_use=False)
        candidates=[p for p in self._profiles.values() if p['scope']==scope and p['representation']==representation]
        if not candidates: return dict(status='hold',label=None,reason='normal_reference_scope_mismatch',operational_use=False)
        matches=[]
        for p in candidates:
            try: vector=_eligible(result,scope,p['rpm_range'],p['load_range'],p['feature_names'],representation,p['angle_config'])
            except ValueError: continue
            matches.append((p,vector))
        if len(matches)!=1:
            return dict(status='hold',label=None,reason='reference_ambiguous' if matches else 'outside_reference_operating_range',operational_use=False)
        p,vector=matches[0]; score=float(np.sqrt(np.mean(((vector-p['center'])/p['scale'])**2)))
        state='normal' if score<=p['normal_accept_limit'] else 'hold' if score<=p['anomaly_limit'] else 'anomaly_unknown'
        return dict(status=state,label='normal' if state=='normal' else None,anomaly=False if state=='normal' else None if state=='hold' else True,
                    normal_score=score,reason='normal_gate_borderline' if state=='hold' else 'within_normal_reference' if state=='normal' else 'normal_departure',
                    reference_name=p['name'],normal_accept_limit=p['normal_accept_limit'],anomaly_limit=p['anomaly_limit'],operational_use=False)


class ReferenceStage:
    def __init__(self,bank,*,representation='time'):
        if representation not in ('time','angle'): raise ValueError('Unknown reference representation')
        self.bank=bank; self.enabled=True; self.representation=representation

    def reset_state(self,*,preserve_profiles=True):
        # Shared host bank is never deleted by resetting one analyzer.
        if not preserve_profiles: self.enabled=False

    def activate(self): self.enabled=True

    def __call__(self,result):
        if not self.enabled: return dict(status='hold',reason='normal_reference_disabled',label=None,operational_use=False)
        return self.bank.analyze(result,representation=self.representation)
