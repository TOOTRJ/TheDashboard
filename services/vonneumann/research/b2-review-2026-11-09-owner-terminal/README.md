# Owner-separated terminal retirement

Two focused cases passed in 12.957 seconds in isolated PostgreSQL 17.6.
The closed setup case independently verified the exact companion catalog and
restricted grants. The second case used a real limited SCRAM issuer and actual
control and reader logins. Direct table and owner-assumption attempts refused.
A competing writer blocked retirement at the package lock. A literal COMMIT
after disabling only the first writer rolled back the marker and role change.
Early `SET CONSTRAINTS … IMMEDIATE` refused both before role changes and after
both logins were disabled. The exact snapshots and original reader replies
survived each refusal.

The authorized literal COMMIT disabled both exact writer logins and recorded
one terminal marker, leaving the native rows unchanged. The live control
committed the original reserved Stop at position four. The independent reader
recovered both prior writer originals and the exact Stop receipt. The test
covered one scope at position three with a single preauthorized permit. An
independent fixture administrator read the committed marker. A production
permit reader, continuing-run handoff and managed adoption remain separate.

Reconstruct the six exact [SCRAM files](../b2-review-2026-11-06-v20-o-r-i2a-scram/README.md)
and apply the [forward patch](candidate-forward.patch). The
[manifest](candidate-manifest.json) pins seven postimages, including one new
SQL companion. The inherited SCRAM SQL, loader, policy and 45 test method
bodies remain byte-identical. The prior SCRAM regression receipts apply to
that earlier source. The companion loads only in the new owned fixture.

The [native receipt](native-receipt.json) records two selected cases, zero
errors, failures or skips, 943 unchanged source files, unchanged dependencies
and normal owned cleanup. The controller and raw log are retained by hash.
The [source and run review](owner-terminal-and-run-review.md) describes the
exact overlay, authority and focused run conditions.

The [continuing-run design](credential-deadlines-and-one-scope-handoff.md)
keeps the original journal and receipts across one scoped recorder handoff.
The [Stop ordering addendum](stop-dispatch-addendum.md) requires durable
original Stop intent before dispatch, with a successor renewal refusal
under the same lock. The [intent contract and race cases](durable-stop-intent-guard.md)
specify the bounded row and acceptance tests once the true successor is
available in submit, COMMIT and readback.
