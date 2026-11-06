# B2 V14 paused fence acquisition review archive

V14 passed 29 actual native PostgreSQL cases in the private laboratory. The
tests took 63.689 seconds, with zero failures, errors or skips. The snapshot
contained 923 exact Git blobs from PR112 head `86f07f7` and six candidate
postimages. All 929 file hashes matched afterward. The approved cached
PostgreSQL 17.6 image ran with networking disabled. The exact container and
process group were gone after normal cleanup.

The candidate adds one bounded operation between installation and the original
reserved Stop. The installed recorder acquires a fence from the database
clock and leaves the source paused. The original Stop binds that committed
fence and clears the active hold while retaining its evidence. Acquisition has
five direct pins and a seven-pin readback closure. Stop with that fence has
six direct pins and a ten-pin closure. The complete witness has 47 retained
rows, 44 logical writes and 88 logical keys, with 47 row and 97 key touches
including staging. These are logical observations, separate from storage
and WAL measurements.

V13 was rejected in source review. Its deferred guard would mark an acquire
as stopped and prevent the reserved Stop. V14 corrects that branch and
preserves all 29 test methods from the rejected candidate. The first
controller preflight refused before test import when macOS injected a locale
marker. The separately pinned runner removed only that Darwin-injected marker
before comparing the complete child environment, then ran the native suite
once. The receipt preserves both outcomes.

Reconstruct the six verified V12 postimages from the
[V12 archive](../b2-review-2026-10-21-v12/README.md) in a new owned copy.
Apply [the V12-to-V14 patch](candidate-forward.patch) to that copy and
check all six hashes against the [candidate manifest](candidate-manifest.json).
The [native receipt](native-receipt.json) binds the exact snapshot, controller,
ordered test IDs, result, raw log and cleanup observations.

This is review evidence. The native package, source loader and tests remain
outside the runtime paths. B2 stays open for Resume and renew, the full
seven-direct-pin Stop proof, independent capacity and owner review, CI, and
separately reviewed production adoption.
