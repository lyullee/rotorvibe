RotorVibe 0.1.0a2 candidate fixes four P0 contracts: strict fault-profile scope and
schema loading, finite numeric distance handling, explicit common decision/alarm
composition, and immutable tag-based build/publish without source restoration.

DecisionStage and normalize_decision are additive APIs. Malformed profiles previously
accepted now raise ValueError; invalid caller scope holds, extreme features raise
ValueError, and held scores cannot recover an alarm. Set alarm thresholds for the
selected score definition; no automatic recalibration or fault probability is supplied.

This is an unshipped candidate until an explicit validated release tag is published.
No new training or independent measured-data performance claim is made. Cross-rig
limitations and copyright exclusions remain. See docs/P0_VERIFICATION.md and README.
