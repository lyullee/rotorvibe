# User guide

This guide describes the public release. Historical reports may refer to private
standards-table implementations that are intentionally absent here.

## 1. Installation and environment ownership

Use Python 3.11 or newer. This source is the 0.1.0a4 candidate; install it with
`python -m pip install .`. PyPI 0.1.0a1 remains the earlier archived version. For an editable
checkout with `python -m pip install -e ".[verification]"`. NumPy and SciPy are numerical
dependencies, not bundled source copies. The optional verification extra provides
build and publication checks; no trained model or measurement dataset is downloaded
as part of package installation.

Both `rotorvibe` and the compatibility namespace `vibration` resolve the same core
classes. Deeper modules remain under `vibration`, for example `vibration.adapters`.
Use `python -m pip show rotorvibe` to check the installed distribution, and
`import rotorvibe; print(rotorvibe.__version__)` for its facade version.

The synchronous NumPy core does not construct a database, web server or background
worker. Importing an optional service is a separate application concern. A service
instance owns its workers and must be closed. Do not share one stream buffer between
assets; create one analyzer per acquisition stream and serialize concurrent calls.

## 2. Required signal contract

`SignalBlock` takes one-dimensional samples or an `N × C` matrix. It copies the input,
checks finite numeric values and stores read-only data. Boolean validity flags may
describe missing or rejected samples. Invalid samples are not silently replaced by a
healthy observation. Channel names must be unique and match the matrix columns.

Supply these fields deliberately:

| Field | Meaning | Frequent mistake |
|---|---|---|
| `sample_rate_hz` | Actual sampling frequency | Using RPM or a display refresh rate |
| `unit` | Physical signal unit, or the configured voltage representation | Calling voltage acceleration without sensitivity |
| `start_time_s` | Start on the declared clock | Mixing wall time and device elapsed time |
| `clock_id` | Identity of that time basis | Joining two devices' unrelated clocks |
| `episode_id` | Continuous acquisition episode | Continuing a buffer across restarts |
| `channels` | Ordered sensor/axis identity | Reordering columns after training |
| `rpm` | Scalar or per-sample externally supplied speed | Inferring speed from whichever fault peak wins |
| `metadata` | Asset, condition and installation provenance | Relabeling a new rig to bypass model scope |
| `sequence` | Optional acquisition sequence identity | Treating a dropped packet as continuous data |

Set `AnalysisConfig.input_representation` and sensor sensitivity explicitly for voltage
conversion. The configured output unit and the block's input unit must agree with
that representation. An `unknown` unit can preserve an uncalibrated research trace;
it cannot justify a physical velocity threshold or standards comparison.

The software cannot verify installation quality, sensor orientation, calibration
certificates, analogue anti-alias filters or a provider's fault labeling. Retain those
facts as acquisition evidence in the host system.

## 3. Direct block analysis versus a live stream

`analyze(block)` computes a complete block without waiting for a future window.
`push(block)` buffers samples and emits every completed configured window. Set
`window_seconds` for resolution and `hop_seconds` for update spacing. A smaller hop
creates overlapping observations, not additional independent experiments.

Preserve continuous timestamps and sequence numbers between chunks. The core
rejects or resets incompatible continuity and identity rather than joining disjoint
assets into a synthetic waveform. `reset()` explicitly discards buffered history.
Changing the analyzer's returned config object does not mutate the active config;
construct a new analyzer for a new configuration.

Results contain start/end times, clock, episode, channel layout, a validity flag,
the calculation payload and measurement/source metadata. The end time is exclusive.
Core arrays are kept native for Python use; `to_dict()` serializes NumPy values for
JSON. `include_features=False` omits internal feature vectors from that export.

Frequency resolution is set by actual observation duration, not zero-filled display
points. A short window cannot separate closely spaced physical components merely
because its chart has more plotted samples.

## 4. Stage and sink interfaces

Stages are an ordered mapping from output name to callable object. A simple stage
implements `__call__(result)`. A waveform-aware stage additionally implements
`analyze_window(result, readonly_values)`; the core selects that hook and passes the
calibrated raw window. Stage outputs become named payload fields and later stages can
read them. Do not use reserved DSP field names for custom stages.

