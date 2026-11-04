# The host owns acquisition and scheduling; this object is synchronous.
# Source identity, sequence and clock discontinuities must not become one FFT window.
# Stage order is semantic: later stages may inspect earlier results; failures propagate.

"""Synchronous NumPy API: no database, server, files, worker or global runtime."""
from dataclasses import replace
import copy
import json
import numpy as np
from .config import AnalysisConfig
from .contracts import SignalBlock, AnalysisResult,json_value
from .dsp import analyze, G0


class VibrationAnalyzer:
    """One instance per stream; caller owns scheduling and synchronization.

    Stages add named outputs, sinks receive completed results. Exceptions propagate
    to the caller; a failed downstream component is never silently marked healthy.
    """
    def __init__(self, config=None, *, bearing_provider=None, stages=None, sinks=()):
        self._config=copy.deepcopy(config or AnalysisConfig()).validate()
        self.bearing_provider=bearing_provider
        self.stages=dict(stages or {}); self.sinks=tuple(sinks)
        reserved={'metrics','quality','status','rpm','rpm_variation_ratio','frequency_resolution_hz','waveform','spectrum','psd',
                  'envelope_spectrum','spectrogram','order_spectrum','bearing_markers','rotation_markers','diagnosis'}
        if any(not isinstance(k,str) or not k or k.startswith('_') or k in reserved or not callable(v) for k,v in self.stages.items()):
            raise ValueError('Stages require unique non-reserved names and callable implementations.')
        if any(not callable(sink) for sink in self.sinks): raise ValueError('Each sink must be callable.')
        self.reset()

    @property
    def config(self): return copy.deepcopy(self._config)

    def reset(self,*,reset_stages=False,preserve_profiles=True):
        """Reset buffering; opt in to stage lifecycle, preserving references by default.

        Legacy reset() remains buffer-only. A stream discontinuity resets compliant
        stage state automatically; external host objects without a hook are untouched.
        """
        if not isinstance(reset_stages,bool) or not isinstance(preserve_profiles,bool):
            raise ValueError('Reset options must be bool.')
        self._a=None; self._valid=None; self._rpm=None; self._rpm_measured=None; self._next=None
        self._identity=None; self._sequence=None; self._time=0.0
        if reset_stages:
            for stage in self.stages.values():
                hook=getattr(stage,'reset_state',None)
                if callable(hook): hook(preserve_profiles=preserve_profiles)

    def analyze(self, block: SignalBlock) -> AnalysisResult:
        c=self._config
        if block.sample_rate_hz!=c.sample_rate_hz or block.values.shape[1]!=c.channels:
            raise ValueError('Signal sample rate/channels must match AnalysisConfig.')
        expected='V' if c.input_representation=='volts' else c.unit
        if block.unit!=expected: raise ValueError(f'Expected input unit {expected!r}.')
        if len(block.values)!=round(c.window_seconds*c.sample_rate_hz):
            raise ValueError('analyze requires exactly one configured window; use push for chunks.')
        quality=[]
        if not block.valid.all(): quality.append('invalid_samples')
        a=block.values
        if c.input_representation=='volts':
            with np.errstate(over='ignore',divide='ignore',invalid='ignore',under='ignore'):
                a=(a-c.bias_voltage_v)/(np.asarray(c.sensitivity_mv_per_g)/1000*c.conditioner_gain)
                if c.unit=='m/s^2': a=a*G0
            if not np.isfinite(a).all(): quality.append('calibration_out_of_range')
        if not quality and np.any(np.max(np.abs(a),axis=0)>1e12): quality.append('amplitude_out_of_range')
        if not quality and np.any(np.ptp(a,axis=0)<=1e-15): quality.append('flat_channel')
        if c.clip_abs is not None and np.any(np.abs(a)>=c.clip_abs): quality.append('clipping')
        rpm=block.rpm if block.rpm is not None else c.rpm
        scalar=float(np.mean(rpm)) if rpm is not None else None
        cfg=replace(c,rpm=scalar)
        bf={}
        if c.bearing_id and scalar is not None:
            if self.bearing_provider is None: raise ValueError('bearing_id requires an explicit bearing_provider.')
            bf=self.bearing_provider.frequencies(c.bearing_id,scalar)
        # Invalid windows remain explicit observations with no numeric diagnosis.
        payload={'quality':{'flags':quality},'status':'invalid' if quality else 'ready'}
        if not quality:
            trace=rpm if isinstance(rpm,np.ndarray) else None
            payload.update(analyze(a,cfg,trace,bf,native=True))
            if trace is not None:
                trace=trace.copy(); trace.setflags(write=False); payload['_rpm_trace']=trace
        metadata={'measurement':c.to_dict(),'source':dict(block.metadata)}
        result=AnalysisResult(block.start_time_s,block.start_time_s+len(a)/c.sample_rate_hz,
                              block.clock_id,block.episode_id,block.channels,not quality,payload,metadata)
        for name,stage in self.stages.items():
            hook=getattr(stage,'analyze_window',None)
            if callable(hook):
                readonly=a.view(); readonly.setflags(write=False)
                payload[name]=hook(result,readonly)
            else: payload[name]=stage(result)
        for sink in self.sinks: sink(result)
        return result

    def push(self, block: SignalBlock) -> list[AnalysisResult]:
        c=self._config; fs=c.sample_rate_hz
        if block.sample_rate_hz!=fs or block.values.shape[1]!=c.channels:
            raise ValueError('Signal sample rate/channels must match AnalysisConfig.')
        expected='V' if c.input_representation=='volts' else c.unit
        if block.unit!=expected: raise ValueError(f'Expected input unit {expected!r}.')
        identity_fields=('asset_id','asset','sensor_id','sensor_ids','calibration_id','condition_id','condition',
                         'operating_mode','measurement_frame','source_id','sensor_installation',
                         'sensor_installation_id','load_unit','acquisition')
        try:
            source_identity=json.dumps(json_value({k:block.metadata[k] for k in identity_fields if k in block.metadata}),sort_keys=True,allow_nan=False)
        except (TypeError,ValueError) as ex: raise ValueError('Stream identity metadata must be JSON-compatible and finite.') from ex
        identity=(block.clock_id,block.episode_id,block.channels,block.unit,source_identity)
        discontinuity=(self._identity!=identity or self._next is None or
                       abs(block.start_time_s-self._next)>0.25/fs or
                       (block.sequence is not None and self._sequence is not None and block.sequence!=self._sequence+1))
        if discontinuity:
            # First input must not cancel a normal collection explicitly begun
            # before push(). Only an established stream boundary resets stages.
            self.reset(reset_stages=self._identity is not None); self._time=block.start_time_s
        self._identity=identity; self._sequence=block.sequence
        self._next=block.start_time_s+len(block.values)/fs
        rpm=block.rpm if block.rpm is not None else c.rpm
        r=np.full(len(block.values),np.nan if rpm is None else rpm) if not isinstance(rpm,np.ndarray) else rpm
        n=round(c.window_seconds*fs); hop=max(1,round(c.hop_seconds*fs)); results=[]
        # Consume in window-sized pieces to bound persistent buffering.
        for offset in range(0,len(block.values),n):
            sl=slice(offset,offset+n)
            self._a=block.values[sl].copy() if self._a is None else np.concatenate((self._a,block.values[sl]))
            self._valid=block.valid[sl].copy() if self._valid is None else np.concatenate((self._valid,block.valid[sl]))
            self._rpm=r[sl].copy() if self._rpm is None else np.concatenate((self._rpm,r[sl]))
            measured=np.full(len(block.values[sl]),isinstance(rpm,np.ndarray),dtype=bool)
            self._rpm_measured=measured if self._rpm_measured is None else np.concatenate((self._rpm_measured,measured))
            while len(self._a)>=n:
                rt=self._rpm[:n]
                if np.isnan(rt).all(): rt=None
                elif not np.isfinite(rt).all():
                    # Mixed tachometer availability cannot support this window.
                    self._valid[:n]=False; rt=None
                elif not self._rpm_measured[:n].all():
                    # Internal scalar expansion is buffering, not a measured
                    # tachometer trace. Never upgrade nominal values to evidence.
                    if self._rpm_measured[:n].any() or np.ptp(rt)>0:
                        self._valid[:n]=False; rt=None
                    else: rt=float(rt[0])
                w=SignalBlock(self._a[:n],fs,block.unit,self._time,block.clock_id,block.episode_id,
                              block.channels,self._valid[:n],rt,metadata=block.metadata)
                results.append(self.analyze(w))
                self._a=self._a[hop:]; self._valid=self._valid[hop:]; self._rpm=self._rpm[hop:]
                self._rpm_measured=self._rpm_measured[hop:]
                self._time+=hop/fs
        return results


def analyze_signal(values, config=None, **block_options):
    analyzer=VibrationAnalyzer(config)
    c=analyzer.config
    block_options.setdefault('unit','V' if c.input_representation=='volts' else c.unit)
    return analyzer.analyze(SignalBlock(values,c.sample_rate_hz,**block_options))
