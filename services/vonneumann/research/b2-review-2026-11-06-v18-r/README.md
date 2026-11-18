# B2 V18-R readback after writer revocation

The standalone PostgreSQL case reproduced a recovery failure in 8.096 seconds.
An independent reader could retrieve the committed original before the fixture
installer was changed to `NOLOGIN`. The same reader could still connect but
received `b2_package_refused` afterward. Stored rows stayed identical. The
fixture restored the disposable role and verified the complete original reply
again. The separate test adds one case and uses unchanged V18 SQL.

The shared catalog seal includes the installer’s live login flag. A production
recovery reader needs the immutable package and actor seals, current authority
for its own scope, and access to committed original replies after another
actor’s authorized retirement. The
[ownership and getter design](review-and-run.md) records those boundaries.

Reconstruct the exact [V18 source](../b2-review-2026-11-06-v18/README.md) and
apply the [test-only patch](candidate-forward.patch). The
[manifest](candidate-manifest.json) and [native receipt](native-receipts.json)
bind the run to the single case, snapshot, fixture and normal cleanup.
