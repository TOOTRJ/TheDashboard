# B2 V16 Renew and seven-pin Stop review archive

The exact candidate passed all 35 native PostgreSQL cases, including the
34 V15 cases, with no failures, errors or skips. The suite ran in 169.337
seconds under the 240-second outer limit. All 936 source files stayed
byte-identical, and the owned process group and network-isolated container
exited through normal cleanup.

In the new case, the installed recorder renews an open hold without
allocating a new fence identity. The old and new fence versions remain
distinct immutable facts. The original reserved Stop pins the previous
control command (Resume), the previous head (Renew) and the renewed fence.
This yields seven distinct direct pins and a 17-pin readback closure.
The test checks exact original replay and observes 68 retained rows,
67 logical writes and 134 logical keys across the five-event path, rising
to 72 row touches and 149 key touches with staging.

The [reserve worksheet](reserve-review.md) bounds Stop bytes for this
admitted path. The native test observes the selected wire shape and
accounting. Late expiry during Renew COMMIT, repeated renewal up to the
position limit, broader admitted maxima, production ownership and hosted
adoption are separate gates. The [next proof plan](next-proof.md) describes
the expiry and position witnesses.

Reconstruct the six exact [V15 files](../b2-review-2026-11-06-v15/README.md),
apply the [forward patch](candidate-forward.patch), and check the
[manifest](candidate-manifest.json). The [native receipt](native-receipt.json)
binds the actual run to the manifest, snapshot, controller, ordered cases
and cleanup. These files are evidence for review. They do not change the
worker runtime, deployed database or hosted admission.
