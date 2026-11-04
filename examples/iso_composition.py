"""Caller-rule composition. Demonstration values are not standard thresholds."""
from vibration.iso import MachineContext,Rule,IsoStage
from rotorvibe import AnalysisConfig,VibrationAnalyzer

def create_rule_analyzer(*,asset_id,result_sink,reviewed_rule,calibrated=False,acquisition_verified=False):
    """The host supplies a lawful engineering rule reviewed for this installation."""
    context=MachineContext(asset_id,'motor',operating_state='steady',condition_id='rated',location='bearing_housing')
    stage=IsoStage(reviewed_rule.standard,context,custom_rule=reviewed_rule,point_id='drive_radial',
        calibrated=calibrated,acquisition_verified=acquisition_verified)
    return VibrationAnalyzer(AnalysisConfig(sample_rate_hz=12000,unit='m/s^2'),stages={'user_rule':stage},sinks=(result_sink,))
