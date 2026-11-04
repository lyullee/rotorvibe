# Experimental subtype head conditioned on an upstream anomaly decision.
# It has no healthy class. Scope holds and novelty rejection are required outcomes.
# Four representatives per original file retain variation without length-based weighting.
# The near-perfect within-rig holdout did not transfer to a new bearing or external rig.

"""Experimental rotor fault candidates with subharmonics, impacts and optional RPM weighting.

Separate optional API; never changes historical frozen conditioned models.
Weights are similarities, not calibrated fault probabilities.
"""
import copy
import json
from collections.abc import Mapping
import numpy as np
from scipy.signal import hilbert
from .conditioned import canonical_values

ALGORITHM='rotor_fault_morphology.v1'


def _scope(value):
    """Same scope contract at fit, load and inference; never infer asset identity."""
    if not isinstance(value, Mapping):
        raise ValueError('Fault scope must be a mapping.')
    value=copy.deepcopy(dict(value))
    if any(not isinstance(value.get(k),str) or not value[k].strip()
           for k in ('asset_id','condition_id','unit')):
        raise ValueError('Explicit nonempty asset_id, condition_id and unit required.')
    if value['unit'] not in ('g','m/s^2'):
        raise ValueError('Fault scope requires calibrated acceleration in g or m/s^2.')
    if any(not isinstance(k,str) or not k.strip() for k in value):
        raise ValueError('Fault scope keys must be nonempty strings.')
    try: json.dumps(value,allow_nan=False)
    except (TypeError,ValueError) as exc:
        raise ValueError('Fault scope must be finite JSON-compatible metadata.') from exc
    return value


def _names(value):
    if (not isinstance(value,(list,tuple)) or not value or
        any(not isinstance(n,str) or not n.strip() for n in value) or len(set(value))!=len(value)):
        raise ValueError('Feature names must be nonempty, unique strings in schema order.')
    return list(value)

def fault_features(values,sample_rate_hz,rpm):
    if isinstance(rpm,(bool,np.bool_)) or not np.isscalar(rpm) or not np.isfinite(rpm) or not 590<=rpm<=1620:
        raise ValueError('Finite nominal RPM in 590..1620 required.')
    a=np.asarray(values,dtype=float)
    if a.ndim==2 and a.shape[1]==1: a=a[:,0]
    if a.ndim!=1 or len(a)!=2*sample_rate_hz: raise ValueError('Single channel, exactly two seconds required.')
    x=canonical_values(a,sample_rate_hz,4000)[:,0]; x=x-x.mean()
    rms=np.sqrt(np.mean(x*x))
    if rms<=1e-15: raise ValueError('Flat waveform.')
    x=x/rms; window=np.hanning(len(x)); power=np.abs(np.fft.rfft(x*window))**2
    f=np.fft.rfftfreq(len(x),1/4000); total=power.sum(); half=max(.75,.03*rpm/60)
    orders=np.arange(.5,20.01,.5); energies=np.array([power[np.abs(f-o*rpm/60)<=half].sum()/total for o in orders])
    names=['log_rms','log_crest','log_kurtosis','log_impulse','log_entropy']
    probability=power/total; entropy=-np.sum(probability*np.log(np.maximum(probability,1e-30)))/np.log(len(power))
    out=[np.log(rms),np.log(np.max(np.abs(x))),np.log(np.mean(x**4)),np.log(np.max(np.abs(x))/np.mean(np.abs(x))),np.log(max(entropy,1e-12))]
    for o,e in zip(orders,energies): names.append(f'order_{o:g}'); out.append(np.log(max(e,1e-12)))
    # Half-order sums and harmonic distortion relative to 1X support looseness vs unbalance.
    for name,e in [('half_orders',energies[::2].sum()),('harmonics_2_10',energies[3:20:2].sum()),('fundamental',energies[1])]:
        names.append(name); out.append(np.log(max(e,1e-12)))
    for low,high in [(0,50),(50,100),(100,200),(200,400),(400,800),(800,1200),(1200,1900)]:
        names.append(f'band_{low}_{high}'); out.append(np.log(max(power[(f>=low)&(f<high)].sum()/total,1e-12)))
    envelope=np.abs(hilbert(x)); envelope-=envelope.mean(); ep=np.abs(np.fft.rfft(envelope*window))**2
    for o in [.5,1,2,3,4,6]:
        names.append(f'envelope_{o:g}'); out.append(np.log(max(ep[np.abs(f-o*rpm/60)<=half].sum()/max(ep.sum(),1e-30),1e-12)))
    return tuple(names),np.asarray(out)

