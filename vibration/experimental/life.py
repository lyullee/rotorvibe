"""Experimental accelerated-bench reference similarity, never field RUL."""
import numpy as np
from dataclasses import dataclass
from collections import defaultdict
import math
from numbers import Real


@dataclass(frozen=True)
class LifeHistory:
    """Elapsed observations; terminal_time is event or last known follow-up.

    Future event labels belong only to evaluation. Censored follow-up does not
    supply an exact failure time. Equal condition metadata is not causal proof.
    """
    record_id: str
    group_id: str
    condition: dict
    times_s: tuple
    rms: tuple
    event_observed: bool
    terminal_time_s: float
    role: str

    def validate(self):
        for v in (self.record_id,self.group_id):
            if not isinstance(v,str) or not v: raise ValueError('Record and original life-group IDs required.')
        if self.role not in ('life_fit','life_calibration','final_test'): raise ValueError('Explicit life-data role required.')
        if not isinstance(self.event_observed,bool): raise ValueError('event_observed must be bool.')
        if not isinstance(self.condition,dict) or not {'rpm','load','load_unit','unit','installation_id'}<=set(self.condition):
            raise ValueError('RPM/load/unit/installation operating condition required.')
        for k in ('unit','load_unit','installation_id'):
            if not isinstance(self.condition[k],str) or not self.condition[k]: raise ValueError('Explicit '+k+' required.')
        if self.condition['unit'] not in ('g','m/s^2'): raise ValueError('Calibrated acceleration RMS unit required.')
        for k in ('rpm','load'):
            v=self.condition[k]
            if isinstance(v,bool) or not isinstance(v,Real) or not math.isfinite(v) or v<0 or (k=='rpm' and v==0):
                raise ValueError('Finite physical '+k+' required.')
        t=np.asarray(self.times_s,dtype=float); x=np.asarray(self.rms,dtype=float)
        if t.ndim!=1 or len(t)<2 or not np.isfinite(t).all() or t[0]<0 or np.any(np.diff(t)<=0):
            raise ValueError('Increasing nonnegative elapsed observation times required.')
        if x.ndim!=2 or len(x)!=len(t) or not 1<=x.shape[1]<=16 or not np.isfinite(x).all() or np.any(x<0) or np.any(x>1e100):
            raise ValueError('Finite nonnegative time x channel RMS required.')
        v=self.terminal_time_s
        if isinstance(v,bool) or not isinstance(v,Real) or not math.isfinite(v) or not t[-1]<=v<=1e100:
            raise ValueError('Event/follow-up time must not precede observations.')
        return self


def evaluate_life_predictions(histories,predictions,*,training_groups):
    """Evaluate final lives only. Intervals supplied by caller, not certified CIs.

    Prediction dict: record_id, observed_until_s, remaining_seconds,
    lower_seconds, upper_seconds. Censored lives contribute only interval
    compatibility with known survival, never fabricated exact error targets.
    """
    training_groups=list(training_groups)
    if not training_groups or any(not isinstance(x,str) or not x for x in training_groups):
        raise ValueError('Original training group IDs required for leakage check.')
    records={}; groups=set()
    for history in histories:
        if not isinstance(history,LifeHistory): raise TypeError('LifeHistory required.')
        history.validate()
        if history.role!='final_test' or history.group_id in training_groups: raise ValueError('Final life overlaps fitting/calibration.')
        if history.record_id in records or history.group_id in groups: raise ValueError('Duplicate life record/group.')
        records[history.record_id]=history; groups.add(history.group_id)
    errors=defaultdict(list); coverage=defaultdict(list); censored=[]; seen=set(); n=0
    for prediction in predictions:
        if set(prediction)!={'record_id','observed_until_s','remaining_seconds','lower_seconds','upper_seconds'}:
            raise ValueError('Explicit prediction identity, observation cutoff and interval required.')
        h=records[prediction['record_id']]
        cutoff=prediction['observed_until_s']; point=prediction['remaining_seconds']
        lo=prediction['lower_seconds']; hi=prediction['upper_seconds']
        if any(isinstance(v,bool) or not isinstance(v,Real) or not math.isfinite(v) or not 0<=v<=1e100 for v in (cutoff,point,lo,hi)):
            raise ValueError('Finite nonnegative prediction values required.')
        if not lo<=point<=hi or cutoff not in h.times_s or cutoff>=h.terminal_time_s:
            raise ValueError('Prediction interval/cutoff does not match observed history.')
        key=(h.record_id,cutoff)
        if key in seen: raise ValueError('Duplicate life forecast cutoff.')
        seen.add(key); n+=1
        remaining=h.terminal_time_s-cutoff
        if h.event_observed:
            errors[h.record_id].append(point-remaining)
            coverage[h.record_id].append(lo<=remaining<=hi)
        else: censored.append(hi>=remaining)
    if not n: raise ValueError('At least one forecast required.')
    # Equal weight per original life prevents densely sampled lives dominating.
    mae=float(np.mean([np.mean(np.abs(v)) for v in errors.values()])) if errors else None
    rmse=float(np.sqrt(np.mean([np.mean(np.square(v)) for v in errors.values()]))) if errors else None
    interval=float(np.mean([np.mean(v) for v in coverage.values()])) if coverage else None
    return {'schema':'vibration.experimental-life-evaluation.v1','status':'experimental_evaluation',
            'forecasts':n,'complete_lives_evaluated':len(errors),'complete_lives_available':sum(h.event_observed for h in records.values()),
            'censored_lives_available':sum(not h.event_observed for h in records.values()),
            'censored_forecasts':len(censored),'mae_seconds_equal_life':mae,'rmse_seconds_equal_life':rmse,
            'empirical_interval_coverage_equal_life':interval,
            'censored_survival_compatible_fraction':float(np.mean(censored)) if censored else None,
            'confidence_interval_validated':False,'field_rul_qualified':False,'operational_use':False}


