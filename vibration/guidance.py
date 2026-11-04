"""Machine-readable next steps for holds; no automatic scope relabeling."""
from collections.abc import Mapping

_ACTIONS={
    'normal_reference_disabled':('activate_reviewed_reference',('reference_name',)),
    'normal_reference':('register_asset_normal_reference',('asset_id','sensor_installation_id','condition_id','rpm','load')),
    'outside_reference':('collect_normal_at_operating_point',('rpm','load','load_unit')),
    'reference_ambiguous':('resolve_overlapping_reference_ranges',('rpm_range','load_range','reference_name')),
    'reference_scope':('supply_reference_identity',('condition_id','load_unit','acquisition')),
    'scope_mismatch':('verify_identity_or_fit_new_reference',('asset_id','condition_id','sensor_installation_id','unit')),
    'scope_missing':('supply_actual_scope',('asset_id','condition_id','unit')),
    'acquisition':('complete_acquisition_evidence',('acquisition','calibration_id','sensor_band_hz','rpm_source')),
    'sampling':('supply_supported_sampling_rate',('sample_rate_hz',)),
    'speed':('supply_measured_speed_and_supported_model',('rpm','rpm_trace','rpm_source')),
    'rpm':('supply_measured_speed',('rpm','rpm_trace','rpm_source')),
    'window':('supply_complete_window',('window_seconds','sample_rate_hz')),
    'layout':('verify_channel_layout',('channels','axes')),
    'quality':('inspect_samples_sensor_and_calibration',('valid','clip_abs','acquisition')),
    'invalid':('inspect_samples_sensor_and_calibration',('valid','clip_abs','acquisition')),
    'source_stage_missing':('connect_producer_before_adapter',('stages','source_stage')),
    'borderline':('collect_separate_calibration_and_review_margin',('calibration_groups','normal_score')),
    'insufficient':('acquire_missing_evidence',('scope','feature_names','calibration_groups')),
}


def hold_guidance(output):
    if not isinstance(output,Mapping): raise ValueError('Decision mapping required')
    status=output.get('status'); reason=output.get('reason',status or 'unspecified')
    if not isinstance(reason,str): raise ValueError('Reason must be a string')
    held=status in ('hold','invalid','quality_hold','incompatible','missing','outside_condition')
    action=None
    if held:
        # Most-specific matches precede broad tokens. Keep a fallback for future codes.
        for token in sorted(_ACTIONS,key=len,reverse=True):
            if token in reason:
                code,parameters=_ACTIONS[token]; action={'code':code,'parameters':list(parameters)}; break
        if action is None: action={'code':'review_unsupported_decision','parameters':['reason','scope']}
    return {'schema':'vibration.guidance.v1','status':status,'reason':reason,
            'required_actions':[] if action is None else [action],
            'automatic_scope_override':False,'operational_use':False}


class GuidanceStage:
    def __init__(self,source_stage='decision'):
        if not isinstance(source_stage,str) or not source_stage.strip(): raise ValueError('Producer stage required')
        self.source_stage=source_stage

    def __call__(self,result):
        return hold_guidance(result.payload.get(self.source_stage,{'status':'hold','reason':'source_stage_missing'}))
