"""Synthetic P1 integration, not measured normal-session validation."""
import numpy as np
from rotorvibe import (AcquisitionInfo, AcquisitionQualityStage, AnalysisConfig,
    SignalBlock, VibrationAnalyzer, NormalRecording, fit_normal_reference,
    NormalReferenceBank, ReferenceStage, DecisionStage, GuidanceStage,
    AlarmStage, RealtimeProcessor)

fs = 12000
config = AnalysisConfig(sample_rate_hz=fs, unit="g", window_seconds=2,
                        hop_seconds=2, load=0.5, rpm=1200)
# Synthetic test declarations only; measured data need actual reviewed evidence.
info = AcquisitionInfo("demo-rig", "sensor-1", "mount-1", "demo-calibration",
    "2026-11-04", "2027-01-01", ("radial",), ("radial",), fs, "g",
    (1, 6000), 5500, "controller_nominal",
    calibrated=True, mounting_verified=True, anti_alias_verified=True)

def block(index, amplitude, installation="mount-1"):
    source = {"asset_id": "demo-rig", "condition_id": "steady",
              "load_unit": "fraction_rated", "acquisition": info.to_dict()}
    source["acquisition"]["sensor_installation_id"] = installation
    samples = amplitude * np.sin(2 * np.pi * 20 * np.arange(fs * 2) / fs)
    return SignalBlock(samples, fs, unit="g", rpm=1200, start_time_s=index * 2,
                       channels=("radial",), metadata=source)

preprocessor = VibrationAnalyzer(config)
def recording(index, amplitude, role):
    return NormalRecording(f"record-{index}", f"acquisition-{index}",
        (preprocessor.analyze(block(index, amplitude)),), True, role)

profile = fit_normal_reference(
    [recording(0, 1.00, "normal_fit"), recording(1, 1.04, "normal_fit")],
    [recording(2, 1.01, "normal_calibration"),
     recording(3, 1.03, "normal_calibration")],
    name="demo-reference", rpm_range=(1188, 1212), load_range=(0.4, 0.6))
bank = NormalReferenceBank([profile])
analyzer = VibrationAnalyzer(config, stages={
    "acquisition": AcquisitionQualityStage(),
    "reference": ReferenceStage(bank),
    "decision": DecisionStage("reference"),
    "guidance": GuidanceStage("decision"),
    "alarm": AlarmStage(score_stage="decision", expected_score_name="normal_score",
        warning=profile["anomaly_limit"], danger=2 * profile["anomaly_limit"],
        persistence_seconds=0, release_seconds=0),
})
processor = RealtimeProcessor(analyzer, max_pending=2, overflow="reject")
assert processor.submit(block(4, 1.02))["accepted"]
normal = processor.process_next()[0]
assert normal.payload["decision"]["status"] == "normal"
assert processor.submit(block(5, 1.02, installation="new-mount"))["accepted"]
held = processor.process_next()[0]
assert held.payload["decision"]["status"] == "hold"
assert held.payload["guidance"]["required_actions"]
assert held.payload["alarm"]["level"] == "unavailable"
print(normal.payload["decision"]["status"], held.payload["guidance"])
processor.close()
