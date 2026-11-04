"""RotorVibe public facade; historical ``vibration`` imports remain supported."""
__version__='0.1.0a1'
__all__=['AnalysisConfig','SignalBlock','AnalysisResult','VibrationAnalyzer','analyze_signal',
    'BearingGeometry','BearingMap','BaselineStage','AlarmStage','GaussianClassifier','extract_rotor_features',
    'RotorFeatures','TwoStageDiagnostic','TwoStageStage','fit_two_stage','IndependentRotorCatalog',
    'fit_conditioned','ConditionedDiagnostic','ConditionedStage','UosRotorCatalog',
    'fault_features','fit_fault_discriminator','FaultDiscriminator','FaultDiscriminationStage']
def __getattr__(name):
    if name not in __all__: raise AttributeError(name)
    from importlib import import_module
    source='vibration.fault_discrimination' if name in __all__[-4:] else 'vibration'
    value=getattr(import_module(source),name); globals()[name]=value; return value
