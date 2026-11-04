# Persistence/release operate on observation time and episode identity.
# A software alarm state is not an independently authorized machine protection trip.

"""Caller-clock alarm policy; gaps/invalid observations never imply recovery."""
import math
from numbers import Real
from .decisions import DECISION_SCHEMA, normalize_decision

class AlarmStage:
    def __init__(self, *, score_stage='baseline', warning=3, danger=6,
                 persistence_seconds=2, release_seconds=3, max_gap_seconds=2,
                 expected_score_name=None):
        if not (all(math.isfinite(x) for x in (warning,danger,persistence_seconds,release_seconds,max_gap_seconds))
                and 0<warning<danger and min(persistence_seconds,release_seconds)>=0 and max_gap_seconds>0):
            raise ValueError('Invalid alarm thresholds/durations.')
        self.score_stage=score_stage; self.warning=warning; self.danger=danger
        if expected_score_name is not None and (not isinstance(expected_score_name,str) or not expected_score_name.strip()):
            raise ValueError('expected_score_name must be a nonempty string or None.')
        self.expected_score_name=expected_score_name
        self.persistence=persistence_seconds; self.release=release_seconds; self.max_gap=max_gap_seconds
        self.reset()

    def reset(self):
        self.level='unavailable'; self.pending=None; self.since=None; self.last=None; self.identity=None

    def reset_state(self,*,preserve_profiles=True):
        self.reset()

    def __call__(self,result):
        t=result.end_time_s; identity=(result.clock_id,result.episode_id)
        if self.identity!=identity: self.reset(); self.identity=identity
        if self.last is not None:
            if t<=self.last: raise ValueError('Alarm observations must have increasing times.')
            if t-self.last>self.max_gap: self.pending=None; self.since=None
        self.last=t
        observation=result.payload.get(self.score_stage,{})
        if observation.get('schema')==DECISION_SCHEMA:
            observation=normalize_decision(observation,source_stage=self.score_stage,valid=result.valid)
            score=observation['score'] if observation['alarm_eligible'] else None
            if self.expected_score_name is not None and observation['score_name']!=self.expected_score_name:
                score=None
        else:
            # Compatibility for existing baseline/host callbacks, excluding holds
            # with stale numeric scores. No missing score is replaced with zero.
            score=observation.get('score')
            if observation.get('status') in ('hold','quality_hold','invalid','missing','incompatible',
                                              'outside_condition','collecting','collected','cancelled'):
                score=None
            if self.expected_score_name is not None and self.expected_score_name!='score': score=None
        if score is not None and (isinstance(score,bool) or not isinstance(score,Real)):
            raise ValueError('Alarm score must be numeric, not bool/string.')
        if not result.valid or score is None or not math.isfinite(score):
            self.pending=None; self.since=None
            return {'level':'unavailable','retained_level':self.level,'score':None}
        desired='danger' if score>=self.danger else 'warning' if score>=self.warning else 'normal'
        rank={'unavailable':-1,'normal':0,'warning':1,'danger':2}
        if desired==self.level: self.pending=None; self.since=None
        else:
            if desired!=self.pending: self.pending=desired; self.since=t
            duration=self.persistence if rank[desired]>rank[self.level] else self.release
            if t-self.since>=duration:
                self.level=desired; self.pending=None; self.since=None
        return {'level':self.level,'pending':self.pending,'score':float(score)}
