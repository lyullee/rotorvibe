"""Bounded history of DSP display PSD rows; never infer missing observations.

This accumulates the 384-bin mean PSD display representation, not
a lossless STFT, band-energy integrator or calibrated diagnostic model input.
"""
from collections import deque
import math
from numbers import Real,Integral
import numpy as np
from .profiles import profile_digest


class SpectrogramAccumulator:
    def __init__(self,*,hop_seconds,max_frames=512,max_age_seconds=600.,max_frequencies=4096):
        if any(isinstance(v,bool) or not isinstance(v,Real) or not math.isfinite(v) or v<=0
               for v in (hop_seconds,max_age_seconds)):
            raise ValueError('Finite positive hop/retention seconds required.')
        if any(isinstance(v,bool) or not isinstance(v,Integral) or not 1<=v<=100000
               for v in (max_frames,max_frequencies)) or max_frames*max_frequencies>8_000_000:
            raise ValueError('Bounded frame/frequency dimensions required (at most 8M cells).')
        self.hop_seconds=float(hop_seconds); self.max_frames=max_frames
        self.max_age_seconds=float(max_age_seconds); self.max_frequencies=max_frequencies
        self.clear()

    def clear(self):
        self._rows=deque(maxlen=self.max_frames); self._frequencies=None; self._identity=None
        self._last_start=None; self._segment=0; self._evicted=0
        self._representation=None; self._edges=None; self._unit=None

    def reset_state(self,*,preserve_profiles=True): self.clear()

    def update(self,result):
        start=result.start_time_s; end=result.end_time_s
        if any(isinstance(v,bool) or not isinstance(v,Real) or not math.isfinite(v) for v in (start,end)) or end<=start:
            raise ValueError('Finite increasing window interval required.')
        source=result.metadata.get('source',{})
        # Measurement settings include the selected channel and PSD unit/window.
        identity=profile_digest({'clock':result.clock_id,'episode':result.episode_id,'channels':result.channels,
            'measurement':result.metadata.get('measurement'),
            'asset':source.get('asset_id'),'installation':source.get('acquisition',{}).get('sensor_installation_id'),
            'acquisition':source.get('acquisition'),'load_unit':source.get('load_unit'),
            'condition':source.get('condition_id'),'operating_mode':source.get('operating_mode'),
            'location':source.get('location'),'operating_state':source.get('operating_state')})
        same=identity==self._identity
        if same and self._last_start is not None and start<=self._last_start:
            raise ValueError('Spectrogram windows must have increasing starts; reset for replay.')
        if same and self._last_start is not None and start<self._last_start+self.hop_seconds-max(1e-9,self.hop_seconds*1e-6):
            raise ValueError('Observed hop is shorter than configured hop_seconds.')
        spectrum=result.payload.get('spectrogram') if result.valid else None
        frequencies=None; db=None
        if result.valid:
            if not isinstance(spectrum,dict): raise ValueError('Valid result requires a spectrogram row.')
            frequencies=np.asarray(spectrum.get('frequencies'),dtype=float)
            db=np.asarray(spectrum.get('db'),dtype=float)
            if (frequencies.ndim!=1 or not 2<=len(frequencies)<=self.max_frequencies or db.shape!=frequencies.shape
                or not np.isfinite(frequencies).all() or not np.isfinite(db).all()
                or frequencies[0]<0 or np.any(np.diff(frequencies)<=0)):
                raise ValueError('Finite increasing Hz axis and matching dB row required.')
            representation=spectrum.get('representation','legacy_interpolated_psd')
            edges=spectrum.get('bin_edges_hz')
            unit=spectrum.get('input_unit',result.metadata.get('measurement',{}).get('unit'))
            if representation not in ('frequency_bin_mean_psd','legacy_interpolated_psd'):
                raise ValueError('Unknown PSD display representation.')
            if representation=='frequency_bin_mean_psd':
                edges=np.asarray(edges,dtype=float)
                if (edges.shape!=(len(frequencies)+1,) or not np.isfinite(edges).all() or np.any(np.diff(edges)<=0)
                    or edges[0]<0 or np.any(frequencies<edges[:-1]) or np.any(frequencies>edges[1:])):
                    raise ValueError('Ordered matching frequency bin edges required.')
                edges=edges.tolist()
            if same and self._representation is not None and (representation!=self._representation or edges!=self._edges or unit!=self._unit):
                raise ValueError('PSD representation/units changed inside one measurement identity.')
            if same and self._frequencies is not None and not np.array_equal(frequencies,self._frequencies):
                raise ValueError('Frequency grid changed inside one measurement identity.')
        if not same:
            if self._identity is not None: self._segment+=1
            self._rows.clear(); self._frequencies=None; self._last_start=None; self._identity=identity
            self._representation=None; self._edges=None; self._unit=None
        if frequencies is not None:
            self._frequencies=frequencies.copy(); self._representation=representation; self._edges=edges; self._unit=unit
        gap=None
        if self._last_start is not None:
            expected=self._last_start+self.hop_seconds
            if start>expected+max(1e-9,self.hop_seconds*1e-6):
                gap=[expected,start]; self._segment+=1
        if len(self._rows)==self.max_frames: self._evicted+=1
        self._rows.append({'start_time_s':float(start),'end_time_s':float(end),'valid':bool(result.valid),
                           'db':None if db is None else db.tolist(),'segment_id':self._segment,'gap_before_s':gap})
        self._last_start=start
        while self._rows and self._rows[0]['end_time_s']<end-self.max_age_seconds:
            self._rows.popleft(); self._evicted+=1
        return {'schema':'vibration.spectrogram-update.v1','frames':len(self._rows),'segment_id':self._segment,
                'gap_before_s':gap,'valid':bool(result.valid),'evicted_frames':self._evicted}

    def snapshot(self):
        import copy
        return {'schema':'vibration.spectrogram-history.v1','frequencies_hz':[] if self._frequencies is None else self._frequencies.tolist(),
                'rows':copy.deepcopy(list(self._rows)),'hop_seconds':self.hop_seconds,'max_frames':self.max_frames,
                'max_age_seconds':self.max_age_seconds,'identity_sha256':self._identity,
                'time_reference':'window_start_and_exclusive_end','frequency_representation':self._representation,
                'bin_edges_hz':None if self._edges is None else list(self._edges),'input_unit':self._unit,
                'db_reference':'10*log10(PSD / (1 input_unit^2/Hz)); floor 1e-20',
                'evicted_frames':self._evicted}


class SpectrogramStage:
    def __init__(self,accumulator):
        if not isinstance(accumulator,SpectrogramAccumulator): raise TypeError('SpectrogramAccumulator required.')
        self.accumulator=accumulator

    def __call__(self,result): return self.accumulator.update(result)

    def reset_state(self,*,preserve_profiles=True): self.accumulator.clear()
