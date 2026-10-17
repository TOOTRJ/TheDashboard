# Portable checkpoint inspector — inert laboratory compatibility, 2026-10-12

The new `PortableCheckpointInspector` and pure
`src/lib/probes/portable-checkpoint-inspector.ts` reader display the original
guarded native checkpoint envelope without changing the existing v5 paper
reader, production route, worker, API or controls. They issue no network request,
read no credential/storage, restore no model/optimizer, sign nothing and grant
no restoration, hosted or running authority. Production projection/API wiring
and actual hosted session acceptance remain separate gates.

The input is the actual nine-key
`ga-portable-native-checkpoint-readback-lab-v1` envelope, including the unchanged
seventeen-key observed receipt and thirteen original component wires. The
caller supplies an explicit owner, opaque session/scope key and independent
display binding. That binding is an integrity input, not authentication; never
derive it from the response being checked and then claim verified server
admission. The browser inspector cannot establish package/reader authenticity,
full transition semantics, provider authenticity, current lease or final visible
COMMIT freshness. It makes these limits visible in the UI.

The duplicate-aware bounded parser refuses unknown fields/formats/statuses,
untagged numbers, malformed JSON/Unicode, changed scope/receipt/digests, provisional
receipts, claimed authority and missing/duplicate/reordered dependencies. It
charges the original 589,824-byte envelope, 65,536-byte manifest, 196,608-byte
individual components and 262,144-byte original dependency aggregate. Inner
canonical tagged UTF-8 wires and all thirteen SHA256 references retain their
original slot order/generation/scope. Decimal counters use BigInt validation
and remain strings for display, including revisions above JavaScript's safe
integer limit. Amounts remain the original exact decimal strings; the existing
USD formatter rounds only the visible summary, and the exact stored values
remain alongside it. All quantities/entry prices stay exact strings.

The small result view contains only model/assessment/profile/source headers,
revision/status/generation, source epoch/sequence/EMA count, risk/restart flags,
reserve, eight account balances/EMA genes and retained holdings. The optimizer
graph is treated as bounded opaque evidence for wire integrity; no object graph,
RNG, cumulative private history or economic simulation is restored or rendered.
Generation is not presented as a count of completed windows. Historical records
are visibly marked and grant no continuation authority. Stop may retain holdings;
the UI does not present it as a sale. The original profile still explicitly says
`synthetic-exact-fixture-v1`, with uncalibrated USD-reference execution costs.

Every publication matches the exact current owner, opaque scope key, raw input
and display binding before rendering. A scope/input replacement removes old
fields immediately while digest checking is pending. Effect retirement suppresses
late success/errors; a new session with the same owner/input receives a new scope
key rather than reviving an earlier publication. The component has no buttons
or write actions. Production callers must derive a fresh opaque scope key from
their existing authenticated account/session generation, never render a token,
and clear owner/key while signed out or unverified.

`tests/probes/fixtures/portable-checkpoint-inspector.json` contains only public
synthetic owner identities and literal synthetic-provider documents. Its native
record preserves an unchanged actual scoped committed Stop readback from owned
PostgreSQL17.6, plus separately observed accepted-head/catalog bindings. The
ephemeral catalog digest is fixture-specific; it is not a production package.
The other records come from original-v2 pure fixtures: two completed windows with
16 assessments, and eight held positions with exact18-place quantities and
36-place cash amounts. They are explicitly labeled as lacking native acceptance.
No source/model version is rewritten to claim real Jupiter operation.

`scripts/browser-fixtures/portable-checkpoint-page.tsx` is not an application
route. Root may copy it into the owned snapshot's
`src/app/(dashboard)/portable-fixture/page.tsx`; its `@/../tests` JSON alias remains
valid from that location. The page requires the exact synthetic loopback Supabase
URL and public fixture key. It offers explicit record, scope and malformed/historical
selectors; these operate only on public in-memory fixture data. It performs no
API or worker operation. Root owns the production-build snapshot/CSP/process
cleanup and actual browser driver. The fixture page's scope selector is an
explicit publication experiment, not a claim of real Auth/native API acceptance.

Fourteen focused Node cases pass with zero skips, including controlled callback
gates for owner replacement, A→B→A sessions, logout, overlapping identical inputs
and obsolete success/errors. Full TypeScript checking and scoped ESLint report
zero errors/warnings. The local full frontend suite passes all224 cases, zero
skips (1.650 seconds), on the isolated reviewed base plus this slice; root must
repeat the composed final-head checks. These component callback tests use a controlled hook harness;
actual React/browser acceptance is still required in the owned fixture. Before a
production projection is connected, accept the independently authenticated
new-version projection/API, old/new reader compatibility and exact-target closed
session/control joins, preserving the existing v5 behavior and all native gates.
