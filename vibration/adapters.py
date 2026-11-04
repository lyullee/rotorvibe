"""Optional process-monitoring-toolkit bridge; no hard dependency."""
import numpy as np
from .contracts import SignalBlock

def from_process_batch(batch, *, sample_rate_hz, clock_id, rpm=None):
    t=np.asarray(batch.time_s,dtype=float)
    if len(t)<2 or not np.allclose(np.diff(t),1/sample_rate_hz,rtol=1e-5,atol=1e-9):
        raise ValueError('Continuous uniformly sampled waveforms required.')
    for name in ('episodes','modes'):
        a=getattr(batch,name,None)
        if a is not None and len(set(np.asarray(a).tolist()))!=1:
            raise ValueError(f'Split differing {name} before adapting.')
    units=tuple(batch.units)
    if not units or len(set(units))!=1: raise ValueError('One common explicit channel unit required.')
    valid=getattr(batch,'valid',None)
    if valid is not None and np.asarray(valid).ndim==2: valid=np.asarray(valid).all(axis=1)
    ep=getattr(batch,'episodes',None)
    return SignalBlock(batch.values,sample_rate_hz,units[0],float(t[0]),clock_id,
                       str(ep[0]) if ep is not None else 'default',tuple(batch.channels),valid,rpm,
                       metadata={'origin':batch.origin,'upstream_metadata':dict(batch.metadata)})

def to_process_batch(results):
    """One feature row/window, timestamped at exclusive window end."""
    from process_monitoring import SignalBatch
    rows=list(results)
    reference=next((r for r in rows if r.valid and r.features is not None),None)
    if reference is None: raise ValueError('No valid feature schema available.')
    names=reference.feature_names; measurement=reference.metadata.get('measurement')
    if any(r.clock_id!=reference.clock_id or (r.valid and r.feature_names!=names) or
           r.metadata.get('measurement')!=measurement for r in rows):
        raise ValueError('Feature schema, clock and measurement settings must agree.')
    x=np.vstack([r.features if r.valid else np.full(len(names),np.nan) for r in rows])
    episodes={e:i for i,e in enumerate(dict.fromkeys(r.episode_id for r in rows))}
    valid=np.broadcast_to(np.array([r.valid for r in rows])[:,None],x.shape).copy()
    return SignalBatch(np.array([r.end_time_s for r in rows]),x,names,
                       units=tuple('dimensionless' for _ in names),valid=valid,
                       episodes=np.array([episodes[r.episode_id] for r in rows]),origin='vibration.analysis.v1',
                       metadata={'clock_id':reference.clock_id,'episode_ids':episodes,'measurement':measurement,
                                 'feature_definition':'log RMS/log crest/Pearson kurtosis/log PSD fractions; RMS log references declared input unit',
                                 'time_reference':'exclusive_window_end','overlapping_windows':True})

def condition_evidence(result, *, asset_id):
    """Neutral condition observation, not an accident frequency/probability."""
    return {'schema':'vibration.condition-evidence.v1','asset_id':asset_id,
            'kind':'condition_observation','valid':result.valid,'clock_id':result.clock_id,
            'time_s':result.end_time_s,'episode_id':result.episode_id,
            'metrics':dict(result.metrics),'diagnosis':result.payload.get('diagnosis'),
            'measurement':result.metadata.get('measurement')}
