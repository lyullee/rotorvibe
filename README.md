# RotorVibe

**Composable rotating-machine vibration analysis for Python.**

RotorVibe turns calibrated waveform blocks into spectra, bearing-frequency markers,
condition-relative evidence and inspectable diagnostic candidates. Use the NumPy API
inside your own application; the local web dashboard is optional.

**Alpha research release, version 0.1.0a1.** Signal calculations and bounded software
checks are documented. Fault classifiers have **not** qualified for unattended field
diagnosis: new-bearing and independent-rig transfer tests failed. No remaining-life
prediction, automatic shutdown authority or standards certification is supplied.

[한국어 설명](README.ko.md) · [User guide](docs/USER_GUIDE.md) ·
[Algorithm notes](docs/ALGORITHMS.md) · [Development record](docs/DEVELOPMENT_HISTORY.md) ·
[Continue this research](docs/CONTINUATION.md) · [Source/rights policy](docs/SOURCES_AND_RIGHTS.md)

## Install

Python 3.11+ with NumPy 2.x and SciPy 1.13+ is required.

```console
python -m pip install rotorvibe==0.1.0a1
```

For an editable checkout and verification tools:

```console
git clone https://github.com/lyullee/rotorvibe.git
cd rotorvibe
python -m pip install -e ".[verification]"
python -m unittest discover -s tests -v
```

The public facade is `rotorvibe`; the earlier `vibration` namespace remains available
so existing Python integrations can keep their imports. Raw experimental data and
trained rig-specific profiles are acquired separately, not installed by pip.

## Module map: purpose, inputs and outputs

**Start here when integrating RotorVibe into another Python system.** Each row is
an importable calculation or integration unit. A web server is not required for the
core. Names in `rotorvibe.__all__` are available from `rotorvibe`; deeper utilities
use the `vibration.*` import paths shown below. `N` = samples, `C` = channels,
`W` = observations/windows, `F` = features; `Hz` = cycles/s and RPM = rev/min.

```text
host DAQ -> SignalBlock + AnalysisConfig -> VibrationAnalyzer
    -> DSP / bearing markers -> ordered stages -> AnalysisResult -> host sinks
                               baseline -> alarm
                               normal gate -> conditional fault-type head
                               caller-supplied measurement rule
```

### Core calculations and replaceable interfaces

| Module / Python entry point | Purpose | Inputs / important parameters | Output / next connection |
|---|---|---|---|
| [`contracts`](vibration/contracts.py): `SignalBlock` | Typed waveform input | `values: float[N] or float[N,C]`, actual `sample_rate_hz`, `unit`, time/identity/validity fields below | Read-only copied samples, normalized to `[N,C]`; input to `analyze` / `push` |
| [`config`](vibration/config.py): `AnalysisConfig` | Analysis, calibration and band settings | Sample rate, channel count/index, window/hop seconds, units, sensitivity, RPM and filter bands | Validated configuration; `create(dict)`, `to_dict()`, `signature()` |
| [`core`](vibration/core.py): `VibrationAnalyzer(config=None, *, bearing_provider=None, stages=None, sinks=())` | Synchronous calculation / stream windowing | Config, optional geometry provider, ordered `{name: stage}`, result callbacks | `analyze(block) -> AnalysisResult`; `push(block) -> list[AnalysisResult]`; `reset() -> None` |
| `core.analyze_signal(values, config=None, **block_options)` | One-call complete-window calculation | Samples, config and `SignalBlock` options; exactly one configured window | `AnalysisResult`; constructs a new analyzer (no retained stream) |
| [`dsp`](vibration/dsp.py): `spectrum(x, fs, window='hann')` | One-sided FFT and PSD | 1-D samples, sample rate Hz, `hann` / `hamming` / `boxcar` | `(frequency_hz[K], amplitude[K], psd[K])`; amplitude in input unit, PSD in unit²/Hz |
| `dsp.channel_features(data, fs)` | Shared numerical feature vector | Finite waveform `[N,C]`, sample rate Hz | `(names, vector[F])`, 7 features/channel: log RMS, log crest, Pearson kurtosis and 4 log band fractions |
| `dsp.analyze(data, config, rpm_trace=None, bearing_frequencies=None, *, native=False)` | Metrics, envelope, spectra and harmonic evidence | Physical waveform, validated config, optional RPM `[N]`, marker `{name: Hz}` | Payload dictionary described below; low-level API, use `VibrationAnalyzer` for calibration/quality/identity checks |
| `dsp.waveform(x, fs, maximum=1600, *, native=False)` / `compact_spectrum(f, a, maximum=1800, *, native=False)` | Prepare plot arrays | Waveform or frequency/value arrays; display size limit | `{x, y}`; `native=True` preserves full arrays, display compaction is not a measurement input |
| `dsp.peak_evidence(f, amplitude, target, tolerance_ratio, resolution, *, spacing_hz=None)` | Find local peak near a predicted frequency | Frequency/amplitude arrays, target and resolution Hz, relative tolerance, optional harmonic spacing | Evidence dictionary or `None`; unresolved bands explicitly reported |
| [`geometry`](vibration/geometry.py): `BearingGeometry(rolling_elements, rolling_diameter, pitch_diameter, contact_angle_deg=0)` | Ideal bearing defect-frequency calculation | Count, diameters in the **same** length unit, angle degrees; `.frequencies(rpm)` | `{BPFI, BPFO, FTF, BSF, 2BSF}` in Hz; no slip correction or vendor catalog |
| `geometry.BearingMap(geometries)` | Replaceable geometry lookup | `{bearing_id: BearingGeometry}`; `.frequencies(id, rpm)` | Same frequency mapping; inject as `bearing_provider` and set `config.bearing_id` |
| [`ports`](vibration/ports.py): `BearingProvider`, `ResultStage`, `WindowStage`, `ResultSink` | Structural contracts for host-written modules | Provider `.frequencies(id,rpm)`; stage `__call__(result)`; optional `.analyze_window(result, readonly_values)`; sink `__call__(result)` | Provider -> Hz map; stage -> named payload; sink -> side effect, return ignored |

