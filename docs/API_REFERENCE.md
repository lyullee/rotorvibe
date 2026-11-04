# Complete public API reference

Source-derived declarations for RotorVibe 0.1.0a1. The README explains purpose, units, shapes, outputs and composition.
Defaults below are source expressions; this page does not construct a service or train a model.
Dataclass annotations describe constructor fields; functions list all declared parameters.

## vibration/adapters.py

[Implementation](../vibration/adapters.py)

```python
from_process_batch(batch, *, sample_rate_hz, clock_id, rpm=None)
```

```python
to_process_batch(results)
```

```python
condition_evidence(result, *, asset_id)
```

## vibration/alarm.py

[Implementation](../vibration/alarm.py)

### AlarmStage

```python
AlarmStage.__init__(self, *, score_stage='baseline', warning=3, danger=6, persistence_seconds=2, release_seconds=3, max_gap_seconds=2)
```

```python
AlarmStage.reset(self)
```

```python
AlarmStage.__call__(self, result)
```

## vibration/baseline.py

[Implementation](../vibration/baseline.py)

```python
utcnow()
```

### Baseline

```python
Baseline.__init__(self)
```

```python
Baseline.begin(self, name, config, target=60)
```

```python
Baseline.observe(self, vector, names, config, rpm)
```

### BaselineStage

```python
BaselineStage.__init__(self, config, *, profile=None)
```

```python
BaselineStage.begin(self, name='normal', windows=60)
```

```python
BaselineStage.export_profile(self)
```

```python
BaselineStage.__call__(self, result)
```

## vibration/bearings.py

[Implementation](../vibration/bearings.py)

### Bearings

```python
Bearings.__init__(self)
```

```python
Bearings.frequencies(self, id, rpm)
```

```python
Bearings.custom(self, values)
```

## vibration/classifier.py

[Implementation](../vibration/classifier.py)

```python
fit_gaussian(x, y, groups, *, variance_floor=0.25, feature_schema=FEATURE_SCHEMA)
```

### GaussianClassifier

```python
GaussianClassifier.__init__(self, profile)
```

```python
GaussianClassifier.scores(self, features)
```

```python
GaussianClassifier.predict_many(self, features, *, reject_unknown=True)
```

```python
GaussianClassifier.predict(self, features)
```

## vibration/client.py

[Implementation](../vibration/client.py)

### VibrationClient

```python
VibrationClient.__init__(self, base_url='http://127.0.0.1:8765', token='', timeout=30)
```

```python
VibrationClient.request(self, path, payload=None)
```

```python
VibrationClient.start(self, sample_rate_hz, channels, unit='unknown', rpm=None, **configuration)
```

```python
VibrationClient.packet(self, samples, rpm=None, rpm_trace=None, timestamp=None)
```

```python
VibrationClient.push(self, samples, **kwargs)
```

```python
VibrationClient.push_udp(self, samples, host='127.0.0.1', port=9001, **kwargs)
```

```python
VibrationClient.stop(self)
```

## vibration/condition_data.py

[Implementation](../vibration/condition_data.py)

```python
file_sha(path)
```

### UosRotorCatalog

```python
UosRotorCatalog.__init__(self, root)
```

```python
UosRotorCatalog.rows(self, role=None)
```

```python
UosRotorCatalog.load(self, record_id, *, frozen_model_sha256=None)
```

### ExposedCrossSpeedDevelopment

```python
ExposedCrossSpeedDevelopment.__init__(self, root)
```

```python
ExposedCrossSpeedDevelopment.rows(self)
```

```python
ExposedCrossSpeedDevelopment.load(self, record_id)
```

## vibration/conditioned.py

[Implementation](../vibration/conditioned.py)

```python
canonical_values(values, source_rate, target_rate=4000)
```

```python
selected_features(names, mode)
```

```python
matrix(values)
```

```python
reference_at(references, rpm, *, interpolate, max_gap, uncertainty)
```

```python
fit_conditioned(normal, normal_rpm, normal_groups, calibration, calibration_rpm, calibration_groups, faults, fault_rpm, fault_labels, fault_groups, *, feature_names, scope, mode='levels_orders', interpolate=False, max_rpm_gap=800.0, interpolation_uncertainty=1.0, min_margin=0.1)
```

### ConditionedDiagnostic

```python
ConditionedDiagnostic.__init__(self, profile)
```

```python
ConditionedDiagnostic.predict(self, features, *, scope)
```

```python
ConditionedDiagnostic.analyze(self, values, sample_rate_hz, rpm, *, scope, channel_names=None)
```

### ConditionedStage

