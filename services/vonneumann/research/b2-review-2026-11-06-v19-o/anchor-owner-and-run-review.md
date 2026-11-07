# V19-O: dedicated laboratory anchor owner

Private source candidate only. No database, container, remote project, credential
or repository file was touched. V19's accepted runtime evidence remains separate.

The existing constructor comparison runs before ownership transfer, against the
same independently constructed table and trigger definitions. A following owned
fixture transaction transfers the anchor schema, its two tables and the exact
`_lock_inputs(text,bool)` broker to `vn_jupiter_b2_anchor_owner`. The native
schema, tables, trigger and functions stay with `vn_jupiter_b2_sealed_owner`.
Both are distinct `NOLOGIN`, `NOINHERIT` roles with no elevated attributes or
membership edges. The final anchor owner explicitly grants only anchor schema
USAGE, SELECT on its two tables, and EXECUTE on its fixed broker to the native
owner. The original pre-transfer broker grant is removed from the SQL suffix.

The fixture independently checks final owner and grantor identities, exact ACLs,
no column ACL additions, table and generated row/array type ownership, both
owner profiles, effective cross-schema/table access and the closed membership
inventory before capturing instance-specific catalog gold. The original runtime
actors retain their exact V19 entry grants. They cannot assume either owner.

`_catalog` now includes the dedicated anchor owner's actual role attributes
and its inbound/outbound membership edges. It retains all V19 catalog fields.
The broker body, all eight table definitions, and the other fifteen native
function bodies are byte-identical. V19's exact reader exception still permits
only the selected original writer's LOGIN bit to differ; owner drift is never
normalized. Lease, Stop, counters, canonical protocol and replay policy stay
unchanged. This slice does not add a managed creator-edge policy, getter-only
ACL, scoped issuer, finite credential expiry, retirement workflow or hosting.

## Exact future run

- V19 manifest: `34942c24e6c9b84fdae89b1e402f3cb848756ad80913cc400a1cafe4dcf7ddba`
- V19-O manifest: `b1da0baaa9262097f69720ae21650703924abcc0844b9216368ac66d494a59dc`
- Forward patch: `b915a8cb6034e5a63143c83024c93f99219b61635c72c9c23af5ee7fa6a86c1d`
- V19-O SQL: `fbee6b885ddbfccfb8e84169811c68fa2824ca3de252315aa13adef51b50f1ea`

Check all six exact V19 preimages, apply the patch in a new owned private copy,
and verify every postimage in `candidate-manifest-v19-o.json`. The finite policy
file stays identical. The new test is an insertion: all 38 prior methods and
their IDs stay byte-identical, for 39 methods present in source.

Use the same 930 exact ordinary blobs from PR113 commit
`7ff9b886a2d19de5388b86a5c3985a8705567edc`, tree
`9d6c512e6ea6f9b036cf82f7cc67199cc57dc4ae`, plus the six pinned postimages.
Verify exact 936-file input and output equality. Only after independent review,
the root operator may use the same reviewed local Unix Docker endpoint, cached
PostgreSQL 17.6 ARM64 image, isolated environment, network none, CPython 3.12.14,
240-second deadline, exact-owned cleanup and the one explicit test ID:

```text
tests.postgres.test_allocation_control_v3.AllocationControlNativeTests.test_dedicated_anchor_owner_denies_assumption_and_seals_role_drift
```

The new case checks both fresh owner logins and all eight actors' actual
`SET ROLE` attempts, proves an admitted broker-mediated installation preserves
the anchor rows, and refuses two separate rollback-only owner drifts. It checks
exact original readback and unchanged stored snapshots after each failed drift.
The second drift creates a disposable probe role only inside the same synthetic
transaction so membership closure is tested without another previously pinned
role changing. It verifies that the probe did not survive. The owner LOGIN
fault is also transaction-local and never commits.

Accept one actual case with zero failures, errors, skips, expected failures or
unexpected successes, exact source equality and normal owned cleanup. Preserve
the receipt/log for any result. Regression execution of the prior 38 methods on
this changed SQL is a separate exact-source gate, preferably keeping the proven
ordinary, reader and real-expiry partitions. Prior V19 results do not accept
the new ownership seal. No managed or hosted operation follows this proof.
