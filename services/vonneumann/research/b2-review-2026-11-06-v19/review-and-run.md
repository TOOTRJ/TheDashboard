# V19 narrow reader recovery and exact run

V19 preserves full catalog equality everywhere except a successfully
authenticated installed reader asking the public getter for one exact
committed original. The internal lookup uses the exact canonical scope
and original ID. It returns no data or mismatch marker before scoped
authorization. Wrong kind and absence use strict authorization. The private
assembler passes a recovery candidate only for a finalized target with the
same expected command digest. All submit, replay and dependency callers
pass false, including in the deferred COMMIT guard.

The recovery candidate is the target's actual stored writer binding.
The live reader must match the exact installed reader profile and genesis
ID. A distinct same-scope writer must match the immutable canonical binding
entry, capabilities, role name and role OID. The writer's one role in the
current full catalog must have LOGIN false. The verifier replaces only
that value with true in a transient object, preserves ordering, and checks
the original held digest. Changes to valid_until, the binding, ACLs and
any other catalog value prevent equality. The catalog object and original
evidence are never written. The historical assembler checks the actual
writer association and the exact committed original as before.

This exception is intentionally limited to the selected original's writer.
A different target's writer, second revocation and absent, mismatched or
provisional originals still use the existing strict refusal behavior. It
does not identify who issued NOLOGIN, establish an irreversible lifecycle,
or establish production access.

## Root-only run

- Manifest SHA-256
  `34942c24e6c9b84fdae89b1e402f3cb848756ad80913cc400a1cafe4dcf7ddba`.
- Forward patch SHA-256
  `1fad867b4adfbf8d92cfb82465767747bee27d5256c6577057a6eb33eb338e26`.
- Reference base is the exact prior PR113 commit
  `7ff9b886a2d19de5388b86a5c3985a8705567edc`, tree
  `9d6c512e6ea6f9b036cf82f7cc67199cc57dc4ae`. Compose 930 exact tracked
  files and the six hash-matched candidate postimages in a fresh owner-only
  temporary directory. Confirm 936 exact regular files and unchanged bytes.
- After independent review, use the previous locally verified isolated
  PostgreSQL 17.6 ARM64 image and Unix Docker socket, exact-owned process
  and container cleanup, allowlisted child environment, CPython 3.12.14,
  network none, and the same 240-second outer bound. Execute only the one
  explicit ID in the manifest. Preserve setup refusals and all raw results.
- The native case checks genuine reader recovery and unchanged originals,
  staged COMMIT denial, held-submit denial and fresh connection denial.
  Negative role/ACL/binding drift runs in rollback-only synthetic transactions.
  Positive reads always use the genuine independently authenticated reader
  connection. Required result is one actual method, zero failure/error/skip
  and normal exact-owned cleanup.
- Thirty-seven earlier methods are byte-identical. The frozen V18-R case
  remains prior counterexample evidence. Any regression run of prior methods
  on changed V19 SQL receives a separate exact manifest and receipt.
