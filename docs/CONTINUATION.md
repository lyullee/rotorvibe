# Research continuation and reproducibility handoff

Read this before retraining or claiming another independent test. It distinguishes
the public software, private original experiment snapshot and externally acquired data.

## Three different things to preserve

1. **Public release:** source, generic rules, portable tests, authored documentation
   and authored numerical evidence. Installable without PDFs or raw measurements.
2. **Private research workspace:** original frozen source/model copies, full source
   manifests, original access ledgers, local ISO investigation and raw measurements.
   Publication preparation did not overwrite this workspace.
3. **External resources:** provider datasets, purchased documents, calibration records
   and external repository contracts, subject to their separate rights and availability.

The public release is not a byte-for-byte copy of private inference source: normative
selectors were removed, a facade was added, release comments were expanded and version
metadata changed. `research/public_release_exclusions.json` and the file-delta inventory
record this. Historical code SHA256 values belong to the original frozen snapshot.
Do not edit an old ledger to make a new checkout appear to match it.

## Locate evidence

`research/README.md` indexes preserved per-experiment metrics, access records,
predictions and frozen protocols. `research/exposure_registry.json` identifies all
known-opened corpora and lists original test file IDs where recorded. Source links and
license information are in `research/data_sources.json`. Trained profiles and raw
feature caches are intentionally not redistributed.

The original local workspace uses `data/` for separately stored corpora and `output/`
for generated models/results. Some historical data paths were symlinks to another
local disk. A Git clone will not reconstruct those targets. Record storage locations
privately and back them up under the appropriate rights; do not publish personal
absolute paths. The public evidence carries paths relative to a project root.

## What has already been exposed

- All original Brito trials used in the successive development experiments.
- All CrossSpeed 600/900/1200 records used by this project, including the failed
  1200 RPM final acquisition set.
- UOS6204: 48 selected 16 kHz single-rotor originals, six 8 kHz healthy references,
  and 42 selected 8 kHz fault originals. Both prior final sets have now been opened.
- New UOS30204: six 16 kHz healthy files and seven 16 kHz/1200 fault files.
- New UFRJ MAFAULDA: the 30 files fixed by the external-blind plan.

A previously downloaded but numerically unopened file can differ from an exposed
file; consult the actual access ledger rather than the presence of an archive.
Provider metadata and filenames used for prospective selection were inspected before
waveforms. Both final-array opening and subsequent metric access must be considered
when deciding whether a new test is still blind.

## First run: software only

```console
python -m pip install -e ".[verification]"
python -m unittest discover -s tests -v
python -m build --no-isolation
python -m twine check dist/*
```

Read `research/public_verification.json` for the published release's actual checks.
The old research ISO tests need the private route and are not public release tests.
`scripts/verify_implementation.py` and `scripts/verify_physics.py` are additional
research runners; inspect their local artifact requirements before execution.

## Historical measured-data replay

Replay reproduces an old result; it does not create a fresh independent test. Use the
original private source/model snapshot, the exact dataset version, the preserved
download/record manifests and access logs. Verify original-file checksums before
loading. Keep a separate replay output directory rather than overwriting an old
`execution.json`, predictions file or ledger.

The retained scripts describe the original mechanisms:

| Experiment | Developer/evaluator | Important original artifact |
|---|---|---|
| Gaussian correction | `scripts/improve_classifier.py`, `diagnose_classifier.py` | `output/classifier_improvement/frozen_model.json`, `final_test.json` |
| Normal-first | `scripts/verify_two_stage.py`, `validate_normal_independent.py` | `output/two_stage/` and original role manifests |
| CrossSpeed 1200 | `scripts/verify_final_cross_speed.py`, `audit_final_cross_speed.py` | `output/final_cross_speed/` and reserved access ledger |
| Conditioned normals | `scripts/develop_matched_conditioned.py`, `verify_conditioned_final.py` | `output/condition_improvement/matched_frozen.json`, `new_final_protocol.json` |
| Morphology types | `scripts/develop_fault_discrimination.py`, `verify_fault_discrimination.py` | `output/fault_discrimination/frozen.json`, `final_protocol.json` |
| Latest external test | `scripts/collect_external_blind.py`, `verify_external_blind.py` | `output/external_blind/protocol.json`, `evaluation_freeze.json` |

The scripts refuse to overwrite completed experiment outputs. Some development
runners refuse to execute after their final set was opened. Do not remove those
guards to make an exposed test look unused. For a deliberate historical replay,
prepare a new explicitly labeled replay runner and compare saved predictions; do
not represent it as the original one-time prospective execution.

