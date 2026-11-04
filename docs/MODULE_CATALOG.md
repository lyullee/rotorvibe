# Module and API catalog

Generated from public source. An entry is an interface, not an independent physical model or a qualification certificate.

Detailed method conventions are in ALGORITHMS.md; experimental model scope is mandatory.

## vibration/__init__.py

Local rotating-machinery vibration analysis workbench.


## vibration/adapters.py

host object interoperability

- `from_process_batch(batch, *, sample_rate_hz, clock_id, rpm=None)`
- `to_process_batch(results)`
- `condition_evidence(result, *, asset_id)`

## vibration/alarm.py

observation-time state machine

- `class AlarmStage — reset`

## vibration/baseline.py

robust normal references

- `utcnow()`
- `class Baseline — begin, observe`
- `class BaselineStage — begin, export_profile`

## vibration/bearings.py

Supporting implementation

- `class Bearings — frequencies, custom`

## vibration/bootstrap.py

Supporting implementation


## vibration/classifier.py

experimental Gaussian baseline

- `fit_gaussian(x, y, groups, *, variance_floor=0.25, feature_schema=FEATURE_SCHEMA)`
- `class GaussianClassifier — scores, predict_many, predict`

## vibration/client.py

Device-neutral HTTP/UDP writer. Use measured arrays; no generated signals.

- `class VibrationClient — request, start, packet, push, push_udp, stop`

## vibration/condition_data.py

Versioned new recording holdout and explicitly exposed development data readers.

- `file_sha(path)`
- `class UosRotorCatalog — rows, load`
- `class ExposedCrossSpeedDevelopment — rows, load`

## vibration/conditioned.py

RPM-scoped normal bank

- `canonical_values(values, source_rate, target_rate=4000)`
- `selected_features(names, mode)`
- `matrix(values)`
- `reference_at(references, rpm, *, interpolate, max_gap, uncertainty)`
- `fit_conditioned(normal, normal_rpm, normal_groups, calibration, calibration_rpm, calibration_groups, faults, fault_rpm, fault_labels, fault_groups, *, feature_names, scope, mode='levels_orders', interpolate=False, max_rpm_gap=800.0, interpolation_uncertainty=1.0, min_margin=0.1)`
- `class ConditionedDiagnostic — predict, analyze`
- `class ConditionedStage — analyze_window`

## vibration/config.py

analysis settings and validation

- `class AnalysisConfig — validate, create, to_dict, signature, for_source`

## vibration/contracts.py

typed array/result contracts

- `class SignalBlock`
- `json_value(value)`
- `class AnalysisResult — features, feature_names, metrics, to_dict`

## vibration/core.py

stream and synchronous analysis

- `class VibrationAnalyzer — config, reset, analyze, push`
- `analyze_signal(values, config=None, **block_options)`

## vibration/datasets.py

Supporting implementation

- `local_path(root, relative)`
- `matrix(a)`
- `class DatasetCatalog — search, details, trial_ids, load, imported`

## vibration/dsp.py

spectral and physical numerical features

- `spectrum(x, fs, window='hann')`
- `compact_spectrum(f, a, maximum=1800, *, native=False)`
- `waveform(x, fs, maximum=1600, *, native=False)`
- `channel_features(data, fs)`
- `peak_evidence(f, amplitude, target, tolerance_ratio, resolution, *, spacing_hz=None)`
- `analyze(data, config, rpm_trace=None, bearing_frequencies=None, *, native=False)`

## vibration/engine.py

optional acquisition/replay worker

- `class EventHub — subscribe, unsubscribe, publish`
- `class Ring — append, snapshot`
- `class Engine — state, configure, live, stop, replay, ingest, close, save_window, baseline_start, baseline_load`

## vibration/fault_discrimination.py

conditional morphology head

- `fault_features(values, sample_rate_hz, rpm)`
- `fit_fault_discriminator(x, labels, rpms, groups, *, names, scope, mode='morphology', rpm_penalty=1.0, margin=0.03)`
- `class FaultDiscriminator — predict, analyze`
- `class FaultDiscriminationStage — analyze_window`

## vibration/geometry.py

ideal bearing frequency providers

- `class BearingGeometry — validate, frequencies`
- `class BearingMap — frequencies`

## vibration/independent_data.py

Explicitly grouped public rotor data reader. Reserved target arrays stay closed.

- `class IndependentRotorCatalog — rows, load, marra_members, load_marra`

## vibration/iso/__init__.py

User-supplied assessment rules; the public package ships no standards tables.


## vibration/iso/contracts.py

typed array/result contracts

- `class MachineContext — validate`
- `class Measurement — validate, canonical_value`
- `class Rule — validate, to_dict`
- `class NotApplicable`
- `class MissingInformation`
- `require(context, *names)`
- `check(condition, message)`
- `structural_axis(context, measurement)`

## vibration/iso/evaluation.py

Original generic interval assessment, with all limits supplied by the caller.

- `available_standards()`
- `select_rule(standard, context, measurement)`
- `evaluate(standard, context, measurement, *, custom_rule=None)`
- `aggregate(results)`

## vibration/iso/measurements.py

Phase-preserving ideal DFT band extraction; does not certify an instrument.

- `measure_waveform(values, *, sample_rate_hz, input_unit, quantity, statistic, frame, band_hz, point_id, axes, calibrated=False, acquisition_verified=False, start_s=0, clock_id='measurement_clock', order=None, filter_bandwidth_hz=None)`
- `energy_equivalent_average(measurements)`
- `class EnergyEquivalentAccumulator — reset, push`

## vibration/iso/stage.py

Raw-window integration of independently supplied engineering rules.

- `class IsoStage — analyze_window`

## vibration/models.py

Supporting implementation

- `class ModelRegistry — load, use_two_stage, use_conditioned, classify_window, classify, train, close`
- `class LifeEstimator — estimate`

## vibration/ports.py

structural Python interfaces

- `class BearingProvider — frequencies`
- `class ResultStage`
- `class WindowStage — analyze_window`
- `class ResultSink`

## vibration/rotor_features.py

Measured-speed rotor features: harmonic power, directional ratios, absolute levels.

- `class RotorFeatures`
- `rotor_features(values, sample_rate_hz, rpm, *, channel_names=None)`
- `feature_indices(names, mode='combined')`

## vibration/server.py

optional local HTTP/SSE application

- `class Application — start_udp, close`
- `class Handler — app, handle, log_message, do_GET, do_POST`
- `main()`

## vibration/stages.py

Bridges to the optional local supervised and reference-life modules.

- `class ClassifierStage — analyze_window`
- `class LifeStage`

## vibration/storage.py

optional local SQLite persistence

- `utcnow()`
- `class Storage — close, start_session, frame, event, save, get, documents, history`

## vibration/two_stage.py

normal-first prototype hypotheses

- `fit_two_stage(normal_fit, normal_fit_groups, normal_calibration, calibration_groups, faults, fault_labels, fault_groups, *, feature_names, scope, mode='relative', normal_quantile=0.8, anomaly_quantile=0.99, min_margin=0.1)`
- `class TwoStageDiagnostic — relative_features, predict, analyze`
- `class TwoStageStage — analyze_window`
