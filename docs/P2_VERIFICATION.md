# P2 verification — local 0.1.0a4 candidate

Verified on 2026-11-04, Windows, Python 3.12.14, NumPy 2.5.4 and SciPy 1.18.1.
This is a local unpublished candidate on feat/p2-composability. No GitHub, PyPI or
Zenodo publication was performed. Remote CI jobs are configured but not run here.

## Scope and executed checks

| P2 item | Implementation | Verification / remaining qualification |
| --- | --- | --- |
| Result protection | Detached nested stage/sink snapshots, copied stage outputs and immutable raw hook buffers | Consumer/stage mutations cannot change other consumers, earlier outputs or returned values; sink object identity intentionally changes |
| External Python bridge | Exact 0.1.0 optional contract, inspection API, pinned upstream install and actual bidirectional example | Actual SignalBatch → Analyzer → feature SignalBatch → Monitor; units/time/episode/mode/validity/provenance checks; cross-packet mode change resets buffers |
| Common profiles | Finite JSON envelopes with schema/algorithm/features/preprocessing hashes, original groups, calibration history and scope | Integrity changes, wrong preprocessing/features/scope, fit/calibration leakage and implicit overwrite rejected; actual normal profile round-trip preserves native inference |
| Spectrogram | Bounded independent history with time/Hz axes, bin edges, null invalid rows, gaps and identity segments | Count/time retention, invalid/backward/grid cases and copy isolation; analytic narrow-tone and PSD-integral checks |
| Rule providers | Reviewed edition/source/hash/date/context documents and structural provider port | Actual raw-window evaluation with invented limits, provenance, ambiguity/missing-scope/identity mismatch checks; no standard tables |
| Experimental life | Separate experimental namespace; estimator/stage default disabled; complete/censored history and evaluation API | Hand-calculated errors, empirical interval inclusion, equal-life weighting, censored null targets, leakage rejection and finite numerical extremes; measured RUL/interval calibration remains unqualified |

A fresh virtual environment installed the candidate wheel. Tests ran outside the
checkout, asserting both rotorvibe and vibration imports resolve to installed
site-packages. **224 tests passed: 164 existing and 60 P2; zero failures, errors or
skips.** The actual optional dependency was present, so bridge tests were executed.
Seven documentation code blocks passed in both the optional-package environment
and a separate fresh base-only environment. Both passed pip check. The standalone
P2 rule/history example and actual process bridge example ran successfully.

The optional source was inspected at commit
`79b4cf52a0acd0d0cbd3addbe82c3d98d6385e5a`. Installing version 0.1.0 from the
queried package index failed with no matching distribution. Installing the pinned
source succeeded; all **28 installed Python source files** matched the checkout.
The base-only environment needs no process package. See p2_external_contract.json
for source hashes and README for explicit install commands.

## Additional existing engineering verification

The six-category verification script passed **58 checks**, including input,
analytic formulas, numerical extremes, composition, regression and end-to-end
computation. Existing exposed CWRU, Paderborn, IMS, Brito, KAIST and FEMTO records
were loaded through the actual readers and analyzer. Loopback HTTP ingestion,
worker calculation, storage and export were exercised.

The sanitized checkout contains no raw fixtures: the first attempt could not find
them. The script now records missing external fixtures as not_executed instead of
implicitly passing them. Supplying the existing private workspace through
VIBRATION_PROJECT_HOME enabled the 58-pass run. No new independent classifier
accuracy is inferred from this reader/DSP regression. Unknown source units remain
unknown and do not establish calibrated magnitude or ISO applicability.

## Defects found and corrected during P2

- Interpolation onto the old 384-point heatmap grid could omit a narrow 100 Hz tone
  entirely. Mean PSD frequency buckets now retain the tone and preserve discrete
  PSD-integrated power before the explicit display floor. Classification features
  and native PSD are unchanged.
- Existing sink examples/tests assumed the exact returned object. They now verify
  independent objects with equal contents, matching the requested copy policy.
- A constant upstream mode must survive adaptation and later export; a change
  between packets must split the buffer. Actual package tests verify both.
- Provider context is checked against live source identity/state and supplied RPM,
  rather than accepting an unrelated reviewed context for another asset.
- Rejected short-hop history updates leave no partial frequency-axis mutation.

## Observed performance and retained limit

The copy benchmark runs 24 one-second, 12 kHz, four-channel windows per case.
On this host, four stages and three sinks gave p95 **0.0181 s**, with approximately
**2.02 MB** peak Python-traced allocations. The no-callback case gave 0.0201 s;
that difference is measurement/order/cache variability, not evidence that copying
speeds computation up. Tracemalloc is not process RSS or a long-duration leak test.

The existing burst benchmark was rerun on the installed candidate:

| Sampling / channels | Processing p95 | Latency p95 | Misses of 250 ms budget |
| --- | --- | --- | --- |
| 4 kHz / 1 | 0.0160 s | 0.0605 s | 0 |
| 12 kHz / 1 | 0.0237 s | 0.0921 s | 0 |
| 12 kHz / 4 | 0.0441 s | 0.1626 s | 0 |
| 48 kHz / 4 | 0.1341 s | 0.5149 s | **17** |

Each case had 93 windows, queue high-water four and no dropped/rejected/failed
packets. The final workload still fails its latency budget. These synthetic host
measurements do not guarantee paced acquisition, OS scheduling or hard realtime.
Raw measurement receipts are p2_result_isolation_benchmark.json and
p2_realtime_benchmark.json under research.

## What remains unqualified

No new model training, measured classification score, independent normal FPR or
field remaining-life accuracy was produced. P1's twin-spool numerical archives
remain unopened/unassigned. They are not complete/censored life evidence.

The life API can evaluate correct labels without fabricating censored failure
times, but the project still needs scoped complete and censored operating lives,
original-group separation, causal prediction generation and independent error/
interval-calibration experiments. Synthetic interval inclusion is not a validated
confidence interval. The reference-life routine remains explicitly experimental.

Only Windows/Python 3.12 was executed locally. The configured base CI matrix and
separate pinned optional bridge jobs must run remotely before cross-platform
qualification. Original code/docs use MIT; external raw data, external package
source and protected standard content remain excluded from the candidate.

Machine-readable evidence: research/p2_verification.json,
research/p2_six_category_checks.json and research/p2_external_contract.json.