For source setup, create a private data root outside the public checkout. The
collection scripts contain provider endpoint/version and selection mechanisms but
cannot confer redistribution permission. Links may expire; compare current metadata
with the recorded provider digest rather than silently changing the dataset version.
Never download an alternative mirror and treat it as the original without documenting
the source and integrity difference.

## Next model development: use a new experiment ID

Copy an experiment template into a new directory with a new protocol identifier.
Explicitly classify previously exposed data as development. If machine adaptation is
allowed, give normal-reference fitting and threshold calibration separate acquisition
groups, and reserve different new normal and fault acquisitions for final evaluation.
If adaptation is forbidden, retain scope rejection and report unsupported coverage;
do not relabel the new machine as the old one.

Before final waveform access, freeze:

- Code, feature schema, prefilter/resampling and window/hop definitions.
- Model/profile bytes and every learned scaling, threshold and novelty radius.
- Asset/channel/axis/unit mapping, RPM source and quality rejection policy.
- Original-file/installation/session membership and duplicate-check criteria.
- Every candidate-selection rule and all model choices already made on development.
- Denominators for normal FPR, normal acceptance, anomaly detection, type accuracy,
  abstention, per-recording votes and sustained alarm episodes.
- The definition of independent acquisition: a separate file alone need not imply
  separate installation, operator setup or fault repetition.

Include fault severity, installation, load, calibration and multiple independent
healthy sessions where possible. The latest independent rig has no looseness class;
obtain independent looseness evidence rather than substituting a bearing fault label.
Prior models lack a valid remaining-life target; do not retrofit an arbitrary hours
output from a novelty score.

## After opening the next holdout

Record access before decoding, preserve per-window decisions, retain the model hash
in each prediction and audit whole-record membership. Count holds/unknowns as errors
for unconditional type recall and also report decision coverage. Do not hide all-hold
behavior behind a zero false-anomaly fraction. Quantify the number of original healthy
acquisitions with any alert; correlated window counts do not establish confidence at
the population level.

If the result is poor, keep the failure. Any subsequent threshold/feature/model change
uses that result as development information, ending the claim that the same final set
is untouched. Seek a different unopened acquisition/session for the next final test.

## Recovering licensed standards behavior

The public code deliberately cannot reconstruct the private machine-limit tables.
Obtain the exact edition lawfully and review applicability, then supply a custom Rule
or maintain a separately licensed private provider. Do not paste a complete table
back into a public pull request. Historical source fingerprints document what was
investigated but do not grant copying rights or claim the edition is current.

## Release continuity

Use alpha tags while qualification is limited. Build source/wheel from the same tag,
test an isolated installed wheel, audit its content, and retain digests. PyPI versions
are not editable replacements; use a new version for fixes. Zenodo archives should
cite the exact version/repository and retain failure qualifications in their metadata.
Never describe a successfully uploaded package or DOI as diagnostic certification.

## Current local P2 continuation point

Use branch feat/p2-composability (0.1.0a4 candidate); published 0.1.0a1 is older.
Read P2_GUIDE.md and P2_VERIFICATION.md, then research/p2_verification.json,
p2_external_contract.json and p2_realtime_benchmark.json. Rebuild API declarations
with python tools/generate_api_reference.py. Tests are portable; the optional real
process bridge needs its pinned upstream source installed first (README commands).

Keep source, test environment and final artifact identities separate. Use the
native model loader after common profile envelope checks. Do not re-enable life
experiments in operational paths; acquire scoped complete/censored original life
groups and freeze an independent evaluation before claiming RUL performance.

P1's twin-spool numerical archives remain sealed/unassigned. Their unit/shaft and
session review still precedes any frozen training/calibration/final-test split.
P2 adds no new measured classifier validation and does not resolve that data gap.

## Reproducing the integrated alpha release

Use tag v0.1.0a4 and the version DOI 10.5281/zenodo.23941252 for this series.
Read RELEASE_0_1_0a4.md and the latest PUBLICATION_CHECK.md before using historical
candidate receipts. The a1 artifacts and earlier transfer failures remain immutable.
Current-version installation and per-module contracts are visible in both READMEs.

## Current release successor

Use v0.1.0a5 and RELEASE_0_1_0a5.md for the integrated release. The a4 tag records
a pre-publication Windows shell failure and remains unchanged, with no a4 PyPI
distribution. The version DOI remains 10.5281/zenodo.23941252 for the final a5 draft.
