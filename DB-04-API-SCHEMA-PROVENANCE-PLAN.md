# Dashboard API schema provenance and table permissions plan

This is a forward-change proposal, not SQL, a migration, persistence acceptance
or authorization to query/change hosted state. It follows frozen APP-03 commit
`70a075e196ebc5b175e0c290776892d40286c029` and the new integer-score alignment.
The only hosted evidence used is the existing read-only catalog receipt
`supabase/audits/2026-10-13-api-schema-readonly.json`, SHA-256
`25d9362d0c22df79f54898cf15933e522a65f0ec479db76205d35d489d53012f`,
query digest `f8e55c02443138d7685e73e64e2b693690bdad81d6dab89d16ed838870872614`.
Root recorded the authorized identity check for `The Dashboard` /
`fxpxsciltakyypunglzr`, organization `cqfnnaunmupdyobkyqfo` /
`Valentine Jester`. This lane read that receipt and local source only;
it performed no additional cloud query and made no hosted or migration change.

The receipt states catalog-only/read-only, no row data read and no schema/ACL
change. It is a dated observation, not proof of present unchanged state,
historical deployment provenance, complete effective privileges, row contents
or successful PostgREST persistence. The main checkout's user-owned migration
was neither read nor changed. Frozen parser/A1/model/Nestegg/API commits retain
their original bytes.

## Observed catalog and local dependencies

The committed local migration inventory contains no creation of either API
table. Existing table metadata in the receipt is:

| Table | Columns and defaults to preserve |
| --- | --- |
| public.test_events | id uuid NOT NULL DEFAULT gen_random_uuid(); payload jsonb NOT NULL; source text nullable DEFAULT 'unknown'; created_at timestamptz nullable DEFAULT now(). |
| public.market_sentiment | id uuid NOT NULL DEFAULT gen_random_uuid(); score integer NOT NULL; sentiment text NOT NULL; summary text NOT NULL; key_factors jsonb NOT NULL DEFAULT '[]'::jsonb; date date NOT NULL DEFAULT CURRENT_DATE; source text nullable DEFAULT 'grok'; created_at timestamptz nullable DEFAULT now(). |

Preserve the named primary keys `test_events_pkey` and
`market_sentiment_pkey`; unique date constraint/index
`market_sentiment_date_key`; `market_sentiment_score_check` (0…100);
`market_sentiment_sentiment_check` (bullish/bearish/neutral); descending indexes
`idx_test_events_created_at` and `idx_market_sentiment_date`. Do not silently
drop the descending date index as apparently redundant; index planning is
separate from this narrow reproducibility repair.

Both are ordinary tables with RLS enabled, FORCE RLS false and no policies
reported. Both raw ACLs are
`{postgres=arwdDxtm/postgres,anon=arwdDxtm/postgres,authenticated=arwdDxtm/postgres,service_role=arwdDxtm/postgres}`.
These broad explicit table grants are unnecessary for the observed API
operations. They do not by themselves prove an anonymous row leak: no effective
role membership/attribute, column ACL, schema grant, policy behavior or data
probe was recorded. Keep RLS and policy state unchanged pending the scoped
permission proof; no new browser-user access policy is proposed.

Local source uses only:

- `src/app/api/v1/test/route.ts:11`: service integration SELECT of
  id/payload/source/created_at ordered by created_at with bounded limit.
- `src/app/api/v1/test/route.ts:30`: service integration INSERT payload/source
  with the same explicit selected reply.
- `src/app/api/v1/sentiment/route.ts:10`: service integration INSERT explicit
  score/sentiment/summary/key_factors/date/source and selected reply including
  generated id/created_at.
- `scripts/browser-fixtures/backend.mjs:140`: synthetic zero-row GET fixture;
  this is not an additional live consumer or a persistence proof.

The route uses a global API key and private admin client. Neither browser login
nor `x-source` becomes owner/provider authority. The catalog has no owner UUID
column for these tables. Preserve that existing global integration contract;
a future owner-scoped product change requires separate schema/authentication
design. No local UPDATE/DELETE/TRUNCATE/reference/trigger/maintenance consumer
was found for these two tables; this bounded source search is not an inventory
of every external consumer or role capability.

## Ordered forward work and acceptance gates

