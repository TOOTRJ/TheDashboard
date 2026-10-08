# Complete forward candidate and additive retirement

DB-03A2D3B2D2 composes the reviewed canonical v5 ledger, native identity checks,
legacy write retirement, and durable legacy evidence in one transaction. The
candidate lives in `db-contract/forward/`, outside `supabase/migrations`. No
application imports or executes it. Production adoption remains conditional on
D3C service/browser integration, C3B managed-host acceptance, and A3 review.

`build.py --check` reproduces `package.sql`, `verify.sql`, and `manifest.json`.
`dependencies.json` pins twenty existing component sources/artifacts, including
the unchanged native issuer/revocation templates. The final manifest enumerates
97 callable signatures with final body/DDL hashes, owners and exact execute
roles, 26 table definitions, indexes/triggers/domain definitions, source hashes,
the release identity and the exact Dashboard provider identities. Issuer
templates are dependencies for separately reviewed operations; installing the
package does not create login credentials.

## Independent review and transaction order

The installer authenticates as actual non-superuser `postgres` with the measured
managed-like privileges. It does not inherit a superuser, obtain managed Auth
grant options, or change shared settings. Identity verification outside SQL
must first prove GitHub `TOOTRJ/TheDashboard` ID `1141090963`, Vercel
`the-dashboard` ID `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` under team
`team_8iNNxiNjrOseD4gdSCHkQEzF`, and Supabase `The Dashboard` ref
`fxpxsciltakyypunglzr` under organization `cqfnnaunmupdyobkyqfo`.

Capture `legacy_catalog.sql` and `forward/review.sql` in completed read-only
sessions, review their results independently, and supply those reviewed JSON
values in session-local temporary tables during the later install. Migration
review includes each version, name, and SHA-256 of the statements array;
matching version numbers alone is insufficient. The SQL target JSON is a
reviewed input, not independent proof of which cloud database accepted it.

The transaction locks migration history in SHARE mode, then the five public
legacy tables in a fixed ACCESS EXCLUSIVE order before creating any private
objects. It compares the supplied release/target/migration review exactly.
The legacy component compares its independently supplied catalog after the
same locks. A drift, unexpected fresh object, old transaction, source mismatch,
late error or failed postcondition aborts all changes. The lock budget is
500 ms; individual review/retirement statements use 8 s. An installer runner
must additionally retain a finite outer deadline and original outcome evidence.
These statement budgets do not establish a maximum total transaction time.

The composed classifier remains installer-owned and uses the existing Auth
identity bridge. Evidence helpers retain the previously proved narrow lock and
aggregate authority. Temporary creation grants are revoked before commit.
Old direct table writes remain denied, including table/column, inherited/SET,
TRUNCATE, REFERENCES, TRIGGER and PostgreSQL 17 MAINTAIN paths. Existing legacy
rows and owner reads are preserved; no history is converted into a v5 ledger.

## Closed installation and verified activation

Installation creates private `vn_release.state` and `operations` tables under
the inert contract owner. They have RLS with no policies, owner-only raw ACLs,
and no API/economic/relay/attestor access. The release starts `closed`.
The installation review and legacy catalog digest are retained in the private
state. A private catalog snapshot records all eight schemas, relation shapes,
columns, constraints, indexes, triggers, policies, the balance domain, callable
attributes/body hashes/ACLs, inert role attributes, contract-owner memberships,
and relevant defaults. It includes no ledger rows or password/verifier data.
The five private evidence tables retain their reviewed owner-only ACL model;
the assembler does not silently change that component's RLS design.

After service/browser, managed identity, provider quota and migration acceptance,
a reviewed operator may call the private owner-only
`vn_release.transition(original_request_id,0,'open',evidence_sha256)` in a
read-committed transaction with nonzero lock/statement budgets no greater than
500 ms/8 s. The hash identifies retained operator evidence; SQL cannot prove
that evidence's external authenticity. No callable is granted to browser users
or worker credentials for opening or retiring the release.

`create_run`, `heartbeat` and `commit_command` require open admission both at
entry and before every successful return. Admission uses a shared row lock held
through transaction end and checks the current private catalog. Native identity
and owner/run checks remain intact. Catalog drift closes ordinary economics;
original `get_command` recovery remains available within its credential deadline.
`verify.sql` is a bounded read-only post-COMMIT check of all final function bodies,
owners/definer flags/ACLs and effective capabilities, private tables/columns/RLS,
legacy catalog, and the complete private snapshot. Run it in a fresh session.

## Additive rollback after acknowledged commands

Close process/browser admission and drain owned operations first. Retain the
original rollback request ID and reviewed evidence hash, then call
`vn_release.transition(original_request_id,current_epoch,'retired',evidence_sha256)`
under the same bounded private-owner transaction. The exclusive row lock waits
for an admitted command's transaction to finish. A lock timeout changes neither
admission nor operation receipts; reconcile before retrying the same request.

Retirement is one-way for this installed release. Original transition receipts
replay exactly, even after later state changes; changing the same request's
payload conflicts. It revokes no recovery authority, drops nothing, regrants no
legacy writer, edits no economics, and does not invent liquidation proceeds.
Original commands, engine checkpoints, balances, positions, history projections,
outbox events, relay receipts, legacy rows, and legacy evidence remain intact.
`get_command`, relay read/accept/acknowledge, owner history, and evidence/archive
reads remain available. After a real lease expires, the existing conservative
`interrupt_expired` command may mark the run failed/reconciliation-required while
preserving holdings. A worker cannot submit a fresh stop economics command after
database admission retires; use drain-before-retirement or safe expiry evidence.

If current catalog drift prevents a new operator transition, inspect and repair
the exact unexpected authority before invoking a reviewed transition. Do not
restore old grants or drop ledgers as a shortcut. An already recorded transition
can still be read back by its exact original payload. Unobserved privileged DDL
that is reverted before observation is not a permanent audit signal; retain
operator audit/drain evidence and explicitly invalidate affected legacy reviews.

## Acceptance and remaining dependencies

Owned synthetic PostgreSQL tests use real separate limited installer and native
TLS/SCRAM logins. They cover complete installation and committed verification,
independent migration/target/catalog review, changed statements under the same
version, already-open/delayed old writers, late atomic failure, closed admission,
all four actual optimizer command sequences, additive retirement, original-ID
readback, relay drain, expiry interruption, preserved archive evidence, waiter
serialization, replay conflicts, stale isolation, and metadata drift. The full
native-session identity/expiry/revocation suite is also run against this package.

The actual managed server, project CA peer validation, Railway outbound IPv6,
credential issuance/storage/expiry, service/browser selection and owner flows,
complete migration history update and uncertain commit reconciliation, measured
connection/lease/relay tails, and hosted paper pilot are separate remaining
acceptance. No hosted worker, live trade, or profitability claim follows from
these offline results.

Further substantial research is required on managed dependency hooks/privileged
wrappers, concurrent administrator DCL history, full transaction and commit tails,
catalog-check CPU/connection cost, checkpoint/journal/source retention and
compaction, and trusted legacy drain/exposure evidence collection.
