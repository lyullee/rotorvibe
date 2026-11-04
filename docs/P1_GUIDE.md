# P1 operating guide — 0.1.0a3 candidate

## 1. Acquisition contract

Attach AcquisitionInfo.to_dict() under SignalBlock.metadata['acquisition'], and use
the actual top-level asset_id, condition_id and load_unit. AnalysisConfig.load is a
numeric value in that declared load unit; rpm_range is rev/min, bands/sample rate
are Hz, input/output acceleration is g or m/s^2. Declare channel names and one axis
per channel in order, frame, sensor/installation/calibration IDs, measured_on and
calibration_due ISO dates, sensor band, anti-alias cutoff and RPM provenance.

Boolean calibration/mounting/anti-alias flags must reflect reviewed evidence. This
software checks declarations against settings; it cannot certify the physical setup.
Nominal controller/operator speed is allowed for a fixed-speed reference, never as
a measured per-sample trace. Actual tachometer/encoder provenance is required for
angle models. No peak-picked vibration frequency is silently substituted for RPM.

## 2. Normal reference fitting and registration

Use different original acquisitions for normal_fit, normal_calibration and final_test.
NormalRecording requires explicit role and confirmed_normal=True. from_plan() rejects
final-test and fault records. Include actual SHA256 when available; supplied raw
duplicates, original group reuse and record ID reuse are refused. Reserve at least
two original groups in each fit/calibration role; this minimum is not a statistical
field qualification threshold. One recording holds all its related windows.

fit_normal_reference gives each original fit group equal weight through median
representatives. Center is the median of those representatives and scale is
max(1.4826*MAD, 0.15). Calibration uses each original recording's maximum score;
normal acceptance and anomaly limits are empirical quantiles with a floor of one.
They are not calibrated population false-alarm guarantees. Overlapping windows do
not create independent acquisitions. Host-supplied operating ranges need validation.

NormalReferenceBank matches the exact measurement signature, asset, installation,
calibration, filters, RPM provenance, frame, axes, condition and load unit; then checks
RPM/load ranges and feature names. An absent, overlapping or unsupported reference
holds. Register() never silently overwrites a named profile; export() returns copies.
The bank does not extrapolate by renaming an asset or rounding a speed.

## 3. Variable speed

angle_resample integrates measured per-sample RPM using the trapezoid rule. A
conservative zero-phase low-pass precedes angle-domain decimation. It refuses grids
that cannot both retain 10X at maximum speed and protect angular Nyquist at minimum
speed. Defaults retain the last 16 measured revolutions at 256 samples/revolution;
supported integer grids are 64..4096 samples/revolution, 8..1024 revolutions and at
most 8 million output values. Native input is 256..2 million samples, 1..16 channels,
100..200000 Hz. The resulting phase is derived from the supplied tachometer trace,
not from an inferred rotor-fault peak.

angle_features returns 23 features/channel: log RMS, log crest, log Pearson kurtosis,
and twenty log order-energy fractions at 0.5X..10X. Its schema differs from fixed-speed
features. Time and angle reference profiles cannot be interchanged. Built-in angle
normal reference currently requires one channel and a full native waveform with the
same length as the measured trace. It checks the sensor's low-order and filter bands.

For a new angle normal gate, fit/register representation='angle' and attach
ReferenceStage(bank, representation='angle'). Separately fit the angle fault head on
fault acquisitions; the head retains the three named rotor fault classes and an
RPM scope of 590..1620. Do not reuse a fixed-speed trained profile. AngleFaultStage
requires experimental_enabled=True, the upstream anomaly flag exactly True and
qualified measured speed evidence. These stages are experimental, not field-qualified.

Synthetic tests cover increasing/decreasing speed, known 0.5X/1X/3X energy, low-pass
alias suppression and distinguishable constructed harmonic shapes. They do not
establish diagnostic accuracy on a different real machine or an independent fault.

## 4. Holds and lifecycle

DecisionStage keeps numerical score definitions separate. GuidanceStage emits
required_actions with affected parameters; it does not modify scope. A borderline
score can remain visible while alarm_eligible=False. Missing/invalid inputs never
become healthy, zero risk or implicit alarm recovery.