```python
ConditionedStage.__init__(self, model)
```

```python
ConditionedStage.__call__(self, result)
```

```python
ConditionedStage.analyze_window(self, result, values)
```

## vibration/config.py

[Implementation](../vibration/config.py)

### AnalysisConfig

| Constructor field | Type | Default |
|---|---|---|
| `sample_rate_hz` | `float` | `12000` |
| `channels` | `int` | `1` |
| `channel` | `int` | `0` |
| `window_seconds` | `float` | `1` |
| `hop_seconds` | `float` | `0.25` |
| `unit` | `str` | `'unknown'` |
| `input_representation` | `str` | `'physical'` |
| `sensitivity_mv_per_g` | `list \| None` | `None` |
| `conditioner_gain` | `float` | `1` |
| `bias_voltage_v` | `float` | `0` |
| `calibration_id` | `str` | `''` |
| `rpm` | `float \| None` | `None` |
| `bearing_id` | `str \| None` | `None` |
| `condition` | `str` | `'기본 운전조건'` |
| `load` | `float \| None` | `None` |
| `window` | `str` | `'hann'` |
| `envelope_low_hz` | `float` | `500` |
| `envelope_high_hz` | `float` | `5000` |
| `velocity_low_hz` | `float` | `10` |
| `velocity_high_hz` | `float` | `1000` |
| `peak_tolerance_ratio` | `float` | `0.03` |
| `warning_score` | `float` | `3` |
| `danger_score` | `float` | `6` |
| `persistence_seconds` | `float` | `2` |
| `release_seconds` | `float` | `3` |
| `rms_warning` | `float \| None` | `None` |
| `rms_danger` | `float \| None` | `None` |
| `clip_abs` | `float \| None` | `None` |
| `model_enabled` | `bool` | `False` |
| `order_tracking` | `bool` | `True` |

```python
AnalysisConfig.validate(self)
```

```python
AnalysisConfig.create(cls, values=None)
```

```python
AnalysisConfig.to_dict(self)
```

```python
AnalysisConfig.signature(self)
```

```python
AnalysisConfig.for_source(self, fs, channels, duration, unit, rpm, bearing_id)
```

## vibration/contracts.py

[Implementation](../vibration/contracts.py)

### SignalBlock

| Constructor field | Type | Default |
|---|---|---|
| `values` | `np.ndarray` | `required` |
| `sample_rate_hz` | `float` | `required` |
| `unit` | `str` | `'unknown'` |
| `start_time_s` | `float` | `0.0` |
| `clock_id` | `str` | `'sample_clock'` |
| `episode_id` | `str` | `'default'` |
| `channels` | `tuple[str, ...]` | `()` |
| `valid` | `np.ndarray \| None` | `None` |
| `rpm` | `float \| np.ndarray \| None` | `None` |
| `sequence` | `int \| None` | `None` |
| `metadata` | `Mapping[str, Any]` | `field(default_factory=dict)` |

```python
json_value(value)
```

### AnalysisResult

| Constructor field | Type | Default |
|---|---|---|
| `start_time_s` | `float` | `required` |
| `end_time_s` | `float` | `required` |
| `clock_id` | `str` | `required` |
| `episode_id` | `str` | `required` |
| `channels` | `tuple[str, ...]` | `required` |
| `valid` | `bool` | `required` |
| `payload` | `Mapping[str, Any]` | `required` |
| `metadata` | `Mapping[str, Any]` | `field(default_factory=dict)` |

```python
AnalysisResult.features(self)
```

```python
AnalysisResult.feature_names(self)
```

```python
AnalysisResult.metrics(self)
```

```python
AnalysisResult.to_dict(self, *, include_features=True)
```

## vibration/core.py

[Implementation](../vibration/core.py)

### VibrationAnalyzer

```python
VibrationAnalyzer.__init__(self, config=None, *, bearing_provider=None, stages=None, sinks=())
```

```python
VibrationAnalyzer.config(self)
```

```python
VibrationAnalyzer.reset(self)
```

```python
VibrationAnalyzer.analyze(self, block: SignalBlock)
```

```python
VibrationAnalyzer.push(self, block: SignalBlock)
```

```python
analyze_signal(values, config=None, **block_options)
```

## vibration/datasets.py

[Implementation](../vibration/datasets.py)

```python
local_path(root, relative)
```

```python
matrix(a)
```

### DatasetCatalog

```python
DatasetCatalog.__init__(self)
```

```python
DatasetCatalog.search(self, query='', dataset='', offset=0, limit=100)
```

```python
DatasetCatalog.details(self, id)
```

