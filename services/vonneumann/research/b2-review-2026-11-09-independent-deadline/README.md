# Independent write, recovery and login deadlines

The focused case passed in 43.559 seconds on isolated PostgreSQL 17.6.
Actual recorder and reader connections used direct SCRAM and verified TLS.
The recorder staged the original Acquire before its application write
deadline. The literal COMMIT refused after that deadline and before
PostgreSQL login or fence expiry. While a fresh recorder login still
worked, the write, duplicate submit and writer getter all refused. The
independent reader still recovered the exact committed Install after the
recorder's PostgreSQL login expired.

A separate reader query passed its initial authorization, then waited on
an owned relation lock. After its read deadline, the final clock check
refused the absent response even though reader login still worked. Fresh
present and absent lookups also refused. Committed rows remained unchanged.
The blocked case exercises an absent lookup. A present lookup already in
progress at cutoff and final wire delivery are outside this proof.

Reconstruct the [six SCRAM inputs](../b2-review-2026-11-06-v20-o-r-i2a-scram/README.md)
and apply the [forward patch](candidate-scram-to-independent-deadline.patch). The
[manifest](candidate-manifest.json) pins the unchanged table declarations,
new private scalar check, changed authorization and exact test census.
The [run recipe](deadline-review-and-run.md) and [native receipt](native-receipt.json)
record the test and source bounds. All 942 source files and locked
dependencies were unchanged, with normal owned cleanup.

The companion [retirement proof](../b2-review-2026-11-09-owner-terminal/README.md)
uses the earlier login-deadline profile. Compose its control and reader
margin checks with these application deadlines before a handoff. The
focused proof uses disposable credentials and a fixed scope.

The initial inherited ordinary run hit the unchanged 240-second controller
limit. It logged 40 successes, then stopped during the last case before a
final result. The exact-owned fallback removed its group and container.
The [timeout receipt](initial-ordinary-timeout.json) keeps that run distinct
from the focused pass.

The [R2 correction](candidate-independent-deadline-to-r2.patch) skips the
extra pre-lookup validation for the two existing package formats. Both
formats still pass the full target-aware authorization before a getter
response. The new deadline profile retains both checks. The
[R2 manifest](candidate-manifest-independent-deadline-r2.json) pins that
two-file delta. All 46 cases passed on the corrected source under the same
per-group deadline. The ordinary 41 took 123.870 seconds. The two real
fence-clock cases, limited issuer, direct SCRAM login cutoff and independent
deadline case each passed in their own bounded group. All five groups
preserved their 942 source files and dependency inventory and cleaned up
normally. [R2 receipts](r2-native-receipts.json).
