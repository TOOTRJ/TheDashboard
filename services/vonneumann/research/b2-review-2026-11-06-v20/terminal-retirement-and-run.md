# V20 terminal retirement and exact root run

This private prototype implements the one explicit fixture-only boundary.
The stored marker binds the current V20 package and catalog digests, scope,
original reserved Stop ID and exact Stop Command hash, and the two exact
installed writer tuples. The trusted fixture uses fixed static role names
and validates their actual PostgreSQL OIDs and installed binding bytes.
It locks package, writer bindings, then scope head with NOWAIT, verifies
the exact open position-three head and intact K, and commits the two
LOGIN removals and the marker together. The worker source has no ALTER ROLE
or marker DML path. The existing broker's SHARE lock holds the marker
stable through the actor transaction.

The marker branch is evaluated before any raw-K acceptance. It requires
both actual NOLOGIN role bits, exact historical writer bindings and a full
original K match after substituting just those bits in memory. The actor
must still be the live, independently pinned control for exact Stop4.
Only its private, same-scope Resume3 dependency read receives terminal
context. COMMIT reauthorizes the same original. The independent reader
can recover the two selected writer originals and the exact committed
Stop. Unknown, different targets, nonreaders, submit replay and other
writes refuse. The two marker-free V19 paths retain their previous rules.

The integrated test uses fixed synthetic roles and checks actual owned
lock refusal, exact owner-only issuance, unchanged actor ledger during the
anchor update, two independently authenticated writer-original reads,
restored-login refusal with a marker still present, and unrelated catalog
drift refusal at recognized COMMIT. It then commits the same exact
reserved Stop after definitive synthetic failure and verifies independent
original readback and replay-through-submit refusal. The restoration is
owned fixture cleanup. The shared catalog includes both fixture scopes,
so the other scope is expected to fail closed during this experiment.

## Exact execution

- Verify the [manifest](candidate-manifest.json) SHA-256
  `61b97eff4123bbaa0970fcb886e1b1bb680bee6d2808fcf717cae0b255154740`.
- Verify the [forward patch](candidate-forward.patch) SHA-256
  `dbad5c8caac40fecb7f69dc7f9296ad8c019c621586137252f9d2dec282fd69c`.
  Reconstruct the six V19-R2 preimages in a fresh owner-only directory,
  apply the patch, and verify all six source hashes and lengths. All six
  already reconstructed in a separate static verification.
- Use 930 exact ordinary tracked files from PR113 commit
  `7ff9b886a2d19de5388b86a5c3985a8705567edc`, tree
  `9d6c512e6ea6f9b036cf82f7cc67199cc57dc4ae`, and the six private
  postimages, for 936 files. Compare every exact hash before and after.
- Independent source and controller review precede launch. Preserve the
  exact isolated local Unix Docker socket, cached PostgreSQL 17.6 ARM64
  image, network none, approved allowlisted child environment, CPython
  3.12.14, normal exact-owned cleanup, and the 240-second outer bound.
  Run only the manifest's one explicit ID. Preserve the raw receipt and
  log for any result. Separately pin any V19/V19-R2 regression methods
  exercised on changed V20 SQL.
- Accept the targeted proof only after one actual method with no errors,
  failures or skips, unchanged exact source and normal owned cleanup.
  The authoring step did not launch it.

The slice covers the open position-three terminal handoff in a fresh
independently sealed V20 fixture. Scope isolation beyond the fixture,
other positions and retirements, arbitrary privileged DDL, cross-package
archive recovery and any deployment require separate evidence.
