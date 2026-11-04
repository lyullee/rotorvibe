"""Local rotating-machinery vibration analysis workbench."""
__version__ = "0.1.0a4"

__all__=['AnalysisConfig','SignalBlock','AnalysisResult','VibrationAnalyzer',
         'analyze_signal','BearingGeometry','BearingMap','BaselineStage','AlarmStage','GaussianClassifier',
         'extract_rotor_features','RotorFeatures','TwoStageDiagnostic','TwoStageStage','fit_two_stage','IndependentRotorCatalog',
         'fit_conditioned','ConditionedDiagnostic','ConditionedStage','UosRotorCatalog',
         'DecisionStage','normalize_decision']

_P1={'AcquisitionInfo':'acquisition','AcquisitionQualityStage':'acquisition','check_acquisition':'acquisition',
     'NormalRecording':'references','fit_normal_reference':'references','NormalReferenceBank':'references','ReferenceStage':'references',
     'GuidanceStage':'guidance','hold_guidance':'guidance','RealtimeProcessor':'realtime',
     'ValidationObservation':'evaluation','evaluate_observations':'evaluation',
     'angle_resample':'angle','angle_features':'angle','AngleFeatures':'angle',
     'fit_angle_fault_discriminator':'angle','AngleFaultDiscriminator':'angle','AngleFaultStage':'angle',
     'DatasetRecord':'validation_plan','ValidationPlan':'validation_plan','FrozenEvaluation':'validation_plan'}
_P2={'ProfileRegistry': 'profiles', 'create_profile': 'profiles', 'validate_profile': 'profiles', 'profile_digest': 'profiles', 'SpectrogramAccumulator': 'spectrogram', 'SpectrogramStage': 'spectrogram', 'process_adapter_info': 'adapters', 'from_process_batch': 'adapters', 'to_process_batch': 'adapters', 'condition_evidence': 'adapters'}
__all__+=list(_P1)+list(_P2)

def __getattr__(name):
    from importlib import import_module
    modules={'AnalysisConfig':'config','SignalBlock':'contracts','AnalysisResult':'contracts',
             'VibrationAnalyzer':'core','analyze_signal':'core','BearingGeometry':'geometry',
             'BearingMap':'geometry','BaselineStage':'baseline','AlarmStage':'alarm','GaussianClassifier':'classifier',
             'extract_rotor_features':'rotor_features','RotorFeatures':'rotor_features','TwoStageDiagnostic':'two_stage','TwoStageStage':'two_stage','fit_two_stage':'two_stage',
             'IndependentRotorCatalog':'independent_data','fit_conditioned':'conditioned','ConditionedDiagnostic':'conditioned',
             'ConditionedStage':'conditioned','UosRotorCatalog':'condition_data',
             'DecisionStage':'decisions','normalize_decision':'decisions'}
    modules.update(_P1); modules.update(_P2)
    if name not in modules: raise AttributeError(name)
    value=getattr(import_module('.'+modules[name],__name__),name)
    globals()[name]=value
    return value

