RotorVibe 0.1.0a4 integrates the P0–P2 development series into a new alpha release.

P0 fixes model scope/numeric validation, common decisions and version-tagged
publishing. P1 adds scoped normal fit/calibration, acquisition provenance,
angle-domain experiments, hold guidance, evaluation, lifecycle and bounded queues.
P2 adds isolated callback results, an actual exact-version process bridge, hashed
profile envelopes, bounded PSD history, reviewed rules and explicit life experiments.

The README lists module purposes, input/output parameters, units and composition
contracts. Reproduction and continuation details are in docs/RELEASE_0_1_0a4.md,
P0/P1/P2 reports, API_REFERENCE.md and CONTINUATION.md. Local preparation passed
224 tests, seven documentation examples in two clean environments and 58 additional
engineering checks. Publication is gated by cross-environment CI and installed-wheel
regressions; final public downloads are independently checked after publication.

Compatibility changes: each sink/stage receives a private result snapshot; edits
are not transmitted implicitly to later consumers. Reference-life estimation and
LifeStage now default disabled and require explicit experimental opt-in. The
optional process bridge supports version 0.1.0 from the documented pinned commit.
Heatmap PSD uses conservative frequency bins, fixing lost narrow tones; classifier
features remain unchanged. Old native profiles still need their native validators.

No new independent fault-classification accuracy, field normal FPR, field RUL,
calibrated prediction interval, standard certification or automatic trip authority
is claimed. A 48kHz/four-channel burst case exceeded 250ms latency 17 times.
New P1 raw waveform candidates remain unassigned. External raw files, source PDFs,
standard tables, trained rig-specific models and external package source are excluded.
Original code/docs: MIT. Previous 0.1.0a1 artifacts are retained unchanged.