### Normal references, alarms and experimental diagnostic units

Profiles are explicit dictionaries, not bundled trained models. Training arrays are
`[W,F]`; feature names/order must match at inference. `groups[W]` identifies original
acquisitions, not shuffled windows. `scope` records the actual asset/sensor/condition
contract used by that profile. Keep normal fitting, calibration and final test
acquisitions disjoint. These models are experimental, with `operational_use=False`.

| Module / Python entry point | Purpose | Inputs / important parameters | Output / next connection |
|---|---|---|---|
| [`baseline`](vibration/baseline.py): `BaselineStage(config, *, profile=None)` | Collect or reuse a robust normal reference | Config; optional compatible profile; `.begin(name='normal', windows=60)` then valid results with source identity | Stage dict: `status`, `score` when supported, contributions; `.export_profile()` -> dict or `None` |
| [`alarm`](vibration/alarm.py): `AlarmStage(*, score_stage='baseline', warning=3, danger=6, persistence_seconds=2, release_seconds=3, max_gap_seconds=2)` | Observation-time alarm persistence | An earlier payload's `score`, result validity, clock/episode/end time; threshold ordering and durations | `{level, pending, score}` or unavailable/retained level; no machine-trip authority |
| [`rotor_features`](vibration/rotor_features.py): `extract_rotor_features(values, sample_rate_hz, rpm, *, channel_names=None)` | Speed-referenced harmonics, levels and cross-channel ratios | Waveform `[N,C]`, finite positive RPM, actual sample rate and channel names | `RotorFeatures(names, values, sample_rate_hz, rpm, channel_names, sample_count, schema)`; `.values` is a feature vector |
| [`classifier`](vibration/classifier.py): `fit_gaussian(x, y, groups, *, variance_floor=0.25, feature_schema=...)` | Fit standardized diagonal Gaussian baseline | Features `[W,F]`, class labels `[W]`, acquisition groups, variance floor and schema | Profile dict; `GaussianClassifier(profile).predict(vector)` -> label/matches; not calibrated probabilities |
| [`two_stage`](vibration/two_stage.py): `fit_two_stage(...)` / `TwoStageDiagnostic(profile)` | Normal-first screening followed by known fault matching | Fit: `normal_fit`, `normal_fit_groups`, `normal_calibration`, `calibration_groups`, `faults`, `fault_labels`, `fault_groups`; keyword `feature_names`, `scope`, `mode`, quantiles, `min_margin` | Profile; `.predict(features, *, scope)` or `.analyze(values, sample_rate_hz, rpm, *, scope, channel_names=None)` -> decision dict |
| `two_stage.TwoStageStage(model)` | Attach two-stage model to analyzer | Model and calibrated raw window + result metadata | Named diagnostic payload; rejects invalid / unsupported variable-speed inputs |
| [`conditioned`](vibration/conditioned.py): `fit_conditioned(...)` / `ConditionedDiagnostic(profile)` | RPM-conditioned normal-reference bank | Fit: `normal`, `normal_rpm`, `normal_groups`, `calibration`, `calibration_rpm`, `calibration_groups`, `faults`, `fault_rpm`, `fault_labels`, `fault_groups`; keyword `feature_names`, `scope`, `mode`, interpolation/gap/uncertainty/margin | Profile; `.predict(features, *, scope)` or `.analyze(values, sample_rate_hz, rpm, *, scope, channel_names=None)` -> decision dict, hold outside supported scope |
| `conditioned.ConditionedStage(model)` | Attach conditioned gate to analyzer | Model and result/raw-window pair | Gate output containing decision status and anomaly evidence; use before fault head |
| [`fault_discrimination`](vibration/fault_discrimination.py): `fault_features(values, sample_rate_hz, rpm)` | Morphology for separating looseness / imbalance / misalignment | Exactly 2 seconds of one channel, actual sample rate and RPM | `(names, vector[61])`; fixed-speed research feature contract |
| `fit_fault_discriminator(x, labels, rpms, groups, *, names, scope, mode='morphology', rpm_penalty=1, margin=0.03)` | Fit conditional fault-type prototypes | Fault-only feature matrix, labels, RPM per row, acquisition groups, names, scope, feature mode and rejection parameters | Profile dict; excludes a healthy class |
| `FaultDiscriminator(profile)` | Conditional fault-type inference | `.predict(features, rpm, *, scope)` or `.analyze(values, sample_rate_hz, rpm, *, scope)` | `{status, label, ...}`: hold / anomaly_unknown / fault_candidate; requires prior anomaly screening |
| `FaultDiscriminationStage(model, gate_key='conditioned')` | Enforce gate-before-head composition | Earlier `payload[gate_key]['anomaly'] is True`, valid window and scope; RPM variation <=3% | Fault-head dict; otherwise hold with explicit reason |
| [`stages`](vibration/stages.py): `ClassifierStage(registry)` / `LifeStage(estimator)` | Bridge host registry / reference-life estimator into stages | Injected registry or estimator and result/raw window | Classification / life payload; constructor does not start training |
| [`models`](vibration/models.py): `ModelRegistry(storage, catalog)` | Optional stored models and explicit training jobs | Storage/catalog; `load(name)`, `use_two_stage(profile)`, `use_conditioned(profile)`, `train(name)` | Classification dict or training-job status; `.close()` releases worker resources |
| `models.LifeEstimator(catalog).estimate(source)` | Experimental PRONOSTIA reference-life similarity | Training complete-life catalog and observed-prefix metadata: dataset, record ID, RPM, baseline/recent RMS | Refusal state or experimental `remaining_seconds`, reference range and matches; **not validated field RUL**, reference range is not a confidence interval |

