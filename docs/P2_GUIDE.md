# P2 composition guide — 0.1.0a4 alpha

P2 provides reusable Python contracts. It does not qualify a diagnostic model for
a new rig, supply protected standard tables or establish field remaining life.
README tables list each purpose/input/output; API_REFERENCE.md lists exact signatures.

## 1. Results and consumers

`AnalysisResult.detached()` returns a new result with independent nested payload,
metadata and NumPy buffers. The frozen dataclass still prevents field assignment;
the snapshot's containers may be edited locally. Measured RPM trace buffers remain
read-only. This is a copy policy, not a claim of universal deep immutability.

`VibrationAnalyzer.analyze/push` now applies that policy automatically:

1. Each stage receives its own copy of the result accumulated so far.
2. Its returned output is copied before insertion under the stage name.
3. A later stage sees earlier returned outputs, but cannot modify their originals.
4. Every sink receives a separate completed copy, independent of the returned result.
5. Raw-window hooks receive calibrated samples with immutable byte backing.

Exceptions still propagate. A sink that already performed an external side effect
is not rolled back if a later sink fails. Sinks must return promptly; synchronous
copies and callbacks cost processing time and memory. No global scheduler is added.

Migration: `sink_result is returned_result` is intentionally false. Move intended
cross-component transformations into explicit stage return values. A sink's local
edits are never an implicit message to the next sink. Host callbacks that communicate
through their own globals/shared state remain the host's responsibility.

`condition_evidence(result, asset_id=...)` also detaches nested data. It exports a
condition observation, not a failure probability, maintenance authority or trip.

## 2. Real optional process bridge

The supported distribution is **process-monitoring-toolkit 0.1.0**, inspected at
Git commit `79b4cf52a0acd0d0cbd3addbe82c3d98d6385e5a`. Its source stays outside this
repository. `process_adapter_info()` reads distribution metadata without importing
the optional package. A missing/different version causes bridge calls to raise
`ImportError`; base RotorVibe imports and analysis continue to work.

The queried package index did not provide this version. Install the pinned source
before resolving the local `process` extra:

```console
python -m pip install "git+https://github.com/lyullee/process-monitoring-toolkit.git@79b4cf52a0acd0d0cbd3addbe82c3d98d6385e5a"
python -m pip install ".[process]"
python examples/process_bridge.py
```

Version equality is a declared compatibility boundary, not source authenticity.
The pinned commit and the actual installed source comparison are recorded in
`research/p2_external_contract.json`. Requalify another version explicitly.

### Input adapter

`from_process_batch(batch, sample_rate_hz=..., clock_id=..., rpm=None)` requires
the actual supported `SignalBatch`, not a fabricated duck type. Its values are
N×C raw waveforms, times are uniformly spaced elapsed seconds, channels have one
common explicit unit, and episode/mode vectors each contain one identity. Split
gaps and differing episodes/modes upstream. Unit and sampling-rate validation then
follows `SignalBlock`/`AnalysisConfig`.

`rpm` is independently supplied rev/min: a scalar nominal value or N measured
samples. This adapter never derives RPM from the vibration or batch time axis.
Validity masks reduce across channels per sample. An upstream `metadata.clock_id`,
if present, must match the argument. `metadata.vibration_source` carries asset and
acquisition declarations into the result's source metadata; the remaining upstream
metadata is preserved separately. Mixed modes are rejected rather than averaged.
The single mode is copied to operating_mode and exported back to batch modes;
conflicting declarations are rejected. A mode change between packets resets the
stream buffer so samples from different modes never form one window.

### Output adapter

`to_process_batch(results)` accepts a nonempty ordered collection with at least one
valid feature vector. Clock, channel layout, measurement signature, source identity
and valid feature schemas must agree. End timestamps must strictly increase.
Changing an installation/condition requires a separate batch.

Output values are W×(7C) fixed `vibration.features.v2` features, not raw spectra.
Times are exclusive window ends; episode strings have an explicit integer mapping
in metadata. Invalid windows contain NaN with all feature validity flags false.
Valid vectors must be finite. Features are dimensionless logs/ratios; metadata
preserves the physical unit used as the log-RMS reference. Masked NaN is part of
the external batch contract and must not be serialized as a bare strict JSON number.

Feature rows carry `time_reference='exclusive_window_end'` and cannot be imported
back as raw waveforms. The working bidirectional example connects the exported
feature batch to the real package's `Monitor`, features and detector. It reuses
synthetic data to demonstrate connections; it is not an independent accuracy test.