Legacy analyzer.reset() remains buffer-only. reset(reset_stages=True) invokes optional
reset_state(preserve_profiles=True) hooks. Established push() stream gaps, sequence
breaks or identity changes reset stage state; the first push preserves collection
explicitly begun before acquisition. BaselineStage cancels collection and optionally
preserves its owned profile. AlarmStage clears persistence state. ReferenceStage
detaches on preserve_profiles=False; it never deletes a shared host bank. activate()
reattaches. Direct analyze() calls still require host-declared stream boundaries.
Custom stages without a reset_state hook remain the host's responsibility.

## 5. Queue, timing and ownership

RealtimeProcessor has no hidden worker. Producers call submit(), one consumer calls
process_next() or drain(). It snapshots samples/metadata, bounds pending packets,
array bytes and chunk size, and limits metadata to 64 KiB. reject returns accepted=False;
drop_oldest explicitly counts discarded chunks and resets continuity before the next
processed chunk. No dropped samples are filled or treated as continuous healthy data.
drain() processes only the queue batch present when called, preventing an endless
result list under continuous producers. It does not retry or swallow stage failures.

stats() provides processing p50/p95/max, queue-wait max, end-to-end p95/max, configured
latency budget and deadline misses. Timing history is capped at 256 chunks. The host
owns scheduling, external consumers, retries and action authority. Stop the consumer
before close(); a concurrent close/second consumer is refused. A measured-throughput
result is not a Windows/Linux scheduling guarantee.

## 6. Validation

ValidationObservation records source/acquisition/asset/clock identity and start/end
seconds, truth, decision and actual alarm level. evaluate_observations refuses duplicate
sample intervals, mixed acquisition truth and contradictory/nonfinite decisions.
It reports normal acceptance and decision coverage separately. Normal FPR divides
false anomaly decisions by supported normal decisions; zero supported denominator
returns None. Unconditional type accuracy counts holds and unknowns wrong. A standalone
conditional head without anomaly=True is not credited as pipeline accuracy; its
known-fault-only head accuracy is reported separately.

Exposure durations union overlapping windows per acquisition. Alarm event counts use
actual emitted warning/danger states. Unavailable is not recovery; large gaps split
observed episodes, and duration excludes unknown spans. False events/hour uses normal
time with available alarm observations, returning None if no alarm coverage exists.
Optional onset delays use known fault onset times; pre-existing alarms are not
credited as new detections. All event estimates depend on the observation schedule,
not merely the number of overlapping windows. No confidence guarantee is manufactured.

## 7. New independent data and prospective access

Two new twin-spool archives and their source/label documents were acquired under
CC BY 4.0: [normal/unbalance](https://data.mendeley.com/datasets/z7jts4xc7p/1) and
[looseness/rubbing/misalignment/compound faults](https://data.mendeley.com/datasets/b6bfd7v86d/2).
Six files total 1,344,341,975 bytes; provider SHA256 matched. ZIP central directories
contain 450 and 750 waveform members. Descriptions/label metadata were reviewed;
waveform members remain undecoded and have no fit/calibration/test role assigned.

These are not a new measured-data result. LP/HP shafts and speed ratios require
explicit mapping, channel 4 placement can change, and displacement channels must
not be passed as acceleration. Use only appropriately mapped acceleration channels.
Calibration, mounting, anti-alias and independent session/installation evidence must
be reviewed before supplying this API's qualification flags. Do not assign three
single-fault labels to compound faults. Relative-to-UOS/Brito/UFRJ rig independence
does not prove independence between every file in the new archives.

DatasetRecord/ValidationPlan checks role, acquisition and raw-hash leakage, and
optional final-vs-development separation by session/installation/rig. Freeze the
plan plus exact model/preprocessing SHA256 before opening final waveforms; freezing
never overwrites a previous file. FrozenEvaluation checks the plan hash, roles and
raw bytes, writes/fsyncs an exposure ledger before decode and passes a BytesIO snapshot
of exactly the verified bytes to the loader. Default raw-record limit is 128 MiB.
For example, a NumPy loader can use np.load(stream, allow_pickle=False). The host owns
the decoder and preprocessing and must not bypass the plan with external file reads.

The access ledger uses an exclusive lock file, including across separate evaluator
instances. A crash-left lock fails closed and needs explicit operator review. A failed
decoder still exposes that record. Subsequent opening requires replay=True and is
labeled historical_replay; it cannot be advertised as a fresh independent test.

See P1_VERIFICATION.md and research/p1_data_receipt.json. Original raw files/documents
remain outside the distributable; the software's MIT license does not replace their
CC BY 4.0 attribution requirements.
