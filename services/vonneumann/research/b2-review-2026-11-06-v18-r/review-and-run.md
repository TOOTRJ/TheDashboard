# V18-R: nonreader retirement versus original readback

This private candidate adds one synthetic PostgreSQL test to exact frozen V18.
It does not change the V18 SQL, grant privileges, modify the checkout, or run
PostgreSQL. The already accepted V18 position-reserve case is separate evidence.

## Exact review and one-case recipe

- V18 manifest SHA-256:
  `589dae6165a38db4375a8a3f5bc2ff167d05b57b30e1d28149921edca5dd00d7`.
- V18-R manifest SHA-256:
  `e1bf98fcc74ce420d0b283a206687fdc521b63c1969e7fdf5a98cba4b57ef1fd`.
- Test-only patch SHA-256:
  `f399e9d04b93925652cb20e4579b29363559340854625c2e73d60dad7cf5e2cc`.
- Unchanged V18 SQL SHA-256:
  `164eaa4d0110a8aba421c3289ee64e8693e0968e9c6fda9e797a07591c402da7`.

All six V18 preimages match the original manifest, and all five non-test
postimages are identical. Removing the added method yields byte-identical
V18 test source; all 37 prior methods remain, and AST validation finds one new
method. The manifest records every postimage and the one explicit test ID.

For a separate root-reviewed native run, compose those six postimages with the
same 930 ordinary blobs from PR113 commit
`7ff9b886a2d19de5388b86a5c3985a8705567edc`, tree
`9d6c512e6ea6f9b036cf82f7cc67199cc57dc4ae`, in a fresh owned directory. Check
every before/after hash in the 936-file snapshot. Keep the accepted V18 local
Unix Docker endpoint, cached image identity, network none, CPython 3.12.14,
allowlisted child environment, exact-owned cleanup and 240-second outer bound.
Run only:

```text
tests.postgres.test_allocation_control_v3.AllocationControlNativeTests.test_revoking_nonreader_login_invalidates_unchanged_reader_catalog_pin
```

Require one executed case, zero failures/errors/skips/expected failures/
unexpected successes, and verified exact-owned cleanup. The case obtains a
committed original as the unchanged reader, changes only the fake installer to
NOLOGIN, expects `b2_package_refused` and unchanged stored snapshots, then
restores that disposable installer's original LOGIN in `finally` and verifies
the same original reply. This demonstrates the current failure mode; restoring
a live revoked actor is not a recovery recommendation. Preserve the raw test
receipt and log even if the run fails.

## Can the getter be split incrementally?

**Yes for capability isolation.** A forward package can grant a dedicated
recovery login `get_original` only and omit `submit`. Independently derive and
verify the new owner/ACL catalog expectations; keep the exact original-wire,
scope, writer-transaction and snapshot checks. This is useful hardening and
preserves the static seal. By itself it does not make recovery survive a
writer's NOLOGIN: V18's getter and `_reply` still reach the shared `_auth`, which
compares the same full catalog including that writer's mutable role facts.

**No as an unchanged-V18 fallback.** Calling `_reply` directly, accepting a
newly observed catalog digest, dropping the catalog check for the reader, or
keeping a revoked writer's login usable to preserve the digest would not prove
both requirements. Splitting only the public wrapper is insufficient because
the shared assembly path also authenticates the read.

**A bounded forward split can satisfy both.** Preserve the installation seal
over the exact target, package/broker/trigger definitions, owners, structural
ACLs and immutable actor identity/capability bindings. Move only explicitly
enumerated authority-lifecycle facts (such as LOGIN and expiry) into an
independently authorized, versioned binding-state policy. A reader checks the
structural seal, its own real name/OID and current read authority, plus the
immutable historical writer binding. It does not require the historical writer
to retain login or an unexpired write lease. A writer still verifies its actual
live authority and any required recorder dependency, under the matching locks
at admission and recognized COMMIT. Explicit retirement denies new logins and
new writes on held sessions; it does not rewrite original binding or receipt
bytes. Unauthorized role/ACL/owner drift still refuses.

If assembly is extracted from `_reply`, keep it a private helper behind checked
entry points. Audit submit's exact replay and prior-dependency callers too;
none may invoke it with an unverified scope or turn its output into new authority.
Require fresh read-only snapshots and preserve original-ID ambiguity on absence.
Before claiming retirement-safe readback, test both directions on owned PostgreSQL:
an admitted writer versus concurrent bounded retirement, post-retirement held
and fresh writer denial, unchanged independent reader success, revoked/foreign
reader denial, role recreation, unauthorized catalog drift and unchanged
original bytes. This needs a new reviewed policy/package; it changes neither
the existing v5 release nor V18's accepted evidence.