## 3. Common profile envelopes

`create_profile(payload, *, profile_id, kind, algorithm, feature_schema,
preprocessing, training_groups, calibration_history, scope)` returns an inert finite
JSON mapping with schema `vibration.profile-envelope.v1`. It copies inputs.

| Parameter | Type / requirement |
| --- | --- |
| `payload` | Nonempty native model mapping; numerical contents still belong to its native loader |
| `profile_id` | Nonempty revision ID; registry never silently replaces it |
| `kind` | `normal_reference`, `fault_model`, `preprocessing`, `life_reference` or `user_rule` |
| `algorithm`, `feature_schema` | Nonempty explicit identifiers; must agree with same-named native fields |
| `preprocessing` | Nonempty finite JSON description of units, sampling/window/filter/angle choices; all relevant choices must be supplied by host |
| `training_groups` | Distinct original acquisition/life-group strings; trained model kinds require at least one; nontrained rule/preprocessing kinds may use an empty list |
| `calibration_history` | List of `{calibration_id, group_id, reviewed_on, method}`; strings, ISO date, unique calibration IDs, groups disjoint from fit groups. Empty list explicitly records no calibration |
| `scope` | Nonempty exact application identity mapping; where native payload contains scope it must agree |

The envelope stores SHA-256 for preprocessing, payload and the entire envelope.
Canonical JSON sorts mapping keys, retains array order, converts NumPy arrays to
lists and rejects NaN/infinity. Hashes detect changes relative to the supplied
digest; an attacker can recalculate hashes. They do not authenticate an author.

`validate_profile(envelope, expected_contract=None, expected_scope=None)` checks
schema, integrity and declared provenance. If supplied, expected contract must
contain exactly algorithm, feature_schema and preprocessing_sha256. Compatibility
is exact rather than a permissive subset. Native `fit_groups/groups` and
`calibration_groups`, when present, must match the envelope's original groups.

`ProfileRegistry.register(envelope)` returns its digest. `get` requires exact
expected contract/scope and returns a detached envelope. `load` additionally
requires a callable native loader and passes it the detached payload. Use
`NormalReferenceBank([payload])`, `FaultDiscriminator(payload)` or the relevant
existing loader; envelope validation does not replace numerical/scope checks.
`remove` is explicit; `list` returns detached summaries. There is no implicit
file discovery, pickle execution, retraining or promotion to operational use.

Existing native profiles remain directly loadable. Wrapping does not convert a
fixed-speed model into an angle model or make a new installation applicable.
RPM/load ranges retained inside the payload continue to be enforced by its loader.

## 4. Spectrogram history

`SpectrogramAccumulator(*, hop_seconds, max_frames=512, max_age_seconds=600,
max_frequencies=4096)` owns its bounded history. Durations must be finite positive
seconds, dimensions positive integers ≤100000, and their product ≤8 million cells.
Call `update(result)` once per time-ordered window. Configure hop to match analyzer
hop. Duplicate/backwards starts and hops shorter than configured raise `ValueError`.

`update` returns a small summary: frame count, current segment, optional gap,
validity and evicted count. `snapshot()` returns detached Hz centers/bin edges,
input unit, dB reference and ordered rows containing window start/exclusive end,
validity, dB values or `None`, segment ID and gap-before interval. Gap intervals
refer to expected window-start cadence, not necessarily disjoint waveform time.
Overlapping windows remain explicitly overlapping.

Counts and elapsed end-time retention both evict old rows. Invalid observations
remain explicit null rows. Missing intervals never become zero/normal spectra.
Clock, episode, measurement settings, asset, acquisition/installation, load unit
or condition changes start a fresh identity and clear history. Frequency grid,
representation or unit changes within a declared identity raise an error.

The DSP row uses 384 frequency centers. Each native FFT PSD bin contributes its
discrete power `PSD*df` to the display frequency bucket; dividing by bucket width
produces mean density. The dB floor is 1e-20 input-unit²/Hz. Integrated power is
preserved before flooring; narrow tones between display centers are retained.
This replaces older point interpolation that could miss a tone entirely.

