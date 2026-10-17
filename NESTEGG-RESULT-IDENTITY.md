# Nestegg calculation identity and same-account publication ordering

NEST-05A, implemented 2026-10-13. This extends the completed NEST-06A
account/login-session boundary. It changes browser state publication and export
provenance. Financial projection formulas, monthly return distribution, tail
clamps, volatility, the FNV-1a/Mulberry32 seed implementation and simulation path
counts are unchanged. Model calibration and historical financial validation
remain separate work.

## Calculation snapshots and eligibility

Every request captures an immutable scalar input snapshot and market preset.
Its result envelope records an opaque workspace identifier, the exact input and
scenario serialization, input revision, request revision, model version, seed
policy, purpose and path count. The input copy preserves insertion order because
the existing seed calculation uses input JSON ordering. These are browser-local
publication identities; they do not carry an Auth token or authorize database
operations. Financial input identity remains private to the mounted workspace
and is never embedded in React keys.

Input edits, preset changes, plan selection and reset retire calculation
revisions synchronously in their event handlers. An X → Y → X edit therefore
cannot resurrect an earlier X result. Rendering derives eligibility against the
current input and request revisions before an effect or the 800 ms debounce can
run. Chart bands, quick odds, hero highlights, goal odds, detailed metrics,
insights, preset comparison, saved-plan comparison and exports receive a current
result or an explicit pending/unavailable state. Deterministic projections still
update immediately.

Light and full requests each have a latest-request revision. Result, progress
and failure callbacks require the existing account/session capture and both the
captured input and request revisions to remain current. Status completion uses
the same guards. Identical-input overlapping runs cannot publish an older
completion or clear a newer running state.

Full analysis publishes its main 1,100-path simulation, three 350-path preset
comparisons and 320-path conservative simulation as one coherent 2,470-path
bundle. Intermediate stages never become full results. A failed stage leaves
the full analysis unavailable and retryable; a current light result can still
serve the quick view and export. Rerunning full analysis retires the previous
full bundle until the replacement completes. Retiring a publication does not
abort already executing Monte Carlo chunks; it discards their callbacks and
prevents retired full stages from starting the next stage.

Saved-plan comparisons independently bind the selected row ID, update revision,
input snapshot and preset. Row changes, refreshed row contents, repeated
requests and retired account sessions cannot show an old comparison under a new
label. Rejections show a retry button instead of indefinite loading.

Exports receive only eligible results. If no current simulation exists, both the
menu and report say **deterministic only**. A simulation export records model
version, seed policy, analysis purpose and total analysis paths alongside its
simulation path count. Model and seed tags describe this code version; they are
not a claim of financial-model accuracy or Monte Carlo independence.

## Cloud replies and workspace intent

Saved-list requests have an independent latest-request revision. An older
refresh cannot publish its rows, show an error, or clear the pending indicator
for a newer refresh. A refresh updates the list without reloading the selected
workspace or replacing local financial edits.

A workspace-intent revision orders selection, edits, reset, save, duplicate,
rename and delete publication. Active-plan saves capture the row ID, inputs,
preset and name before dispatch. A late save cannot replace a newly selected
plan, newer inputs/name, or their dirty baseline. Local dialog revisions also
protect newer duplicate/rename names and cancelled dialogs. A duplicate reply
may select its captured saved row only while that original workspace intent is
current. Rename publishes name metadata and its saved-name baseline without
reloading stored financial inputs, preserving existing unsaved financial edits.

Original owner predicates, RLS, verified per-request token snapshots and account
session checks remain in `scenarios-supabase.ts` and the existing session scope.
An already dispatched write can finish under its captured authority after its
browser publication is retired. This repair neither rolls back such a write nor
implements server-side optimistic concurrency/idempotency. Concurrent writes
from another tab/device, or overlapping dispatched writes to one row, still
require a separate database concurrency contract; refreshing can recover the
actual stored state. Retired replies never claim that an uncertain write was
reversed.

## Verification and remaining acceptance

Twenty-three new controlled Node cases exercise the actual helper/page/toolbar/
comparison/export source. They cover every result consumer during debounce,
X → Y → X, old light completion before a new effect, same-input overlapping full
requests, late progress/error/completion, staged bundle publication, partial
failures, newest refresh, save A/select B, save then input/name edits,
metadata-only rename, export provenance/unavailability, selected-row refresh,
comparison failure/retry, retired sessions and late duplicate/rename dialog
replies. The 21 existing account/storage regressions remain passing. The final focused suite has 44 cases; the complete frontend/helpers suite has 233 cases. TypeScript passes and scoped lint has zero errors or warnings; broad source/test/script lint retains the existing 32 warnings and has zero errors. The isolated fresh fake-configuration production build passes with 151 reviewed files (1,328,622 bytes).

The VM/custom-hook fixture executes controlled callbacks and JSX props. It is
not a real React renderer, browser, Supabase/Auth integration or hosted financial
acceptance. QA-01B must exercise the real browser flows, including Strict Mode,
account replacement, routing and event/paint ordering. Broader portfolio-link
semantics, financial formulas/calibration and popup/download success reporting
remain their existing open tasks. No database migration, hosted data,
credential change or financial operation is needed by NEST-05A.

Rollback is a reviewed code/documentation revert. It would reintroduce stale
result and late-response publication; it is not a draft storage migration and
must preserve the independent NEST-06A account/session boundary.
