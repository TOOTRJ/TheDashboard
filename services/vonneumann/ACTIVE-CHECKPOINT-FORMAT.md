# Bounded GA active-checkpoint format foundation

2026-10-08. PAPER-COMPACT-02A implements an **offline format foundation**. It is
not a production v6 model, native command, migration, continuation decoder,
history deletion or worker activation. PAPER-COMPACT-02 remains open until its
new model/provenance work and many-window acceptance pass. The existing v5
runtime, finite pilot, identities, source and command limits remain unchanged.

## What is implemented

[The codec](vonneumann/research/active_checkpoint.py) captures only an owned,
admitted provider-v5 GA candidate. It revalidates the complete original
transition, including economic/source/optimizer continuation, before projection.
The format has its own explicit name, `ga-active-checkpoint-research-v1`, and
cannot enter either PreparedCommand v5 or an unsupported v6 route.

The active projection preserves reserve, source state, status, revision, risk,
indicators, quote/decision cursors, pending decisions and **all eight original
current members and their accounts**. An early-terminal member remains present
with frozen terminal evidence and its retired zero-cash account until the common
window ends; the cash already reclaimed into reserve is not counted again.
Only open positions remain in the active projection, at most one per member
and eight total. All live accounts/holdings in the admitted source must be
included. Retired nonmember accounts must have zero cash before they can be
omitted from this view.

Configuration, optimizer/RNG evidence, cohort evidence and the eight genomes
form exactly eleven typed immutable components. A component binds format,
hash-policy, owner/run, kind, entity and generation. Its digest hashes the exact
canonical UTF-8 JSON envelope; it is explicitly **not** the opaque PostgreSQL
JSONB checkpoint hash used by PAPER-COMPACT-01, a server receipt or a source
authenticity proof. Configuration uses generation zero; other blocks must match
the current generation and genomes must match the exact ordered membership.

The resolver requires the caller's expected owner/run/revision, every exact
typed slot and the full dependency set. It rejects unavailable, extra,
duplicated, foreign, altered, stale-generation and substituted blocks, including
a valid rehashed phenotype that differs from frozen optimizer evidence. The
resolved projection must equal an independently captured projection of every
original current field. Output is detached and immutable; no solver/RNG/runtime
object or lease is constructed.

References are flat. Unknown configuration fields and generic patches fail
closed. Optimizer node references remain within their one reviewed evidence
block; they are not recursively fetched components. Existing optimizer graph
validation and its separately bounded primitive audit expansion remain in use.

Bounded admission checks cover 64 KiB manifests, 192 KiB individual components,
a conservative 256 KiB manifest-plus-components aggregate **before** resolution,
and 256 KiB resolved evidence. Input traversal has explicit depth64, node20,000,
sequence/map4,096, UTF-8 string16,384-byte and integer256-bit limits before
ordinary encoding/allocation. This v5 bridge still rejects generation4,
source-sequence/EMA-count4,097 and source watermark reset. It does not silently
lift the old guardrails.

Comparing two owned captures identifies changed components. That comparison
is not proof that either checkpoint committed or that a server retained the
blocks. A price-only capture can reuse all eleven components; attempting to
resolve only its empty diff fails. The native contract must establish retained
availability, dependency pins and original-request reconciliation before it can
omit uploads or delete anything.

## Measured evidence and limits

[The retained artifact](research/active-checkpoint-capacity.json) covers two
deterministic real GA preparation traces, sparse and dense, with51 admitted v5
candidates each and the original three complete replacements. Intermediate
price seconds are skipped. The original source is never modified or replaced
by the research capture.

| Measurement | Sparse | Dense |
| --- | ---: | ---: |
| Final source accounts / retained positions | 32 / 13 | 32 / 48 |
| Final projected current accounts / open positions | 8 / 0 | 8 / 0 |
| Final resolved active checkpoint bytes | 54,106 | 54,112 |
| Maximum resolved active checkpoint bytes | 56,638 | 58,481 |
| Maximum manifest bytes | 19,889 | 19,991 |
| Maximum open positions in a capture | 8 | 8 |
| Captures with no changed component | 46 of51 | 46 of51 |
| Component blocks changed across the trace, including bootstrap | 43 | 43 |