### Engineering measurement and user-supplied criteria

The `vibration.iso` namespace has **no distributed ISO/KS threshold tables or machine
selectors**. Limits come from the caller. `available_standards()` returns `()`.

| Module / Python entry point | Purpose | Inputs / important parameters | Output / next connection |
|---|---|---|---|
| [`iso.contracts`](vibration/iso/contracts.py): `MachineContext` | Identify assessment condition | Required `asset_id`, `machine`; explicit `operating_state`, `condition_id`, `location`; optional engineering context | Validated context; extra category fields do not enable built-in normative selectors |
| `iso.contracts.Measurement` | Typed magnitude at a measurement point | `value`, `quantity`, `unit`, `statistic`, `frame`, `band_hz`, `duration_s`, `axis`, `point_id`; calibration/acquisition flags and provenance | Typed observation; `.canonical_value()` -> acceleration m/s², velocity mm/s, displacement µm |
| `iso.contracts.Rule` | Caller-owned limit contract | `standard`, `key`, `quantity`, `statistic`, `frames`, increasing `limits`, `band_hz`, `source_page`, `source_clause`; optional `zones`, duration, notes | Validated rule; `.to_dict()` -> serializable contract; no implicit RMS/peak conversion |
| [`iso.measurements`](vibration/iso/measurements.py): `measure_waveform(values, *, ...)` | Measure filtered waveform magnitude | Required `sample_rate_hz`, `input_unit`, `quantity`, `statistic`, `frame`, `band_hz`, `point_id`, `axes`; calibration/acquisition flags, time/clock, optional order/filter bandwidth | `list[Measurement]`, one per channel; DFT band integration, no instrument certification |
| `energy_equivalent_average(measurements)` / `EnergyEquivalentAccumulator(period_s).push(measurement)` | Duration-weighted RMS averaging | Compatible RMS observations with matching units/point/band/time context; accumulation period seconds | Averaged `Measurement`; accumulator returns `None` until period reached |
| [`iso.evaluation`](vibration/iso/evaluation.py): `evaluate(standard, context, measurement, *, custom_rule=None)` | Assess one observation against explicit limits | Rule ID, context, measurement, caller `Rule` | Dict: `status`, `zone`, canonical value/unit and rule provenance; no rule / mismatch -> no zone; equality stays in lower interval |
| `iso.evaluation.aggregate(results)` | Preserve assessed-point coverage | Nonempty per-point results for same asset/rule/condition | Combined dict; `whole_machine_compliance=False` |
| [`iso.stage`](vibration/iso/stage.py): `IsoStage(standard, context, *, custom_rule=None, point_id, axis='radial', calibrated=False, acquisition_verified=False)` | Raw waveform -> measurement -> rule in one stage | One-channel window and explicit context/rule/qualification flags | Named evaluation payload; no rule -> indeterminate; multi-channel input requires separate per-channel use |

