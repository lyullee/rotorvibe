# Persistence/release operate on observation time and episode identity.
# A software alarm state is not an independently authorized machine protection trip.

"""Caller-clock alarm policy; gaps/invalid observations never imply recovery."""
import math

class AlarmStage:
    def __init__(self, *, score_stage='baseline', warning=3, danger=6,
                 persistence_seconds=2, release_seconds=3, max_gap_seconds=2):
        if not (all(math.isfinite(x) for x in (warning,danger,persistence_seconds,release_seconds,max_gap_seconds))
                and 0<warning<danger and min(persistence_seconds,release_seconds)>=0 and max_gap_seconds>0):
            raise ValueError('Invalid alarm thresholds/durations.')
        self.score_stage=score_stage; self.warning=warning; self.danger=danger
        self.persistence=persistence_seconds; self.release=release_seconds; self.max_gap=max_gap_seconds
        self.reset()

    def reset(self):
        self.level='unavailable'; self.pending=None; self.since=None; self.last=None; self.identity=None

    def __call__(self,result):
        t=result.end_time_s; identity=(result.clock_id,result.episode_id)
        if self.identity!=identity: self.reset(); self.identity=identity
        if self.last is not None:
            if t<=self.last: raise ValueError('Alarm observations must have increasing times.')
            if t-self.last>self.max_gap: self.pending=None; self.since=None
        self.last=t
        score=result.payload.get(self.score_stage,{}).get('score')
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