The dense final full source after-state is110,027 bytes. The artifact's
hypothetical manifest-plus-new-block sizes exclude operations/events/input
evidence, before-state/reference, create/heartbeat/relay/stop and server retention
checks. They assume previously captured blocks remain available, which is not
an ACK or native commit proof. Do not call these full-command, SQL storage,
TOAST, throughput, latency, Railway-cost or continuous-operation savings.

The existing maximum generation3 is deliberately unchanged. These traces show
that historical rows do not enter the projected active graph; they do not prove
hundreds of accepted windows, durable identity reuse prevention or restoration.
Those are required remaining acceptance cases, not inferred from a byte count.

## Remaining implementation order

1. **PAPER-COMPACT-02B: a separately versioned fresh GA model and provenance.**
   Implement the active model against a bounded ledger boundary, without changing
   old v5 runs or treating this projection as a decoder. Capture finalized
   assessment provenance atomically at scoring time, before retirement erases
   account cash or replacement drops member metrics. Include exact observed
   drawdown ratio/peak/capital, the finite calculation drawdown, final closed-fill
   count, original policy/formula/weight/status, common/source windows, terminal
   reason/time, genes, source policy and exact execution profile. Preserve early
   terminal evidence through the deadline and withhold interrupted cohorts.
   Missing older fields stay missing; no inference from fitness or retrospective
   formula attachment. Prove many dense/sparse windows, finite counter overflow,
   exact cash, complete held positions and same-input optimizer behavior.
2. **PAPER-COMPACT-03: reviewed durable SQL/native admission.** Independently
   query/validate every active account and holding under the owner/run lock;
   enforce historical account/position/command identity uniqueness through
   durable constraints/indexes, not a caller's current-ID list. Verify lineage
   and closed-fill counts against history. Store each original compact request
   once, preserve immutable history/provenance, validate flat components and
   final freshness/lease boundaries, and update old full-journal projection
   dependencies explicitly. Prepare limited-installer/native/old-reader tests,
   reserved Stop capacity, migration validation and evidence-preserving rollback.
3. **PAPER-COMPACT-04…05: exact restoration, retention and hosted acceptance.**
   Prove decoded next-wire/RNG equivalence and original-ID reconciliation, pinned
   readback/archival/restore, actual table/index/TOAST and timing budgets, a closed
   hosted package and bounded many-window/load/restart/held-position operation.

**Deep substantial research remains required:** the smallest effective GA
optimizer/RNG dependency block; actual component invalidation frequency; exact
assessment record/cross-version comparability; indexed completeness/uniqueness
checks under concurrency; retention pins/archives and counter overflow; database
validation/lock/TOAST tails and representative worker/provider budgets. Measure
these before selecting new live-runtime limits.

## Validation, release and rollback

The focused suite covers actual sparse/dense captures, immutable output,
component reuse/availability, generation replacement, early terminal then abort,
owner/run/revision/type/slot/hash errors, rehashed genotype substitution, omitted
member/account/holding evidence, recursive patch refusal, independent aggregate
capacity, structural exhaustion, old watermark/generation caps and runtime
version refusal. The canonical v5 and forward-package checks confirm unchanged
production artifacts. Exact counts and release source/deployment evidence are
recorded in the associated PR after validation. The final focused batch passes
33 cases:20 active-format cases, six checkpoint-reference cases and seven
canonical/forward-package cases. Python parsing and diff checks pass. These
are offline checks; no PostgreSQL/native/hosted many-window acceptance is claimed.

No database grant/schema/data or Railway runtime changes are needed for this
slice. Rollback is a reviewed code/docs revert; there is no production research
schema or accepted compact command to delete. Future rollback must preserve
committed evidence and original pending commands.

From `services/vonneumann`, use the isolated project Python environment with
dotenv disabled:

```sh
python -m unittest tests.test_active_checkpoint tests.test_checkpoint_reference tests.test_canonical_v5_package tests.test_forward_package -v
python -m tests.measure_active_checkpoint --measure
```

Both use deterministic synthetic data with network denied. No production
credentials, source provider requests, global installation, cloud migration or
worker activation is part of the tests.