### Integration, acquisition, data access and optional service

| Module / Python entry point | Purpose | Inputs / important parameters | Output / ownership |
|---|---|---|---|
| [`adapters`](vibration/adapters.py): `from_process_batch(batch, *, sample_rate_hz, clock_id, rpm=None)` | Convert host batch to waveform contract | Object with uniform `time_s`, `values`, common channel `units`, `channels`, `origin`, `metadata`; optional validity/episode/mode | `SignalBlock`; split mixed modes/episodes first |
| `adapters.to_process_batch(results)` | Convert results into feature batch | Compatible `AnalysisResult` iterable; matching clock, measurement settings, feature order | External `process_monitoring.SignalBatch`, `[W,F]`, timestamps at exclusive window end; **requires host-installed process_monitoring**, not a pip dependency |
| `adapters.condition_evidence(result, *, asset_id)` | Neutral condition observation for other modules | Result and explicit asset identity | `vibration.condition-evidence.v1` dict; not accident probability/frequency |
| [`datasets`](vibration/datasets.py): `DatasetCatalog` | Optional local dataset index/import | Locally acquired files; `search(...)`, `details(id)`, `load(id, snapshot=0)`; `imported(filename, payload, fs=None, unit='unknown', channels_axis=1, skip_columns=0)` | Index metadata or `(array, metadata)`; raw files are not installed or downloaded automatically |
| [`independent_data`](vibration/independent_data.py): `IndependentRotorCatalog` | Group-aware rotor acquisition reader | Explicit root/manifest; `rows(*, role=None, normal_only=False)`, `load(record_id, *, frozen_model_sha256=None)` and Marra archive methods | File identities / waveform blocks and metadata; preserve original-acquisition split |
| [`condition_data`](vibration/condition_data.py): `UosRotorCatalog` / `ExposedCrossSpeedDevelopment` | Conditioned-study readers | Local dataset root; `rows(role=None)` and `load(record_id, *, frozen_model_sha256=None)` for UOS | Rows and `(array, metadata)`; readers are not pretrained models or fresh holdouts |
| [`client`](vibration/client.py): `VibrationClient(base_url='http://127.0.0.1:8765', token='', timeout=30)` | Optional HTTP/UDP producer | `.start(sample_rate_hz, channels, unit, rpm, **configuration)`, `.push(samples, **kwargs)` / `.push_udp(...)`, `.stop()` | Server JSON / sent-packet response; server owns analysis, host owns network/retries |
| [`engine`](vibration/engine.py): `Engine(storage, catalog, bearings, models)` | Optional live/replay worker | Injected services; `configure(values)`, `live(...)`, `ingest(payload)`, `replay(id, speed, loop, ...)` | State/events/history; `EventHub` distributes events, `Ring` buffers samples; call `.close()` |
| [`storage`](vibration/storage.py): `Storage` | Optional local SQLite state | Sessions/config, result frames, events and named profiles via `save/get/history` | IDs / stored rows / retrieved documents; writable runtime directory, `.close()` |
| [`server`](vibration/server.py): `Application` / `rotorvibe-monitor` | Optional HTTP/SSE/UDP dashboard | CLI `--host`, `--port`; runtime/project environment paths and configured authentication | Local service/UI and streamed observations; close application resources; no server in direct core |
| [`bearings`](vibration/bearings.py): `Bearings` / [`bootstrap`](vibration/bootstrap.py) | Optional dashboard lookup / project-path bootstrap | Separately supplied local catalog files and project/runtime paths | Service lookup / environment paths; use `BearingGeometry` + `BearingMap` for portable host integration |

