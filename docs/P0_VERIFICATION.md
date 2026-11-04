# P0 fixes and regression verification — 0.1.0a2 candidate

Date: **2026-11-04 (Asia/Seoul)**. Scope: the public RotorVibe source, not the
historical private standards-table implementation. This candidate is prepared
locally and has not been published to PyPI, GitHub Releases or Zenodo.

## Changes and verified behavior

| P0 item | Before | Implemented and checked |
|---|---|---|
| Profile loading | The loader accepted an empty scope and did not enforce fit-time metadata contracts | One scope/name contract for fitting and loading; required nonblank asset/condition, g or m/s^2 units, finite JSON metadata, ordered unique names, mode/indices, acquisition groups and research-use flag. Missing/invalid inference scope holds. Existing fit-generated and historical frozen profiles still load. |
| Finite numerical output | Huge finite features overflowed distances, producing a NaN margin and non-JSON finite output | Features/profile parameters bounded; guarded intermediate arithmetic; explicit ValueError on unsupported magnitudes/overflow. Small, boundary and supported large values yield finite results. No replacement of bad values with normal/zero. |
| Release pipeline | Manual dispatch restored the old archive into main and pushed changes | Read-only tag/version/HEAD/clean-source guard; build/test/audit from explicit tag; installed wheel/examples before publication; same artifacts for PyPI/GitHub and release checksums. No source restoration or Git commit/push command. |
| Module I/O composition | Baseline score, conditioned normal_score and heterogeneous hold statuses required bespoke wiring | Additive DecisionStage/normalize_decision contract; retain original score name and reason; explicit alarm eligibility and optional expected_score_name. Held/invalid/stale-score observations cannot recover an alarm. Existing producer fields and legacy score callbacks remain. |

## Regression results

- **122 tests passed**, 0 failures, 0 errors, 0 skipped: all previous 97 public
  checks plus 25 new P0 regressions. Source checkout and fresh installed-wheel runs
  passed. HTTP/SSE/UDP/authentication/file-input and resource-lifecycle regressions
  in the existing suite remained enabled.
- The installed run used a **new Python 3.12.14 venv**, NumPy 2.5.4 and SciPy 1.18.1.
  Both rotorvibe and vibration imports were asserted to resolve inside that venv,
  with a working directory outside the source checkout. The public test files and
  two non-package helper modules were copied beside the runner; application code
  was imported from the installed wheel. `pip check` passed.
- **Five executable examples passed** from the installed wheel: four README Python
  blocks, including actual baseline→decision→alarm and scope-hold behavior, plus
  the invented caller-rule user-guide example. The Korean README links these examples.
- **6,000 supported predictions exactly matched 0.1.0a1**, using seeded synthetic
  2-feature/order and 61-feature/morphology profiles at 590/1200/1620 RPM. The two
  fitted profiles were identical to the original implementation, and four supported
  scope-mismatch outcomes matched. This checks numerical regression, not field accuracy.
- The original privately retained frozen morphology profile was loaded successfully
  without editing it or reopening any measured holdout arrays. That profile is not
  included in this release.
- Reproduced defects covered empty/malformed loader scope, huge finite features,
  tiny scales causing intermediate overflow, nonfinite profiles, invalid feature
  schemas, and stale numeric scores attached to holds. Every accepted output in
  the numerical boundary checks serialized with `allow_nan=False`.
- Release-guard tests used actual disposable local Git repositories: clean matching
  tag passes without changing source or refs; branches, injected tag text, missing
  tag, mismatched package/facade version, moved HEAD and dirty/untracked source fail.
- **actionlint 1.7.12** validated release.yml and verify.yml with no diagnostics
  (ShellCheck integration disabled). Tag-push and manual-input expressions were
  checked; official GitHub workflow permission/reference semantics were consulted.
- Wheel/source builds, `twine check`, source/distribution content audits and
  Markdown parsing passed. Private standards tables, raw data and credentials remain
  excluded. Full updated declarations are in [API_REFERENCE.md](API_REFERENCE.md).

## Compatibility and intentional rejection changes

Existing calibrated, fit-generated profiles and normal-range calculations remain
supported. Previously accepted malformed profiles and unsupported numeric magnitudes
are intentionally rejected. An invalid caller scope returns hold. A malformed profile
or invalid numerical calculation raises ValueError, so the host must handle errors
explicitly; they are not silently converted to healthy observations.

The common adapter does not make baseline and conditioned scores interchangeable.
Select model-specific thresholds and enforce the expected score definition. A fault
head without an independently meaningful score remains unscored and cannot drive
threshold alarms through this adapter alone. Gaussian candidates are not upgraded
to confirmed physical anomalies.

No retraining, threshold tuning, new independent measured-data test, ISO certification
or diagnostic-transfer improvement is claimed. Historical failure records are intact.

## Reproduce from this prepared checkout

```console
python -m pip install -e ".[verification]"
python -m unittest discover -s tests -v
python tools/run_readme_examples.py
python -m build --no-isolation
python -m twine check dist/*
python tools/audit_release.py --dist dist
```

For installed validation, create another venv, install the wheel, change to a directory
outside the checkout and run `python /path/to/checkout/tools/run_readme_examples.py
--installed`. Keep the test-only helper modules available if rerunning the complete
test suite outside the source tree. Windows uses `Scripts/python.exe`; POSIX uses
`bin/python`.

The current source is a candidate. New-source remote matrix CI and actual authenticated
publication were **not executed** as part of these local checks. The workflow requires
an explicit matching release tag, and neither an ordinary branch push nor these
verification commands publishes a new package. CITATION.cff's DOI identifies archived
0.1.0a1; it must not be presented as an archive of this changed candidate.

The publisher refuses an already-existing PyPI distribution instead of silently
skipping it and attaching a potentially different rebuild to GitHub. If publishing
succeeds but the later GitHub job fails, retry that failed job, not a new build of
the same published version.

Machine-readable counts and parity results: [p0_verification.json](../research/p0_verification.json).
The older public_verification.json and final_publication_check.json remain receipts
for the already published 0.1.0a1 release.
