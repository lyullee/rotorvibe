# Final public distribution and clean-install check

Verified on **2026-11-04 (Asia/Seoul)**. This is a software/distribution check,
not a new independent measured-fault validation or a change to classifier qualification.

## Public access

| Service | Anonymous verification | Result |
|---|---|---|
| [GitHub](https://github.com/lyullee/rotorvibe) | Repository API says public; tag v0.1.0a1 release is published, not draft; wheel and source downloaded without credentials | Pass |
| [PyPI](https://pypi.org/project/rotorvibe/0.1.0a1/) | Public JSON metadata, wheel/source downloads and real pip installation without credentials | Pass |
| [Zenodo](https://zenodo.org/records/23937890) | Published record, open access, MIT license, DOI 10.5281/zenodo.23937890; both archives downloaded without credentials | Pass |

All six downloaded files (wheel and source on each service) matched these SHA-256 values:

```text
011002b53c2c79635ef89d9895afac08229b0cf8cfedb5da7e9d3618ac44bccd  rotorvibe-0.1.0a1-py3-none-any.whl
063ceafaed83778709e6c9bd7b879cecf2ab4dce22842170ecab128899bda685  rotorvibe-0.1.0a1.tar.gz
```

## Clean installation and examples

Created a new Python 3.12.14 virtual environment without system site packages and ran:

```console
python -m venv clean_env
clean_env/Scripts/python -m pip install --index-url https://pypi.org/simple --no-cache-dir rotorvibe==0.1.0a1
clean_env/Scripts/python -m pip check
```

On POSIX use `clean_env/bin/python`. The environment installed NumPy 2.5.4 and
SciPy 1.18.1. Imports resolved inside this new environment, with the working directory
outside the source checkout. `pip check` found no broken requirements. This isolates
Python packages, not the Windows operating system or hardware.

Every Python fenced block in the latest README and user guide was executed separately
using the installed distribution. The Korean README refers to the English executable
examples and adds no separate Python block.

| Example | Actual result | Verification |
|---|---|---|
| README complete signal calculation | valid=True; RMS 0.14142135623730953, peak 0.2 | RMS equals 0.2/sqrt(2), peak equals 0.2; finite JSON export |
| README direct module composition | custom stage quality_accepted=True; sink receives same result object | Actual analysis, bearing-provider injection, stage execution and sink callback completed |
| README bearing geometry | BPFI=96, BPFO=64, FTF=8, BSF=48, 2BSF=96 Hz | BPFO=64 Hz analytically checked |
| User-guide invented caller rule | status=evaluated, zone=B, value=2.0 mm/s | Demonstration limits only; not an ISO table or compliance claim |

The portable public test suite also passed **97 checks** against the installed PyPI
library. The outside-checkout runner initially lacked the research-only
`scripts.external_blind_metrics` helper; that produced one discovery error. Supplying
that helper from the public checkout resolved discovery, and the final run passed all
97 tests. No library change was needed. The normal README test command runs from the
repository root, where that helper already exists.

[The six-environment CI run](https://github.com/lyullee/rotorvibe/actions/runs/41782143647)
also passed on Windows/Linux with Python 3.11, 3.12 and 3.13 for the published source.

## Documentation improvements

Both README files now include module-level purpose/input/output tables, exact signal
and result contracts, configuration defaults, array shapes, physical units, explicit
stage/sink ordering and optional-dependency ownership. The former construction-only
integration snippet is now self-contained and executes a real stage and sink.

[API_REFERENCE.md](API_REFERENCE.md) contains public constructor/method declarations
and dataclass fields extracted from the released source. This supplements the README's
explanation rather than replacing it with a list of names.

The updates apply to GitHub main. Already-published **0.1.0a1** artifacts, tag and
PyPI's embedded README preserve the initial release snapshot. Their public README
links point to the maintained GitHub documentation. No version, numerical code,
training data, frozen model, threshold or original scientific result changed.

Machine-readable download hashes, example outputs and environment versions are in
[the check receipt](../research/final_publication_check.json).