### Exact input contract and configuration parameters

`analyze` requires `N == round(sample_rate_hz * window_seconds)`;
`push` accepts arbitrary nonempty chunks and returns zero or more complete windows.
Config and block sample rate, channel count and input unit must agree. One analyzer
instance owns one stream; the host serializes calls and owns DAQ scheduling.

| `SignalBlock` parameter | Type / default | Meaning and unit |
|---|---|---|
| `values` | Required array `[N]` or `[N,C]` | Numeric samples; copied and made read-only, 1..16 channels |
| `sample_rate_hz` | Required positive finite number | Actual sampling frequency Hz |
| `unit` | `'unknown'` | `g`, `m/s^2`, `V`, or uncalibrated `unknown`; physical meaning must be declared |
| `start_time_s` | `0.0` | First sample time in caller clock, seconds |
| `clock_id`, `episode_id` | `'sample_clock'`, `'default'` | Time-basis and continuous-acquisition identity; set deliberately |
| `channels` | `()` | Ordered unique names; auto-generated if omitted |
| `valid` | `None` or bool `[N]` | Sample-validity mask; nonfinite sample values are also invalid |
| `rpm` | `None`, scalar or `[N]` | Externally measured rev/min; block value overrides config |
| `sequence` | `None` or nonnegative integer | Consecutive acquisition packet identity |
| `metadata` | `{}` | Actual asset/sensor/condition/calibration/frame provenance; propagated under `result.metadata['source']` |

| `AnalysisConfig` fields (defaults) | Purpose / unit |
|---|---|
| `sample_rate_hz=12000`, `channels=1`, `channel=0` | Hz; total channels and zero-based channel selected for scalar spectra/metrics; feature vector uses all channels |
| `window_seconds=1`, `hop_seconds=0.25` | Window and step seconds; 256..2,000,000 samples/window; hop >=0.02 s and <= window |
| `unit='unknown'`, `input_representation='physical'` | Output acceleration unit `g` / `m/s^2` or unknown; representation `physical` / `volts` |
| `sensitivity_mv_per_g=None`, `conditioner_gain=1`, `bias_voltage_v=0`, `calibration_id=''` | Voltage -> g calibration: `(V-bias)/(sensitivity/1000*gain)`; sensitivity list of 1 or C positive values; calibrated output unit required for voltage mode |
| `rpm=None`, `bearing_id=None`, `condition`, `load=None` | Nominal rev/min, host bearing lookup ID, operating-condition name and optional load metadata |
| `window='hann'` | FFT window; also hamming / boxcar |
| `envelope_low_hz=500`, `envelope_high_hz=5000` | Carrier band Hz, strictly below Nyquist; configure lower bands for low-rate data |
| `velocity_low_hz=10`, `velocity_high_hz=1000` | Acceleration integration band Hz; output mm/s RMS |
| `peak_tolerance_ratio=0.03` | Relative marker peak-search tolerance, also bounded by frequency resolution |
| `warning_score=3`, `danger_score=6`, `persistence_seconds=2`, `release_seconds=3` | Optional service policy settings; direct `AlarmStage` has its own explicit arguments and must be attached |
| `rms_warning=None`, `rms_danger=None`, `clip_abs=None` | Optional service RMS thresholds and absolute clipping level, in configured unit; clip check also used by direct core |
| `model_enabled=False`, `order_tracking=True` | Optional service classifier switch; RPM-trace angle resampling switch. Models are attached explicitly in direct API |

