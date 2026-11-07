# V19-O dedicated anchor ownership

The focused native case passed in 9.707 seconds on the 936-file snapshot. It
verified that neither of the two owner roles can log in, that none of the eight
runtime actors can assume either owner, and that the lock broker admits the
expected installation while preserving the anchor rows. An owner login change
and an added owner membership each caused refusal. Rolling back each synthetic
fault restored the exact original read and preserved committed state.

All 39 cases also passed on the exact PR115 main base, including 37 ordinary
cases and two tests using actual credential expiry. Both runs verified the
same 942 source files before and after, with normal owned container cleanup.
The 39 count includes the focused case exercised again on that base.

Apply the [forward patch](candidate-forward.patch) to the reconstructed
[V19 candidate](../b2-review-2026-11-06-v19/README.md). The [manifest](candidate-manifest.json),
[review recipe](anchor-owner-and-run-review.md) and [native receipts](native-receipts.json)
pin the ownership change and the results. The managed issuer's creator-grant
shape, V20's terminal retirement marker and a production installer require
separate composition and review.
