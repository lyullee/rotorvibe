"""Application-owned composition. Functions accept actual acquired measurements."""
from vibration import (AnalysisConfig, SignalBlock, VibrationAnalyzer,
                       BearingGeometry, BearingMap, BaselineStage, AlarmStage)
from vibration.adapters import to_process_batch, condition_evidence


def create_pipeline(*, result_sink, calibrated_unit='m/s^2'):
    config=AnalysisConfig(sample_rate_hz=25600,channels=2,unit=calibrated_unit,
                          rpm=1800,bearing_id='drive',condition='load-A')
    bearings=BearingMap({'drive':BearingGeometry(8,7.94,39.04)})
    baseline=BaselineStage(config)
    analyzer=VibrationAnalyzer(config,bearing_provider=bearings,
                               stages={'baseline':baseline,'alarm':AlarmStage()},
                               sinks=(result_sink,))
    # Only call begin after the operator has identified a healthy operating period.
    return analyzer,baseline


def accept_acquired_chunk(analyzer, samples, *, start_time_s, rpm_trace, sequence):
    c=analyzer.config
    return analyzer.push(SignalBlock(samples,c.sample_rate_hz,c.unit,start_time_s,
                                     clock_id='daq_elapsed',episode_id='run-001',
                                     channels=('drive_radial','drive_axial'),rpm=rpm_trace,sequence=sequence,
                                     metadata={'sensor_installation':'operator supplied'}))


def score_with_process_monitoring(trained_monitor, results):
    # trained_monitor is provided by the host; no implicit fitting or calibration.
    return trained_monitor.score(to_process_batch(results))


def export_asset_observation(result, asset_id):
    return condition_evidence(result,asset_id=asset_id)