Sinks are callbacks invoked after stages complete. They may write to an application
event bus or storage layer. Stage/sink exceptions propagate: the core does not turn a
failed downstream calculation into a normal machine result. Own retries and idempotent
storage at the host boundary. Use `(asset, clock, episode, start, end, configuration)`
as part of a stable observation identity rather than a UI row number.

`vibration.ports` documents structural interfaces for bearing providers, stages,
waveform stages and sinks. `vibration.adapters.to_process_batch` and
`condition_evidence` preserve source and unit context for compatible external Python
objects. External modules are supplied by the application; no other repository is
vendored or automatically installed.

## 5. Spectra, units and bearing geometry

FFT amplitude and PSD are distinct outputs. The FFT uses window coherent-gain
normalization and one-sided endpoint handling; PSD uses window energy normalization.
RMS is AC RMS after demeaning, and kurtosis uses the Pearson convention. A constant
or clipped channel is a quality issue, not an especially healthy rotating machine.

Velocity integration removes DC and uses the configured frequency band. Integration
of an acceleration trace is sensitive to low-frequency drift and instrument response.
Never compare values calculated in different bands as though they were identical
measurements. See `docs/ALGORITHMS.md` for the numerical assumptions.

`BearingGeometry` needs rolling-element count, rolling diameter, pitch diameter and
contact angle. Both diameters use the same unit. The class checks elementary packing
consistency; it does not reconstruct proprietary bearing internals from a model name.
`BearingMap` and a host-provided `frequencies(id, rpm)` provider allow replaceable
catalogs. No vendor geometry catalog is shipped in the public package.

## 6. Normal references and alarms

`BaselineStage` collects a user-declared normal period or accepts an explicitly loaded
profile. Starting collection is an affirmative choice by the host. It computes a
robust center/scale and records the scope/configuration. It does not determine that
the underlying machine was healthy. Overlapping collection windows remain correlated.

Reserve different original acquisitions for normal fitting, threshold calibration and
final evaluation. If one long file supplies all three roles, a high window count is
not strong independent validation. `AlarmStage` uses observation time and separate
persistence/release behavior. A window-level anomaly rate is not the same as a count
of sustained operational alarm events per hour.

Normal scores are relative distances to a recorded reference. Unit, installation,
speed and load changes can move normal operation far from that center. Do not fix a
failed blind test by updating the reference and continue calling that test unused.

## 7. Experimental fault models

`GaussianClassifier` provides a standardized diagonal Gaussian baseline. The corrected
algorithm includes the class-dependent variance normalization. Its outputs still
require the recorded feature contract, and its historical normal failures remain in
the research record.

`TwoStageDiagnostic` first screens normal deviations, then considers known fault
prototypes. `ConditionedDiagnostic` uses nominal-RPM normal references and ordinarily
refuses unsupported speeds instead of extrapolating. Optional interpolation is a
declared research setting; enabling it does not prove behavior through a resonance.

`fault_features` extracts morphology features from exactly two seconds of a single
channel. `FaultDiscriminator` is a conditional fault-type head, not a four-class
healthy/fault model. `FaultDiscriminationStage` requires an earlier gate whose
`anomaly` field is exactly `True`. Check scope and quality before interpreting any
candidate. A missing RPM or varying speed may require an angle-domain method not
qualified by this fixed-speed profile.

Profiles are normal Python dictionaries suitable for JSON serialization. Keep the
algorithm identifier, feature names, selected indices, source grouping, reference
speeds, scope and validation evidence together. Loading an old profile under a changed
feature definition is not a supported migration. Trained UOS profiles are not shipped
as ready-to-deploy field models; create your own validated normal/diagnostic evidence.

## 8. User-provided engineering criteria

The public `vibration.iso` compatibility namespace contains typed measurement
contracts, waveform measurement helpers and a generic custom-rule evaluator. It has
**zero built-in normative profiles**. It is not equivalent to the private ten-edition
research implementation.

