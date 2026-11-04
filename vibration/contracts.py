# Explicit samples/units/channels/time/RPM/source identity are mathematical inputs.
# Read-only input copies prevent host mutation races; result payloads still need care.

"""In-process contracts. Times are seconds in the explicitly named caller clock."""
from dataclasses import dataclass, field
from typing import Any, Mapping
import copy
import math
from numbers import Real, Integral
import numpy as np


@dataclass(frozen=True)
class SignalBlock:
    values: np.ndarray
    sample_rate_hz: float
    unit: str = 'unknown'
    start_time_s: float = 0.0
    clock_id: str = 'sample_clock'
    episode_id: str = 'default'
    channels: tuple[str, ...] = ()
    valid: np.ndarray | None = None
    rpm: float | np.ndarray | None = None
    sequence: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        a=np.array(self.values,dtype=float,copy=True)
        if a.ndim==1: a=a[:,None]
        if a.ndim!=2 or not len(a) or not 1<=a.shape[1]<=16:
            raise ValueError('values must be nonempty samples × channels (1..16).')
        if (isinstance(self.sample_rate_hz,bool) or not isinstance(self.sample_rate_hz,Real) or
            not math.isfinite(self.sample_rate_hz) or self.sample_rate_hz<=0 or
            isinstance(self.start_time_s,bool) or not isinstance(self.start_time_s,Real) or not math.isfinite(self.start_time_s)):
            raise ValueError('Finite positive sample rate and finite start time required.')
        if self.unit not in ('unknown','g','m/s^2','V'): raise ValueError('Explicit supported input unit required.')
        if (not math.isfinite(self.start_time_s+len(a)/self.sample_rate_hz) or
            self.start_time_s+1/self.sample_rate_hz<=self.start_time_s):
            raise ValueError('Clock magnitude cannot represent sample spacing; use an elapsed clock.')
        if self.sequence is not None and (isinstance(self.sequence,bool) or not isinstance(self.sequence,Integral) or self.sequence<0):
            raise ValueError('Sequence must be a nonnegative integer.')
        names=tuple(self.channels) or tuple(f'ch{i+1}' for i in range(a.shape[1]))
        if (len(names)!=a.shape[1] or len(set(names))!=len(names) or
            any(not isinstance(x,str) or not x for x in names)):
            raise ValueError('Channel names must be nonempty, unique and match values.')
        if not isinstance(self.clock_id,str) or not self.clock_id or not isinstance(self.episode_id,str) or not self.episode_id:
            raise ValueError('Explicit nonempty clock_id and episode_id required.')
        valid=np.isfinite(a).all(axis=1)
        if self.valid is not None:
            v=np.asarray(self.valid)
            if v.shape!=valid.shape: raise ValueError('valid must have one flag per sample.')
            if v.dtype.kind not in 'buif' or not np.isfinite(v).all() or not np.isin(v,(0,1)).all():
                raise ValueError('valid must contain boolean flags or finite numeric 0/1, never strings/NaN.')
            valid &= v.astype(bool)
        rpm=self.rpm
        if rpm is not None:
            if np.asarray(rpm).dtype.kind=='b': raise ValueError('RPM must be numeric, not boolean.')
            r=np.asarray(rpm,dtype=float)
            if r.ndim not in (0,1) or (r.ndim==1 and r.shape!=(len(a),)) or not np.isfinite(r).all() or np.any(r<1e-6) or np.any(r>1e9):
                raise ValueError('RPM must be scalar or per-sample, within 1e-6..1e9.')
            rpm=float(r) if r.ndim==0 else r.copy()
            if isinstance(rpm,np.ndarray): rpm.setflags(write=False)
        a.setflags(write=False); valid.setflags(write=False)
        object.__setattr__(self,'values',a); object.__setattr__(self,'valid',valid)
        object.__setattr__(self,'channels',names); object.__setattr__(self,'rpm',rpm)
        object.__setattr__(self,'metadata',copy.deepcopy(dict(self.metadata)))


def json_value(value):
    if isinstance(value,np.ndarray): return value.tolist()
    if isinstance(value,np.generic): return value.item()
    if isinstance(value,Mapping): return {k:json_value(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)): return [json_value(v) for v in value]
    return value


@dataclass(frozen=True)
class AnalysisResult:
    start_time_s: float
    end_time_s: float  # exclusive
    clock_id: str
    episode_id: str
    channels: tuple[str, ...]
    valid: bool
    payload: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def features(self): return self.payload.get('_features')

    @property
    def feature_names(self): return tuple(self.payload.get('_feature_names',()))

    @property
    def metrics(self): return self.payload.get('metrics',{})

    @property
    def rpm_trace(self):
        """Read-only per-sample measured RPM, or None; never fabricate a trace."""
        return self.payload.get('_rpm_trace')

    def to_dict(self, *, include_features=True):
        p={k:v for k,v in self.payload.items() if include_features or not k.startswith('_')}
        return json_value({'schema':'vibration.analysis.v1','start_time_s':self.start_time_s,
                           'end_time_s':self.end_time_s,'clock_id':self.clock_id,'episode_id':self.episode_id,
                           'channels':self.channels,'valid':self.valid,'payload':p,'metadata':self.metadata})