class ReferenceLifeEstimator:
    """Experimental reference-life matching. Held-out full lives never enter the library."""
    def __init__(self,catalog,*,experimental_enabled=False):
        if not isinstance(experimental_enabled,bool): raise ValueError('Explicit bool experimental opt-in required.')
        self.enabled=experimental_enabled
        self.references=[]
        if not self.enabled: return
        for id,row in catalog.lives.items():
            if row['role']!='training_complete_life': continue
            rms=np.asarray(row['nominal_rms_series'],dtype=float)
            if (rms.ndim!=2 or len(rms)<21 or not 1<=rms.shape[1]<=16 or not np.isfinite(rms).all()
                or np.any(rms<0) or np.any(rms>1e100)):
                raise ValueError('Reference requires at least 21 finite nonnegative RMS observations.')
            if isinstance(row['nominal_rpm'],bool) or not isinstance(row['nominal_rpm'],Real) or not 0<row['nominal_rpm']<=1e9:
                raise ValueError('Finite positive nominal reference RPM required.')
            base=np.maximum(np.median(rms[:20],axis=0),1e-12)
            hi=np.log(np.maximum(rms,1e-12)/base)
            smooth=np.vstack([np.mean(hi[max(0,i-4):i+1],axis=0) for i in range(len(hi))])
            self.references.append({'bearing':row['bearing'],'rpm':row['nominal_rpm'],
                                    'hi':smooth,'seconds_left':np.arange(len(hi)-1,-1,-1)*10})

    def estimate(self, source):
        if not self.enabled:
            return {'status':'disabled','reason':'experimental_reference_life_opt_in_required',
                    'field_rul_qualified':False,'operational_use':False}
        if source.get('dataset')!='FEMTO':
            return {'status':'outside_domain','reason':'수명 추정은 현재 PRONOSTIA 관측 이력에 한정됩니다.'}
        prefix=source.get('rul_prefix')
        if not prefix:
            return {'status':'insufficient_history','reason':'첫 20개 관측 이후에 과거 구간으로 기준을 잡습니다.'}
        baseline=np.asarray(prefix['baseline_rms'],dtype=float)
        recent=np.asarray(prefix['recent_rms'],dtype=float)
        if (baseline.ndim!=1 or not 1<=len(baseline)<=16 or recent.ndim!=2 or not len(recent)
            or recent.shape[1]!=len(baseline) or not np.isfinite(baseline).all() or not np.isfinite(recent).all()
            or np.any(baseline<0) or np.any(recent<0) or np.any(baseline>1e100) or np.any(recent>1e100)):
            raise ValueError('Finite nonnegative matching RMS prefix required.')
        if isinstance(source.get('rpm'),bool) or not isinstance(source.get('rpm'),Real) or not 0<source['rpm']<=1e9:
            raise ValueError('Finite positive source RPM required.')
        baseline=np.maximum(baseline,1e-12)
        query=np.mean(np.log(np.maximum(recent,1e-12)/baseline),axis=0)
        matches=[]
        for r in self.references:
            if r['hi'].shape[1]!=len(baseline): continue
            if r['bearing']==source['record_id'] or abs(r['rpm']-source['rpm'])>5: continue
            distance=np.sqrt(np.mean((r['hi']-query)**2,axis=1))
            # Earliest points cannot estimate life meaningfully before an observable change.
            distance[:20]=np.inf
            index=int(np.argmin(distance))
            matches.append({'reference_bearing':r['bearing'],'distance':float(distance[index]),
                            'remaining_seconds':int(r['seconds_left'][index])})
        if len(matches)<2: return {'status':'insufficient_references','reason':'동일 RPM의 다른 학습 수명 두 개 이상이 필요합니다.'}
        if float(np.max(query))<0.25:
            return {'status':'no_degradation_evidence','reason':'정상 수준과 구분되는 열화 증가가 부족해 시간 예측을 보류합니다.'}
        values=np.asarray([m['remaining_seconds'] for m in matches])
        return {'status':'experimental','remaining_seconds':float(np.median(values)),
                'field_rul_qualified':False,'operational_use':False,'confidence_interval_validated':False,
                'reference_range_seconds':[float(values.min()),float(values.max())],'references':matches,
                'method':'같은 RPM의 학습 수명에서 초기 20관측 대비 log RMS 이력 유사도',
                'note':'범위는 참고 수명의 분산이며 검증된 신뢰구간이 아닙니다. 가속시험 종료까지의 벤치 추정입니다.'}
