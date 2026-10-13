# Original portable-v2 restoration contract — offline research, 2026-10-12

`portable_restoration_wire.py`, `portable_restoration_graph.py` and
`portable_restoration.py` reconstruct the original
`ga-portable-provider-model-research-v2` GA-only two-EMA research state. They do
not change economic formulas, selection, mutation, distributions, RNG policy,
model/assessment formats, or the thirteen-slot checkpoint format. They do not
install a production runtime, read credentials, issue a lease, activate a worker,
submit a command, retry an uncertain write, or authorize trading.

## Independent trust boundary

The caller must obtain `ExpectedHead` from a separately authenticated,
owner/run-scoped committed native reader and an independently verified operator
package binding. It supplies the exact owner, run, revision, manifest SHA256,
original command ID/SHA256, accepted semantic validator SHA256 and installed
native catalog SHA256. Do not construct it from the receipt being checked or
from arbitrary browser JSON. A Python value, matching hash, receipt boolean or
test fixture cannot authenticate a server or prove historical semantic admission.
The pure test bindings intentionally use synthetic digests and prove no such
acceptance. The native reader/package join remains a separate gate.

The original semantic and native contracts must admit the same versioned model,
assessment, prior chain and historical identity ledger. A seed, fabricated prior,
hash-only head or provisional return before COMMIT does not satisfy this boundary.
Operator checks must bind the reviewed worker source/dependency package as well
as the installed SQL catalog; a matching model version string alone cannot prove
that code has not changed. Preserve original v2 records under original semantics.

Every decoded/restored result reports `restoration_authority=false` and
`hosted_authority=false`. Checkpoint readback also reports no pending-command
authority; restored model state reports no restored lease or history ledger.
The decoder constructor prevents accidental unchecked checkpoint DTO creation.
These local object checks are validation boundaries, not credentials or a Python
process sandbox.

## Wire and reconstruction rules

The native readback envelope is ordinary UTF-8 PostgreSQL JSON, bounded at
589,824 bytes. Its outer field order/spacing is immaterial. Duplicate/unknown
keys, untagged numbers, unknown formats, malformed UTF-8 and oversized/deep
containers are refused before model construction. Revision fields are canonical
decimal strings, UUIDs canonical lower-case strings and SHA256s exactly 64
lower-case hexadecimal digits. Boolean/integer aliases are refused.

The manifest is at most 65,536 bytes; each component at most 196,608 bytes; the
manifest plus all thirteen component wires at most 262,144 bytes. Inner wires
remain byte-exact canonical tagged numeric UTF-8 JSON. No JSONB reserialization,
rounded JavaScript number or new digest substitutes for the original bytes.
SHA256 binds each wire to its original ordered reference. All thirteen slots
must be present once, in original order: configuration, optimizer, cohort,
eight ordered member genomes, source bars, EMA. Stable slots have generation
zero; variable slots use the original model generation. Scope, reference type,
kind/entity/generation, source model format and revision must all agree.

The exact 17-key observed receipt must bind every independent expected identity
and digest, original model/assessment formats, `record_observed=true` and
`pending_until_commit=false`. Its guard time must be a valid UTC timestamp in
`YYYY-MM-DDTHH:MM:SS.ffffff+00:00` form. It cannot claim final visible-instant
freshness, restoration or hosted authority. This timestamp is a recorded native
guard observation, not a guarantee that the checkpoint is presently fresh.

After bounded primitive/source/economic/cohort/mirror validation, reconstruction
assembles all original configuration, reserve, accounts, held positions, EMA
values/count/previous values, source bars/epoch/watermark, risk latch/counters,
pending decisions, member cursors/assessments, cohort genomes/results and search
state. The graph decoder permits only six reviewed fixed classes: GA strategy,
search streams, selection cohort, genome, evaluated candidate, evaluation cohort.
It preserves ordered maps, aliases and original object field layouts. Missing,
forward or cyclic references and unreviewed classes/tags are refused.

The Python MT19937 words, cursor and optional Gaussian cache are installed with
the builtin fixed allocator plus `setstate`; neither RNG initialization/seeding,
bootstrap, fresh identifiers, optimizer evolution nor ask/tell runs during
loading. Search seed/algorithm/epoch/mutation counter and all primitive mirrors
must agree. A read-only original encoder confirms the exact graph round trip.
Only CPython 3.12.14, NumPy 2.5.3 and cmaes 0.13.1 under the reviewed original
evidence header are admitted. Supporting another runtime requires explicit new
acceptance, not silent header rewriting.

Historical readback may be decoded for inspection only when independently
requested. It cannot prepare continuation. A current checkpoint must equal the
independently held current revision and status; there is no automatic rewind.

## Preparation and pending commands

The original public producer requires its complete in-process
`SimulationLedger`. The restoration adapter does not invent one from active
checkpoint rows. The separately authenticated native `lookup_identity_ids`
capability supplies an exact, bounded set of up to 128 offered UUIDs bound to
the same current owner/run/revision/manifest/catalog. Missing or extra lookup
entries, an unknown/stale head, mismatched package or an unchecked allocation
refuse; there is no default `unused=false/true` fallback. An empty allocation set
is valid for a control that needs none. Previously retired IDs remain used.
Names may repeat; no historical name uniqueness is invented.