### Output contract: what downstream code receives

| `AnalysisResult` field / payload | Meaning / unit |
|---|---|
| `start_time_s`, `end_time_s`, `clock_id`, `episode_id`, `channels` | Window identity; end time is exclusive; seconds in declared clock |
| `valid` / `payload['quality']['flags']` | Numeric-window quality, **not a healthy/fault label**; invalid windows omit numeric DSP results |
| `metrics` | AC `rms`, `peak`, `peak_to_peak`, `mean`, `rms_raw` in configured unit; `crest_factor`, Pearson `kurtosis`, `skewness` dimensionless; `velocity_rms_mm_s`; `envelope_rms`; `band_power` in unit² |
| `payload['spectrum']`, `['psd']`, `['envelope_spectrum']` | `{x,y}` arrays: x Hz; y amplitude, unit²/Hz, or envelope amplitude respectively |
| `payload['waveform']` | `{x,y}` with relative seconds and calibrated samples for selected channel |
| `payload['spectrogram']` | One window's frequency grid and log-PSD row (`frequencies`, `db`); **host stacks rows over time** to form a spectrogram |
| `payload['rpm']`, `['rpm_variation_ratio']`, `['frequency_resolution_hz']`, `['order_spectrum']` | Rev/min, dimensionless speed variation, Hz bin spacing; optional order axis (cycles/revolution) with resampling mode |
| `payload['bearing_markers']`, `['rotation_markers']`, `['diagnosis']` | Predicted/observed Hz, peak contrast and nonexclusive candidate evidence; not confirmed faults |
| `features`, `feature_names` | Full feature vector and exact ordered names; keep together with configuration/profile schema |
| `payload[stage_name]` | Stage-defined output; baseline score, alarm level, diagnostic dict or custom-rule assessment |
| `metadata['measurement']`, `metadata['source']` | Effective configuration and original host metadata |
| `to_dict(include_features=True)` | JSON-compatible `vibration.analysis.v1` dictionary; `False` removes internal underscore-prefixed feature fields |

Stage order is insertion order. Later stages can read earlier named payloads.
Raw-window stages receive calibrated full arrays, not plot-decimated arrays.
Stage/sink exceptions propagate to the caller; sinks run synchronously after stages.
Use separate analyzer instances for different assets. A diagnostic `hold` or a missing
score must not be converted to `normal` or zero risk by the downstream system.

For every public constructor/method signature and dataclass field, see the
[complete source-derived API reference](docs/API_REFERENCE.md). The tables above are
the integration map; the [user guide](docs/USER_GUIDE.md) explains operating sequences.

## A complete first calculation

This generated waveform verifies the API; it is not a measured fault example.

```python
import numpy as np
from rotorvibe import AnalysisConfig, SignalBlock, VibrationAnalyzer

fs = 12000
t = np.arange(fs) / fs
samples = 0.20 * np.sin(2 * np.pi * 20 * t)

analyzer = VibrationAnalyzer(AnalysisConfig(
    sample_rate_hz=fs, channels=1, unit="m/s^2",
    window_seconds=1, hop_seconds=0.25, rpm=1200,
))
result = analyzer.analyze(SignalBlock(
    samples, fs, unit="m/s^2", rpm=1200,
    channels=("drive_radial",), clock_id="daq_elapsed", episode_id="run-001",
    metadata={"asset_id": "motor-01", "condition_id": "rated_load"},
))
print(result.valid, result.metrics)
serializable = result.to_dict(include_features=False)
```

`samples` may also be an `N × C` array. A one-dimensional input represents one
channel. Supply the physical unit, channel ordering, time basis and actual asset
identity; a numeric array alone cannot establish sensor calibration or installation.

## Connect modules directly

The host controls acquisition, scheduling, storage and decisions. An analyzer instance
owns one stream; application callbacks receive the results synchronously.

