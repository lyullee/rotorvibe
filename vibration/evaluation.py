"""Coverage-aware validation and observation-time alarm episodes, not a field guarantee."""
from dataclasses import dataclass
from numbers import Real
import math
from .decisions import normalize_decision


@dataclass(frozen=True)
class ValidationObservation:
    record_id: str
    acquisition_id: str
    start_s: float
    end_s: float
    truth: str
    decision: dict
    alarm_level: str = 'unavailable'
    clock_id: str = 'elapsed'
    asset_id: str = 'asset'


def _union_duration(intervals):
    total=0.; end=None
    for lo,hi in sorted(intervals):
        if end is None or lo>end: total+=hi-lo
        elif hi>end: total+=hi-end
        end=hi if end is None else max(end,hi)
    return total


def evaluate_observations(observations,*,fault_onsets=None,max_gap_seconds=2.):
    rows=list(observations); onsets=dict(fault_onsets or {})
    if not rows: raise ValueError('Validation observations required')
    if isinstance(max_gap_seconds,bool) or not isinstance(max_gap_seconds,Real) or not math.isfinite(max_gap_seconds) or max_gap_seconds<=0:
        raise ValueError('Positive finite alarm gap required')
    seen=set(); groups={}; record_truth={}; record_context={}
    for row in rows:
        if not isinstance(row,ValidationObservation): raise ValueError('ValidationObservation required')
        if any(not isinstance(s,str) or not s.strip() for s in (row.record_id,row.acquisition_id,row.truth,row.clock_id,row.asset_id)):
            raise ValueError('Explicit validation identities/labels required')
        if any(isinstance(v,bool) or not isinstance(v,Real) or not math.isfinite(v) for v in (row.start_s,row.end_s)) or row.end_s<=row.start_s or not math.isfinite(row.end_s-row.start_s):
            raise ValueError('Finite positive observation interval required')
        if row.alarm_level not in ('normal','warning','danger','unavailable'): raise ValueError('Unknown alarm level')
        if not isinstance(row.decision,dict): raise ValueError('Decision mapping required')
        normalize_decision(row.decision,source_stage='evaluation')
        key=(row.asset_id,row.clock_id,row.acquisition_id)
        if record_context.setdefault(row.record_id,key)!=key: raise ValueError('Record identity spans different acquisitions/clocks')
        identity=(*key,row.start_s,row.end_s)
        if identity in seen: raise ValueError('Duplicate validation sample interval')
        seen.add(identity); groups.setdefault(key,[]).append(row)
        previous=record_truth.setdefault(key,row.truth)
        if previous!=row.truth: raise ValueError('Split mixed ground-truth acquisition intervals before evaluation')
    for key,onset in onsets.items():
        if not isinstance(key,str) or isinstance(onset,bool) or not isinstance(onset,Real) or not math.isfinite(onset):
            raise ValueError('Record onset times must be finite numbers')
        if key not in {r.record_id for r in rows}: raise ValueError('Unknown onset record')
    normal=[r for r in rows if r.truth=='normal']; faults=[r for r in rows if r.truth!='normal']
    def supported(r):
        return r.decision.get('status')=='normal' or (r.decision.get('status') in ('anomaly_unknown','fault_candidate') and r.decision.get('anomaly') is True)
    false=[r for r in normal if supported(r) and r.decision.get('anomaly') is True]
    supported_normal=[r for r in normal if supported(r)]
    head=[r for r in faults if r.decision.get('status')=='fault_candidate' and isinstance(r.decision.get('label'),str)]
    typed=[r for r in head if r.decision.get('anomaly') is True]
    correct=[r for r in typed if r.decision['label']==r.truth]
    event_count=0; false_events=0; active_seconds=0.; elapsed=0.; normal_elapsed=0.; supported_normal_seconds=0.; normal_alarm_seconds=0.
    acquisition_normal=0; acquisition_any_false=0
    for key,items in groups.items():
        items=sorted(items,key=lambda r:r.end_s)
        if any(a.end_s==b.end_s for a,b in zip(items,items[1:])): raise ValueError('Alarm observations must have distinct end times')
        duration=_union_duration([(r.start_s,r.end_s) for r in items]); elapsed+=duration
        is_normal=items[0].truth=='normal'
        if is_normal:
            acquisition_normal+=1; normal_elapsed+=duration
            acquisition_any_false+=int(any(r in false for r in items))
            supported_normal_seconds+=_union_duration([(r.start_s,r.end_s) for r in items if supported(r)])
            normal_alarm_seconds+=_union_duration([(r.start_s,r.end_s) for r in items if r.alarm_level!='unavailable'])
        active=False; last=None; previous_level='unavailable'
        for row in items:
            gap=last is not None and row.end_s-last>max_gap_seconds
            if gap: active=False
            level=row.alarm_level
            if level in ('warning','danger'):
                if not active:
                    event_count+=1; false_events+=int(is_normal)
                if active and previous_level in ('warning','danger') and not gap:
                    active_seconds+=row.end_s-last
                active=True
            elif level=='normal': active=False
            # unavailable is not recovery; a later active observation may belong
            # to the same episode, but unknown time is excluded from duration.
            previous_level=level; last=row.end_s
    delays={}
    for record,onset in onsets.items():
        matching=[r for r in faults if r.record_id==record]
        if not matching or not min(r.start_s for r in matching)<=onset<max(r.end_s for r in matching):
            raise ValueError('Fault onset must lie within an observed faulty record')
        detections=[r.end_s-onset for r in matching if r.end_s>=onset and r.alarm_level in ('warning','danger')]
        preexisting=any(r.end_s<onset and r.alarm_level in ('warning','danger') for r in matching)
        delays[record]=min(detections) if detections and not preexisting else None
    rate=lambda n,d: n/d if d else None
    if not all(math.isfinite(v) for v in (elapsed,normal_elapsed,active_seconds,supported_normal_seconds,normal_alarm_seconds)):
        raise ValueError('Evaluation duration exceeds finite numeric range')
    return {'schema':'vibration.validation.v1','windows':len(rows),'normal_windows':len(normal),'fault_windows':len(faults),
        'normal_acceptance':rate(sum(r.decision.get('status')=='normal' for r in normal),len(normal)),
        'supported_normal_windows':len(supported_normal),'normal_false_positive_rate':rate(len(false),len(supported_normal)),
        'normal_decision_coverage':rate(len(supported_normal),len(normal)),
        'fault_detection_recall':rate(sum(supported(r) and r.decision.get('anomaly') is True for r in faults),len(faults)),
        'fault_type_accuracy_unconditional':rate(len(correct),len(faults)),
        'fault_type_accuracy_conditional':rate(len(correct),len(typed)),'fault_type_coverage':rate(len(typed),len(faults)),
        'fault_head_accuracy_given_true_fault':rate(sum(r.decision['label']==r.truth for r in head),len(head)),
        'fault_head_coverage_given_true_fault':rate(len(head),len(faults)),
        'normal_acquisitions':acquisition_normal,'normal_acquisitions_with_false_positive':acquisition_any_false,
        'observation_seconds':elapsed,'normal_seconds':normal_elapsed,'supported_normal_seconds':supported_normal_seconds,
        'alarm_events_observed':event_count,'false_alarm_events_observed':false_events,
        'normal_alarm_coverage_seconds':normal_alarm_seconds,
        'false_alarm_events_per_normal_hour':rate(false_events,normal_alarm_seconds/3600),
        'alarm_duration_confirmed_seconds':active_seconds,'detection_delay_seconds':delays,
        'denominator_note':'Overlapping windows share time; union durations used. Unsupported normal windows excluded from FPR, never counted as correct normals.',
        'uncertainty_note':'Unavailable spans are not recovery. Gaps can split observed episodes; duration excludes unknown spans. No field population error guarantee.',
        'operational_use':False}
