"""Local rotating-machinery vibration analysis workbench."""
__version__ = "0.1.0a1"

__all__=['AnalysisConfig','SignalBlock','AnalysisResult','VibrationAnalyzer',
         'analyze_signal','BearingGeometry','BearingMap','BaselineStage','AlarmStage','GaussianClassifier',
         'extract_rotor_features','RotorFeatures','TwoStageDiagnostic','TwoStageStage','fit_two_stage','IndependentRotorCatalog',
         'fit_conditioned','ConditionedDiagnostic','ConditionedStage','UosRotorCatalog']

def __getattr__(name):
    from importlib import import_module
    modules={'AnalysisConfig':'config','SignalBlock':'contracts','AnalysisResult':'contracts',
             'VibrationAnalyzer':'core','analyze_signal':'core','BearingGeometry':'geometry',
             'BearingMap':'geometry','BaselineStage':'baseline','AlarmStage':'alarm','GaussianClassifier':'classifier',
             'extract_rotor_features':'rotor_features','RotorFeatures':'rotor_features','TwoStageDiagnostic':'two_stage','TwoStageStage':'two_stage','fit_two_stage':'two_stage',
             'IndependentRotorCatalog':'independent_data','fit_conditioned':'conditioned','ConditionedDiagnostic':'conditioned',
             'ConditionedStage':'conditioned','UosRotorCatalog':'condition_data'}
    if name not in modules: raise AttributeError(name)
    value=getattr(import_module('.'+modules[name],__name__),name)
    globals()[name]=value
    return value

