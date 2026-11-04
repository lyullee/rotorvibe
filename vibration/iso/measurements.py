"""Phase-preserving ideal DFT band extraction; does not certify an instrument."""
from dataclasses import replace
import math
import numpy as np
from .contracts import Measurement

def measure_waveform(values,*,sample_rate_hz,input_unit,quantity,statistic,frame,band_hz,
                     point_id,axes,calibrated=False,acquisition_verified=False,start_s=0,
                     clock_id='measurement_clock',order=None,filter_bandwidth_hz=None):
    a=np.asarray(values,dtype=float)
    if a.ndim==1: a=a[:,None]
    if a.ndim!=2 or len(a)<256 or not 1<=a.shape[1]<=16 or not np.isfinite(a).all() or np.max(np.abs(a))>1e12: raise ValueError('Finite samples x channels array within +/-1e12 input units required.')
    if not math.isfinite(sample_rate_hz) or not 1<=sample_rate_hz<=200000 or len(axes)!=a.shape[1]: raise ValueError('Sample rate/axis contract invalid (1..200000 Hz).')
    lo,hi=band_hz
    if not 0<lo<hi<sample_rate_hz/2: raise ValueError('Band must lie strictly below Nyquist and exclude DC.')
    duration=len(a)/sample_rate_hz
    if duration*lo<4: raise ValueError('At least four cycles of the lower analysis frequency required by this implementation.')
    unit_info={'m':(0,1.),'mm':(0,1e-3),'um':(0,1e-6),'m/s':(1,1.),'mm/s':(1,1e-3),'m/s^2':(2,1.),'g':(2,9.80665)}
    if input_unit not in unit_info or quantity not in ('displacement','velocity','acceleration'): raise ValueError('Explicit physical input/target units required.')
    if statistic not in ('rms','peak_to_peak'): raise ValueError('Use shaft_orbit for Smax; no peak/RMS shortcuts.')
    input_order,scale=unit_info[input_unit]; target_order={'displacement':0,'velocity':1,'acceleration':2}[quantity]
    a=(a-a.mean(axis=0))*scale
    f=np.fft.rfftfreq(len(a),1/sample_rate_hz); mask=(f>=lo)&(f<=hi)
    factor=np.zeros(len(f),dtype=complex)
    factor[mask]=(2j*np.pi*f[mask])**(target_order-input_order)
    y=np.fft.irfft(np.fft.rfft(a,axis=0)*factor[:,None],n=len(a),axis=0)
    conversion={'displacement':1e6,'velocity':1000.,'acceleration':1.}[quantity]
    amplitude=np.max(np.abs(y),axis=0)
    normalized=np.divide(y,amplitude,out=np.zeros_like(y),where=amplitude>0)
    magnitudes=(amplitude*np.sqrt(np.mean(normalized*normalized,axis=0)) if statistic=='rms' else np.ptp(y,axis=0))*conversion
    result=[]
    for channel,(value,axis) in enumerate(zip(magnitudes,axes)):
        m=Measurement(float(value),quantity,{'displacement':'um','velocity':'mm/s','acceleration':'m/s^2'}[quantity],
                      statistic,frame,tuple(band_hz),duration,axis,point_id if a.shape[1]==1 else f'{point_id}:ch{channel+1}',start_s,clock_id,
                      calibrated,acquisition_verified,averaging='energy_equivalent' if statistic=='rms' else 'single_window',
                      order=order,filter_bandwidth_hz=filter_bandwidth_hz,
                      provenance={'method':'ideal_DFT_band_phase_preserving','input_unit':input_unit,'sample_rate_hz':sample_rate_hz,
                                  'samples':len(a),'channel':channel,'instrument_response_certified':False})
        result.append(m.validate())
    return tuple(result)

def energy_equivalent_average(measurements):
    rows=list(measurements)
    if not rows: raise ValueError('Measurements required.')
    first=rows[0].validate()
    if first.statistic!='rms': raise ValueError('Energy averaging applies to RMS only.')
    for i,m in enumerate(rows):
        m.validate()
        if not m.valid or not m.calibrated or not m.acquisition_verified: raise ValueError('All source intervals must be valid/qualified.')
        for name in ('point_id','axis','frame','quantity','statistic','band_hz','clock_id'):
            if getattr(m,name)!=getattr(first,name): raise ValueError('Measurement contracts differ.')
        if i and abs(m.start_s-(rows[i-1].start_s+rows[i-1].duration_s))>1e-8:
            raise ValueError('Time intervals must be contiguous and non-overlapping; overlapping analysis windows cannot be summed.')
    values=np.array([m.canonical_value() for m in rows]); weights=np.array([m.duration_s for m in rows]); scale=values.max()
    with np.errstate(over='ignore'):
        total_duration=weights.sum()
    if not np.isfinite(total_duration): raise ValueError('Total evaluation duration overflow.')
    magnitude=float(scale*np.sqrt(np.average((values/scale)**2,weights=weights))) if scale else 0.
    return replace(first,value=magnitude,unit={'acceleration':'m/s^2','velocity':'mm/s','displacement':'um'}[first.quantity],
                   duration_s=float(weights.sum()),averaging='energy_equivalent',observations=len(rows),
                   provenance={'method':'time_weighted_RMS_energy_average','source_count':len(rows)})


class EnergyEquivalentAccumulator:
    """One synchronous measurement stream; never count overlapping windows twice."""
    def __init__(self,period_s):
        if not math.isfinite(period_s) or period_s<=0: raise ValueError('Positive averaging period required.')
        self.period_s=period_s; self.reset()

    def reset(self): self.rows=[]; self.duration_s=0.

    def push(self,measurement):
        measurement.validate()
        if len(self.rows)>=100000: raise ValueError('Too many subintervals; use longer measurement windows.')
        # Validate qualification, continuity, and contracts before accumulating.
        # A two-row check is sufficient; sum-of-squares is only formed on completion.
        energy_equivalent_average([self.rows[-1],measurement] if self.rows else [measurement])
        self.rows.append(measurement); self.duration_s+=measurement.duration_s
        if self.duration_s+1e-8<self.period_s: return None
        result=energy_equivalent_average(self.rows); self.reset(); return result
