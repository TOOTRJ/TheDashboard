# V19-R2 retirement boundary

The isolated PostgreSQL case passed in 10.530 seconds on unchanged V19 SQL.
The valid reserved open Stop reached a provisional result and rolled back
before the role changes. With the first synthetic writer set to `NOLOGIN`,
the reader could recover that writer’s exact original and the live control
session could no longer stage the reserved Stop. With both synthetic writers
set to `NOLOGIN`, both original reads and Stop returned the package refusal.
The committed table snapshots stayed identical. Restoring the disposable
fixture roles restored both exact original replies.

This is a counterexample for controlled retirement. The focused test used
genuine independent reader and control connections, with normal cleanup.
It leaves the production retirement and terminal recovery package open.

Reconstruct the exact [V19 files](../b2-review-2026-11-06-v19/README.md) and
apply the [test-only patch](candidate-forward.patch). The [manifest](candidate-manifest.json)
and [native receipt](native-receipt.json) pin the single case and snapshot.
The [terminal retirement design](terminal-retirement-design.md) proposes an
owner-authorized batch with an exact original Stop and a scoped lock order.
The design requires its own implementation and native proof.