```python
from vibration.iso import MachineContext, Measurement, Rule, evaluate

context = MachineContext("demo", "motor", operating_state="steady",
                         condition_id="rated", location="housing")
measurement = Measurement(2.0, "velocity", "mm/s", "rms", "housing",
                          (12.0, 850.0), 2.0, "radial", "DE",
                          calibrated=True, acquisition_verified=True)
rule = Rule("example-only", "invented", "velocity", "rms", ("housing",),
            (1.1, 2.2, 3.3), (12.0, 850.0), 0,
            "invented demonstration values")
print(evaluate("example-only", context, measurement, custom_rule=rule))
```

Those limits and the band are invented examples. Obtain applicable real criteria
under appropriate rights, check edition/class/installation applicability independently
and supply a reviewed rule. Missing calibration, mismatched statistic/frame/band or
an absent rule produces no assessment zone. No automatic trip output is issued.

## 9. Optional local service and troubleshooting

Start `rotorvibe-monitor --host 127.0.0.1 --port 8765` only when the dashboard or
network ingest is required. The service includes optional HTTP/SSE/UDP and SQLite
history. Do not confuse this convenience interface with the direct synchronous API.
When constructed from Python, `Application.close()` releases worker/socket resources.

Use a writable `VIBRATION_RUNTIME_HOME` for application state. Use a separate
`VIBRATION_PROJECT_HOME` for externally acquired datasets. Do not write runtime DBs
inside installed site-packages. A non-loopback binding needs the service's configured
authentication; retain the origin/body-size/unit checks in the shipped service.

| Symptom | Check |
|---|---|
| Import works but no public dataset menu | Raw data are intentionally not installed |
| Every new-machine decision is `hold` | Scope/reference may be absent; this is not healthy status |
| Low-rate configuration fails | Envelope/velocity bands must lie below Nyquist |
| Invalid or flat waveform | Check real samples, sensor clipping and validity flags |
| Spectrum moves after RPM change | Reassess physical operating domain; do not relabel metadata |
| Historical audit fails on public checkout | Historical hashes refer to the private frozen snapshot; see release delta |
| Installed `vibration` resolves unexpectedly | Inspect package paths and avoid conflicting distributions using that namespace |

## 10. Verification and reporting

Run portable tests without external data first. Reproduce scientific results only
with the exact source versions, original-file membership, frozen model and code from
that experiment. Report correct counts and denominators, abstentions, normal
acceptance, fault detection and fault-type accuracy separately. A classifier that
rejects everything has no demonstrated working-domain false-alarm rate.

Follow `docs/CONTINUATION.md` before starting new data collection. Raw holdouts already
opened in this project are now exposed. Collect a genuinely new acquisition/session
for the next final test, and freeze the evaluation protocol before reading it.

## 11. P0 migration

See the README P0 input/output table for the common `DecisionStage` adapter,
`normalize_decision` schema, `AlarmStage.expected_score_name`, stricter fault-profile
loading and finite-distance errors. Existing raw producer outputs remain unchanged.
Add the adapter after its producer; a missing/misordered producer returns hold.
The adapter never invents probabilities, scores for unscored heads or new thresholds.
Held/invalid outputs do not recover a previously raised alarm. Old malformed profiles
with blank scope or missing original-acquisition metadata must be repaired from actual
provenance, not filled with invented asset identities.

## 12. P1 monitoring contracts

See [P1_GUIDE.md](P1_GUIDE.md) for acquisition evidence, recording-disjoint normal
references, angle-domain models, bounded processing, lifecycle and prospective
validation access. These are additive research APIs; measured cross-rig qualification
and a strict real-time service guarantee remain unestablished.

## P2 composition and compatibility

See [P2_GUIDE.md](P2_GUIDE.md) for isolated results, optional real-package bridge,
profile envelopes, bounded spectrogram history, reviewed rule providers and explicit
experimental life APIs. See [P2_VERIFICATION.md](P2_VERIFICATION.md) for executed checks.
