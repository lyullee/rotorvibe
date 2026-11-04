# P1 verification — local 0.1.0a3 candidate

Verified on 2026-11-04 with Windows and Python 3.12.14. This candidate has not
been published to GitHub, PyPI or Zenodo. The configured Windows/Linux Python
3.11–3.13 CI matrix has not run remotely for this candidate.

## Implemented scope

| Priority item | Implementation and qualification |
| --- | --- |
| Scoped normal references | Separate fit/calibration acquisitions; explicit installation, RPM, load and acquisition signatures; unsupported or ambiguous scope holds |
| Looseness/unbalance support | Separate angle-domain morphology model and explicit gating; synthetic discrimination checked; new measured data collected but accuracy qualification remains pending |
| Hold guidance | Structured reason, action code and affected parameters; no automatic scope override |
| Evaluation | Coverage, supported-normal FPR, unconditional pipeline accuracy, conditional head accuracy, alarm episodes and delay; missing evidence remains unavailable |
| Acquisition quality | Sensor/calibration/band/anti-alias/RPM provenance declarations checked; declarations do not certify hardware |
| Variable speed | Measured RPM angle resampling with anti-alias filtering and a distinct feature/model schema; physical analytic checks passed |
| Lifecycle | Reset, profile preservation, discontinuity handling and stage detachment contracts |
| Realtime queue | Bounded packets/bytes, explicit overflow and discontinuity, single consumer, bounded timing history and deadline counters |

See [P1_GUIDE.md](P1_GUIDE.md) for input/output contracts, scope restrictions and
integration details. README and API_REFERENCE list the exported entry points.

## Executed verification

A new virtual environment installed the wheel. Tests ran outside the source
checkout and asserted both package imports resolve to installed site-packages.
All **164 tests passed**: 122 existing tests and 42 P1 tests; no errors or skips.
All six executable documentation blocks passed, the standalone P1 integration
example ran, and pip dependency checks passed.

Checks include invalid acquisition declarations; fit/calibration role and raw-hash
separation; scope ambiguity; measured versus nominal RPM; analytic half/first/third
orders under speed ramps; filtering; synthetic fault morphology; lifecycle resets;
queue limits and consumer exclusion; evaluation denominators and overlapping time;
frozen-plan hashes, exposure logging and verified byte snapshots.

The executable example exposed a buffering defect: scalar nominal RPM had been
expanded into an array and could appear measured. Buffering now tracks RPM origin;
constant nominal input remains scalar, genuine traces retain their samples, and
mixed/changing nominal windows are invalidated. Existing regression tests passed.

These are software and synthetic physical checks. Synthetic labels do not measure
real looseness/unbalance classification accuracy or field false-alarm rates.

## Realtime performance limit

The benchmark submits 24 one-second chunks in bursts of four, with 0.25-second
analysis hops and a 0.25-second latency budget. Each case produced 93 windows.
No packets were lost, rejected or failed.

| Sampling / channels | Processing p95 | End-to-end latency p95 | Deadline misses |
| --- | --- | --- | --- |
| 4 kHz / 1 | 0.016 s | 0.061 s | 0 |
| 12 kHz / 1 | 0.027 s | 0.097 s | 0 |
| 12 kHz / 4 | 0.044 s | 0.160 s | 0 |
| 48 kHz / 4 | 0.143 s | 0.537 s | **17** |

The final case fails this latency budget. This host-driven burst experiment is
not paced DAQ testing or a hard realtime guarantee. Full machine-readable results
are in `research/p1_realtime_benchmark.json`.

## New measured data and remaining work

Two versioned Mendeley datasets were collected: [twin-spool fault data](https://data.mendeley.com/datasets/b6bfd7v86d/2)
and [normal/unbalance data](https://data.mendeley.com/datasets/z7jts4xc7p/1).
Six files total 1,344,341,975 bytes; all provider SHA-256 hashes were matched and
rechecked. ZIP directories contain 1,200 waveform members. Provider descriptions,
labels and ZIP directories were reviewed; numerical waveform arrays remain sealed.
No training, calibration, development or final-test roles have been assigned.

Before a new measured accuracy claim, review units, shaft/channel mapping,
acquisition/session independence and measurement evidence; assign disjoint groups;
freeze the model, preprocessing and evaluation plan; then expose the final data
through the logged evaluator. Dataset novelty alone does not establish independence
between files. Unsupported compound faults must not be relabeled as single faults.

The 580-window historical metrics replay uses already exposed predictions and is
explicitly not a new independent test. No new measured normal FPR or fault-type
accuracy is claimed by this release.

Raw archives, provider prose and standard tables are excluded from distribution.
Original code and documentation use MIT; external material retains its own terms.
`scripts/collect_p1_candidates.py --data-root <private-folder> --verify-only`
rechecks the collected files without decoding waveforms. Omit `--verify-only` to
download pinned provider files into a separate private folder.
