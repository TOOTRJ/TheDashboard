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

## Current implementation status — 2026-11-17

Vercel hosts the authenticated dashboard, Supabase stores application data and the
paper ledger, and Railway hosts the Python worker. PR119 and documentation PR120
are merged. The first continuous run reached bootstrap but failed before its
first evaluation; its original owner Stop is now independently verified at head
2, with zero open positions and all history retained. The next local reliability
candidate addresses repeated mark parsing and stale-sample/current-mark recovery,
plus finite credential renewal. Its release and a fresh pilot's complete
observation gate remain pending. The dated checkpoint in
[the preflight](CONFIGURATION-PREFLIGHT.md) records the evidence and boundaries.

The active work joins the two-EMA prospective model to durable observations,
restartable state, owner controls and dashboard history. Initial warm-up requires
915 complete qualifying minutes, followed by a full 60-minute evaluation before
the first replacement. Source adoption and the bounded native/hosted launch
checks are accepted. Stale-sample recovery, finite credential renewal, genuine-gap
succession and terminal/storage headroom remain prioritized in the active TODO
before claiming reliable unattended operation.

This personal application uses one production Supabase database and one Vercel
project. Pull requests retain offline verification; only `main` automatically
deploys to Vercel production. Branch previews and separate staging databases are
not required. Railway releases target only the pinned Dashboard worker. Private
worker credentials stay in that service; browser variables never carry them.

See [TODO.md](TODO.md) for the active ordered checklist,
[MVP-READINESS.md](MVP-READINESS.md) for acceptance details,
[CONFIGURATION-PREFLIGHT.md](CONFIGURATION-PREFLIGHT.md) for target/release evidence,
and [RAILWAY-SETUP.md](RAILWAY-SETUP.md) for worker configuration. Further data/cost
research and the broader dashboard audit can run alongside implementation. Live
funding, signing, swaps and activation require separate authorization.

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
`.env` does not configure Railway or Vercel. Local development uses the same authorized production database; use offline
fixtures for destructive or synthetic integration tests. Automatic branch previews
are disabled by the production-only deployment policy. Do not copy worker/admin secrets into browser variables.

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
npm run test:frontend
npm run typecheck
npm run lint
npm run check:advisories
npm run check:build
```

A build needs explicit Supabase client **and server** configuration because API
modules construct the server client during page-data collection. `check:build`
copies only tracked frontend/build inputs into a new owned temporary directory,
installs the lock without lifecycle scripts and builds with fixed fake keys and
the reserved `dashboard-ci.invalid` URL. It excludes private environment files,
cloud/agent configuration and existing dependencies/build outputs. New frontend
source must be staged before this tracked-input check. The checkout's `.next`
and other-agent files remain untouched.

Run Python tests with `PYTHON_DOTENV_DISABLED=1` and
`PYTHONPATH=services/vonneumann` in the isolated worker environment. From this
repository root, use that environment's Python executable:

```bash
/path/to/dashboard-worker-venv/bin/python scripts/check-worker.py offline
/path/to/dashboard-worker-venv/bin/python scripts/check-ci.py
```

The worker wrapper requires the hash-locked CPython 3.12.14 environment and
sanitizes its own child before discovering worker and helper tests. Ordinary
offline regressions report SQL skips rather than claiming integration acceptance.
Real PostgreSQL cases require the reviewed native wheel bundle and `scripts/check-worker.py postgres
--allow-isolated-postgres` and the reviewed owned fixture setup. Their passing
results establish the tested scope, not hosted source, COMMIT, quota or latency
acceptance. [CI gates and isolation](CI-VERIFICATION.md) document the three
independent verification gates, seven required jobs and their first-run acceptance requirement. Actual browser
acceptance and broader audit closeout remain separate QA work.

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
