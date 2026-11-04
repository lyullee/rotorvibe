# RotorVibe 0.1.0a4 — P0–P2 integrated release record

Prepared on 2026-11-04. This alpha integrates the previously unshipped P0/P1/P2
series. The release version is 0.1.0a4; 0.1.0a2 and 0.1.0a3 are development
milestones, not claimed as earlier published packages.

## Identity and reproducibility

- Repository: https://github.com/lyullee/rotorvibe
- Version tag: https://github.com/lyullee/rotorvibe/releases/tag/v0.1.0a4
- Distribution: https://pypi.org/project/rotorvibe/0.1.0a4/
- Version DOI: https://doi.org/10.5281/zenodo.23941252 (reserved before packaging;
  registered when the matching Zenodo version is published)
- All-version DOI: https://doi.org/10.5281/zenodo.23937889
- Previous immutable 0.1.0a1 DOI: https://doi.org/10.5281/zenodo.23937890
- Original code and authored documentation: MIT. External rights remain separate.

The local development commits are preserved: 8c4857e (P0), 7b8eb95 (P1),
7f107c4 (P2). The release preparation adds documentation and stronger release
verification. Use the published tag commit for exact reproduction, not a historical
candidate commit. Final public access/CI/hash receipts are recorded after publishing
in docs/PUBLICATION_CHECK.md and research/release_0_1_0a4_publication.json on main.
Those later receipts cannot be embedded retrospectively in immutable PyPI artifacts.

## What changed

| Series | Implemented behavior | Primary implementation / guidance |
| --- | --- | --- |
| P0 | Reject incomplete model scope, invalid feature contracts and numeric overflow; normalize decisions without treating holds as healthy; build explicit version tags without overwriting source from an old archive | fault_discrimination.py, decisions.py, alarm.py, release workflow; P0_VERIFICATION.md |
| P1 | Fit normal references per installation/RPM/load with separate original-group calibration; check acquisition evidence; measured-speed angle features/models; actionable holds; coverage/event metrics; stage lifecycle and finite realtime queue | acquisition.py, references.py, angle.py, guidance.py, evaluation.py, realtime.py, validation_plan.py; P1_GUIDE.md |
| P2 | Isolate stages/sinks; connect an actual supported external package; unify profile provenance/compatibility; accumulate spectral time/Hz history; provide reviewed user rules; separate reference-life experiments and complete/censored-life evaluation | contracts.py/core.py, adapters.py, profiles.py, spectrogram.py, iso/providers.py, experimental/life.py; P2_GUIDE.md |

README and README.ko.md expose purpose, parameter, unit/shape, output and next-stage
contracts. API_REFERENCE.md contains source-derived signatures and dataclass
constructor fields. Rebuild it with tools/generate_api_reference.py.

Two additional defects were found through integration: nominal scalar RPM must not
be upgraded to a measured trace by buffering; and interpolated heatmap samples
could miss a narrow tone. RPM origin is preserved, and heatmap mean-PSD frequency
buckets preserve discrete PSD power before their declared display floor. Classifier
feature definitions remain unchanged. Cross-packet modes and live rule context
must not be combined into an inappropriate common measurement window.

## Compatibility changes users must apply

1. Sinks and stages receive independent nested results. A sink result is not the
   exact returned object. Return intended transformations from named stages;
   mutating a sink snapshot no longer modifies later consumers.
2. ReferenceLifeEstimator, compatibility LifeEstimator and LifeStage default
   disabled. Explicit experimental opt-in is required for bench reference matching.
3. The optional bridge requires the actual process-monitoring-toolkit 0.1.0;
   arbitrary duck types or unsupported versions are rejected. Install the inspected
   pinned commit first, as described in README; base analysis has no such dependency.
4. Heatmap rows retain frequencies/db fields and add mean-PSD representation,
   frequency bin edges and unit metadata. Do not treat display bins as model input.
5. Old native profiles still use their native validators. A common profile envelope
   adds integrity/compatibility and provenance, not model conversion or certification.

## Executed local evidence

Windows, Python 3.12.14, NumPy 2.5.4 and SciPy 1.18.1:

