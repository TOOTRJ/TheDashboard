# DB-04 independent API foundation — 2026-10-17

The independent baseline and separate permissions step pass all **19 owned
PostgreSQL/PostgREST tests**, zero skips, in 36.825 seconds. A fresh read-only
catalog from the exact Dashboard Supabase project matches the entire independent
structural expectation. Hosted permissions still match the reviewed broad
envelope. Final-head CI, transport review, rollout and post-change acceptance
remain; no hosted schema or ACL change has run at this checkpoint.

The pure emitter separates fresh-fixture construction, baseline-only installation
and permissions-only application. Existing matching tables execute no
CREATE/GRANT/REVOKE; missing exact tables receive narrow grants in their creation
transaction. Permissions-only requires both tables, accepts only reviewed broad
or final envelopes, and executes no ACL writes when already final. Preserve all
12 columns, eight default bindings, five constraints/indexes, legitimate NULLs,
native CURRENT_DATE, rows/IDs, postgres ownership, enabled/unforced RLS and zero
policies. Full owned row/array/index/TOAST structures, native default/CHECK trees,
core function/operator identities and direct dependencies are bound. Unknown,
incomplete, over-cap or extra structure refuses.

## Independent source and executed proof

The expectation comes from a disposable PG17.6 constructor, **not the hosted
observation**. Initdb's private bootstrap admin is OID10. A separate postgres is
NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOBYPASSRLS and owns application objects.
Constructor, baseline, catalog and snapshot acceptance use that ordinary role;
the socket-only admin handles bootstrap and deliberate drift setup/cleanup. It
has no HTTP HBA entry or membership edges. API roles are NOLOGIN/INHERIT;
authenticator is LOGIN/NOINHERIT with checked memberships. JWTs are synthetic.
Core owners bind native OID10, while application owners remain postgres and
their owner dependency edges remain present.

| Final artifact | SHA-256 |
| --- | --- |
| constructor.sql | `333b25347ff71eb6f809316cdb501070210a61959228157b9b8c5cad38c6326a` |
| catalog.sql | `b9d0f75661672bc240767680b83d9b9daffad9df398639137b317afdb15f22b3` |
| expected.json, 76,505 bytes | `74f3a96c7e3d3eb759e43307752abbb0541e8d7288ad3fdea23aed4c13488568` |
| tested emitter | `9286a31aac28bfcafe52c2f7eb90dd60b35712fd1e99a123fa4d7aee918f73ee` |
| native tests | `af71d6f0f71934a42eaddb6db9500d621d4e37b2ea1bb88d77d4feada216fb66` |

Private original v3 constructor receipt SHA:
`9e3c529ea59558078bf02990ed5b9b8162aba71ce1929480e83cedf63c9dcb20`.
It used emitter b336a683 before the expected-file pin and baseline-only repairs;
the historical receipt is unchanged. The full expected structure equals that
original frame and has independent peer review: 28 objects, 27 attributes,
32 ordinary dependency edges, eight non-null default trees, two non-null CHECK
trees, seven per-root function records and three operator records. Constructor
execution measured 0.059 seconds locally.

Private final 19-case log SHA:
`7741c7234646a77ce49585974e85de451d1a35decf71dabb056ef96d6b63718c`.
Proof covers fresh/matching/repeated/both mixed-missing states; structural,
default, constraint, index, trigger, policy, dependency and permission drift;
relation/type/array name collisions; first-table and complete late rollback;
actual held-lock refusal; original row/tuple/catalog identity preservation; and
unchanged unrelated sentinel, roles, schemas and creator defaults. All 48 table
and 144 column privilege records, actual SQL denials and service
SELECT/INSERT/RETURNING pass. Real HTTP selected single-object replies have
independent committed SQL readback. Defaults, explicit nullable values,
range/enum/date/null checks and duplicate-date23505 pass without adding
`missing=default`. REFERENCES reaches a regular role-owned child/parent check;
MAINTAIN uses PostgreSQL's actual ANALYZE warning/skip behavior.

Earlier local failures remain historical: regproc names mislabeled as OIDs;
PostgreSQL's prohibited bootstrap-role demotion; JSON operator precedence in the
identity-containment check; missing safe owner refusal before LOCK; and the
invalid TEMP-to-permanent REFERENCES fixture. All are corrected in the accepted
source. No hosted migration failed during this work.

Cached ARM identities: PG
`sha256:965e2dfb5a23a0d6541b6106541e777b303656ebabd4e878746b189d550c0a66`;
PostgREST
`sha256:b574528fe109c8343c1247155734d03df8c34b462f342dca0ccc20244fc36ef9`.
No pulls/global tool changes/shared credential changes accompany this proof.
Local ARM acceptance is distinct from required final-head amd64 CI.

All **155 helper tests** also pass, including 14 new fixed-operation transport
cases; zero skips. Private log SHA:
`f64d08c17e00b7b7cfcd68c4b1335264279778761b83bc69342fc3fc78f7de99`.
The no-argument transport admits only held, SHA-pinned emitter bytes and
permissions mode, after verified target identity, under a dedicated 196,608-byte
SQL cap. The generic 65,536-byte query cap is unchanged. A failed identity
refresh retires prior admission. Uncertain requests are not retried.

## Hosted observation and rollout boundary

Fresh identity checks confirm `The Dashboard` / `fxpxsciltakyypunglzr`, owner
`cqfnnaunmupdyobkyqfo`. The complete catalog equals the independent structure
with zero differing paths; both ACL objects equal the reviewed broad envelope.
API-role attributes and zero outgoing memberships match. The read-only channel
uses supabase_read_only_user. A separate metadata-only SELECT on the normal
channel confirms current/session postgres, OID16384, NOSUPERUSER,
LOGIN/INHERIT/CREATEROLE/CREATEDB/REPLICATION/BYPASSRLS, PG170006, UTC and
READ COMMITTED. No application rows/routine bodies were read and no schema or
ACL changed. Extra shared ACL edges reflect the broad grants and are compared
separately from retained structural owner dependencies.

Private hosted catalog SHA:
`78d0584ce250daae3d7a9ad630c6943189205f45e3ddbe48a790abe351fc23cc`;
installer-context SHA:
`7e65f1426bbd0c802d5b13d32268690f511ecdfaf3faa3fe3401b2c49e023dbb`.

Target-table locks do not freeze ACL/role/schema/default administration. Retain
externally serialized Dashboard administration, fixed-order locks, READ COMMITTED
pre/post checks and one-second lock/ten-second statement bounds. Caller wall
and cleanup budgets and hosted locale/context require explicit rollout review;
no global catalog lock or absolute administrative-exclusion claim is made.
Uncertain responses require original-scope reconciliation before retry or
compensation.

Only the two tables' three API-role grants may change: remove broad direct grants
and grant service SELECT/INSERT. Preserve schema, owners, RLS/policies, roles,
creator defaults and rows. Rollback restores only saved original direct grants
after fresh exact-shape/identity/final-ACL checks; it never drops tables/data,
disables RLS or resets defaults. Existing Dashboard-only authorization covers
reviewed rollout; target mismatch or an unresolved boundary requires stopping.
Railway stays closed and all live-trading gates remain open.
