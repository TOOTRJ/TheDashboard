# Python worker hosting research

Research date: **2026-09-30**. Scope: public primary documentation and the Dashboard's local source. No provider account was queried, service provisioned, credential inspected or changed, or worker started for this research. Prices are USD estimates before tax, provider API subscriptions, and any unlisted usage charges. Recheck the selected plan and region before provisioning.

**Recommendation:** use a paid **Render Web Service in Oregon** for the first controlled paper pilot, after the recovery and ownership gates below pass. Budget initially for **1 CPU / 2 GB at $25/month**; this is a provisional capacity choice, not a measured requirement. Railway is a strong alternative with usage-based billing. Fly.io is worth evaluating when measured regional latency or VM control justifies its additional operational work. Keep the existing Next.js frontend on Vercel.

**No host makes the current worker ready for unattended operation.** DB-03 durable restart/reconciliation and SVC-02 ownership/resource coordination remain prerequisites. Hosting selection does not establish strategy quality, realistic execution, profitability, or authorization for wallet funding, signing, swaps, or live trading.

## Actual application requirements

The current worker combines FastAPI HTTP controls, authenticated read-only WebSockets, and continuous colony tasks in one Python process:

- [The FastAPI app](services/vonneumann/vonneumann/server/app.py) creates a module-level `ColonyManager`; its lifespan calls manager shutdown. The same server accepts HTTP and WebSocket traffic.
- [The manager](services/vonneumann/vonneumann/core/colony_manager.py) keeps controllers, tasks, locks, and status callbacks in process memory. Two Uvicorn workers would own different managers. A process restart restores no runtime checkpoint. Its shutdown currently stops colonies sequentially, so the host's termination allowance must be tested against the whole configured workload.
- The public `/api/v1/health` route currently returns process liveness only. It does not prove database/feed readiness, reconciliation, or ownership of previously running colonies.
- SVC-02A now reserves starts before writes and supplies a bounded, owned drain with a permanent controller pause. Authenticated `/api/v1/readiness` remains HTTP 503 with durable recovery unavailable, even when local admission is open. The default 32 retained-colony bound is not a measured host-capacity limit. Validate the host's grace period against pending-write/cleanup tails; the 40-second local report cannot prevent SIGKILL or restore state after process loss. [Implemented lifecycle contract](services/vonneumann/WORKER-LIFECYCLE.md).
- [The runtime pin](services/vonneumann/.python-version) is CPython **3.12.14**. [Runtime dependencies](services/vonneumann/requirements.txt) are pinned with hashes; the direct inputs are in [requirements.in](services/vonneumann/requirements.in). A Linux image installation still needs verification; local macOS test success is not that verification. There is no worker Dockerfile yet.
- [Configuration](services/vonneumann/vonneumann/config.py) reads worker secrets and exact allowed browser origins. The documented Uvicorn command uses port 8765; deployment must explicitly bind the platform's port on `0.0.0.0`. Declaring `VN_WS_PORT` alone does not configure a Uvicorn CLI invocation.
- The [preflight report](CONFIGURATION-PREFLIGHT.md#1-exact-project-scope-and-available-access) records Supabase `The Dashboard` in **`us-west-2`**. This is existing recorded metadata, not a new remote verification. Oregon is therefore an initial database-proximity hypothesis; benchmark the actual paths before final selection.

Use one Uvicorn process, one desired service instance, and no autoscaling or app sleeping for the initial design. These settings do **not** prevent temporary deployment overlap or replace durable ownership fencing.

## Provider comparison

| Provider | Fit for this code | Cost basis and tradeoffs |
|---|---|---|
| **Render paid Web Service** | Straightforward FastAPI service with HTTPS/WSS. A Web Service is appropriate because this app receives browser traffic. | Current compute IDs: `0.5c-512mb` at **$7/month**, `1c-2g` at **$25/month**. The old Starter/Standard names remain compatible; Render introduced the new names in August 2026 without changing existing plan specifications/prices. A Hobby workspace is $0 plus compute; Pro adds **$25/month** if its features are needed. Bandwidth, builds, and storage can add cost. [Pricing](https://render.com/pricing), [compute plans](https://render.com/docs/compute-plans). |
| **Railway** | Continuously running FastAPI with managed public networking and service secrets. Keep Serverless/app sleeping disabled. | Hobby has **$5 minimum monthly usage**, including $5 usage; Pro has a **$20 minimum**, including $20. Published service rates are approximately **$10/GB-month RAM + $20/vCPU-month CPU used**, plus **$0.05/GB egress**. Illustrative 1 GB RAM and average 0.1 vCPU for 30 days costs about **$12**, before egress, or the $20 Pro minimum. Actual usage is unmeasured. [Pricing](https://railway.com/pricing), [serverless behavior](https://docs.railway.com/deployments/serverless). |
| **Fly.io Machines** | Explicit Docker/VM configuration and regional placement; more deployment and machine-management decisions. Ensure exactly one machine for the manager and disable automatic stopping. | **Pricing changes October 1, 2026.** The announcement's default displayed shared-CPU 256 MB base is **$2.19/month**, with added RAM at **$6/GB-month**. On that displayed basis, 1 GB is approximately **$6.69/month**, and 2 GB **$12.69**, before region variation, egress, and storage. These are forthcoming-price examples, not a September invoice quote or a verified Oregon-region quote. Shared CPU is not guaranteed sustained CPU. [Pricing update](https://fly.io/pricing-update/), [resource pricing](https://docs.fly.io/about/pricing/). |
| **Vercel Functions / Services** | Python and WebSockets are supported. The current continuous loop and in-memory colony ownership are the mismatch. Services backends run as Functions on Fluid Compute, rather than providing a permanently owned worker process. | Functions have duration limits: Hobby **300 seconds**, Pro/Enterprise **800 seconds**, with a qualifying **1,800-second beta**. WebSockets close at maximum duration and reconnects can reach another instance. A durable Workflow/queue and external-state redesign would be needed; adding a Dockerfile or `services` entry is insufficient. [Services execution model](https://vercel.com/kb/guide/vercel-services-fluid-compute), [WebSockets](https://vercel.com/docs/functions/websockets), [limits](https://vercel.com/docs/functions/limitations). |

Render's Background Worker product does not accept incoming network traffic. It would fit a future separated execution process behind a queue/API, not the current combined server. Render's Web Service supports one public port for both HTTP and WebSockets and requires binding on `0.0.0.0`; its default expected port is 10000. [Background workers](https://render.com/docs/background-workers), [web services](https://render.com/docs/web-services).

Paid Render WebSockets have no fixed connection-duration limit, but maintenance and instance replacement still disconnect them. Keep reconnect/backoff and session reauthentication. [WebSocket lifecycle](https://render.com/docs/websocket). The Free compute plan is unsuitable for this always-on pilot: it can sleep after 15 minutes without inbound traffic, restart at any time, and be suspended for substantial service-initiated traffic. Buying a workspace upgrade alone does not remove Free compute limitations. [Free-service limits](https://render.com/docs/free).

## Deployment overlap, shutdown, and recovery

All candidates require an application recovery policy. A persistent disk does not automatically checkpoint Python objects, stop duplicated work, reconcile incomplete writes, or restore a correct optimizer.

- **Render:** new instances start before old instances stop. The documented deploy sequence routes to the new instance and waits 60 seconds before signaling the old one with SIGTERM. The subsequent shutdown allowance defaults to 30 seconds and can be extended to 300 seconds. [Deploy lifecycle](https://render.com/docs/deploys).
- **Railway:** its documented singleton deployment includes overlap. The default grace after SIGTERM is **zero seconds** before SIGKILL. Review `RAILWAY_DEPLOYMENT_DRAINING_SECONDS` and `RAILWAY_DEPLOYMENT_OVERLAP_SECONDS`; mandatory platform-initiated moves also occur. A drain setting is not a durable recovery mechanism. [Deployment reference](https://docs.railway.com/deployments/reference).
- **Fly.io:** first deployment can create two machines for redundancy. Explicitly review machine count and deployment strategy; available strategies include rolling, immediate, canary, and blue-green. Disabling automatic stopping keeps idle machines running, but does not prevent deployment or host interruption. [Deployment behavior](https://docs.fly.io/launch/deploy/), [autostop behavior](https://docs.fly.io/reference/fly-proxy-autostop-autostart/).

For the initial worker, define **one fenced writer**: a durable lease with an increasing fencing token, validated by state mutations, must prevent an old process from writing after another takes ownership. A process-local `asyncio.Lock`, a replica count, or a lease checked only once at startup is insufficient. A session advisory lock obtained through a short-lived REST database request is not a substitute for a deliberately managed ownership protocol.

Persist or reproducibly reconstruct the controller ledger, positions, optimizer/RNG state, shared candle/EMA state, equity metrics, and relevant source/execution cursors. Treat ambiguous write acknowledgments as reconciliation work. Do not replay pending signal intents after restart merely because they existed in a checkpoint; their receipt/expiry evidence must still be valid, and monotonic clocks cannot be reused across process lifetimes.

Before a supervised pilot, use deliberate deployments and an explicit drain/reconcile runbook. Before unattended paper operation, pass crash and overlapping-owner tests. Horizontal scaling needs an additional routing/shared-state design; copying the process does not provide it.

## Capacity, location, and continuous-operation cost

Render offers Oregon and Railway offers a California region. These are reasonable initial candidates given the recorded database region. Neither location guarantees the lowest Jupiter, Birdeye, or Solana RPC latency. [Render regions](https://render.com/docs/regions), [Railway regions](https://docs.railway.com/deployments/regions).

Measure cold startup, the eight-asset 3,660-minute history warmup, peak RSS, CPU, event-loop lag, database acknowledgment time, quote source age, request p50/p95/p99, and graceful shutdown under the configured maximum colony/population load. Include long-running trade/dead-probe retention, not only idle health checks. The manager currently allows 30 seconds for colony startup; the separate history adapter has a longer batch deadline, so a slow full warmup can fail startup by design. Do not extend safety deadlines just to pass a hosting demo.

**Provider usage may cost more than compute.** The [Jupiter feed](services/vonneumann/vonneumann/market/jupiter_feed.py) has a 0.8-second quote cache. A nominal one-second polling cycle can approach 86,400 requests/day, or 2.592 million per 30 days, before time spent awaiting other work. The [candle adapter](services/vonneumann/vonneumann/market/birdeye_candles.py) refreshes each asset per completed-minute cutoff: eight assets imply approximately 11,520 requests/day, or 345,600 per 30 days, plus startup. These are arithmetic workload illustrations, not measured production usage or plan entitlements. Separate colonies can multiply the calls.

Jupiter currently documents Free at 60 requests/minute in a 60-second sliding window, with quotas shared across an **organization**, not independently granted to every key/team. Other projects sharing that allowance must be included in a budget without changing their credentials or settings. [Jupiter rate limits](https://developers.jup.ag/docs/portal/rate-limits).

**Helius billing documentation currently conflicts:** its [credits page](https://www.helius.dev/docs/billing/credits) lists `getBlockTime` at **1 credit**, while its [RPC documentation index](https://www.helius.dev/docs/api-reference/rpc/http/llms.txt) still lists **10 credits**. Earlier project notes cited the latter. Resolve the intended endpoint/plan's actual billing before approving a 24/7 estimate; do not treat this research as proof that the user's bill changed. Deduplicating RPC slots reduces calls, but batching does not inherently make multiple method executions one billable operation.

The comparison does not establish a fastest trading host. The current candle strategy works on minute-scale signals. Future subsecond/arbitrage research requires distinct measurements of event arrival, quote generation, decision delay, transaction submission, landing, and confirmed fills under realistic load. Hosting latency alone establishes none of those outcomes. Keep source-age/revision policy, plan quotas, licensed immutable datasets, and realistic costs as separate requirements.

## Prioritized implementation and setup gates

The actionable checklist is maintained in [TODO.md](TODO.md), HOST-01 through HOST-07, under Phase 3. In order:

1. **HOST-01 / DB-03:** durable recovery, reconciliation, and fenced ownership; block unattended execution until tested.
2. **HOST-02:** reproducible Linux image, exact dependency installation, one process, signal handling, and a clean build context.
3. **HOST-03:** measured region/capacity/drain selection, with startup and long-run resource acceptance.
4. **HOST-04 / SVC-02:** shared provider quotas, measured monthly cost, billing-documentation reconciliation, and safe exhaustion behavior.
5. **HOST-05:** isolated worker secrets, production origins, correct HTTPS/WSS frontend settings, and preview data separation.
6. **HOST-06:** liveness/readiness separation, secret-safe observability, failure/kill/deployment drills, and rollback acceptance.
7. **HOST-07:** exact hosting identity and budget approval, bounded paper pilot, and measured follow-up decisions.

Worker-only configuration includes `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, a dedicated `SUPABASE_PUBLISHABLE_KEY` or `SUPABASE_ANON_KEY` for Auth verification, `JUP_API_KEY`, `BIRDEYE_API_KEY`, and `VN_SOLANA_RPC_URL`. Use the new worker service's private secret store. Set `VN_ENVIRONMENT=production`, exact `VN_ALLOWED_ORIGINS`, and `PYTHON_DOTENV_DISABLED=1` in the image/runtime. Only the reviewed endpoint URLs belong in frontend `NEXT_PUBLIC_VN_API_URL` and `NEXT_PUBLIC_VN_WS_URL`. Do not copy worker secrets into Vercel's browser environment or shared shell files.

A proposed startup command, to validate in the reviewed image rather than execute during research, is:

```sh
exec python -m uvicorn vonneumann.server.app:app --host 0.0.0.0 --port "${PORT:-8765}" --workers 1 --lifespan on
```

Use a non-root image, an explicit worker working directory, and a build context that excludes environment files and unrelated repository drafts. Pin the reviewed base image digest at implementation time; do not invent one here. API/WS identity and authorization remain necessary even when the platform supplies TLS.

Readiness should report locally known dependency/ownership state without making external market requests on every host health probe. A deliberate failed colony is not automatically a reason to restart the entire server. Keep a safe failed/reconciliation state visible instead of entering a restart loop.

Research acceptance is separate from hosting acceptance. Before publishing strategy rankings, RES-01/RES-02 must settle portfolio-return sampling, serial dependence, non-normality, effective trial count, and the applicability of Probabilistic/Deflated Sharpe Ratio or other multiple-testing controls. A successful deployment, a finite Sharpe number, or a low-latency response is not evidence of out-of-sample predictive performance.

Selecting a provider does not authorize creating a new hosting account/service, billing changes, credential movement, or modifying shared projects. Record the new host's exact account/project/service identity and region before any consequential action. Existing Vercel/Supabase allowlists, the dedicated CLI profile, preview isolation constraints, and the prohibition on live trading remain in force.
