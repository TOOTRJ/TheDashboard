# B2 V19 exact reader recovery after one writer loses login

The focused native PostgreSQL case passed in 11.810 seconds. The independent
reader obtained the identical committed original after its pinned writer
lost LOGIN. The staged writer COMMIT, a later write on a held connection
and a fresh writer connection were refused. The getter still refused the
wrong original, unrelated catalog changes and a second role retirement.
All 35 ordinary regressions and both real-expiry cases also passed on the
same 936-file snapshot, for 38 cases across three bounded runs. All fixtures
and process groups exited through normal cleanup.

The getter checks its actual live reader and selects the writer from the
finalized original in the same scope, with the exact kind and command
digest. It compares the full held catalog digest after substituting the
single writer login bit in memory. Submit, submit replay, dependency
checks, COMMIT and nonreader reads still require the strict catalog seal.

The scope is a same-installation PostgreSQL experiment. Production
retirement needs an explicit lifecycle and an original-preserving handoff.
Reserved Stop during catalog changes, held-position recovery, broader
storage limits and the hosted roles and runtime package remain separate.

Reconstruct the six exact [V18-R files](../b2-review-2026-11-06-v18-r/README.md),
apply the [forward patch](candidate-forward.patch), and check the
[manifest](candidate-manifest.json). The [native receipts](native-receipts.json)
bind the observations to their exact source and owned fixture.
[Run recipe and review](review-and-run.md)
