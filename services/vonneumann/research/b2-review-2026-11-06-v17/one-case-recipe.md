# V17 one-case late Renew test

The [manifest](candidate-manifest.json) names one exact native case.
Its SHA-256 is
`4ed0a39ebf69aca88a7ff4a73014c64e273d2ad9082d91d6b1b93cc867598110`.
The [test-only patch](candidate-forward.patch) SHA-256 is
`48c3f6cd2e79765729f93c1a4566eda69a56b202c96e91c6a68a718c10b12cec`.
All six postimage hashes verify after applying it to a fresh copy of exact
V16. All 35 V16 method bodies and the other five source files are identical.

Compose the six postimages against the exact prior accepted PR113
snapshot base, commit `7ff9b886a2d19de5388b86a5c3985a8705567edc`, tree
`9d6c512e6ea6f9b036cf82f7cc67199cc57dc4ae`. Its 930 tracked files
plus six private postimages give 936 files. Use an owned, owner-only
export and require absent candidate destination paths before copying.
Confirm all hashes before and after. Review any newer base separately.

After independent source and controller review, keep the accepted V16
controller's exact local Unix socket, immutable cached PostgreSQL 17.6
ARM64 image, opt-in and allowlisted child environment, normal exact
owned cleanup, CPython 3.12.14 and 240-second outer limit. Replace only
the case list, its expected count, and the version-specific pins. Run
the one explicit test ID in the manifest. Do not use broad discovery.
Accept one actual method, zero failures/errors/skips/expected failures/
unexpected successes, exact snapshot equality, and normal owned cleanup.
Retain original raw log and receipt regardless of the result.

The actual acquisition clock drives the three owned reads. Resume waits
until issue plus 10 seconds, the writer begins near old expiry minus
5.5 seconds, and COMMIT is bracketed after old expiry plus 100 milliseconds
and before Resume COMMIT plus 60 seconds. The latter is a conservative
lower bound on any new fence expiry from the unchanged V16 issuance rule.
The test also verifies a provisional exact-original response, separately
invisible original, guard SQLSTATE and context, unchanged table snapshots,
fresh expired Renew refusal, and original Stop from open at position four.
The active writer keeps its existing limits and every clock read uses the
owned PostgreSQL clock. A missed wall-clock window leaves this case unproved.

Report the V16 35-case run and V17 one-case run as separate receipts against
identical SQL. V17 preparation was static only.
