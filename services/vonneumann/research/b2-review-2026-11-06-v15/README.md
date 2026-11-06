# B2 V15 Resume and open Stop review archive

The exact V15 candidate passed 34 native PostgreSQL tests in the isolated
laboratory. The suite took 204.871 seconds under the 240-second outer bound
with zero failures, errors or skips. The snapshot held 930 exact PR113 Git
blobs and six candidate postimages. All 936 source files matched afterward,
and the owned container and process group exited through normal cleanup.

Resume binds the locked current head and fence revision, authenticates the
actual control principal, and checks the installed recorder binding under a
row lock through COMMIT. It leaves the same fence in place and opens the
source. The original reserved Stop can close from open mode while the
recorder binding row is locked. The separate expiry test uses two bounded
reads tied to the actual retained expiry. The provisional Resume refuses at
COMMIT after expiry, a fresh Resume refuses, and the reserved paused Stop
still completes. The whole-package seal continues to reject role or catalog
drift.

The native witness covers six direct dependencies and ten closure pins for
Resume, and six direct dependencies and thirteen closure pins for open Stop.
The full path has 56 retained rows, 54 logical writes and 108 logical keys.
Including staging, it touches 58 rows and 120 keys. These are logical
observations. The next renew transition makes the prior control and prior
head pins distinct for the seven-direct-pin Stop proof.

Reconstruct the six files from the [V14 archive](../b2-review-2026-11-05-v14/README.md)
in an owned temporary copy, apply the [forward patch](candidate-forward.patch)
and verify the [V15 manifest](candidate-manifest.json). The
[native receipt](native-receipt.json) binds the actual test run, snapshot,
controller, raw log and cleanup. These review files preserve the source and
evidence for later adoption. The worker runtime, database migration and
hosted admission paths are separate.