```python
DatasetCatalog.trial_ids(self, id)
```

```python
DatasetCatalog.load(self, id, snapshot=0)
```

```python
DatasetCatalog.imported(self, filename, payload, fs=None, unit='unknown', channels_axis=1, skip_columns=0)
```

## vibration/dsp.py

[Implementation](../vibration/dsp.py)

```python
spectrum(x, fs, window='hann')
```

```python
compact_spectrum(f, a, maximum=1800, *, native=False)
```

```python
waveform(x, fs, maximum=1600, *, native=False)
```

```python
channel_features(data, fs)
```

```python
peak_evidence(f, amplitude, target, tolerance_ratio, resolution, *, spacing_hz=None)
```

```python
analyze(data, config, rpm_trace=None, bearing_frequencies=None, *, native=False)
```

## vibration/engine.py

[Implementation](../vibration/engine.py)

### EventHub

```python
EventHub.__init__(self)
```

```python
EventHub.subscribe(self)
```

```python
EventHub.unsubscribe(self, q)
```

```python
EventHub.publish(self, kind, payload)
```

### Ring

```python
Ring.__init__(self, n, channels)
```

```python
Ring.append(self, a, rpm)
```

```python
Ring.snapshot(self)
```

### Engine

```python
Engine.__init__(self, storage, catalog, bearings, models)
```

```python
Engine.state(self)
```

```python
Engine.configure(self, values)
```

```python
Engine.live(self, values=None)
```

```python
Engine.stop(self)
```

```python
Engine.replay(self, id, speed=1, loop=False, snapshot=0, loaded=None, sequence=False)
```

```python
Engine.ingest(self, payload)
```

```python
Engine.close(self)
```

```python
Engine.save_window(self)
```

```python
Engine.baseline_start(self, name, target)
```

```python
Engine.baseline_load(self, name)
```

## vibration/fault_discrimination.py

[Implementation](../vibration/fault_discrimination.py)

```python
fault_features(values, sample_rate_hz, rpm)
```

```python
fit_fault_discriminator(x, labels, rpms, groups, *, names, scope, mode='morphology', rpm_penalty=1.0, margin=0.03)
```

### FaultDiscriminator

```python
FaultDiscriminator.__init__(self, profile)
```

```python
FaultDiscriminator.predict(self, features, rpm, *, scope)
```

```python
FaultDiscriminator.analyze(self, values, sample_rate_hz, rpm, *, scope)
```

### FaultDiscriminationStage

```python
FaultDiscriminationStage.__init__(self, model, gate_key='conditioned')
```

```python
FaultDiscriminationStage.__call__(self, result)
```

```python
FaultDiscriminationStage.analyze_window(self, result, values)
```

## vibration/geometry.py

[Implementation](../vibration/geometry.py)

### BearingGeometry

| Constructor field | Type | Default |
|---|---|---|
| `rolling_elements` | `int` | `required` |
| `rolling_diameter` | `float` | `required` |
| `pitch_diameter` | `float` | `required` |
| `contact_angle_deg` | `float` | `0` |

```python
BearingGeometry.validate(self)
```

```python
BearingGeometry.frequencies(self, rpm)
```

### BearingMap

```python
BearingMap.__init__(self, geometries)
```

```python
BearingMap.frequencies(self, id, rpm)
```

## vibration/independent_data.py

[Implementation](../vibration/independent_data.py)

### IndependentRotorCatalog

```python
IndependentRotorCatalog.__init__(self, root)
```

```python
IndependentRotorCatalog.rows(self, *, role=None, normal_only=False)
```

```python
IndependentRotorCatalog.load(self, record_id, *, frozen_model_sha256=None)
```

```python
IndependentRotorCatalog.marra_members(self)
```

```python
IndependentRotorCatalog.load_marra(self, archive_name, member)
```

## vibration/iso/contracts.py

[Implementation](../vibration/iso/contracts.py)

### MachineContext

