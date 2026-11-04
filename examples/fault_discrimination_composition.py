"""Host supplies two-second raw blocks; this module starts no server or database."""
from vibration import VibrationAnalyzer,AnalysisConfig,ConditionedDiagnostic,ConditionedStage,SignalBlock
from vibration.fault_discrimination import FaultDiscriminator,FaultDiscriminationStage

def create_analyzer(normal_gate_profile,fault_profile,*,sample_rate_hz,rpm):
    """Profiles must match the real asset/installation/units; UOS profiles are experimental."""
    config=AnalysisConfig(sample_rate_hz=sample_rate_hz,window_seconds=2,hop_seconds=2,
        unit='g',rpm=rpm,envelope_high_hz=min(3000,sample_rate_hz*.4))
    return VibrationAnalyzer(config,stages={
        'conditioned':ConditionedStage(ConditionedDiagnostic(normal_gate_profile)),
        'fault_type':FaultDiscriminationStage(FaultDiscriminator(fault_profile)),
    })

def analyze_block(analyzer,samples,*,sample_rate_hz,rpm,asset_id,condition_id):
    """This single-channel profile uses the radial_vibration layout."""
    return analyzer.analyze(SignalBlock(samples,sample_rate_hz,unit='g',rpm=rpm,
        channels=('radial_vibration',),metadata={'asset_id':asset_id,'condition_id':condition_id}))
