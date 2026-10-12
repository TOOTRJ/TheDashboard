# The Dashboard

The Dashboard is a Next.js application with an evolutionary paper-trading worker
and a Nestegg retirement calculator. The repository is still undergoing its
correctness and reliability audit. Read [AGENTS.md](AGENTS.md) before operating
cloud tools: another project uses the same local and cloud accounts.

## Nestegg (retirement calculator)

The feature at `/nestegg` is documented in [README-NESTEGG.md](README-NESTEGG.md).
Its financial-model, privacy, result-identity and export audit items remain open
in [TODO.md](TODO.md); existing outputs are not independently accepted financial
projections.

## Current implementation status — 2026-10-12

Vercel hosts the dashboard, Supabase holds the selected v5 exact paper ledger and
owner history, and Railway hosts the Python service in **closed mode**. The
original supervised zero-cost hour passed at revision 514 with 504 prices, one
replacement, eight funded children, two closed trades and 32 acknowledged events.
The owner history repair/readback passed; temporary credentials were revoked and
ordinary closed startup restored. This is finite mechanical acceptance, not
continuous operation or evidence of trading profitability.

PR96 and [PR97](https://github.com/TOOTRJ/TheDashboard/pull/97) are merged. The
reviewed baseline is `67cff30`; PR97 production
`dpl_ASo5z4Zc6APWsUPseQVrvw52Aici` was READY with canonical-alias/four-probe
verification. Railway remains closed at deployment
`cf05895d-adc5-427f-873e-82ad6606e5a1`. This review freshly reverified exact baseline deployment metadata and all four
read-only probes, plus unchanged Railway target/service settings. Prior native
TLS/image/active-workload acceptance was not repeated.

The portable two-EMA integer model and compact transport are built offline. A
new review reproduced a boolean/integer configuration-type acceptance defect;
repair that boundary before completing independent version 2 SQL semantics. The
new model is not fully validated, admitted by the hosted native writer or enabled
in Railway. Native compact effects, exact restoration, dependency-safe retention,
new-version dashboard compatibility and hosted fault/load acceptance remain open.
Live funding, signing, swaps and execution remain unavailable and unauthorized.

See [MVP-READINESS.md](MVP-READINESS.md) for the current gate order,
[TODO.md](TODO.md) for dependencies and parallel work, and
[CONFIGURATION-PREFLIGHT.md](CONFIGURATION-PREFLIGHT.md) for release evidence.
[RAILWAY-SETUP.md](RAILWAY-SETUP.md) records exact worker target and credential
boundaries. Security/CI, app/API honesty and privacy, and data/fill/objective
research can proceed alongside the ordered SQL/native/restoration work.

## Getting Started

Use Node.js 24, as selected by `package.json`, and the checked-in npm lock. Keep
runtime selection local; do not globally upgrade or change shared CLI profiles.

For the frontend, check port 3000 before starting a process and track only the
process you start:

```bash
npm ci
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

Routes are under `src/app`. Private environment files and `ssl/` are ignored.
Use explicit project-specific configuration from the preflight report; a local
`.env` does not configure Railway or Vercel. Current Vercel preview/development
settings share production Supabase values, so previews are not isolated write-test
environments. Do not copy worker/admin secrets into browser variables.

The Python worker targets Python 3.12 and hash-locked dependencies in
`services/vonneumann/requirements.txt` and `requirements-dev.txt`. Use a dedicated
virtual environment outside the source checkout; the worker tests must not load
private dotenv settings. [Offline research](services/vonneumann/OFFLINE-RESEARCH.md)
and the [isolated PostgreSQL harness](services/vonneumann/tests/postgres/README.md)
document reproducible local work. Starting a local process or decoding a
checkpoint does not grant a hosted lease or permission to trade.

## Verification and remaining acceptance

The frontend's local checks are:

```bash
node --test tests/*.test.mjs tests/probes/*.test.mjs
npx tsc --noEmit
npm run lint
```

A build needs explicit Supabase client **and server** configuration because API
modules construct the server client during page-data collection. For a
credential-free check, copy only tracked `src/`, `public/`, build configuration
and manifests plus reviewed dependencies into a task-specific temporary directory;
exclude `.env*`, `.vercel`, `ssl/`, `.claude/` and other private files. Run there
with fake values, preserving the checkout's `.next`:

```bash
NEXT_TELEMETRY_DISABLED=1 \
NEXT_PUBLIC_SUPABASE_URL=https://dashboard-build.invalid \
NEXT_PUBLIC_SUPABASE_ANON_KEY=dashboard-build-placeholder \
SUPABASE_SERVICE_ROLE_KEY=dashboard-build-placeholder \
API_SECRET_KEY=dashboard-build-placeholder \
npm run build
```

Run Python tests with `PYTHON_DOTENV_DISABLED=1` and
`PYTHONPATH=services/vonneumann` in the isolated worker environment. From this
repository root, use that environment's Python executable:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
PYTHONPATH=services/vonneumann /path/to/dashboard-worker-venv/bin/python \
  -m unittest discover -s services/vonneumann/tests -t services/vonneumann
```

Ordinary offline regressions require no production credentials; real PostgreSQL cases are
explicitly opt-in and own their network-disabled containers. Their passing
results establish the tested scope, not hosted source, COMMIT, quota or latency
acceptance. Secret-free CI wiring and broader audit closeout remain QA work.

## Release boundaries

Use `codex/` branches and reviewed pull requests to `TOOTRJ/TheDashboard` through
the repository's scoped GitHub helper. Reverify exact GitHub, Vercel, Supabase and
Railway identities before consequential operations. Use only the dedicated
Dashboard Vercel profile; retain the other agent's credentials, tools and processes.

A dashboard Git deployment does not deploy or activate the Python worker.
The ordered next steps are strict portable configuration repair, complete
independent version 2 SQL semantics, atomic native compact effects, exact
restoration, verified retention and new-version reader compatibility, then
closed-package and bounded hosted acceptance. Prepare migration verification and
evidence-preserving rollback before any authorized forward application. Expanding
genes, replacing optimizers and real execution follow their separate research
and authorization gates.
