# Exact research configuration type repair

PAPER-COMPACT-TYPE1, reviewed 2026-10-12. This repairs configuration evidence
validation in both provider GA research versions. It does not select a new
runtime, native command, SQL contract, checkpoint restoration or hosted worker.

## Defect and preserved evidence

The original v1 and v2 reconstruction guards used ordinary Python dictionary
equality. A configuration component could replace the pinned integer
`lifecycle_policy.max_lifespan_seconds = 0` with boolean `False`, recompute its
canonical component hash, and resolve successfully because Python treats
`False == 0`. The historical [review evidence](research/2026-10-12-config-type-review.json)
records this behavior against the original source hashes. It remains unchanged;
it is evidence of the defect, not current acceptance or hosted authority.

## Rejection before reconstruction

The research-only `exact_configuration.py` helper walks an immutable trusted
template produced from each model's reviewed default configuration. It requires
exact primitive types, complete dictionary keys, fixed list lengths and pinned
policy/header values before constructing a configuration from caller values.
Only eight documented plain string settings may vary: initial cash, candidate
seed capital, search seed, the three execution cost settings, account loss bps
and source epoch. Their canonical text, range and economic relationships remain
checked by the existing constructors. Final canonical JSON byte equality refuses
normalization into a different declared configuration.

Candidate guards additionally validate the original before/after configuration
records. Boolean, integer, float and string substitutions cannot pass by matching
an owned state through Python equality. Unsupported types, extra/missing fields,
changed headers/policies and altered list membership fail. The helper consumes
no RNG, runs no trading or solver operation, reads no environment credential and
creates no owned runtime state.

## Compatibility and version decision

The original v1/v2 model, code, operator, software and transport policy headers
stay unchanged. This is stricter rejection of evidence that was already outside
the declared type contract; no canonical input/output semantics change. The
repair never converts `False` to `0`, relabels a checkpoint, accepts a different
model chain or changes default GA selection. Previously canonical configurations
reconstruct to identical bytes, and every original legacy candidate/compact-wire
hash remains mandatory in regression acceptance.

The v1 validator source hash intentionally changes. The original legacy and
portable measurement artifacts remain historical. The
[repair evidence](research/configuration-type-repair-measurements.json) separately
binds original and repaired sources, both refused reproductions and the version
decision. The legacy regression test permits only the exactly source-bound
documented repair for `provider_ga_model.py`; the two unchanged legacy checkpoint
source hashes and all seventy original wire pairs still must match.

## Acceptance and remaining gate

Six focused offline tests pass, covering 423 scalar type substitutions rejected
before model reconstruction, 29 correctly rehashed nested/unknown/missing-field
cases, original before/after candidate refusal, unchanged owned state/RNG/ledger,
identical reserved Stop preparation and canonical alternate cash/cost/seed values
with unchanged version/software bindings. Unsupported dictionary key subclasses
are rejected before any custom equality can run. Twenty-two existing package tests pass.
Float aliases are rejected during typed-component validation; validly encoded
boolean/string/integer aliases reach the complete resolver and are rejected there.

The portable model regression additionally reruns the original seventy legacy
wire pairs and three seeds/four synthetic windows each. New results are recorded
in [repaired portable measurements](research/portable-ga-model-type-repair-measurements.json),
with a hash linking the unchanged historical portable measurement artifact.
These are finite offline consistency checks, not economic calibration or proof of
all possible inputs.

Complete independent v2 SQL semantics remain PAPER-COMPACT-03B3C2B2B. It must
enforce this exact configuration contract alongside all mutation, RNG, selection,
ancestry, economics, source, lifecycle, assessment and same-version prior-chain
checks. Atomic journal/receipt/identity/pin/final-freshness/lease/Stop admission,
exact restoration and retention/closed hosted acceptance remain subsequent gates.
No research function is installed in Supabase and no worker capability is opened
by this repair. Rollback is a reviewed code/docs revert; original defective type
aliases must never be treated as newly accepted canonical evidence.
