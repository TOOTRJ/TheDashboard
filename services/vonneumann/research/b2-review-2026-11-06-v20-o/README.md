# V20-O combined ownership and terminal retirement

The combined candidate keeps the trusted anchor tables and lock broker under
the dedicated `NOLOGIN` owner. The separate native owner retains read and
broker access. The isolated fixture administrator records the terminal marker
and retires the two exact writers in one transaction. The independent reader
can recover their committed originals, and the live control can commit only
the reserved Stop. Both focused cases passed together.

All 41 native cases then passed on the exact PR115 main base. The 39 ordinary
cases and two database fence-expiry cases used the same 942-file snapshot as
the focused run. All three runs completed with exact source equality and
normal owned cleanup. [Native receipts](native-receipts.json)

Reconstruct from either the [V19-O parent](../b2-review-2026-11-06-v19-o/README.md)
or the [V20 parent](../b2-review-2026-11-06-v20/README.md) using the matching
patch named in the [manifest](candidate-manifest-v20-o.json). The [review and
run recipe](ownership-composition-and-run.md) identifies both exact source
bases and the focused tests. The observed test receipts use the PR115 base.

The test administrator is a disposable fixture superuser. The [managed
issuer compatibility design](managed-issuer-compatibility.md) separates the
creator grant, real credential expiry and owner-authorized terminal recording.
Those managed tests and the production installer remain open.
