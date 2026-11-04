# RotorVibe 0.1.0a5 — final public release verification

Verified on 2026-11-04. This is the current P0–P2 distribution check, not new independent measured diagnostic or remaining-life validation.

## Public availability

| Service | Anonymous verification | Result |
| --- | --- | --- |
| [GitHub release](https://github.com/lyullee/rotorvibe/releases/tag/v0.1.0a5) | Public prerelease; wheel, source, SHA256SUMS and installed-test receipt available without credentials | Pass |
| [PyPI](https://pypi.org/project/rotorvibe/0.1.0a5/) | Public metadata, wheel/source downloads, actual fresh pip install from pypi.org | Pass |
| [Zenodo](https://zenodo.org/records/23941252) | Version 0.1.0a5, open files, MIT, DOI 10.5281/zenodo.23941252 | Pass |

All six anonymous wheel/source downloads matched these SHA-256 values; Zenodo also matched the GitHub SHA256SUMS file byte for byte.

```text
7b800e7b21a610d6cdb1e300893350d07fdc49e4777e4ebb541e62a4d6d1ab20  rotorvibe-0.1.0a5-py3-none-any.whl
e4b98f4d78a84b47d0bb7f344471f263931f44a1f0a917d3da38478b7b8620b3  rotorvibe-0.1.0a5.tar.gz
```

The CI-built wheel contains 45 runtime Python files; each matched the canonical source hash recorded for the tag. The actual PyPI installer downloaded that exact wheel hash. Source and distribution audits found no shipped raw datasets, original PDFs, protected standard tables, credentials or personal absolute paths.

## Remote release qualification

[Release workflow 41803037969](https://github.com/lyullee/rotorvibe/actions/runs/41803037969) finished successfully: all 11 jobs passed.

| Job group | Executed environments | Result |
| --- | --- | --- |
| Base qualification | Windows/Linux × Python 3.11, 3.12, 3.13 | Six jobs passed; optional-package tests explicitly skipped in base-only jobs |
| Real optional bridge | Windows and Linux, Python 3.12 | Both jobs passed against pinned process-monitoring-toolkit 0.1.0 |
| Build and installed wheel | Linux Python 3.12.15 | 224 installed tests, zero failures/errors/skips; seven documentation examples passed |
| PyPI / GitHub publication | Trusted Publishing / release assets | Both jobs passed after qualification |

The version tag is v0.1.0a5 at commit 68f03d000ab5b98bfedc65189bc8e4abb9d3464c. Local P0/P1/P2 development commits remain in repository history. GitHub and PyPI receive one build-job artifact pair, and those same downloaded bytes were uploaded to Zenodo; a separate local rebuild was not substituted.

## Actual public installation

A fresh Windows Python 3.12.14 venv installed rotorvibe==0.1.0a5 from https://pypi.org/simple using --no-cache-dir. The first lookup immediately after publishing still saw the old simple index; the subsequent lookup showed a5 and the install succeeded. No alternate index or locally built RotorVibe wheel was used for this final installation.

The real optional package was separately installed from inspected commit 79b4cf52a0acd0d0cbd3addbe82c3d98d6385e5a because that distribution version was unavailable from the queried package index. Base RotorVibe does not require it.

After public installation, tools/run_installed_tests.py ran outside the checkout: **224 tests passed, zero failures/errors/skips**. Imports resolved to the venv site-packages. All **seven** README/user-guide blocks passed against that installation; pip check passed. All 45 installed Python files matched canonical tag source. The installed wheel SHA matched GitHub, PyPI metadata and Zenodo.

Local release preparation separately reran 58 engineering checks with previously exposed reader fixtures (CWRU, Paderborn, IMS, Brito, KAIST, FEMTO), including HTTP/worker/storage/export. These are regressions, not another independent accuracy experiment.

## Retained failed attempt and boundaries

The earlier a4 release attempt stopped before publishing because Windows PowerShell did not expand the bash-style RELEASE_TAG variable. The version-tag command now explicitly uses bash. The a4 tag was retained without force-moving it; no a4 PyPI or Zenodo distribution was published. See research/release_0_1_0a4_ci_failure.json.

New measured fault accuracy, normal operational FPR, field RUL and statistical prediction-interval calibration remain unqualified. The 48kHz/four-channel burst test still exceeded 250ms latency 17 times. P1 raw waveform candidates remain unopened/unassigned. MIT covers original software/docs, not external raw/standard content.

## Evidence and continuation

Current machine-readable receipt: [research/release_0_1_0a5_publication.json](../research/release_0_1_0a5_publication.json). Module purpose/input/output tables remain in both READMEs; exact signatures in API_REFERENCE.md; integrated development and migration record in RELEASE_0_1_0a5.md.

This post-publication check is appended on main. Immutable PyPI and Zenodo artifacts cannot retroactively contain their own future download-check receipt. The earlier a1 check remains in the v0.1.0a4/history tree and the original a1 version artifacts; the a1 DOI is 10.5281/zenodo.23937890.