These rows represent the configured selected channel, not all channels or a
lossless STFT. Use full native PSD for quantitative integration/model inputs.
Legacy interpolated rows may be accumulated with an explicit legacy representation;
they cannot be silently mixed with new binned rows. `SpectrogramStage(accumulator)`
adds only the update summary; full history remains outside each result. Its
`reset_state` and accumulator `clear()` remove history. Objects are host-owned and
require external synchronization if used concurrently.

## 5. Reviewed rule providers

`RuleDocument(rule, edition, source_uri, source_sha256, reviewed_by, reviewed_on,
context_scope)` contains one caller-owned `Rule`, pinned edition/source hash and
ISO review date. Context scope must explicitly include asset_id, machine,
condition_id, location and operating_state; extra fields must be MachineContext
fields with concrete valid values. Source hashes document claimed provenance;
this API does not download, license or authenticate the source.

`RuleProvider.resolve(standard, context)` is a structural port returning one
document or `None`. `MemoryRuleProvider` registers copies and selects exact scoped
matches; duplicate document identities and ambiguous matches are errors. Different
editions require deliberate provider selection, never implicit newest selection.

`evaluate_with_provider(standard, context, measurement, provider)` preserves normal
quantity/unit/statistic/frame/band/duration/calibration checks, then returns the
per-point result plus edition/source/review/document hashes. Missing scope returns
indeterminate. A custom provider returning a wrong identifier is rejected.

`IsoStage(..., rule_provider=...)` is mutually exclusive with `custom_rule`. For
the provider route, raw source metadata must match context asset_id, condition_id,
location and operating_state; provided operating RPM must match the result, and
large within-window speed variation holds. Raw measurement requires one explicit
reference frame and one channel. Existing explicit custom-rule calls remain valid.
The standalone example uses invented thresholds, not extracted standard numbers.

Rules evaluate supplied points only. No normative tables, application selectors,
whole-machine certification or automatic trip authority are distributed.

## 6. Experimental reference life

The numerical similarity routine now lives in `vibration.experimental.life`.
`ReferenceLifeEstimator(catalog, experimental_enabled=False)` and compatibility
`vibration.models.LifeEstimator` default disabled. The engine therefore does not
silently estimate reference life. `LifeStage(..., experimental_enabled=False)` is
also disabled by default; explicitly enable both estimator and stage for experiments.

The legacy experiment uses accelerated PRONOSTIA complete-life log-RMS shape
matching at the same nominal RPM, with its historical 10-second observation
cadence. It excludes the same bearing, rejects insufficient/invalid histories,
requires two references and holds before observable degradation. The result is
time to benchmark endpoint under this construction. Reference spread is not a
validated statistical prediction interval. Data in the supplied prefix must have
been available by the current observation cutoff; the host must not insert future
observations. Outputs explicitly deny field qualification and operational use.

### Complete and censored evaluation data

`LifeHistory(record_id, group_id, condition, times_s, rms, event_observed,
terminal_time_s, role)` defines a full life/follow-up record:

- Condition requires RPM, nonnegative load, load_unit, calibrated `g`/`m/s^2` RMS
  unit and installation_id. RMS is nonnegative finite time×channel data (1–16
  channels), timestamps increasing nonnegative elapsed seconds.
- `terminal_time_s` is observed failure/endpoint time if event_observed is true;
  otherwise it is known survival follow-up. It cannot precede the final reading.
- Role is life_fit, life_calibration or final_test; entire original life groups
  stay together. A censored endpoint is never treated as an observed failure.

`evaluate_life_predictions(histories, predictions, training_groups=...)` accepts
final-test lives only, disjoint from all listed fit/calibration groups. Predictions
contain record_id, observed_until_s, remaining_seconds, lower_seconds and
upper_seconds. Cutoffs must be actual observation times before terminal follow-up;
all values finite nonnegative, lower≤point≤upper; duplicate cutoffs are rejected.

For complete lives it reports MAE/RMSE and empirical interval inclusion, weighting
each original life equally. For censored lives it reports only whether the upper
interval can accommodate known survival. All-censored exact-error metrics are
`None`. This is not a survival-model score, calibrated confidence interval, or
proof that a model used no future information. Predict using only each cutoff
prefix, freeze the pipeline/split, then pass future labels only to evaluation.

Physical remaining-life error and interval calibration still need properly scoped
complete and censored operating lives with independent original groups. Existing
project causality checks do not establish field RUL accuracy. P1's sealed twin-spool
archives are fault-condition data and have not been repurposed as run-to-failure
or censored-life evidence.
