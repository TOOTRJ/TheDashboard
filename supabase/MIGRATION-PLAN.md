# Worker schema repair — 2026-09-30

Authorized target: **The Dashboard**, project `fxpxsciltakyypunglzr`, organization
`cqfnnaunmupdyobkyqfo` (Valentine Jester). No other project is in scope. The user
authorized applying migrations after verification of this exact target.

**Execution result:** both files were applied successfully on 2026-09-30. The
ledger contains all 12 versions, with no pending migrations. Catalog comparison,
the temporary-table contract script, and a zero-row PostgREST read pass. The CLI
emitted `SET LOCAL can only be used in transaction blocks` for the requested
timeouts, so their enforcement was not verified. The limits below describe the
reviewed intent, not a proven runtime guarantee. Keep the exact applied SQL and
history; validate transaction/timeout behavior in isolation before future DDL.
The applied SQL comments about transaction/timeout behavior record preflight
assumptions; this execution caveat supersedes those comments. Do not edit or
replay the applied files to change this project's current schema.
See CONFIGURATION-PREFLIGHT.md section 13 for the complete execution record.

## Recorded preflight and scope (before application)

Provider project metadata and this checkout's `supabase/.temp/project-ref` agree.
Remote history contains the ten tracked versions from `20260402100000` through
`20260409210000`, in order. There is no missing or out-of-order migration to repair.
History is version/name evidence, not proof that an edited historical file equals
the deployed SQL; the required live columns, constraints, indexes, policies, and
trigger function bindings were independently inspected.

The reviewed pending set was exactly these two migrations, in this order:

1. `20260418120000_vonneumann_parent_ids.sql`: adopt the existing draft's DDL,
   adding only five-second lock and thirty-second statement timeouts.
   Add `vn_probes.parent_ids JSONB NOT NULL DEFAULT '[]'::jsonb` and its GIN index.
   The column and index are absent in the preflight schema. Existing `parent_id`
   and embedded genome ancestry are preserved. This does not reconstruct old
   multi-parent lineage or change the genealogy UI. The index is retained from
   the draft; current consumers do not require JSON containment queries.
2. `20260930010000_vonneumann_trade_exit_reasons.sql`: widen the existing validated
   check to retain all five prior exit reasons and allow `EVOLUTION` and
   `TERMINAL_LOSS`. NULL remains valid for an open trade. Both changes to the check
   occur in one atomic ALTER TABLE. The five-second lock and thirty-second
   statement timeouts were requested but not verified at execution (see above).
   Notify PostgREST to refresh the schema cache.

The pre-existing edit to `20260409210000_vonneumann_colonies.sql` stays outside this
change. That version is already applied; the live colony trigger is enabled and
bound to `extensions.moddatetime`. Replaying it is unnecessary. All four event
tables already have nullable UUID `run_id` columns; the generation-stats unique
constraint is already `(user_id, run_id, generation)` with no old two-column
unique constraint. All five worker tables have RLS enabled with 18 policies.
No RLS, grants, triggers, extensions, realtime publications, credentials, project
settings, existing application rows, or historical migration entries are changed.

The preflight table sizes are small (probes approximately 720 KiB, trades 576 KiB).
Adding the column/index and replacing the check still acquire table locks. The
parent-ID migration uses the normal transactional GIN build, not a concurrent
index build. Do not treat `--dry-run` as SQL execution or a locking rehearsal.

## Recorded execution and verification procedure

These application instructions describe the completed batch. A fresh dry run
now reports no pending migrations; do not reset history to repeat the batch.

Before applying, recheck provider name/ID/organization and the local link. Run:

```sh
supabase db push --linked --dry-run --workdir /Users/redjester/Projects/Next/TheDashboard
```

Proceed only when the pending set is exactly the two files above. Do not pass
`--include-all`, `--include-seed`, `--include-roles`, a different database URL,
or a shared-profile login/link operation. Apply with the same explicit workdir
and `--linked`. Supabase CLI 2.84.2's upstream source describes each migration's
SQL/history insertion as an implicit transactional batch in its
[migration executor](https://github.com/supabase/cli/blob/v2.84.2/pkg/migration/file.go).
The observed `SET LOCAL` warning means explicit-transaction settings must not be
assumed effective in this path. Do not infer untested failure atomicity from the
successful run. Treat the files independently: if the second fails, retain the
first and inspect actual history and catalog state before retrying.

After application:

- Confirm both history entries and no remaining pending migrations.
- Verify the new column's type, nullability and default, the valid GIN index,
  and the validated seven-reason check.
- Compare all existing column/constraint/index definitions, policies, RLS flags,
  and trigger bindings against the metadata-only preflight snapshot.
- Run `supabase/tests/worker_schema.sql` against the verified link. It exercises
  temporary copies of the actual deployed definitions and rolls back. It does
  not write application/auth records or establish RLS/service/UI integration.
- Make a privileged, zero-row PostgREST read of `vn_probes.parent_ids` to verify
  the API schema cache. Keep credentials in memory and reject redirects.
- Run TypeScript and the frontend regression suite for the exit-reason type.

Record actual results in CONFIGURATION-PREFLIGHT.md and TODO.md. Schema readiness
alone does not start a worker, establish authenticated browser/RLS isolation,
repair event replay, or validate trading results.

## Failure and rollback

On identity mismatch, unexpected pending versions, lock timeout, incompatible
schema, or failed verification, stop further remote writes and inspect the
specific failure. Never reset the database or mark an unapplied migration applied.

Both changes are backward compatible with the currently deployed app. If an app
release needs rollback, keep the additive schema and roll back the app separately.
Prefer a reviewed forward correction for a schema defect. Do not drop `parent_ids`
after new writes; that would lose lineage. Do not restore the old exit check after
new reasons have been stored; it may fail validation or require destructive data
rewriting. Any destructive rollback requires a separate reviewed data plan and
user decision. No restore of another project or shared account changes is allowed.