def fit_fault_discriminator(x,labels,rpms,groups,*,names,scope,mode='morphology',rpm_penalty=1.,margin=.03):
    names=_names(names); scope=_scope(scope)
    x=np.asarray(x,dtype=float); y=np.asarray(labels); rpm=np.asarray(rpms,dtype=float); groups=np.asarray(groups)
    if x.ndim!=2 or x.shape[1]!=len(names) or not np.isfinite(x).all() or not len(x) or np.any(np.abs(x)>1e100): raise ValueError('Invalid or out-of-range feature matrix.')
    if any(v.shape!=(len(x),) for v in (y,rpm,groups)) or not np.isfinite(rpm).all(): raise ValueError('Invalid labels/RPM/groups.')
    classes=sorted(set(y.tolist()))
    if set(classes)!={'looseness','misalignment','unbalance'}: raise ValueError('Three declared rotor fault classes required.')
    if mode not in ('orders','morphology') or not np.isfinite([rpm_penalty,margin]).all() or min(rpm_penalty,margin)<0 or max(rpm_penalty,margin)>1e100: raise ValueError('Invalid model settings.')
    if np.any((rpm<590)|(rpm>1620)) or len(set(names))!=len(names): raise ValueError('Invalid speed or feature names.')
    indices=[i for i,n in enumerate(names) if mode=='morphology' or n.startswith('order_')]
    prototypes=[]; py=[]; pr=[]; pg=[]
    for group in sorted(set(groups.tolist())):
        mask=groups==group
        if len(set(y[mask]))!=1 or len(set(rpm[mask]))!=1: raise ValueError('Mixed original recording.')
        # Four chronological sections preserve within-recording variation, equally per file.
        for block in np.array_split(x[mask],4):
            if not len(block): continue
            prototypes.append(np.median(block[:,indices],axis=0)); py.append(str(y[mask][0])); pr.append(float(rpm[mask][0])); pg.append(group)
    p=np.asarray(prototypes); center=np.median(p,axis=0); scale=np.maximum(1.4826*np.median(np.abs(p-center),axis=0),.3)
    p=(p-center)/scale
    # Leave-original-file-out empirical novelty radius, not within-window calibration.
    limits=[]
    for label in classes:
        ds=[]
        for i in np.flatnonzero(np.asarray(py)==label):
            mask=(np.asarray(py)==label)&(np.asarray(pg)!=pg[i])
            if not mask.any(): raise ValueError('Multiple original recordings per fault required.')
            distance=np.mean((p[mask]-p[i])**2,axis=1)+rpm_penalty*(np.log(np.asarray(pr)[mask]/pr[i])/.2)**2
            ds.append(float(np.sqrt(distance.min())))
        limits.append(max(1.,float(np.quantile(ds,.99))*1.5))
    profile=dict(algorithm=ALGORITHM,names=list(names),indices=indices,center=center.tolist(),scale=scale.tolist(),
        prototypes=p.tolist(),labels=py,rpms=pr,groups=pg,classes=classes,limits=limits,scope=copy.deepcopy(scope),
        mode=mode,rpm_penalty=float(rpm_penalty),margin=float(margin),operational_use=False)
    FaultDiscriminator(profile)
    return profile

