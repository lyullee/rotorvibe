"""Optional process-monitoring-toolkit bridge; no hard dependency."""
import numpy as np
import copy
from importlib.metadata import version,PackageNotFoundError
from .contracts import SignalBlock,json_value
from .profiles import profile_digest

SUPPORTED_PROCESS_VERSION='0.1.0'


def process_adapter_info():
    """Report installed distribution compatibility without importing it."""
    try: installed=version('process-monitoring-toolkit')
    except PackageNotFoundError: installed=None
    return {'distribution':'process-monitoring-toolkit','supported_version':SUPPORTED_PROCESS_VERSION,
            'installed_version':installed,'compatible':installed==SUPPORTED_PROCESS_VERSION,
            'contract':'process-monitoring.SignalBatch/0.1.0'}


def _require_process():
    info=process_adapter_info()
    if not info['compatible']:
        raise ImportError('Install the pinned process-monitoring-toolkit 0.1.0 source (README optional bridge), '
                          'then rotorvibe[process]; found '
                          +str(info['installed_version']))
    from process_monitoring import SignalBatch
    return SignalBatch

def from_process_batch(batch, *, sample_rate_hz, clock_id, rpm=None):
    """Supported SignalBatch -> waveform; split gaps/episodes/modes first."""
    if not isinstance(batch,_require_process()): raise TypeError('Supported SignalBatch required.')
    if isinstance(sample_rate_hz,bool) or not np.isfinite(sample_rate_hz) or sample_rate_hz<=0:
        raise ValueError('Finite positive sample_rate_hz required.')
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
    upstream=dict(batch.metadata)
    if upstream.get('clock_id',clock_id)!=clock_id: raise ValueError('Upstream clock_id differs.')
    if upstream.get('time_reference')=='exclusive_window_end':
        raise ValueError('Window features cannot be adapted as raw waveforms.')
    source=copy.deepcopy(upstream.get('vibration_source',{}))
    mode=getattr(batch,'modes',None)
    if mode is not None:
        mode=json_value(mode[0])
        if 'operating_mode' in source and profile_digest(source['operating_mode'])!=profile_digest(mode):
            raise ValueError('Mode vector differs from declared operating_mode.')
        source['operating_mode']=mode
    source.update(origin=batch.origin,upstream_metadata=upstream)
    return SignalBlock(batch.values,sample_rate_hz,units[0],float(t[0]),clock_id,
                       str(ep[0]) if ep is not None else 'default',tuple(batch.channels),valid,rpm,
                       metadata=source)

def to_process_batch(results):
    """One feature row/window, timestamped at exclusive window end."""
    SignalBatch=_require_process()
    rows=list(results)
    reference=next((r for r in rows if r.valid and r.features is not None),None)
    if reference is None: raise ValueError('No valid feature schema available.')
    names=reference.feature_names; measurement=reference.metadata.get('measurement')
    if any(r.clock_id!=reference.clock_id or (r.valid and r.feature_names!=names) or
           r.channels!=reference.channels or profile_digest(r.metadata.get('source'))!=profile_digest(reference.metadata.get('source')) or
           profile_digest(r.metadata.get('measurement'))!=profile_digest(measurement) for r in rows):
        raise ValueError('Feature schema, clock and measurement settings must agree.')
    if any(a.end_time_s>=b.end_time_s for a,b in zip(rows,rows[1:])):
        raise ValueError('Strictly increasing window end times required.')
    if any(r.valid and (np.asarray(r.features).shape!=(len(names),) or not np.isfinite(r.features).all()) for r in rows):
        raise ValueError('Valid rows require finite features matching the declared schema.')
    x=np.vstack([r.features if r.valid else np.full(len(names),np.nan) for r in rows])
    episodes={e:i for i,e in enumerate(dict.fromkeys(r.episode_id for r in rows))}
    valid=np.broadcast_to(np.array([r.valid for r in rows])[:,None],x.shape).copy()
    return SignalBatch(np.array([r.end_time_s for r in rows]),x,names,
                       units=tuple('dimensionless' for _ in names),valid=valid,
                       modes=np.repeat(reference.metadata.get('source',{}).get('operating_mode'),len(rows))
                             if 'operating_mode' in reference.metadata.get('source',{}) else None,
                       episodes=np.array([episodes[r.episode_id] for r in rows]),origin='vibration.analysis.v1',
                       metadata=copy.deepcopy({'clock_id':reference.clock_id,'episode_ids':episodes,'measurement':measurement,
                                 'vibration_source':reference.metadata.get('source',{}),
                                 'feature_definition':'log RMS/log crest/Pearson kurtosis/log PSD fractions; RMS log references declared input unit',
                                 'time_reference':'exclusive_window_end','overlapping_windows':True}))

def condition_evidence(result, *, asset_id):
    """Neutral condition observation, not an accident frequency/probability."""
    return {'schema':'vibration.condition-evidence.v1','asset_id':asset_id,
            'kind':'condition_observation','valid':result.valid,'clock_id':result.clock_id,
            'time_s':result.end_time_s,'episode_id':result.episode_id,
            'metrics':copy.deepcopy(dict(result.metrics)),'diagnosis':copy.deepcopy(result.payload.get('diagnosis')),
            'measurement':copy.deepcopy(result.metadata.get('measurement'))}
