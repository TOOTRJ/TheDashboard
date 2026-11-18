# One-recorder handoff and durable Stop intent

The corrected candidate passed three focused cases on disposable,
network-disabled PostgreSQL 17.6. It uses synthetic credentials and direct
TLS-verified SCRAM connections. A fixture-owned witness independently
confirms the committed issuance marker. A scoped independent reader
recovers the exact original operations and Stop intent.

| Case | Observed outcome |
| --- | --- |
| Recorder handoff | A limited issuer retired the original recorder and enabled one successor in the same transaction. A held old session could no longer write, and a fresh old login failed. The successor committed the exact authorized Renew on the existing fence. The independent reader recovered the original Install, Acquire and Resume receipts. |
| Stop intent commits first | A provisional intent was invisible to the independent reader. The successor visibly waited on the same scope lock, then refused Renew after the intent committed. The reader recovered the exact intent and the control committed the original reserved Stop at position 4. |
| Renew commits first | The control visibly waited to register Stop at the previous head. The committed Renew made the old intent stale before registration or dispatch. At the new head, the reader independently recovered the first committed intent after the registration response was discarded. The control committed Stop at position 5 using the same preallocated action ID. |

The fixtures also exercise rollback after an incomplete handoff, early
constraint forcing, attempted registration and dispatch in one transaction,
changed Stop bytes, and altered control binding. Every accepted run verified
its exact source inventory and normal cleanup.

All 49 inherited cases passed on the same corrected snapshot, including
real fence expiry, limited issuance, direct SCRAM expiry, independent
application deadlines and owner-separated retirement. The full candidate
passed 52 native cases across 11 isolated fixtures with zero skips.
[Native receipts](native-receipts.json).

## Reproduce the held candidate

Start with the seven-file [retirement and deadline parent](../b2-review-2026-11-09-retirement-deadline/README.md).
Apply the [handoff and Stop patch](candidate-retirement-deadline-to-generation-stop.patch)
and verify the [first manifest](candidate-manifest-generation-stop.json).
Then apply the [parser correction](candidate-generation-stop-to-r2.patch)
and verify the [final manifest](candidate-manifest-generation-stop-r2.json).
The first native attempt failed in fixture installation because PostgreSQL
rejected the helper argument named `position`. R2 renames it and updates the
fixture's matching catalog expectation. The test methods and policy bytes
are identical. [Failed installation receipt](failed-r1-native-receipt.json) ·
[Original review and run recipe](GENERATION-STOP-REVIEW-AND-RUN.md) ·
[Parser correction record](R2-PARSER-REVIEW.md).

The runner combined the ten pinned files with 936 tracked PR115 blobs.
PR117's subsequent production changes are confined to seven Nestegg files.
The lab covers one scope, one recorder replacement and one durable Stop
intent. The independently observed intent must still be wired into worker
dispatch. The managed issuer, scoped issuance-marker readback, repeat
rotation, post-handoff terminal retirement and physical storage capacity
require separate evidence. The
[durable capture fixture](../b3-review-2026-11-10-durable-acquisition/README.md)
is also separate. Join it to this same scope, journal, head and fence before
closed managed installation and hosted interruption testing.
