# V20 bounded terminal retirement

One focused test passed in 12.801 seconds in an isolated PostgreSQL 17.6
container. The fixture administrator verified the exact open head at position
three, took the prescribed locks, and made two pinned writers `NOLOGIN` in the
same transaction as the terminal marker. The independent reader recovered both
exact originals. The live control could commit only the reserved Stop at
position four, and the reader recovered its exact committed result. A held
writer blocked retirement. Unrelated catalog drift prevented COMMIT, and
restored login bits with the marker still present caused refusal.

Apply the [forward patch](candidate-forward.patch) to the reconstructed
[V19-R2 candidate](../b2-review-2026-11-06-v19-r2/README.md). The [manifest](candidate-manifest.json)
and [native receipt](native-receipts.json) pin the exact source and observed
result. The [pre-run review](terminal-retirement-and-run.md) describes the
authority, lock order, test and scope. All 936 source files matched before and
after the test, with normal cleanup.

V20 keeps the original laboratory anchor owner. Composition with V19-O,
full regression, partial-retirement rollback, the commit-wins lock case and the
managed owner and credential design remain separate. This archive supplies no
production migration or runtime admission.
