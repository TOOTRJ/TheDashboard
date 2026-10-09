# Compact checkpoint research and implementation order

2026-10-08. **The reference prototype is offline only.** It is not a v6
migration, runtime command, restart decoder, retention job or continuous-paper
release. The existing v5 worker, native capabilities, release catalog, source
freshness, lease budgets and finite-pilot limits remain unchanged.

## Findings and measured boundary

The actual owner hour previously retained 58,114,764 logical request bytes and
23,316,227 compressed column bytes. Those figures exclude row/index/TOAST
overhead. PostgreSQL [TOAST](https://www.postgresql.org/docs/17/storage-toast.html)
compresses or stores variable-length values outside a tuple; it does not remove
the logical validation cost or change the application's 262,144-byte admission
limit. Compression settings alone cannot repair growing command/state graphs.

The new deterministic [capacity artifact](research/checkpoint-reference-capacity.json)
measures the actual v5 candidate/PreparedCommand encoding against a reference
transport, using synthetic provider documents, original pure preparation and
unchanged admission. The placeholder hash is exactly 64 characters; it is not
a server receipt. Counts and savings cover accepted prepared commands only,
excluding creation, heartbeats, event relay and stop, and skip intermediate
price seconds. This is neither a polling/latency benchmark nor a replay of the
actual hour. No empirical database storage, CPU, RAM or hosting savings are
claimed. Rejected model preparations remain rejected and are not installed.

| Synthetic trace | Accepted commands | Original logical request bytes | Reference logical request bytes | Reduction | Final generation |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sparse GA | 51 | 6,970,811 | 3,640,657 | 47.77% | 3 |
| Dense GA | 51 | 8,307,811 | 4,358,155 | 47.54% | 3 |
| Dense DE | 51 | 8,544,842 | 4,480,674 | 47.56% | 3 |
| Dense PSO | 50 | 10,064,114 | 5,235,032 | 47.98% | 2; next replacement rejected |
| Dense CMA | 34 | 6,308,499 | 3,309,389 | 47.54% | 1; next replacement rejected |

All eight sparse/dense solver traces reduce logical request bytes by
47.54–48.22%. The dense GA after-state is still 110,027 bytes: positions alone
are 43,920 bytes and optimizer evidence 31,962 bytes. It retains 32 accounts,
48 positions and 80 used IDs at generation three. Component lengths are
individual JSON values; punctuation/top-level fields add further bytes, so
their sum is not an exact decomposition of the whole payload. Maximum dense
GA reference payload is 129,664 bytes while its expanded validation payload
remains 234,635 bytes. A reference to yesterday's full growing state does not
make tomorrow's active state bounded.

Other explicit bounds remain: the inner model's three replacements, 32
accounts, 64 positions, 100 used IDs; EMA count and provider sequence through 4,096; owner
through 4,096 command identities; the finite pilot's 4,000 commands, 3,601
quotes, one completed generation and 3,660 elapsed source seconds. These are
separate guardrails, not settings to silently increase. The source watermark,
command-identity retention and model policy must all be reviewed with the new
format rather than bypassed by a transport change.

## Implemented reference experiment

[The pure codec](vonneumann/research/checkpoint_reference.py) accepts an owned
ExactCandidate, revalidates its unchanged v5 byte/model limits, removes only
`transition.before`, and retains a detached immutable wire. The descriptor
contains owner, run, prior revision, hash-policy version and SHA-256 of the
server's PostgreSQL-17 JSONB checkpoint text, including explicit JSON null for
fresh bootstrap. Client JSON bytes are never called the server hash. JSONB
normalizes objects and has its own textual/numeric representation; see
[PostgreSQL JSON types](https://www.postgresql.org/docs/17/datatype-json.html).
The local codec checks binding and complete expansion but cannot authenticate
that opaque hash. The server must verify it against its locked state.

[The SQL experiment](db-contract/research/checkpoint_reference.sql) requires an
explicit offline fixture marker and ships no client grants. It runs only in an
owned, network-none disposable PostgreSQL17 container. Fixture setup grants
only the synthetic economic role; installation/observation use fixture
administration. This is not proof of a deployable limited-installer/native
authentication contract. It is outside the production builders/manifests and
has no runtime import or API routing. The marker prevents accidental execution;
it is not a cloud security boundary.

The experiment locks the exact owner/run row, verifies version, worker/fence and
current lease, compares an existing command's complete original request before
resolving a new checkpoint, then checks current revision and the complete
descriptor. It reconstructs the original v5 transition exactly and applies the
unchanged independent source/model/economic/projection/outbox checks. Both the
compact wire and expanded logical model remain bounded at 262,144 bytes.
[Row locks](https://www.postgresql.org/docs/17/explicit-locking.html) serialize
this inspection against a competing writer; the reference is checked after
waiting for the lock. Additional research journaling is followed by source
freshness and lease checks before returning. External transaction lifetime
still needs the established native transport's transaction-end/cleanup policy.

It keeps **both** the ordinary full v5 journal and a research original-wire
journal. Therefore the fixture adds storage; the byte savings above are a
counterfactual transport comparison. Production cannot use this wrapper as a
storage repair. A future version must journal the original compact wire once,
retain its component dependencies, and update the projection trigger that
currently reads full before/after states directly from the v5 request.

Original replay returns the original response without expansion against a
newer checkpoint. Readback remains available after lease expiry. A missing row
is not evidence of failure and never permits a new ID. Late journal failure,
late freshness/lease loss, wrong identity/fence/hash, capacity overflow and
inner economic/source corruption roll back all effects. Anonymous/browser,
service-role and relay fixture clients have no research access. Old v5 readers
and command admission are not widened. A digest is a corruption check under
the authoritative owner/run/revision and lock; it is not a substitute for lease
authority or full original-request equality.

## Next forward format: active state and immutable history

Start with the eight-candidate, two-EMA-gene GA paper profile. The four-solver
measurements do not grant restart/continuous support for DE, PSO or CMA. Proposed
changes below need a separately versioned model/configuration and SQL package;
they are not transformations of old v5 evidence.

1. **Bound active state structurally.** Keep exactly the current eight cohort
   accounts, including early-terminal members until the window ends, and only
   their open positions (at most one each). Keep current reserve, risk latch,
   pending decisions, indicator state and bounded source cursor/bars. Retired
   nonmember accounts and closed positions stay in immutable owner/run ledger
   rows and curated history, not in the active model. SQL independently checks
   current cohort membership and all live ledger accounts/positions; omission
   cannot hide money, an open position or a terminal candidate.
2. **Avoid repeated immutable graph blocks.** Version immutable configuration,
   genes/lineage, optimizer/RNG snapshots and completed assessments as typed
   component records. A checkpoint manifest binds component identities/hashes
   to the same owner/run/entity/generation/revision. Send only new blocks and
   bounded explicitly typed changes to mutable state. Avoid a generic JSON
   patch or recursively expanding reference chain. Independently bound the
   resolved aggregate bytes, reference fanout and validation work. A price mark
   should not resend an unchanged full optimizer graph.
3. **Move global uniqueness to the durable ledger.** Account/position/command
   identity uniqueness must cover historical records after active pruning.
   Latest-memory `used_ids` cannot provide that guarantee. Never delete or
   reuse identities still referenced by a pending original command, lineage,
   current checkpoint, relay/ACK, recovery or audit/export requirement. A
   source counter remains monotonic for the run; do not wrap or reset it just
   to fit an old 4,096 limit. Prove overflow and reserved Stop behavior.
4. **Freeze completed assessment evidence atomically.** Store a new explicit
   assessment format with fitness policy version/formula/weight and status,
   tagged finite ROI/fitness/calculation drawdown, exact observed drawdown
   ratio and terminal peak/capital, final closed-trade count, terminal reason
   and measurement time/basis. Bind original membership/genes, common source
   start/deadline/completion, source policy/window evidence, effective exact
   execution costs and selection policy. Preserve the early-terminal result
   through the common deadline. Aborted cohorts remain withheld, including
   early scores; missing old provenance remains missing. Do not reconstruct
   historical drawdown from fitness or attach a new formula to old results.
5. **Prove restart, not just serialization.** The present optimizer artifact
   is an evidence encoder, not a decoder, and ExactState deliberately admits
   fresh bootstrap only. Implement a reviewed GA-only allowlisted decoder
   with exact dependency/policy versions, alias/order/type checks, RNG state,
   cohort frozen genomes/evaluations, indicators, source identity and accounts.
   The restored run must reconcile pending original commands and holdings;
   loading a checkpoint does not obtain a lease or automatically resume trades.
   Compare the entire next prepared wire against uninterrupted execution for
   mid-window, terminal, replacement, stopped and uncertain-commit boundaries.
6. **Design retention with pins before deletion.** Retain original wires and
   immutable blocks needed for replay/recovery/history. Separate terminal
   receipt lookup from large blocks; evaluate partitioning/archival only after
   verifying equivalent original-ID lookup and dependency pins. An archive
   needs manifest, owner scope, integrity verification, readback and restoration
   proof before referenced data can be removed. Choose age/count/storage budgets
   from representative measurements, not an invented fixed number of days.

## Acceptance, deployment and rollback

The next stages must prove long flat-price periods, dense entry/exit periods,
many cohort replacements, early death, cost-triggered risk halt, interrupted
holdings, restored next-wire/RNG equivalence, late rollback, source regression,
source/lease expiry at final commit, pending Stop reserve, complete read
projections and actual ledger uniqueness under concurrency. Measure wire,
resolved validation, table/index/TOAST growth and query tails separately. Use
equal synthetic inputs/versions when comparing before/after; do not extrapolate
the skipped-second traces to Railway cost or sustained throughput.

Before a hosted migration, prepare the new canonical package/manifest,
limited-installer/native capability tests, closed writer-drain/catalog checks,
old/new read compatibility, explicit grant/binding review and exact-target
forward validation. Old runs remain v5 historical evidence; no implicit
in-place restoration, version switch or rescoring. First deploy closed, prove
read/recovery compatibility, and only then run another bounded paper acceptance
with temporary scoped capabilities. Continuous operation stays gated.

This research slice requires **no Supabase migration or Railway activation**.
Rollback is a reviewed code/docs revert; there is no production research schema
to drop. Future schema rollback must preserve accepted original commands and
assessments, close/revoke only the new scoped writer, and reconcile pending
operations before selecting any earlier runtime; dropping committed evidence
or silently downgrading a new checkpoint is not a rollback strategy.

Validation for this slice: 11 pure codec/model/capacity cases, 11 actual isolated
PostgreSQL cases (the ten-case batch plus the added final-source expiry case),
and seven unchanged canonical/forward package checks pass. The six codec cases
are rerun after adding explicit original-envelope key validation. All eight
measurement traces are retained with Python/NumPy/CMA and model/transport
versions. These are focused checks, not a claim that all repository tests or
future restoration/continuous-operation acceptance are complete.

**Deep substantial research remains required:** component addressing versus
bounded typed deltas; archive pins and legal/operational retention needs;
GA decoder/version maintenance and exact randomness; objective sensitivity and
cross-version metrics; database lock/TOAST/validation and network timing tails;
effective Jupiter metering and representative source-age/fill distributions.
Use current primary documentation and measurements before finalizing defaults.

## Reproduce offline

Use the isolated project Python environment, with dotenv disabled:

```sh
python -m unittest tests.test_checkpoint_reference tests.measure_checkpoint_reference -v
python -m tests.measure_checkpoint_reference --measure
DASHBOARD_ISOLATED_POSTGRES_TESTS=1 python -m unittest tests.postgres.test_checkpoint_reference -v
```

Run from `services/vonneumann`. The PostgreSQL harness requires the already
cached pinned image and local Unix-socket Docker/Colima daemon, starts only its
unique network-none container, and removes only that owned container. It never
loads production database credentials, mounts application secrets, publishes
ports, installs global tooling or prunes shared Docker state.
