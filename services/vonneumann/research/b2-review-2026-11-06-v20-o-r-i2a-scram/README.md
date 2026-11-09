# Direct SCRAM and credential expiry at COMMIT

One focused native case passed in 36.780 seconds in an isolated PostgreSQL 17.6
ARM64 container. Independent installer, recorder and reader connections used
TCP, SCRAM, verified TLS and required channel binding. A wrong hostname and
wrong CA failed before SQL. The correct reader over the fixture trust socket
was refused by the authorization guard.

The recorder staged an original Acquire before its database-issued credential
deadline. The same session remained connected after expiry. Its literal
`COMMIT` returned `42501 b2_credential_expired` while the staged fence would
still have been valid. A fresh recorder login failed. The independent reader
recovered the prior committed Install and confirmed that the Acquire was
unresolved and the committed state was unchanged. All 942 source files stayed
byte-identical. The owned process group and container were removed normally.
[Native receipt](native-receipt.json).

Reconstruct the six [I2a preimages](../b2-review-2026-11-06-v20-o-r-i2a/README.md),
apply the [forward patch](candidate-v20-o-r-i2a-to-v20-o-r-i2a-scram.patch)
and verify the [frozen manifest](candidate-manifest-v20-o-r-i2a-scram.json).
The [review and run recipe](DIRECT-SCRAM-AND-CREDENTIAL-CLOCK-REVIEW.md)
documents the exact source and clock conditions. Its preparation statements
predate the native receipt above.

All 44 inherited methods also pass on this exact SCRAM snapshot. The 41
ordinary cases took 161.148 seconds, the two real fence-expiry cases took
131.839 seconds, and the limited-issuer case took 9.009 seconds. Together
with the earlier direct SCRAM case, the runs cover all 45 test IDs once.
The 942 source files and 145 dependency files stayed byte-identical and
all three owned process groups and containers were removed normally.
[Inherited regression receipts](regression-receipts.json).

The issuer used the owned trust socket. The direct SCRAM fixture uses one
deadline for login and runtime authority and checks expiry at the recognized
COMMIT guard. Managed transport, independent write and recovery deadlines,
owner-separated terminal recording and hosted handoff remain separate gates.
