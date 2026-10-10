# Independent SQL numeric/hash boundary — offline research, 2026-10-09

PAPER-COMPACT-03B1 independently validates the canonical tagged numeric wire in
PostgreSQL17 and reproduces its SHA256. The compact checkpoint format cannot use
PostgreSQL JSONB text as a substitute for that wire. This layer preserves tagged
JSON as primitive evidence; it grants no command, lease, receipt or restart
authority and constructs no optimizer/RNG object.

## Input and canonical binding

The input is original UTF-8 wire text, bounded before JSON parsing. Validate
unique decoded keys before JSONB conversion; JSONB discards duplicate keys and
does not preserve original object order or whitespace. Ordinary strings are
escaped with PostgreSQL's JSON string emitter; object keys are sorted with
explicit C collation. Independently regenerate compact JSON and compare the
complete original bytes. Reject alternate whitespace, order, escapes, duplicate
or escaped duplicate keys, invalid Unicode/null characters and untagged numbers.
[PostgreSQL JSON types](https://www.postgresql.org/docs/17/datatype-json.html),
[JSON functions and unique-key predicates](https://www.postgresql.org/docs/17/functions-json.html).

The research artifact requires its explicit offline fixture marker, UTF8 server
encoding and standard-conforming SQL strings before installing four invoker
functions in its own private schema. It creates no tables or client grants.
The marker prevents accidental execution; it is not an authentication capability.
The real deployment will require the reviewed native installer/catalog manifest,
not this standalone research artifact.

Bounds match the Python numeric policy: at most262,144 wire/traversal bytes,
20,000 visits, depth64,4,096 entries/container,16,384 UTF-8 bytes/string and256
integer bits. The caller can choose a smaller byte ceiling but cannot increase
the fixed limit. Nodes/budget propagate across siblings. Tag values use the
same100-character maximum and tag shortcut semantics as the Python decoder.
Ordinary192KiB and Stop256KiB admission limits still need to be bound to actual
native command type; accepting a byte ceiling here grants no such authority.

## Exact numbers

Every integer must be a one-field $integer object with a canonical decimal
string: no leading zeros, sign on zero, exponent or alternate digits. PostgreSQL
numeric retains the exact signed value through ±(2^256−1). Booleans remain
booleans. Field-specific signed-bigint revisions, unsigned64 provider blocks,
generation bounds and the Stop-reserved final revision remain independent
admission checks; the generic numeric decoder does not authorize those fields.

Every actual binary64 value uses a one-field $float64 object containing the
canonical Python hex representation. Independently validate normal/subnormal/
zero grammar,52 fraction bits and exponent range, excluding infinities/NaNs and
rounded aliases. Assemble sign/exponent/fraction bits and emit the exact eight
big-endian IEEE-754 bytes through integer binary output. This preserves negative
zero without converting through PostgreSQL decimal JSON or a rounded host float.
The audit returns the original validated tags; callers must not substitute a
plain floating JSON value or interpret a tag as a string-valued gene.

Hash the exact UTF-8 canonical wire with PostgreSQL's built-in byte SHA256,
then emit its lowercase hex identity. This needs no extension or global tool.
[PostgreSQL binary string/hash functions](https://www.postgresql.org/docs/17/functions-binarystring.html).

## Actual isolated acceptance

Eleven tests use a uniquely owned network-none PostgreSQL17.6 fixture and an
actual synthetic installer role with NOSUPERUSER/NOCREATEDB/NOCREATEROLE/
NOINHERIT/NOBYPASSRLS. Only that role receives database CREATE for this disposable
fixture; it owns the private schema/functions. The four functions are invoker
functions with search_path=pg_catalog; PUBLIC receives no schema/function
privilege. Only a synthetic auditor receives fixture execution grants. Browser,
service-role and relay identities fail, and the auditor cannot create schemas.
This does not prove the future complete production installer or RLS contract.

Acceptance includes:

- exact SHA256 for Unicode, control characters, key order and numeric limits;
- exact IEEE-754 bytes for509 finite values, including500 seeded bit patterns,
  negative zero, smallest subnormal, normal boundaries and maximum finite value;
- 256 seeded mixed documents with independent SQL/Python canonical hashes;
- all19 complete owned commands through a dense window and all13 final components;
- duplicate/escaped duplicate keys, noncanonical JSON/tags, invalid/nonfinite
  binary64, oversized/deep/many-node/traversal inputs and caller limit escalation;
- failed installation without marker or with incompatible string settings,
  invalid helper budgets, invoker ownership and client privilege denial.

Seven unchanged canonical-v5/forward package tests also pass:18 focused cases
total. All SQL writes are to the owned disposable fixture; it is removed after
acceptance. There is no Supabase installation/migration, package hash change,
runtime selection, hosted grant, data deletion or Railway change.

## Measurement and remaining work

Thirty warm server samples per request actually evaluate the full audit. The
wire is a PL/pgSQL variable and the fixture forces generic plans so immutable
literal constant folding cannot replace repeated validation with a cached
constant. The initial literal timing method was rejected and its artifact
replaced; only the corrected measurements are retained.

| Request | Wire bytes | p50 audit milliseconds | p95 audit milliseconds | Maximum milliseconds |
| --- | ---: | ---: | ---: | ---: |
| Bootstrap |128,635 |54.999 |58.874 |60.478 |
| Quote |9,192 |3.177 |3.235 |3.950 |
| Replacement |149,024 |52.875 |54.869 |56.347 |

These are local warm validation/hash diagnostics on a fixture limited to one
CPU. They exclude TLS/transport, run locks/contention, economic/source/lineage
validation, journal/pins/projections, final lease/source checks, COMMIT/WAL/relay
and hosted tails. They cannot establish an accepted production cadence or
five-second final source freshness.
[Pinned source, identity and measurements](research/native-numeric-wire-measurements.json).

Next,03B2 resolves all13 typed components under the owner/run lock with exact
prior binding and scope/hash/slot checks.03 must independently validate complete
economic/model/source/history/lineage transitions, store the original request
once, preserve durable original-ID replay/readback and all dependencies, reserve
native Stop resources and recheck lease/source freshness after transactional
effects. Rehearse the limited installer and old/new projections/readers before
any exact-target migration.04 still gates explicit exact restoration;05 gates
retention/archive and closed hosted multi-window acceptance.

**Deep substantial research:** complete retained SQL/lock/COMMIT/WAL/TOAST tails,
parser/allocation cost under adversarial bounded input, binary-digest/pin indexes,
cross-version canonical maintenance and scoped archive/recovery costs. Keep the
full optimizer/RNG evidence until exact next-command restoration is proven.
Rollback of this slice is a reviewed code/docs revert; no hosted objects exist.

Reproduce from the project root with the isolated worker Python and cached local
PostgreSQL image, with dotenv disabled:

    DASHBOARD_ISOLATED_POSTGRES_TESTS=1 DASHBOARD_NUMERIC_WIRE_MEASURE=1 PYTHONPATH=services/vonneumann PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.postgres.test_numeric_wire -v
    PYTHONPATH=services/vonneumann PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_canonical_v5_package tests.test_forward_package -v
