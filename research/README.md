# Evidence archive

These files are project-authored numerical records, not raw measurement datasets.
They retain prospective split rules, model/code digests, original-file access events,
predictions and metric summaries. The external data retain their separate rights.

| Directory | Evidence scope |
|---|---|
| `classifier_improvement` | Historical Gaussian correction and fixed-trial comparison |
| `final_cross_speed` | Failed source-only 1200 RPM transfer |
| `condition_improvement` | Matched normal references and eight new 16 kHz files |
| `fault_discrimination` | Morphology head and seven new 8 kHz fault files |
| `external_blind` | New normals, new bearing domain, independent UFRJ rig; no adaptation |

`exposure_registry.json` identifies data already opened. `data_sources.json` identifies
primary sources and terms. `public_release_exclusions.json` records private material
not copied. `public_file_delta.json` links public files to their original private
fingerprints and documents deliberate changes. `public_verification.json` describes
the **public release**, not the private 547-test historical campaign.

The public checkout is deliberately different from the private standard-table source.
Historical protocol hashes should be interpreted against that original snapshot, not
silently updated to match this release. Trained model bytes and raw arrays are absent;
refer to the continuation guide for lawful reproduction and private artifact needs.

No corpus listed here may be advertised as a newly unopened final test again. New
model choices informed by these results require a genuinely new held acquisition.

The publication normalizes text to LF for portable Git checkout. Old execution
receipts retain the SHA256 of the original private Windows bytes; those digests must
not be silently recomputed after newline normalization. Evidence-copy receipts record
both private original and public representation hashes. Reconstruct exact historical
bytes from the private handoff archive when a byte-level original audit is required.