1. **Align the small known API mismatch now.** Reject fractional sentiment
   scores before DB access, preserving integer-value normalized JSON semantics
   and 0…100 bounds. Do not round, change the INTEGER column, fabricate nullable
   source/created_at values, or infer persistence from mocked replies. Generic
   23505 remains 409: the observed date constraint name does not authenticate
   which constraint a later error came from.

2. **Prepare a reproducible forward baseline with fail-closed catalog checks.**
   Draft one later reviewed migration/manifest for exactly these two public
   tables. In a fresh owned database, create the observed shapes/defaults/
   constraints/indexes and RLS state. Against existing tables, verify the
   complete declared shape before any permission step; never rely solely on
   CREATE IF NOT EXISTS as equivalence. Mismatched objects, additional columns,
   conflicting named indexes/constraints or unsupported ownership/dependencies
   must stop for review rather than be dropped, altered, recreated or relabeled.
   Preserve existing rows, IDs and nullable/default semantics. No migration
   timestamp or SQL is frozen by this proposal.

3. **Freeze effective permission prerequisites before a table-only ACL repair.**
   The receipt does not include table ownership, role inheritance/BYPASSRLS,
   transitive membership, effective column/schema privileges, default ACLs,
   security-definer entry points or external consumer requirements. Specify
   these as later exact-target read-only prerequisites; no query is performed
   here. The proposed smallest permissions for the currently observed routes
   are SELECT + INSERT for service_role on these two tables, including SELECT
   needed by the explicit insert reply. Propose revoking explicit privileges
   from anon/authenticated on these two tables and revoking unnecessary
   UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER/MAINTAIN privileges from service_role.
   A PUBLIC or inherited/column grant, if found, must be assessed explicitly;
   a direct-table revoke alone is not proof that effective access is gone.
   Preserve owner privileges and schema privileges. Do not change global default
   privileges, other tables, role definitions/memberships, RLS, policies, shared
   credentials or organization-wide settings. This step is blocked until its
   exact reviewed ACL delta and consumer/role prerequisites are frozen.

4. **Prove the baseline and narrow ACL delta offline.** Use an owned bounded
   database and, when separately reviewed, PostgREST fixture with synthetic
   identities/data. Test fresh creation, exact existing-shape continuation,
   second application and intentional drift refusal without partial writes.
   Cover service SELECT/INSERT plus selected replies; anonymous/authenticated
   denial of intended disallowed table operations; refusal of service UPDATE/
   DELETE and other revoked operations; unchanged unrelated-table ACLs/global
   defaults and unchanged RLS/policies. Exercise INTEGER boundaries/fraction
   refusal, enum/date checks, named same-date conflict and nullable source/time.
   No test may borrow real app secrets, create a live data fixture or claim an
   empty limit=0 read establishes insert behavior. DB SQL and PostgREST probes
   are distinct acceptance layers and must be reported separately.

5. **Prepare an exact-target application and rollback plan before any rollout.**
   Obtain separate implementation/release approval, reverify the pinned project
   and organization, and compare a fresh scoped catalog fingerprint with the
   reviewed manifest. Define a transaction/lock budget and stop on drift. Record
   exact before/after ACL and schema fingerprints. A rollback may restore only
   these two tables' verified previous explicit grants when approved; it must
   not reset a project, disable RLS, drop existing tables/data or change default
   privileges. No hosted action is authorized by this document. Any later test
   write needs its own unique fixture/reconciliation/cleanup plan and cannot
   blindly retry a lost acknowledgment.

6. **Close persistence and documentation gaps separately.** After actual
   schema/permission acceptance, validate returned row fields with the real
   nullable types and update route/schema documentation. Keep unknown-write
   outcomes explicit; a non-null object check is not a durable receipt.
   Performance/index tuning, payload/text CHECK constraints, archival/retention,
   authentication redesign and financial-wire parsing are independent work,
   not hidden additions to this baseline. Perform deeper research into
   effective Supabase/PostgREST role behavior and table-specific ACL/RETURNING
   semantics before freezing the permission implementation.

Step 1 can be reviewed and tested independently of schema implementation.
Baseline drafting and effective-permission research may proceed in parallel
after scope approval, but the ACL delta depends on both. Hosted application
depends on reviewed offline database and API-layer proof, current exact-target
verification, rollback and explicit action authorization. Catalog existence
and integer-score alignment do not complete DB-04 or the dashboard audit.
