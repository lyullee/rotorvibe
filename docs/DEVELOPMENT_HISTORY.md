# Development history and decision record

This narrative reconstructs the work from preserved scripts, reports and machine
artifacts created in the November 2026 project. The original workspace was not a Git
repository. These phases are **not fabricated historical commits**; the public Git
history starts with the reviewed release. Machine-readable evidence and frozen hashes
provide the experiment-level trace. Dates inside retained reports identify executions
when known; phase order below records the development sequence.

## D01 — From documents to measurable inputs

The initial request was to digitize vibration-analysis reference material and assess
what a real-time module could calculate. The scope separated waveform/FFT/spectrogram
processing from health inference. RMS, peaks, kurtosis and band energy are numerically
available with raw samples and acquisition metadata. Bearing markers additionally
need RPM plus geometry or a trusted part-specific frequency provider. Unbalance,
misalignment and looseness can yield candidates, but identifying a unique physical
cause needs directional measurements, operating context and confirmed fault examples.
Remaining-life hours require degradation histories and were not implemented as a
supported prediction capability.

Reference PDFs were local research inputs, not a public documentation source to copy.
Later publication review removed their transcriptions and standards tables from the
redistributable tree. The private originals remain outside this repository.

## D02 — Public data and source inventory

Collection work gathered waveform datasets, bearing geometry/frequency references,
operating metadata and fault definitions. Download plans and manifests recorded URLs,
provider/local checksums, roles and unit limitations. Missing physical units were kept
as unknown instead of converted from a guessed sensor sensitivity. External files
stayed separate from implementation source.

The important distinction was between a signal window and an acquisition. Many
consecutive windows came from the same experiment and could not be counted as
independent installations. Later holdouts therefore used whole original files/trials.
Acquisition identification remained limited when providers did not publish session or
reassembly IDs. Those limits are preserved rather than filled with invented metadata.

## D03 — Library-first implementation

The host-integration requirement led to explicit Python contracts rather than a
server-only design. `SignalBlock` carries samples, units, timing, channel identity,
RPM and source scope. `VibrationAnalyzer` accepts direct blocks or buffered chunks.
Stages add outputs in order; sinks receive completed records. Waveform-aware stages
receive the read-only calibrated window. The optional HTTP/SSE/UDP dashboard, worker
and SQLite storage were implemented around that core, not as mandatory dependencies
of numerical analysis.

Interoperability uses Python objects and replaceable providers. External repositories
were inspected for their contracts, but their source snapshots are not redistributed.
Actual direct/stage/registry/storage/replay parity checks were distinguished from
claims that every other application has already integrated the library.

## D04 — Software verification and physical controls

The user requested input rejection, analytic formula checks, numerical extremes,
module chaining, regression and full input-to-result executions. Test work covered
inconsistent units/layouts, invalid values, known spectral amplitudes, round trips,
timestamps, alarm persistence, API hooks and service shutdown behavior.

Physical controls added known mixtures, motion-equation references, amplitude/frequency
relations and explicit negative controls for aliasing and finite observation duration.
These controls validate bounded calculations; they do not turn simulated signals
into confirmed field defects. Tests and measured-data classification were always
reported separately.

## D05 — Private standards investigation

Ten supplied KS/ISO edition routes were implemented and tested in the local research
workspace, including machine applicability, band/statistic/frame checks, per-point
evaluation, averaging and boundary conventions. The historical campaign counted 363
checks and 2408 profile boundary assertions across 314 profiles. These counts identify
the private route's work; they are not public built-in-profile capabilities.

Publication review found numerical tables in those selectors and private verification
fixtures. Those files are excluded from this release. The public interface keeps
generic typed observations, user-supplied `Rule` evaluation and numerical measurement
helpers. A separate public synthetic-rule suite covers the replacement. The release
delta and exclusion inventory record the difference explicitly.

## D06 — Gaussian classifier diagnosis

Early classification was poor. The Gaussian class score lacked the class-dependent
variance normalization, allowing broad classes to receive artificially favorable
scores. The corrected version retained the existing feature schema and included the
missing term. A historical Brito comparison reported 24.94% before and 63.69% after the
correction on its fixed final split. A normal final acquisition remained wrong in
all 420 windows, and acquisition-level internal validation was also weak.

The code correction was meaningful, but the result was not sufficient for operation.
The Brito trials later became exposed development data. This history is not an unused
test pool for another blind-performance claim. See `CLASSIFIER_IMPROVEMENT.rst` and
the copied original result summaries under `research/classifier_improvement`.

## D07 — Normal-first diagnostics and additional normal records

A two-stage route separated normal deviation from known-type matching. Rotor order
power and directional features were added, while feature contracts and asset scope
remained explicit. Matched CrossSpeed source models used their own normal references
and threshold-calibration records. A held group of 24 acquisitions / 479 windows
achieved 93.74%; healthy decisions were 129 normal and 30 hold, with no fault alert in
those 159 healthy windows. This was calibrated same-rig evidence, not untrained
machine transfer.