The adapter stages explicit original frame/history/UTC/monotonic evidence using
the original source validators, then invokes the unchanged original-v2
`_prepare_protective`, `_prepare_decision` or `_prepare_control` kernel. It does
not read a clock, call a provider or create an allocation. The offered allocation
tuple must exactly match the checked oracle set. The native transaction must
still enforce the current head, global historical ID uniqueness, lease/fence,
source freshness and final effects atomically; a preparatory lookup cannot
guarantee that the head remains current until COMMIT.

`prepare_restored_transport` retains the original prior manifest digest and
component digest set and emits only the following original changed components.
It preserves every original operation, history record, assessment/evaluation,
source input and event. Ordinary 196,608-byte and reserved Stop 262,144-byte
limits include the original tagged wire, JSONB representation and expanded
numeric JSON. It returns bytes, never a submission or accepted receipt.

`PendingOriginalRequest` captures the exact saved original command UUID, scope,
wire/hash, resulting manifest/hash and revision. `reconcile_original_request`
interprets only a separately authenticated getter for that same original request.
An observed receipt must return the byte-exact original request and independently
bound package/semantic provenance. An absent lookup remains
`not_observed_uncertain`; it grants no retry or rollback conclusion. A different
UUID/wire/hash is refused. The loader generates no replacement ID or automatic
write/retry. Stop retains holdings, cash and risk state and cannot turn a stopped
checkpoint into a running one.

## Acceptance and remaining ordered joins

The focused offline suite checks exact full next-candidate and compact-command
wires across two generations, both clone/crossover mating, mid-window and pending
signals, early terminal completion, pause/resume with an explicit search restart,
risk halt/recovery, increasing original source cursors and Stop with eight retained
positions. It also checks retired identity reuse refusal, historical inspection,
original uncertain-request reconciliation, duplicate/unknown/truncated/oversized
wires, type/hash/scope/semantic/catalog/receipt/authority rejection, graph/runtime
forgery, and denied configuration/provider/database/network imports. These are
literal synthetic-provider experiments, not provider authenticity, native
durability, profitable results or hosted throughput.

Acceptance receipt: the 15 focused cases pass with zero skips in the isolated
locked worker runtime (90.697 seconds). Five traces contain 78 exact full/compact
next-command comparisons; the resulting second generation includes both clone
and crossover mutation. Run with a sanitized child environment:

```sh
env -i PATH=/private/tmp/dashboard-locked-worker/bin:/usr/bin:/bin \
  PYTHONPATH=services/vonneumann PYTHON_DOTENV_DISABLED=1 \
  PYTHONDONTWRITEBYTECODE=1 /private/tmp/dashboard-locked-worker/bin/python \
  -m unittest tests.test_portable_restoration -v
```

The source import boundary test separately rejects dotenv/private configuration,
live provider/repository clients and network calls. Pure source/database protocol
validators are allowed; no database driver or credentials are imported by the
restoration modules. The local runtime path is a fixture dependency, not a
production deployment path.

Next joins must proceed in this order:

1. Install the reviewed guarded native laboratory package under its limited
   installer. Independently verify catalog/owner/role/grant and semantic hashes,
   committed current head and accepted original command under scoped reader
   credentials; pass those expected bindings to this decoder. Exercise all 13
   original pins, real independent COMMIT readback, foreign/missing getters,
   current-head identity oracle, stale head, reused retired IDs and original
   request reconciliation. Loading remains closed with every authority false.
2. Define a forward real-provider runtime profile. Original v2 configuration
   explicitly retains `source=synthetic-exact-fixture-v1`; provider-shaped fixture
   documents do not authorize relabeling it as live Jupiter data. Version the
   model/config/source/assessment/checkpoint/command/SQL semantic/projection and
   reader contracts coherently. Specify acquisition authenticity, original raw
   response retention, clock/process epoch policy, rate/error/staleness behavior,
   contiguous completed-candle warmup and immutable history/price provenance.
   Keep original v2 journals readable without mutation or retrospective rescoring.
3. Implement and accept retained archive/receipt/original-ID lookup and all
   dependency pins before deleting evidence. Preserve the append-only identity
   ledger and package/runtime/semantic manifests needed for future restoration.
   Measure table/index/TOAST/WAL/pin/history growth and held-position Stop reserves;
   choose hot/archive limits and bounded pilot duration from those measurements.
4. Join the explicit new projection with old/new UI readers, lost-ACK controls,
   pending Stop and session replacement. Only then prepare exact-target closed
   deployment, writer-drain/rollback steps and bounded Railway restart/multi-window
   acceptance under the approved pilot ceiling. A lease is separately acquired
   only after original pending requests and holdings are reconciled and all gates
   pass. No part of this pure restoration experiment opens that lease path.

Further substantial research is needed on authenticated provider recording and
publication-time evidence, real source/process-clock transitions after restart,
long-term version/runtime support, dependency-safe cold archive lookup, retention
cost/COMMIT tails and bounded hosted risk-response intervals. These questions
should be resolved with measured joins rather than inferred from canonical hashes.
