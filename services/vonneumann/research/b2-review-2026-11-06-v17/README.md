# B2 V17 late Renew expiry review archive

One standalone native PostgreSQL case passed in 70.645 seconds with no
failures, errors or skips, under the same 240-second outer limit. All 936
files stayed byte-identical and the owned process and network-isolated
container exited through normal cleanup. The earlier [35-case V16
run](../b2-review-2026-11-06-v16/README.md) is separate evidence. This
candidate changes only the test file by adding one method.

The recorder started Renew before the old fence expired. The writer
received the provisional result while an independent reader saw no
committed original. Literal COMMIT after the old expiry and before the
earliest possible renewed expiry returned the exact fence-clock refusal.
The committed snapshots stayed unchanged. A fresh Renew against the
expired hold refused. The original reserved Stop then closed from open
mode at position 4.

Reconstruct the exact V16 files, apply the [test-only forward patch](candidate-forward.patch),
and compare the [manifest](candidate-manifest.json) and [native receipt](native-receipt.json).
The [recipe](one-case-recipe.md) records the one-case selection and clock
bound. Repeated Renew at the position limit, broader capacity and hosted
adoption remain separate.
