# Source inventory and publication rights boundary

Original RotorVibe implementation and authored explanatory material are MIT-licensed
by Ugwiyeon Lee. That license does not change the rights in a standard, measurement,
paper, vendor catalog or another repository. No endorsement by those organizations
is asserted. This inventory records the release decisions; it is not a legal opinion
or a claim that software checks can prove absence of every possible rights issue.

## Standards and local documents

The private project used supplied KS/ISO documents for a ten-edition engineering
investigation. The public distribution contains none of the documents, page images,
text extractions, translated paragraphs, normative threshold tables or table-backed
machine selectors. The corresponding direct numeric fixtures are excluded too.
Changing the wording of a copied table or paragraph is not treated as permission.

The public `vibration.iso` path is a compatibility name for original generic code:
typed contexts, unit/statistic/frame checks, waveform measurement and explicit
user-provided rules. `available_standards()` returns an empty tuple. A standard's
identifier is citation/provenance, not a promise that its requirements are included.
Users must obtain lawful criteria separately and assess applicability themselves.
ISO's own publication-rights notice is at https://www.iso.org/copyright.html.

Historical reports retain the fact that these local studies happened, their test
counts, limitations and source fingerprints. They do not reproduce complete normative
tables or grant the ability to reconstruct the licensed source from this package.
See `research/public_release_exclusions.json` for the exact removed module paths.

## Primary measurement sources

| Resource | Identifier / authorship | Terms and use in this project |
|---|---|---|
| Mechanical faults in rotating machinery | DOI `10.17632/zx8pfhdtnb.3`; Lucas Costa Brito and collaborators | CC BY 4.0 source; historical original-trial classifier experiments |
| Four-channel cross-speed rotor data | Mendeley `y8mv28hjwb`, version 1 | Provider-specific source/roles preserved; supported-speed and failed 1200 RPM tests |
| Generic rotating-machine vibration signals | Zenodo `14388093` | Additional research collection; source record terms retained separately |
| UOS deep-groove ball bearing | DOI `10.17632/53vtnjy6c6.1`; Seongjae Lee, Taewan Kim, Taehyoun Kim | CC BY 4.0; normal-reference and morphology development, same-rig file holdouts |
| UOS tapered roller bearing | DOI `10.17632/2cygy6y4rk.1`; same authors | CC BY 4.0; test-only new bearing-domain assessment |
| MAFAULDA | UFRJ COPPE/Poli; Felipe M. L. Ribeiro and collaborators; https://www02.smt.ufrj.br/~offshore/mfs/page_01.html | Official page did not state explicit raw-data license or CSV physical unit; local research only, no raw redistribution |

The UOS explanatory paper is identified by DOI `10.1016/j.dib.2024.110940` and
https://pmc.ncbi.nlm.nih.gov/articles/PMC11437749/. Its publication license is distinct
from the measurement dataset's terms. The paper itself is not bundled.
The MAFAULDA authors' method paper is identified through
https://biblioteca.sbrt.org.br/articlefile/601.pdf; it is cited rather than copied.

Other historical acquisition sources, including run-to-failure bearing examples and
sensor/reference catalogs, remain recorded in local download manifests and authored
historical reports. Their inclusion in a research plan does not imply that they were
used for fitting the current diagnostic head or that redistribution is permitted.
`research/data_sources.json` is the machine-readable resource index.

## What the software archive does contain

The archive contains original calculation code, synthetic tests, original guides and
project-authored numerical experiment outputs. Predictions, confusion counts, model
fingerprints and role/access ledgers are original analysis records and include source
identifiers so attribution is not lost. Their MIT-covered authorship does not relicense
the external measurements from which the experiments were calculated.

The package omits raw waveform arrays, spectrograms, source archives, vendor geometry
catalog copies, external repository snapshots and trained rig-specific profile bytes.
Model hashes and algorithm names identify the experiments without presenting those
profiles as universal pretrained fault detectors. Obtain sources independently before
historical reproduction and respect their attribution and access terms.

## Prose, comments and mandatory text

New README, guides, handoff and algorithm descriptions were authored for this release.
Long-form external explanatory passages and figures are not incorporated. The public
source was checked against available local reference text for substantive long-span
overlap, alongside an explicit source-file exclusion audit. A short common phrase or
method name is not the same as reproducing a protected explanation.

MIT license language, copyright notices, citation titles/identifiers, technical names
and API identifiers are retained accurately. Removing mandatory notices or corrupting
a standard identifier to make every string different would impair attribution and
license compliance. No claim of globally unique wording is made.

## Dependencies and contributions

NumPy, SciPy, Python, setuptools and publication/CI tools retain their respective
licenses. They are dependencies fetched by the installer or CI, not source copies
relicensed by this repository. GitHub Actions workflows reference their maintainers'
actions and do not transfer their source ownership to RotorVibe.

Contributions should contain original code or clearly licensed material with the
required notices. Do not attach purchased standards, private logs, credentials,
customer measurements, raw benchmark archives or copied machine-limit matrices.
Where a contribution depends on a restricted reference, provide an interface,
source identifier and independently authored explanation instead of redistributing
the protected content. Report suspected rights problems through the repository issue
tracker without posting the restricted document itself.