| Check | Recorded result |
| --- | --- |
| Installed-wheel portable regressions, with actual optional package | 224 passed, zero failed/errors/skips: 164 pre-P2 + 60 P2 |
| README/user-guide executable blocks | Seven passed in each of two fresh environments, one base-only and one with optional package |
| Actual optional dependency identity | All 28 installed Python files matched inspected commit 79b4cf52a0acd0d0cbd3addbe82c3d98d6385e5a |
| Additional six-category engineering checks | 58 passed with existing private fixtures; six data readers plus loopback acquisition/worker/storage/export |
| Packaging | Wheel/source metadata and restricted-content audit passed; original raw data and normative tables excluded |
| Numerical/physical controls | Known-order ramps, narrow-tone PSD-integral conservation, hand-calculable life errors, censored null targets and finite numerical bounds |

Historical phase counts overlap and are not summed. Existing data readers used
previously exposed records: CWRU, Paderborn, IMS, Brito, KAIST and FEMTO. They do not
constitute another independent classification test. Their unknown units remain
unknown. Historical private 547-check reports concern a different private scope.

Local receipts are research/p0_verification.json, p1_verification.json,
p2_verification.json, p2_six_category_checks.json, p2_external_contract.json and the
phase-specific benchmark records. These describe what was run at that phase and
retain its then-unpublished status; they are not rewritten as remote/public claims.

## Final release gates and reproduction

The publishing workflow checks the requested tag/version and a clean source tree.
It waits for Windows/Linux × Python 3.11/3.12/3.13 base runs and Windows/Linux real
optional-package runs. Base-only jobs explicitly skip optional tests; the actual
optional jobs and strict installed-wheel run execute them. The build job then
audits/builds one wheel and one source archive, checks metadata, and executes the
installed wheel outside the source checkout before Trusted Publishing.

GitHub and PyPI receive the same build-job distributions. The matching anonymous
downloads, not a separately rebuilt archive, are uploaded to the new Zenodo version.
SHA256SUMS identifies that artifact pair; Linux CI build metadata/timestamps may
differ from preliminary Windows local builds. Check runtime source against the
version tag, then compare distributed bytes across all three services.

```console
python -m venv rotorvibe-release-env
rotorvibe-release-env/Scripts/python -m pip install rotorvibe==0.1.0a4
rotorvibe-release-env/Scripts/python -m pip check
```

On POSIX use bin/python. For source tests, clone the repository and check out
v0.1.0a4, install the documented optional pinned package, then install .[verification,process]
and run python -m unittest discover -s tests -v. Run README examples with
python tools/run_readme_examples.py. For installed checks, invoke
tools/run_installed_tests.py from outside the checkout using the wheel environment;
the tool copies tests/helpers only and rejects source-package imports and skips.

Additional measured-reader regression requires an existing private dataset
workspace through VIBRATION_PROJECT_HOME. scripts/verify_implementation.py reports
missing external fixtures as not_executed; it must not count them as successes.
Its original records are not downloaded or distributed with the release.

## Retained failures and unfinished physical qualification

The strict earlier independent-rig/new-bearing experiment held all 580 windows.
This release does not relabel holds as normal or conditional fault-head results as
unconditional system accuracy. New P1 waveform archives total 1,344,341,975 bytes
and 1,200 ZIP members; numerical arrays remain sealed/unassigned and were not
trained, tuned, calibrated or evaluated in this series. Review shaft/channel units
and independent sessions/installations before freezing a new split.

The latest 48kHz/four-channel burst benchmark missed a 250ms deadline 17 times
(latency p95 approximately 0.515s). Queue bounds and counters do not establish a
hard realtime guarantee, acquisition reliability or hardware installation quality.

Field fault-type accuracy, normal FPR, complete/censored-life RUL error and
statistically calibrated prediction intervals remain unqualified. Synthetic checks
only verify specified calculations. Reference-life spread is not a confidence
interval. User-rule evaluation covers the supplied point and declarations, not
standards certification, whole-machine compliance or automatic shutdown authority.

## Continuing the work

Preserve the tag, artifact SHA256SUMS, model/preprocessing hashes, original-group
role manifests and exposure logs. Read CONTINUATION.md before opening sealed data
or fitting a new model. If final results influence tuning, mark them development
and obtain another unopened independent acquisition. Keep the recorded failures
and operational limits in future documentation. Do not publish original PDFs,
standard tables, private caches or external waveforms under this repository's MIT.
