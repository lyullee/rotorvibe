RotorVibe 0.1.0a3 is an unshipped P1 candidate including the earlier P0 fixes.
It adds acquisition declarations, scoped normal registration and separate calibration,
angle-domain experimental models, actionable holds, lifecycle hooks, bounded queues,
coverage/alarm metrics and prospective validation access. See docs/P1_VERIFICATION.md.

New archives remain sealed candidates; no new independent measured-data accuracy is
claimed. A 48 kHz/4-channel burst workload exceeded a 0.25 s latency budget. No field
diagnostic certification or hard realtime guarantee is supplied. Existing archived
0.1.0a1 remains unchanged. External data rights remain separate from software MIT.