| Constructor field | Type | Default |
|---|---|---|
| `asset_id` | `str` | `required` |
| `machine` | `str` | `required` |
| `power_kw` | `float \| None` | `None` |
| `rated_rpm` | `float \| None` | `None` |
| `operating_rpm` | `float \| None` | `None` |
| `max_continuous_rpm` | `float \| None` | `None` |
| `bearing_type` | `str \| None` | `None` |
| `support` | `str \| None` | `None` |
| `shaft_height_mm` | `float \| None` | `None` |
| `operating_state` | `str` | `'unknown'` |
| `location` | `str` | `'unknown'` |
| `condition_id` | `str` | `'unknown'` |
| `thrust_bearing` | `bool` | `False` |
| `land_based` | `bool \| None` | `None` |
| `aero_derivative` | `bool \| None` | `None` |
| `coupled` | `bool \| None` | `None` |
| `category` | `str \| None` | `None` |
| `impeller_blades` | `int \| None` | `None` |
| `nominal_clearance_um` | `float \| None` | `None` |
| `orientation` | `str \| None` | `None` |
| `reciprocating_class` | `int \| None` | `None` |
| `hydro_group` | `int \| None` | `None` |
| `hydro_type` | `str \| None` | `None` |
| `bearing_position` | `str \| None` | `None` |
| `runner_blades` | `int \| None` | `None` |
| `guide_vanes` | `int \| None` | `None` |
| `load_fraction` | `float \| None` | `None` |
| `journal_diameter_mm` | `float \| None` | `None` |
| `smooth_pelton_operation` | `bool \| None` | `None` |
| `hydraulic_normal_operation` | `bool \| None` | `None` |
| `pumping_at_rated_capacity` | `bool \| None` | `None` |
| `geared` | `bool \| None` | `None` |
| `offshore` | `bool \| None` | `None` |
| `icing` | `bool \| None` | `None` |
| `purpose` | `str` | `'monitoring'` |
| `flow_region` | `str \| None` | `None` |
| `support_design_confirmed` | `bool \| None` | `None` |
| `hydro_extended_housing_band` | `bool` | `False` |
| `exclusions` | `tuple[str, ...]` | `()` |

```python
MachineContext.validate(self)
```

### Measurement

| Constructor field | Type | Default |
|---|---|---|
| `value` | `float` | `required` |
| `quantity` | `str` | `required` |
| `unit` | `str` | `required` |
| `statistic` | `str` | `required` |
| `frame` | `str` | `required` |
| `band_hz` | `tuple[float, float]` | `required` |
| `duration_s` | `float` | `required` |
| `axis` | `str` | `required` |
| `point_id` | `str` | `required` |
| `start_s` | `float` | `0` |
| `clock_id` | `str` | `'measurement_clock'` |
| `calibrated` | `bool` | `False` |
| `acquisition_verified` | `bool` | `False` |
| `valid` | `bool` | `True` |
| `averaging` | `str` | `'single_window'` |
| `observations` | `int` | `1` |
| `revolutions_per_observation` | `float \| None` | `None` |
| `order` | `float \| None` | `None` |
| `filter_bandwidth_hz` | `float \| None` | `None` |
| `provenance` | `dict` | `field(default_factory=dict)` |

```python
Measurement.validate(self)
```

```python
Measurement.canonical_value(self)
```

### Rule

| Constructor field | Type | Default |
|---|---|---|
| `standard` | `str` | `required` |
| `key` | `str` | `required` |
| `quantity` | `str` | `required` |
| `statistic` | `str` | `required` |
| `frames` | `tuple[str, ...]` | `required` |
| `limits` | `tuple[float, ...]` | `required` |
| `band_hz` | `tuple[float, float]` | `required` |
| `source_page` | `int` | `required` |
| `source_clause` | `str` | `required` |
| `zones` | `tuple[str, ...]` | `('A', 'B', 'C', 'D')` |
| `authority` | `str` | `'user_supplied_limits'` |
| `minimum_duration_s` | `float` | `0` |
| `minimum_upper_band` | `bool` | `False` |
| `notes` | `tuple[str, ...]` | `()` |

```python
Rule.validate(self)
```

```python
Rule.to_dict(self)
```

### NotApplicable

### MissingInformation

```python
require(context, *names)
```

```python
check(condition, message)
```

```python
structural_axis(context, measurement)
```

## vibration/iso/evaluation.py

[Implementation](../vibration/iso/evaluation.py)

```python
available_standards()
```

```python
select_rule(standard, context, measurement)
```

```python
evaluate(standard, context, measurement, *, custom_rule=None)
```

```python
aggregate(results)
```

## vibration/iso/measurements.py

[Implementation](../vibration/iso/measurements.py)

```python
measure_waveform(values, *, sample_rate_hz, input_unit, quantity, statistic, frame, band_hz, point_id, axes, calibrated=False, acquisition_verified=False, start_s=0, clock_id='measurement_clock', order=None, filter_bandwidth_hz=None)
```

```python
energy_equivalent_average(measurements)
```

### EnergyEquivalentAccumulator

```python
EnergyEquivalentAccumulator.__init__(self, period_s)
```

```python
EnergyEquivalentAccumulator.reset(self)
```

```python
EnergyEquivalentAccumulator.push(self, measurement)
```