Additional Marra and CrossSpeed sources were collected with source/role manifests.
Some sources had unknown amplitude units and were not promoted to calibrated physical
comparisons. Large raw archives and upstream catalog facts remain external resources.

## D08 — First 1200 RPM failure

The 600/900 RPM profiles did not support 1200 RPM. A separate pooled source-only
qualification candidate was frozen before opening the new target-speed records.
The 1178-window / 59-acquisition test reached only 11.04%, and all 399 normal windows
were marked anomalous. Its model SHA256 was
`364a14e7f6e32a5b8cfaf6b7e3b1cfcb93785688f6a8963dabf81c805fa03696`.

Normal score shifted materially: source median about 1.213, target median about
4.360, versus a fixed boundary about 2.386. Channel-ratio changes and correlated
features made one global reference inadequate. The supported-speed models were not
quietly widened. The opened target was reclassified as development material and its
original access ledger preserved. See `FINAL_CROSS_SPEED_VALIDATION.rst`.

## D09 — Matched normal references and common-band model

UOS 6204 original MAT files were collected from the primary dataset: 48 single-rotor
records at 16 kHz plus six healthy records at 8 kHz, about 1.04 GB. The six healthy
8 kHz acquisitions included 1200 RPM and were explicitly allowed normal fitting
data. Eight 16 kHz/1200 RPM files stayed outside fitting, calibration and model choice.

An initial interpolation attempt failed source validation and was not tested as if
qualified. A matched-speed normal bank and anti-aliased common 4 kHz analysis path
were then developed. Six candidates were selected on declared source recording
validation before the new final files were opened. The selected candidate used level
and order features with zero margin, preserving exact-tie and novelty rejection.

The frozen model SHA256 was
`4ebdd4393b4267eae4013b3ef649384624617defcb827e4d93f0652f8dc33ecd`.
The new original-file test contained 320 windows: 31/40 healthy accepted, eight hold,
one false anomaly; all 280 fault windows detected, but only 135 fault types correct.
Overall accuracy was 51.875%, fault-type accuracy 48.214%. Healthy data came from one
test acquisition, which had at least one false anomaly. Its 2.5% window rate was not
claimed as an operational field FPR.

Alternate-rate raw duplication/noise screens supported distinct source records, not
independent reassembly. No post-test tuning was performed in that experiment. See
`CONDITIONED_IMPROVEMENT.rst`.

## D10 — Looseness and unbalance morphology improvement

Analysis of the now-exposed 16 kHz test separated two failure mechanisms. Strong
unbalance had the right nearest class in all 40 windows but was rejected by distance
limits. Looseness remained only 20/40 even if rejection was ignored, demonstrating
that threshold relaxation alone would not solve the problem. Weak unbalance also
overlapped other candidate types.

The new head added 61 morphology features: fine half-order coverage, impact shape,
band energy and envelope order energy. Four chronological representatives per source
file retained within-recording variation. A new 8 kHz collection added 42 fault
originals / about 811 MB. Thirty-five non1200 records were development data; seven
1200 records were reserved before numeric decoding.

Twelve candidates compared order/full morphology, RPM penalties and margins. Two
whole-speed validation folds excluded both acquisition rates at 1000 or 1400 RPM.
The chosen full-morphology candidate had mean development Macro-F1 about 86.41%.
RPM proximity weighting reduced validation performance and was rejected. Final fitting
used 77 fault files / 4480 windows, while the existing normal gate stayed unchanged.

Model SHA256:
`456b3388bbb2c6d73b6a1e443620aa7a761939419db0c5ab4fa3e28abfb3047b`.
On the same seven new fault files / 560 windows, the old comparator achieved 275/560
(49.11%), the new gated head 559/560 (99.82%). Looseness was 80/80, unbalance 240/240,
misalignment 239/240. One previously correct misalignment window regressed. There
was no new healthy test and no proof of independent installation or new severity.
See `FAULT_DISCRIMINATION_IMPROVEMENT.rst`.

## D11 — New normal and independent-bench transfer: failure retained

The next request explicitly prohibited training or tuning on the new material. Both
models and all production inference source hashes were therefore frozen unchanged.
Selection and evaluation rules were fixed before decoding 43 new original records.

UOS NTN30204 contributed six healthy acquisitions / 240 windows and seven fault
acquisitions / 280 windows, a bearing-domain change on the same AST apparatus.
UFRJ MAFAULDA contributed fifteen healthy and fifteen fault acquisitions, 60 windows
from a genuinely different institutional ABVT rig. Selection used source metadata
only. The inaccessible vertical-misalignment directory was excluded before waveform
opening. Downloaded bytes totaled 777,976,958.

The real API received actual identities, layouts, rates and units. All 580 windows
held. Consequently normal acceptance and type decision coverage were zero, and a
supported-decision FPR was undefined. Zero actual alerts in this condition cannot
be marketed as a successful zero-FPR detector.

