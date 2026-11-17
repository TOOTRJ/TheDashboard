# Picomatch development tooling review — November 17, 2026

The fresh full npm audit reports 14 high development dependency findings from
one leaf advisory, [GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf).
The separate production audit reports zero findings. The affected installed
picomatch versions are 2.3.2 and 4.0.7, reached through the existing Next.js and
TypeScript ESLint tooling. No application endpoint supplies patterns to this
development lint graph.

The official advisory describes denial of service from repeated single-branch
extglob patterns and lists no patched release. The public registry and
[upstream releases](https://github.com/micromatch/picomatch/releases) still identify
4.0.7 as latest. The cited [upstream PR 194](https://github.com/micromatch/picomatch/pull/194)
remains open and explicitly leaves the `+(*a)` case unresolved. That PR is not a
complete security repair. npm's proposed Next 14 lint configuration downgrade
is unsuitable for the current Next 16 and ESLint 9 setup.

The reviewed exception expires at **2026-11-24 00:00 UTC**. It accepts only this
advisory, its exact severity/range, all 14 observed dependency graph entries,
their exact direct edges, and 15 exact development-only lockfile paths and
versions. The evaluator rejects changed or additional graph evidence, runtime
classification, unrelated advisories, scanner failures and expiry. Production
dependencies must continue to have zero findings.

Lint inputs are fixed repository paths (`src`, `tests`, `scripts`) and reviewed
repository configuration, executed in bounded verification jobs. This scoped
exposure assessment does not make execution of untrusted repository JavaScript
or malicious lint configuration safe. The advisory remains present and visible;
no dependency was represented as patched, no lint rule was removed, and no
package or framework downgrade was applied.

Remove this exception as a priority when a compatible published repair is
available. Before the expiry, recheck the official advisory and registry,
review the transitive graph, and either install a verified fix or explicitly
reassess this exact development exposure. The previous withdrawn braces
exception remains removed.