## vibration/iso/stage.py

[Implementation](../vibration/iso/stage.py)

### IsoStage

```python
IsoStage.__init__(self, standard, context, *, custom_rule=None, point_id, axis='radial', calibrated=False, acquisition_verified=False)
```

```python
IsoStage.__call__(self, result)
```

```python
IsoStage.analyze_window(self, result, values)
```

## vibration/models.py

[Implementation](../vibration/models.py)

### ModelRegistry

```python
ModelRegistry.__init__(self, storage, catalog)
```

```python
ModelRegistry.load(self, name)
```

```python
ModelRegistry.use_two_stage(self, profile)
```

```python
ModelRegistry.use_conditioned(self, profile)
```

```python
ModelRegistry.classify_window(self, values, config, source, *, vector=None, channel_names=None, rpm=None, rpm_variation_ratio=0.0)
```

```python
ModelRegistry.classify(self, vector, config, source)
```

```python
ModelRegistry.train(self, name)
```

```python
ModelRegistry.close(self)
```

### LifeEstimator

```python
LifeEstimator.__init__(self, catalog)
```

```python
LifeEstimator.estimate(self, source)
```

## vibration/ports.py

[Implementation](../vibration/ports.py)

### BearingProvider

```python
BearingProvider.frequencies(self, id: str, rpm: float)
```

### ResultStage

```python
ResultStage.__call__(self, result: AnalysisResult)
```

### WindowStage

```python
WindowStage.analyze_window(self, result: AnalysisResult, values: Any)
```

### ResultSink

```python
ResultSink.__call__(self, result: AnalysisResult)
```

## vibration/rotor_features.py

[Implementation](../vibration/rotor_features.py)

### RotorFeatures

| Constructor field | Type | Default |
|---|---|---|
| `names` | `tuple` | `required` |
| `values` | `np.ndarray` | `required` |
| `sample_rate_hz` | `float` | `required` |
| `rpm` | `float` | `required` |
| `channel_names` | `tuple` | `required` |
| `sample_count` | `int` | `0` |
| `schema` | `str` | `ROTOR_SCHEMA` |

```python
rotor_features(values, sample_rate_hz, rpm, *, channel_names=None)
```

```python
feature_indices(names, mode='combined')
```

## vibration/server.py

[Implementation](../vibration/server.py)

### Application

```python
Application.__init__(self, token='')
```

```python
Application.start_udp(self, host, port)
```

```python
Application.close(self)
```

### Handler

```python
Handler.app(self)
```

```python
Handler.handle(self)
```

```python
Handler.log_message(self, fmt, *args)
```

```python
Handler.do_GET(self)
```

```python
Handler.do_POST(self)
```

```python
main()
```

## vibration/stages.py

[Implementation](../vibration/stages.py)

### ClassifierStage

```python
ClassifierStage.__init__(self, registry)
```

```python
ClassifierStage.__call__(self, result)
```

```python
ClassifierStage.analyze_window(self, result, values)
```

### LifeStage

```python
LifeStage.__init__(self, estimator)
```

```python
LifeStage.__call__(self, result)
```

## vibration/storage.py

[Implementation](../vibration/storage.py)

```python
utcnow()
```

### Storage

```python
Storage.__init__(self)
```

```python
Storage.close(self)
```

```python
Storage.start_session(self, id, source, config)
```

```python
Storage.frame(self, session_id, frame)
```

```python
Storage.event(self, session_id, level, kind, payload)
```

```python
Storage.save(self, kind, name, value)
```

```python
Storage.get(self, kind, name)
```

```python
Storage.documents(self, kind)
```

```python
Storage.history(self, kind='events', limit=200, session_id=None)
```

## vibration/two_stage.py

[Implementation](../vibration/two_stage.py)

```python
fit_two_stage(normal_fit, normal_fit_groups, normal_calibration, calibration_groups, faults, fault_labels, fault_groups, *, feature_names, scope, mode='relative', normal_quantile=0.8, anomaly_quantile=0.99, min_margin=0.1)
```

### TwoStageDiagnostic

```python
TwoStageDiagnostic.__init__(self, profile)
```

```python
TwoStageDiagnostic.relative_features(self, features, *, scope)
```

```python
TwoStageDiagnostic.predict(self, features, *, scope)
```

```python
TwoStageDiagnostic.analyze(self, values, sample_rate_hz, rpm, *, scope, channel_names=None)
```

### TwoStageStage

```python
TwoStageStage.__init__(self, model)
```

```python
TwoStageStage.__call__(self, result)
```

```python
TwoStageStage.analyze_window(self, result, values)
```