class FaultDiscriminator:
    def __init__(self,profile):
        if not isinstance(profile,Mapping): raise ValueError('Fault profile must be a mapping.')
        self.profile=copy.deepcopy(profile); p=self.profile
        required={'algorithm','names','indices','center','scale','prototypes','rpms','limits',
                  'classes','labels','groups','scope','mode','rpm_penalty','margin','operational_use'}
        if not required.issubset(p): raise ValueError('Missing fault profile fields: '+', '.join(sorted(required-set(p))))
        if p.get('algorithm')!=ALGORITHM: raise ValueError('Unsupported fault profile.')
        self.scope=_scope(p['scope']); _names(p['names'])
        if p['mode'] not in ('orders','morphology') or p['operational_use'] is not False:
            raise ValueError('Unsupported fault mode or operational-use claim.')
        for key in ('center','scale','prototypes','rpms','limits'):
            a=np.asarray(p[key],dtype=float)
            if not np.isfinite(a).all() or np.any(np.abs(a)>1e100): raise ValueError('Nonfinite/out-of-range profile.')
        if np.any(np.asarray(p['scale'])<=0): raise ValueError('Invalid scale.')
        indices=np.asarray(p['indices']); d=len(indices); n=len(p['labels'])
        if indices.ndim!=1 or not d or indices.dtype.kind not in 'iu' or min(indices)<0 or max(indices)>=len(p['names']) or len(set(indices))!=d: raise ValueError('Invalid feature indices.')
        expected=[i for i,name in enumerate(p['names']) if p['mode']=='morphology' or name.startswith('order_')]
        if indices.tolist()!=expected: raise ValueError('Selected indices differ from declared feature mode/schema.')
        if np.asarray(p['prototypes']).shape!=(n,d) or np.asarray(p['center']).shape!=(d,) or np.asarray(p['scale']).shape!=(d,) or np.asarray(p['rpms']).shape!=(n,): raise ValueError('Invalid profile dimensions.')
        if set(p['classes'])!={'looseness','misalignment','unbalance'} or set(p['labels'])!=set(p['classes']) or len(p['classes'])!=3 or len(p['limits'])!=3 or min(p['limits'])<=0: raise ValueError('Invalid fault classes/radii.')
        if not np.isfinite([p['rpm_penalty'],p['margin']]).all() or min(p['rpm_penalty'],p['margin'])<0 or max(p['rpm_penalty'],p['margin'])>1e100 or min(p['rpms'])<590 or max(p['rpms'])>1620: raise ValueError('Invalid profile speed/settings.')
        if not isinstance(p['groups'],(list,tuple)) or len(p['groups'])!=n:
            raise ValueError('One acquisition group per prototype required.')
        memberships={}
        for group,label,rpm in zip(p['groups'],p['labels'],p['rpms']):
            if isinstance(group,bool) or not isinstance(group,(str,int)) or (isinstance(group,str) and not group.strip()):
                raise ValueError('Acquisition group must be a nonempty string or integer.')
            key=(type(group).__name__,group)
            if key in memberships and memberships[key]!=(label,rpm): raise ValueError('Mixed acquisition group.')
            memberships[key]=(label,rpm)
        if any(sum(label==v[0] for v in memberships.values())<2 for label in p['classes']):
            raise ValueError('Multiple original acquisition groups per fault required.')

    def predict(self,features,rpm,*,scope):
        p=self.profile; base={'operational_use':False,'conditional_on_anomaly':True}
        # Invalid/missing caller scope is an unsupported observation, not a wildcard.
        try: scope=_scope(scope)
        except ValueError: return dict(base,status='hold',label=None,reason='fault_scope_missing_or_invalid')
        if any(scope.get(k)!=v for k,v in self.scope.items()): return dict(base,status='hold',label=None,reason='fault_scope_mismatch')
        v=np.asarray(features,dtype=float)
        if v.shape!=(len(p['names']),) or not np.isfinite(v).all() or np.any(np.abs(v)>1e100): raise ValueError('Invalid or out-of-range fault features.')
        if rpm is None or isinstance(rpm,(bool,np.bool_)) or not np.isscalar(rpm) or not np.isfinite(rpm) or not 590<=rpm<=1620: return dict(base,status='hold',label=None,reason='outside_speed_scope')
        try:
            with np.errstate(over='raise',invalid='raise',divide='raise',under='ignore'):
                z=(v[p['indices']]-p['center'])/p['scale']
                distances=np.sqrt(np.mean((np.asarray(p['prototypes'])-z)**2,axis=1)+p['rpm_penalty']*(np.log(np.asarray(p['rpms'])/rpm)/.2)**2)
                by=np.array([distances[np.asarray(p['labels'])==c].min() for c in p['classes']])
                order=np.argsort(by); winner=order[0]; gap=float(by[order[1]]-by[winner])
            if not np.isfinite(distances).all() or not np.isfinite(gap): raise FloatingPointError()
        except FloatingPointError as exc:
            raise ValueError('Fault distance calculation exceeds finite numeric range.') from exc
        matches=[dict(label=c,distance=float(d)) for c,d in zip(p['classes'],by)]
        if by[winner]>p['limits'][winner] or gap<=max(p['margin'],1e-12): return dict(base,status='anomaly_unknown',label=None,relative_matches=matches,margin=gap)
        return dict(base,status='fault_candidate',label=p['classes'][winner],relative_matches=matches,margin=gap)

    def analyze(self,values,sample_rate_hz,rpm,*,scope):
        names,x=fault_features(values,sample_rate_hz,rpm)
        if list(names)!=self.profile['names']: raise ValueError('Feature schema mismatch.')
        return self.predict(x,rpm,scope=scope)

class FaultDiscriminationStage:
    """Compose AFTER an anomaly gate; never interprets healthy windows as faults."""
    def __init__(self,model,gate_key='conditioned'): self.model=model; self.gate_key=gate_key
    def __call__(self,result):
        raise RuntimeError('FaultDiscriminationStage requires raw-window hook.')
    def analyze_window(self,result,values):
        gate=result.payload.get(self.gate_key,{})
        if not result.valid or gate.get('anomaly') is not True: return {'status':'hold','label':None,'reason':'confirmed_anomaly_gate_required','operational_use':False}
        if result.payload.get('rpm_variation_ratio',0)>.03: return {'status':'hold','label':None,'reason':'variable_speed_requires_angle_domain_features','operational_use':False}
        config=result.metadata['measurement']; scope={**result.metadata.get('source',{}),'unit':config['unit']}
        return self.model.analyze(values,config['sample_rate_hz'],result.payload.get('rpm'),scope=scope)
