"""Compose an asset-specific two-stage diagnostic without a server or database.

Collections are prepared by the host: normal_fit/calibration items are
(N x C samples, RPM, acquisition_id); fault items also append a confirmed label.
Never put windows from one acquisition in different collections.
"""
import numpy as np
from vibration import extract_rotor_features,fit_two_stage,TwoStageDiagnostic,TwoStageStage,VibrationAnalyzer,AnalysisConfig


def train_for_asset(normal_fit,normal_calibration,faults,scope):
    names=None
    def features(items,has_label=False):
        nonlocal names
        vectors=[]; groups=[]; labels=[]
        for item in items:
            samples,rpm,group=item[:3]
            if len(samples)!=scope['window_samples']: raise ValueError('Window lengths must match scope.')
            f=extract_rotor_features(samples,scope['sample_rate_hz'],rpm,channel_names=scope['channel_names'])
            if names is not None and names!=f.names: raise ValueError('Feature contracts differ.')
            names=f.names; vectors.append(f.values); groups.append(group)
            if has_label: labels.append(item[3])
        return np.vstack(vectors),groups,labels
    normal,normal_groups,_=features(normal_fit)
    calibration,calibration_groups,_=features(normal_calibration)
    fault_values,fault_groups,labels=features(faults,True)
    profile=fit_two_stage(normal,normal_groups,calibration,calibration_groups,fault_values,labels,fault_groups,
        feature_names=names,scope=scope,mode='relative')
    return TwoStageDiagnostic(profile)


def compose_analyzer(model):
    scope=model.scope
    config=AnalysisConfig(sample_rate_hz=scope['sample_rate_hz'],channels=len(scope['channel_names']),
        window_seconds=scope['window_samples']/scope['sample_rate_hz'],unit=scope['unit'],
        envelope_high_hz=min(5000,scope['sample_rate_hz']*.45))
    return VibrationAnalyzer(config,stages={'diagnostic':TwoStageStage(model)})

# block = SignalBlock(samples, fs, unit=scope['unit'], channels=tuple(scope['channel_names']),
#                     rpm=measured_rpm, metadata={'asset_id':..., 'condition_id':...})
# result = compose_analyzer(model).analyze(block)
# diagnostic = result.payload['diagnostic']
# Optional service: registry.use_two_stage(model.profile); enable config.model_enabled.
