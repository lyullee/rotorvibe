"""Explicit stage-output adapter; scores remain distances, never probabilities."""
from collections.abc import Mapping
from numbers import Real
import math

DECISION_SCHEMA='vibration.decision.v1'
DECISION_STATUSES=('normal','scored','candidate','anomaly_unknown','fault_candidate','hold','invalid')
_HOLDS={'hold','missing','incompatible','outside_condition','collecting','collected',
        'cancelled','outside_domain','insufficient_history','insufficient_references',
        'no_degradation_evidence','disabled','not_loaded'}


def normalize_decision(output, *, source_stage, valid=True):
    """Return finite common fields without guessing thresholds or missing scores.

    score/normal_score are recognized; simultaneous values must agree. score_name
    preserves the source definition. Holds can retain a score for inspection but
    are never eligible to update an alarm. Similarity weights are not scores.
    """
    if not isinstance(source_stage,str) or not source_stage.strip():
        raise ValueError('Explicit source stage name required.')
    if not isinstance(valid,bool): raise ValueError('valid must be bool.')
    if not isinstance(output,Mapping): raise ValueError('Stage output must be a mapping.')
    status=output.get('status')
    if status is not None and not isinstance(status,str): raise ValueError('Status must be a string.')
    scores={}
    for key in ('score','normal_score'):
        value=output.get(key)
        if value is not None:
            if isinstance(value,bool) or not isinstance(value,Real) or not math.isfinite(value) or value<0:
                raise ValueError('Score must be finite, nonnegative and numeric.')
            scores[key]=float(value)
    if len(scores)==2 and scores['score']!=scores['normal_score']:
        raise ValueError('Conflicting score definitions; adapt explicitly.')
    name=next(iter(scores),None); score=scores.get(name)
    if output.get('schema')==DECISION_SCHEMA and name=='score':
        name=output.get('score_name')
        if not isinstance(name,str) or not name.strip(): raise ValueError('Normalized score requires score_name.')
    reason=output.get('reason'); label=output.get('label'); anomaly=output.get('anomaly')
    for field,value in (('reason',reason),('label',label)):
        if value is not None and (not isinstance(value,str) or not value.strip()):
            raise ValueError(field+' must be a nonempty string or None.')
    if anomaly is not None and not isinstance(anomaly,bool): raise ValueError('anomaly must be bool or None.')
    if not valid or status in ('invalid','quality_hold'):
        state='invalid'; label=None; anomaly=None; reason=reason or 'invalid_window'
    elif status in _HOLDS:
        state='hold'; label=None; anomaly=None; reason=reason or status
    elif status=='normal':
        if anomaly is True: raise ValueError('Normal contradicts anomaly=True.')
        state='normal'; anomaly=False
    elif status=='known_candidate': state='candidate'
    elif status=='unknown': state='anomaly_unknown'
    elif status in ('scored','candidate','anomaly_unknown','fault_candidate'): state=status
    elif status in (None,'ready') and score is not None: state='scored'
    else:
        state='hold'; label=None; anomaly=None; reason=reason or 'unsupported_or_missing_decision'
    if state in ('anomaly_unknown','fault_candidate') and anomaly is False:
        raise ValueError('Fault/anomaly outcome contradicts anomaly=False.')
    return {'schema':DECISION_SCHEMA,'source_stage':source_stage,'status':state,
            'label':label,'anomaly':anomaly,'score':score,'score_name':name,
            'score_unit':'dimensionless' if score is not None else None,
            'alarm_eligible':state not in ('hold','invalid') and score is not None,
            'reason':reason or state,'operational_use':False}


class DecisionStage:
    """Insert after the named producer, before consumers such as AlarmStage."""
    def __init__(self,source_stage):
        if not isinstance(source_stage,str) or not source_stage.strip():
            raise ValueError('Explicit source stage name required.')
        self.source_stage=source_stage

    def __call__(self,result):
        output=result.payload.get(self.source_stage)
        if output is None: output={'status':'hold','reason':'source_stage_missing'}
        return normalize_decision(output,source_stage=self.source_stage,valid=result.valid)