A separately declared offline fixed-weight stress route suppressed applicability
checking without fitting anything. On the known-g UOS30204 data it falsely flagged
240/240 healthy windows and classified only 124/280 faults correctly. Looseness was
2/40, unbalance 2/120, misalignment 120/120: systematic bias toward misalignment.
UFRJ raw units were not explicit in the primary description. Two predeclared native
amplitude factors both gave no correct fault types; the conditional head rejected all
30 fault windows. That is not a calibrated physical FPR assessment. Independent-rig
looseness was not covered. See `EXTERNAL_BLIND_VALIDATION.rst`.

The conclusion is unadapted cross-bearing/cross-rig operational qualification failed.
The prior 99.82% is valid only in its original narrow apparatus protocol. No data
from this new experiment were used for fitting, tuning or reference calibration.

## D12 — Public release preparation

The user authorized public GitHub, PyPI and Zenodo publication and selected MIT for
original work. The release is named RotorVibe and tagged 0.1.0a1 to make its research
status visible. Original imports remain available through the compatibility namespace.

Publication preparation created a separate public checkout rather than overwriting
the frozen private research workspace. Third-party source documents, normative table
selectors/fixtures, raw measurements, runtime state and trained rig-specific models
are omitted. Original comments and new algorithm explanations describe the actual
models without copying substantive external prose. Mandatory legal text and citations
remain accurate. A public custom-rule implementation replaces the private standards
lookup route and receives fresh synthetic tests.

The public evidence archive includes project-authored predictions, split protocols,
metrics and audit summaries; external raw files remain separately acquired resources.
The public test count and build/install results are recorded independently of the
historical private 547 checks. The first Git commit is a truthful release snapshot,
not an invented sequence of prior implementation commits.

## Research position at handoff

The numerical core is reusable; the trained fault candidates are not qualified as
general-purpose field diagnosis. Continue by separating machine-specific normal
adaptation from truly independent final acquisitions, extending sensor/installation
evidence and evaluating normal decisions and type rejection together. If exposed
transfer failures influence a new model, those data become development material and
another unopened final experiment is required. Keep failures in the next report.

## P2 local candidate (2026-11-04)

The feat/p2-composability branch adds detached callback results, a pinned real
process-package bridge, canonical profile envelopes, bounded spectral history,
reviewed rule providers and explicitly gated reference-life experiments. Native
models/loaders remain authoritative; wrapping does not retrain or convert them.

A narrow-tone display check found that interpolation onto 384 points could miss
100 Hz entirely. Frequency-bin mean PSD now preserves the discrete PSD integral
and keeps narrow tones visible. Fixed model features remain unchanged. The old
sink-identity regression assertion was deliberately replaced with different-object,
equal-content checks because isolation is the intended P2 compatibility change.

Actual optional dependency installation from the queried package index failed;
the inspected upstream Git commit was installed separately and all 28 installed
Python files matched it. Bidirectional SignalBatch/Analyzer/Monitor wiring was
exercised. A subsequent review added preservation of constant modes, cross-packet
mode boundaries and live rule-context boundaries. Final installed tests total 224.

The legacy reader verification initially lacked private fixtures in the sanitized
checkout. Its missing-fixture case is now explicit not_executed. Supplying the
existing private data workspace enabled all 58 additional engineering checks,
including six measured-data readers and loopback HTTP/worker/storage computation.
Those are exposed-data regressions, not new independent diagnostic validation.

See P2_VERIFICATION.md and research/p2_verification.json. No P2 publication, fresh
measured classifier score, statistical interval qualification or field RUL claim
has occurred. All earlier failure reports and P1 sealed-waveform status are retained.

## Integrated 0.1.0a4 release preparation

The user authorized final P0–P2 verification and publication on GitHub, PyPI and
Zenodo. The existing a4 candidate number is retained because it was not previously
published. Phase reports remain historical evidence; docs/RELEASE_0_1_0a4.md is the
combined implementation, migration, test-scope and continuation record.

Version DOI 10.5281/zenodo.23941252 was reserved on a new version of the existing
Zenodo record before packaging. README exposes the current installation command,
module purposes/inputs/outputs, compatibility changes and retained limits.
CITATION.cff and package archive metadata identify that version; a1 stays archived.

Publication now waits on the complete OS/Python matrix, real optional-package
verification and a strict installed-wheel suite. The public installed-test runner
copies only tests/helpers into an owned temporary folder and checks site-packages
imports; skipped optional tests are refused in release mode. No model retraining
or opening of P1 sealed waveforms is part of this publication. Final remote CI,
public anonymous download and artifact-hash receipts are appended after publishing
in PUBLICATION_CHECK.md and research/release_0_1_0a4_publication.json on main.

## Windows release preflight correction and 0.1.0a5

Run 41801960560 retained its a4 tag and stopped publication: three Windows base
jobs used PowerShell's empty local RELEASE_TAG variable. Three Linux base jobs and
two actual optional-package jobs passed. The failing step preceded Windows tests,
so it is not recorded as a passed Windows numerical test. The command now declares
bash. Current package/version documentation advances to a5; no tag was force-moved
and no a4 PyPI/Zenodo distribution was uploaded. The reserved Zenodo draft version
is updated to a5 before publication. Full receipts preserve the failed attempt.