```python
import numpy as np
from rotorvibe import AnalysisConfig, SignalBlock, VibrationAnalyzer
from rotorvibe import BearingGeometry, BearingMap

received = []  # Replace with your own event bus / storage callback.

class MyCalculation:
    def __call__(self, result):
        return {"quality_accepted": result.valid}

fs = 12000
samples = 0.20 * np.sin(2 * np.pi * 20 * np.arange(fs) / fs)
analyzer = VibrationAnalyzer(
    AnalysisConfig(sample_rate_hz=fs, unit="m/s^2", rpm=1200,
                   bearing_id="demo", window_seconds=1),
    bearing_provider=BearingMap({"demo": BearingGeometry(8, 7.0, 35.0)}),
    stages={"host_calculation": MyCalculation()},
    sinks=(received.append,),
)
result = analyzer.analyze(SignalBlock(
    samples, fs, unit="m/s^2", rpm=1200, channels=("drive_radial",),
    clock_id="daq_elapsed", episode_id="run-001",
    metadata={"asset_id": "motor-01", "condition_id": "rated_load"},
))
assert received[0] is result
assert result.payload["host_calculation"]["quality_accepted"] is True
print(result.metrics["rms"], result.payload["host_calculation"])
```

For streaming input, call `analyzer.push(block)` and consume the returned list of
completed windows. Gaps, sequence changes, operating identity and clock continuity
matter. `analyze(block)` handles one complete block directly. Raw-window stages can
implement `analyze_window(result, readonly_values)` to use calibrated samples instead
of a display-decimated waveform. See [composition examples](examples/python_composition.py)
and the [module catalog](docs/MODULE_CATALOG.md).

## What is implemented

| Area | Available behavior | Required evidence or boundary |
|---|---|---|
| Waveform and spectra | AC RMS, peak, crest, Pearson kurtosis, FFT amplitude, PSD, spectrogram and envelope views | Physical units, sample rate and usable sensor bandwidth |
| Bearing markers | BPFO, BPFI, FTF, BSF and 2BSF from explicit geometry or injected providers | RPM and validated bearing dimensions; ideal kinematics, no slip model |
| Normal reference | Robust feature center/scale, scope checks, relative scores and time-based alarm state | Confirmed normal records separated from threshold calibration and testing |
| Fault candidates | Gaussian baseline, normal-first diagnostics, RPM-conditioned reference bank and morphology head | Experimental; asset, channel, band, duration and speed contracts apply |
| Rule evaluation | Quantity/unit/frame contracts and caller-provided limits | **No ISO/KS limit tables are distributed**; obtain and assess rules lawfully |
| Optional service | Local HTTP, UDP ingest, SSE, SQLite history and offline UI | Start explicitly; configure authentication before non-local exposure |

### Bearing-frequency example

```python
from rotorvibe import BearingGeometry

# Illustrative geometry in a common diameter unit, not a vendor catalog entry.
bearing = BearingGeometry(rolling_elements=8, rolling_diameter=7.0,
                          pitch_diameter=35.0, contact_angle_deg=0)
print(bearing.frequencies(1200))
```

### Diagnostic states are different outcomes

`normal` means the applicable normal gate accepted the observation. `hold` means
there is no supported decision, not that the machine is healthy. `anomaly_unknown`
means deviation is detected but a trained fault type is not supported.
`fault_candidate` is a hypothesis within the model's recorded scope, not confirmation
of a physical root cause. Distances and similarity weights are not calibrated fault
probabilities. Keep `operational_use=False` for the research classifiers.

The morphology head must follow an anomaly gate. A standalone call to
`FaultDiscriminator` assumes that anomaly screening has already happened; it cannot
identify a healthy class. [A two-stage composition](examples/fault_discrimination_composition.py)
shows the ordering. No downloaded profile is silently enabled.

## Evidence: retain the failures

The following experiments have different datasets and protocols. Their percentages
must not be merged into a single product accuracy score.

