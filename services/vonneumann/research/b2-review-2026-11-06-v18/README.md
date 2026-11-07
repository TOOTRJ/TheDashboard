# B2 V18 repeated Renew and reserved Stop

The isolated PostgreSQL test committed twelve renewals at positions 4 through 15.
The next otherwise valid Renew reached the reserve check at position 16 and
refused without changing committed rows. The other budget dimensions fit.
The original Stop then committed at position 16 with seven direct dependency
pins and a 61-pin getter closure. Its original reply replayed exactly.

The final scope had 189 retained rows, 199 logical writes and 398 logical
keys. Including staging, it touched 215 rows and 446 keys. The position
case passed in 16.715 seconds. The separate groups of 34 ordinary and two
real-expiry regressions passed in 94.646 and 131.728 seconds respectively.
All 37 cases used the same 936-file snapshot across the three runs, each
under its 240-second limit and with normal owned process and container cleanup.

In a separate successful run, a read-only query measured 884,736 allocated
relation bytes across the fixture’s eight tables, including their indexes
and TOAST. The 189 rows in the stopped scope held 349,651 canonical text
bytes. Its contract accounted for 474,252 logical bytes. The physical
measurement covers both synthetic scopes and one small fixture. It leaves
long-run growth, write-ahead log usage and hosted capacity open.
The [observer diff](storage-observer.patch) is included for review. The
historical controller preimage and raw log are identified by hash in the
[measurement receipt](storage-receipt.json).

Reconstruct the six [V17 files](../b2-review-2026-11-06-v17/README.md),
apply the [forward patch](candidate-forward.patch), and check the
[manifest](candidate-manifest.json). The [native receipts](native-receipts.json)
bind the runs to their exact sources and ordered cases. The
[reserve worksheet](review-and-run.md) records the independent calculation.
Full storage limits and production owner and recovery behavior need separate
proof. The [reader revocation result](../b2-review-2026-11-06-v18-r/README.md)
identifies one of those gaps.
