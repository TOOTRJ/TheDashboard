# Conservative retained-artifact report scaffold

`retention_manifest.py` is pure, bounded inventory/report code. It makes no file,
database, provider or credential calls and implements **no pruning**. Every
supplied artifact remains protected and ineligible for deletion, including
older or apparently unreferenced artifacts. A report cannot authorize worker
continuation, restoration, live activity, or hosted deletion.

The descriptor classes cover the full original command bytes and receipts;
checkpoint manifests and all immutable referenced components/pins; identity
allocation evidence; holdings/reconciliation evidence; the original unresolved
request bytes; and the original Start/Stop identities. Callers retain those
exact blobs outside the report. A digest/report is never a replacement for the
original command, pending request, component, receipt or identity rows.

The initial native formats being investigated are the original v2 compact
command/manifest/component formats and
`ga-portable-native-command-readback-lab-v1`,
`ga-portable-native-checkpoint-readback-lab-v1`,
`ga-portable-native-receipt-lab-v1`, and
`ga-portable-native-identity-lookup-lab-v1`. This scaffold does **not** parse or
authenticate those formats. Its artifact classes are report metadata, not a new
native wire format. A validated adapter may supply their complete exact bytes;
until then the report explicitly says schema/owner authority and inventory
completeness are unverified. In particular, bounded identity lookups do not
prove that the complete allocation ledger was enumerated, and there is no
separately accepted native pending-request-set format yet.

References are exact SHA-256 digests of other retained supplied blobs. Missing
links and absent artifact classes appear as evidence gaps and never become
deletion candidates. Multiple classes may describe one blob, for example an
unresolved original request. The report distinguishes summed descriptor bytes
from deduplicated unique blob bytes. Both are exact measures of the supplied
wire bytes; neither estimates actual table tuples, TOAST, indexes, WAL,
replication copies or provider billing. Those physical storage figures remain
unknown. Content hashes and canonical report ordering provide byte identity,
not authenticated provenance or a completeness proof.

Limits are 4,096 descriptors, 8,192 aggregate references, 589,824 bytes per blob,
32 MiB summed input bytes, and 1 MiB report bytes. Inputs use immutable byte strings and explicit unique
references. Reports return fresh decoded values. Code and property checks keep
all authority/deletion flags false regardless of inventory size, order, missing
references or sharing.

The next integration must bind authenticated owner/run, current head and exact
package/validator digest; complete command receipts, immutable dependency pins,
identity allocation history, open holdings and reconciliation; and all original
pending Start/Stop/command IDs and bytes. Joined native restoration and original-ID
reconciliation tests must prove that retaining this closure preserves the exact
next command. Only after a separately reviewed retention transaction, lock
contract, archive semantics, storage measurement and failed-cleanup tests can
pruning eligibility be considered. No hosted deletion readiness is claimed.

## Actual isolated retained-storage trace

`tests/postgres/test_portable_retention_storage.py` and the source-bound
`research/portable-retention-storage-acceptance.json` now record one accepted
PostgreSQL 17.6 trace using the reviewed native laboratory package from
`5603cbde76b1365956b3879185c84166c36a6da6`. The test constructs the existing
opt-in native fixture inside its own setup, never invokes its per-test reset,
and uses a genuine server-clock bootstrap followed by 32 data-free controls.
The last control is Stop while flat. Every command passes the unchanged native
semantic, actor, lease, catalog, source and recognized COMMIT checks. Heartbeats
renew the same live worker/fence before further control batches; errors or
original-ID conflicts are refusals, with no alternate-ID retry.

At control counts 0, 8, 16 and 32, the test reads every accepted original ID and
the exact checkpoint manifest plus all 13 ordered immutable component wires.
All 60 original-ID readbacks and all 60 complete checkpoint readbacks passed.
Historical envelopes retain their original receipt and manifest while reporting
the actual current revision. Current and historical readback authority flags
stay false. All eight original allocation rows remain unchanged, and bounded
current-head lookups match their kind and birth revision. No deletion, pruning,
semantic-head copying, source-window relaxation or vacuum occurs.

The operator measures only the fixture's 13 private tables in `READ ONLY`
transactions. Exact `octet_length` sums cover six retained TEXT columns: original
command wires, deduplicated immutable component wires, the current manifest,
current resolved projection, historical projections and event wires. These are
selected payload bytes, not full row sizes or a complete storage inventory.

| Accepted commands | Controls | Selected TEXT payload bytes | Native logical charge bytes | Measured total relation bytes |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0 | 266,663 | 269,131 | 720,896 |
| 9 | 8 | 476,707 | 544,669 | 966,656 |
| 17 | 16 | 541,539 | 675,037 | 1,179,648 |
| 33 | 32 | 671,205 | 935,775 | 1,744,896 |

The empty fixture already allocates 294,912 relation bytes for its tables,
indexes and TOAST objects, including its two actor bindings and one package
manifest. At the final revision there are 33 native journal rows, 33 semantic
original-command rows, 33 historical projections, 429 dependency pins, 15
deduplicated components, 42 events and eight identity allocations. The active
projection, semantic head and current checkpoint each remain one row. Every
dependency pin resolves to its retained component.

Final physical allocation consists of 221,184 main heap bytes, 147,456 heap FSM
bytes, zero heap VM bytes, 409,600 table-index bytes, and 966,656 TOAST total
bytes. `pg_table_size` includes TOAST and auxiliary forks: its 1,335,296 bytes
plus `pg_indexes_size` equals `pg_total_relation_size` of 1,744,896 bytes.
TOAST must not be added again to that total. Page allocation and ordinary
UPDATE dead tuples are included; no vacuum was issued. The native logical
charge is therefore an accounting cap, and does not cap actual database bytes.

This proves retained original-command, historical projection and dependency
readability for this specific bounded trace. The 39.097-second observation is
contended local mechanics timing, not a throughput or hosting benchmark. The
constant-price synthetic bootstrap and mostly unchanged flat controls are
compressible and introduce no trades, mutations or market-data volume growth.
Do not extrapolate the measured ratio to real trading, larger graphs, 127
ordinary commands, other native packages, or hosted databases. The later direct
server-clock future-anchor guard is not this package; adoption requires a
separately source-bound rerun.

Deletion eligibility remains false. Representative retained-graph and holdings
growth, unresolved original request sets, retention lock/transaction/archive
semantics, failed cleanup, actual restoration after any proposed cleanup, WAL,
replicas, backups, physical crash durability and hosted cost/latency remain
separate gates. This fixture's tmpfs storage and synchronous COMMIT checks are
not a power-loss durability proof. The pure seven-case retention test suite and
its 64 seeded inventory checks remain unchanged.