| Historical experiment | Recording-level separation | Observed result | Interpretation |
|---|---|---|---|
| Brito Gaussian comparison | Fixed four-recording final split; subsequently exposed | 63.69% overall; healthy recording 0/420 | Historical reproduction, not field qualification |
| CrossSpeed supported-speed check | 24 held acquisitions after rig-specific fitting | 93.74% of 479 windows | Matched apparatus and own normal reference |
| CrossSpeed 1200 RPM transfer | 59 acquisitions / 1178 windows | 11.04%; all 399 healthy windows anomalous | Cross-speed transfer failed |
| UOS 6204 conditioned model | Eight new source files / 320 windows | 51.88% overall; fault type 48.21% | Better normal reference handling; weak type coverage |
| UOS morphology improvement | Seven new 8 kHz fault files / 560 windows | 559/560 = 99.82%; old comparator 49.11% on the same new files | Same apparatus, bearing and severities; no new healthy test |
| New UOS 30204 bearing domain | Six healthy + seven fault files; all test-only | Strict API: all hold. Offline scope-bypassed stress: healthy 240/240 anomalous, types 124/280 | Generalization failed even after scope bypass |
| Independent UFRJ ABVT rig | Fifteen healthy + fifteen fault files; all test-only | Strict API: all hold. Two predeclared amplitude assumptions: types 0/30 | Unit unresolved; no physical FPR qualification |

In the latest unadapted evaluation, 580 windows all held in the real API. Zero alerts
with zero accepted healthy observations does **not** demonstrate a zero false-alarm
rate. The offline stress route is explicitly separate from the product API and must
not be used to hide an asset mismatch. UFRJ native CSV units are not explicit in its
official page; both fixed amplitude assumptions are reported without choosing one.

The private research workspace passed 547 checks, including its licensed standards
route. That is a historical count, **not the public release's test count**. Public
release checks are recorded separately in `research/public_verification.json`; the
normative table tests are excluded and replaced with synthetic caller-rule checks.
Read [the latest external assessment](docs/EXTERNAL_BLIND_VALIDATION.rst) and
[the evidence index](research/README.md) before quoting any performance figure.

## Standards and copyright boundary

The private development project investigated ten supplied KS/ISO editions. This
public release deliberately excludes the PDFs, transcriptions, threshold lookup
tables, normative selectors and corresponding table fixtures. `vibration.iso` now
accepts an explicit `custom_rule`; it does not select an ISO machine category for you.
The example rules use invented demonstration numbers, not published standard limits.

Independent algorithm implementations, our explanatory comments and our experiment
results are released under MIT. The original external measurements, papers, vendor
catalogs and standards retain their own terms. Citation identifiers and legal license
text are intentionally preserved; third-party substantive prose and figures are not
repackaged. See [the rights inventory](docs/SOURCES_AND_RIGHTS.md).

## Optional dashboard

```console
rotorvibe-monitor --host 127.0.0.1 --port 8765
```

The service does not simulate measured validation data when no dataset is present.
Use your own live waveform input or explicitly acquired research files. Python hosts
that construct `Application` must call `close()` to stop workers and sockets.
`VIBRATION_RUNTIME_HOME` selects a writable state directory;
`VIBRATION_PROJECT_HOME` locates separately acquired datasets. Do not point these
variables at confidential data when hosting an externally reachable service.

## Published artifacts and documentation versions

Version **0.1.0a1** is public on [PyPI](https://pypi.org/project/rotorvibe/0.1.0a1/),
[GitHub Releases](https://github.com/lyullee/rotorvibe/releases/tag/v0.1.0a1) and
[Zenodo](https://doi.org/10.5281/zenodo.23937890). All three distribute the same
SHA-256-verified wheel and source archive. The GitHub `main` README includes subsequent
documentation clarifications; immutable 0.1.0a1 archives and their embedded PyPI README
remain the original release snapshot. No numerical model or training data changed.

## Reproduce, continue, cite

1. Start with synthetic core checks; they need no PDFs or raw data.
2. Use the source inventory to acquire external files under their own terms.
3. Distinguish historical replay from a new blind test: every previously opened
   recording is listed as exposed and cannot become a fresh holdout again.
4. Freeze model, preprocessing, thresholds, metadata mapping and record membership
   before opening the next holdout. Audit by original acquisition, not random windows.
5. Keep independent normal reference, calibration and final-test records. Record
   unsupported coverage and false negatives as well as correct classifications.

[Continuation instructions](docs/CONTINUATION.md) identify exact commands, preserved
artifacts, unavailable private components, model hashes and next validation needs.
The archive DOI is [10.5281/zenodo.23937890](https://doi.org/10.5281/zenodo.23937890);
use `CITATION.cff` for software citation. A DOI identifies an archived release; it
does not certify a diagnostic model.

Copyright © 2026 Ugwiyeon Lee. Original software: [MIT](LICENSE).
