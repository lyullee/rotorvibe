RotorVibe 0.1.0a4 is an unshipped P2 candidate including P0 and P1.

P2 adds protected callback snapshots, an exact-version optional process bridge,
common inert profile envelopes, bounded spectrogram accumulation, reviewed rule
providers and explicitly disabled-by-default experimental reference-life matching.
See P2_GUIDE.md and P2_VERIFICATION.md for contracts, migration and executed checks.

Compatibility changes: sink identity differs from the returned result; sink edits
are private; unknown optional-package versions are refused; life experiments need
explicit opt-in. Heatmap rows use mean PSD frequency bins with preserved integrated
power rather than interpolation that could omit narrow tones. Model features stay
unchanged. Existing raw acquisition, model and output scopes remain enforced.

No new measured fault accuracy or field remaining-life accuracy is claimed.
Complete/censored operating lives and statistically calibrated prediction intervals
still require independent qualification. P1's high-rate burst latency limitation
remains; no hard realtime guarantee. The archived public 0.1.0a1 is unchanged.
External datasets/standards and the optional package retain their own rights.
