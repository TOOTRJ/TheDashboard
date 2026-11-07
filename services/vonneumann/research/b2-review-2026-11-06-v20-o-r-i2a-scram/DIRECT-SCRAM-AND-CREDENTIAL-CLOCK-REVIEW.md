# Direct SCRAM and credential deadline at literal COMMIT

This source packet extends the native-tested I2a candidate. Four of six files
change. The held loader and finite policy stay byte-identical. The actual held
loader checks eight unchanged table declarations, the fixed broker and 16
unchanged signatures. Only `_auth` changes. All 44 inherited methods are
byte-identical. The exact forward/reverse reconstruction, six source hashes,
pinned tracked helper bytes and 45 test IDs pass offline checks.

## Scope

An explicit new trusted fixture package-input format requires real direct
SCRAM session identity and a TCP peer. It is selected by the owned installer,
not a caller flag. It additionally requires the existing limited creator
profile and finite role `VALID UNTIL` ahead of `clock_timestamp()`. This guard
applies to the actual actor and required live dependencies after existing
broker locking, and at the recognized deferred COMMIT path. Historical
association checks remain unchanged and do not require an old writer's active
credential. The old socket-trust package format preserves prior behavior.

Use the existing tracked test CA/TLS server, SCRAM verifier generator and
allowlisted owned harness. The new direct libpq path pins `hostaddr=127.0.0.1`,
`sslmode=verify-full`, reviewed synthetic CA, required channel binding and a
2-second connect timeout. No SET ROLE, external traffic, host mounts, shared
configuration, or real credentials. Each generated password lives only in
memory and a mode-0600 owned container tmpfs passfile. The limited creator
uses synthetic SCRAM verifiers with bounded absolute deadlines. Fixture
issuance refuses with a sanitized fixed message if its SQL fails. The client
separately reads the session's own `pg_stat_ssl`, outside any definer. The
SQL guard uses `system_user` and the actual peer, since it cannot rely on
unredacted TLS statistics from inside a definer.

## Exact focused acceptance

1. Require independent real TCP SCRAM sessions and active TLS for installer,
   recorder and reader. Wrong hostname and wrong CA must fail before SQL.
   The same correct reader role over the owned trust socket must refuse.
2. The real limited issuer independently produces the same eight creator edges.
   Compare the eight finite absolute deadlines against real PostgreSQL role
   catalog values before sealing. The recorder has 35 seconds and all seven
   other actors have 180 seconds, from one actual database clock sample.
3. Commit the exact original Install and obtain its independent readback. Use
   the actual database clock to stage one provisional recorder Acquire starting
   6 seconds before its deadline, with more than 2 seconds still remaining at
   the stage start. Require provisional acknowledgment before expiry and no
   committed original on the independent reader.
4. Wait on the real database clock until at least 150 ms after the deadline.
   Verify the same authenticated recorder connection is alive, then send a
   single literal COMMIT. Require exact `42501 b2_credential_expired`. The
   observed interval must still be less than 60 seconds since before staging,
   ruling out expiry of the newly staged fence as the refusal cause. No local
   clock adjustment, fixture timestamp edit or role mutation creates expiry.
5. Require a fresh recorder login failure, unchanged committed rows and exact
   prior Install and unresolved Acquire readback from a fresh live reader.

This proves a recognized COMMIT guard point, not the final-visible instant.
It uses one role deadline for both login and runtime authority. Separate write
and recovery windows, owner-separated issuer retirement, finite handoff and
managed/hosted deployment remain separate gates. It changes no owner, ACL,
broker or retirement semantics and does not select a production credential TTL.

## Reviewed run recipe

Reconstruct the six I2a preimages, apply the frozen forward patch in an owned
private directory and verify every postimage hash and byte count. Use exact
PR115 main, tree and 942-file composition from the manifest. In the pinned
controller, collect all 45 source IDs across the no-issuer, direct SCRAM and
managed creator test classes, then execute only this new exact case:

```text
tests.postgres.test_allocation_control_v3.AllocationDirectScramNativeTests.test_direct_scram_actor_credential_expires_before_literal_commit
```

Retain the approved cached PostgreSQL 17.6 ARM64 image and explicit local Unix
socket, CPython 3.12.14 locked environment with the existing cryptography
package, network none, no pull or mounts, allowlisted environment, 240-second
outer timeout, immutable source inventory and normal exact-owned cleanup.
A missed real clock window is a refusal; do not widen or retry the experiment
implicitly. Keep the native receipt and raw log separately. Run old classes
separately before claiming regression coverage on this changed SQL. No native
execution was performed while preparing this packet.
