# Dashboard-only Railway setup and remaining acceptance

The user approved a **$20/month ceiling for the initial paper pilot** on 2026-10-07.
This is a spending constraint, not a selected paid subscription, resource estimate,
production cadence or approval to change account-wide billing for other projects.

## Authoritative worker status — 2026-10-21

The replacement production-scoped token passes the exact Dashboard project/workspace/environment and service checks at October 22 01:52 UTC / October 21 Denver. Deployment `cf05895d-adc5-427f-873e-82ad6606e5a1` remains the latest SUCCESS; the configured mode is closed and both dotenv-disable flags are set. The 19-variable inventory contains only platform metadata, public Supabase URL/publishable key, public CA, allowed origins and closed-mode configuration; no current database/provider/native secret or Railway management token is present. These are read-only configuration observations, not fresh in-container image/Auth/TLS acceptance. The earlier `project_token_not_found` failure remains diagnostic evidence; its cause is not proven.

Dashboard releases through PR110 are accepted, but the new B2/native/reader/recovery package remains under local validation. The original finite owner hour does not establish current continuous operation. [Current implementation order](TODO.md), [latest release](RELEASE-PR110-ACCEPTANCE-2026-10-21.md), and [private B2 experiment evidence](B2-NATIVE-EXPERIMENTS-2026-10-21.md) supersede older pending implementation statements below. Preserve the $20/month pilot ceiling and keep activation closed until the applicable gates pass; no repeat account, Docker or certificate setup is currently required.

Railway's [official status](https://status.railway.com/) reports a major outage and paused deployments, with a separate [October 21 security disclosure](https://blog.railway.com/p/security-disclosure-wednesday-october-21st) recommending rotation of credentials stored there. Current absence does not establish that earlier temporary provider/native variables were never exposed. Complete the Dashboard-only historical credential/dependency assessment and any necessary rotation/usage review before hosted activation; keep the worker closed while builds are paused. [Scoped incident assessment](RAILWAY-INCIDENT-ASSESSMENT-2026-10-21.md). No credentials or services have been changed in response to this checkpoint.

The token file is the helper's single authoritative source. **Do not add the replacement to `.env`, Vercel or worker runtime variables.** An older local `.env` copy is unused by the helper; previous statements below that both copies matched describe their historical checkpoint. Do not use shared login/link commands or change another project's credentials.

## Historical worker checkpoint — 2026-10-12

The service is provisioned and remains in ordinary **closed mode** at deployment
`cf05895d-adc5-427f-873e-82ad6606e5a1`. The original owner hour completed at
revision 514 with 504 prices, one replacement, eight funded children, two closed
trades and 32 acknowledged events. The repaired complete owner history and repeat
read passed. All 16 temporary settings were removed, the original variable map
restored, and finite native credentials revoked/NOLOGIN. This is accepted finite
zero-cost mechanical evidence; no continuously evolving worker is running.
[Hour and closed cleanup](supabase/audits/2026-10-08-owner-hour-first-replacement.json).

PR96 and PR97 are merged; reviewed source `67cff30` and PR97 Vercel production
`dpl_ASo5z4Zc6APWsUPseQVrvw52Aici` have recorded READY/canonical-alias/four-probe
checks, freshly repeated read-only by the root reviewer. Exact Railway target and
unchanged service settings also match; no active workload was restarted. The new
portable model/compact transport is offline research code. A reproduced
boolean/integer configuration-type defect needs repair before complete independent
version 2 SQL validation. The new model is not fully validated, installed as a
native writer, restored from durable checkpoints or enabled on Railway.

Keep the service closed until the ordered gates below pass. Security/CI,
data/fill/objective research, app/API correctness and project-only maintenance can
proceed in parallel. None grants live funding, signing or swap authority. Earlier
dated setup and canary notes below preserve historical evidence; they do not
reopen completed account, native-session or first-hour setup questions.

## Exact target

| Scope | Name | Immutable ID |
| --- | --- | --- |
| Workspace | Red Jester's Projects | `f3fcd4b2-e424-4c6b-ac33-91196ccc96e1` |
| Project | The Dashboard Worker | `38facb49-4de9-4d66-85aa-2861e0306dcf` |
| Environment | production | `9bbe52c6-2305-467a-bf39-8d5e1a98e4e4` |
| Service | dashboard-paper-worker | `8e78ad4b-1d8f-43e7-898a-3882ac5053d7` |
| Region / replicas | US West / one | `us-west2` |
| Last verified ordinary closed deployment | SUCCESS | `cf05895d-adc5-427f-873e-82ad6606e5a1` |

The production-scoped token and actual project/environment names and workspace
were verified through the scoped helper and subsequent release checks. The service is hosted
in **closed mode**, with mode/dotenv flags, the supplied public CA and explicit Dashboard Auth settings. No
database/provider credentials, GitHub integration, billing change, native ledger
or paper run is enabled. [Health endpoint](https://dashboard-paper-worker-production.up.railway.app/health).
Hobby was observed in the account UI. Do not create a replacement or select a
similarly named target. [Approved evidence](supabase/audits/2026-10-07-railway-closed-host.json).

## Credential setup and completed SSL maintenance

The user saved the token in ignored `ssl/railway-project-token.txt` and `.env`
under `RAILWAY_TOKEN`. Both copies match without values being output. The dedicated
file is an owned regular file with mode `0600`; it remains the helper's only
credential source. Do not source `.env` into the shell or upload either file.
Do not add the deployment token to the worker's runtime variables. Paper startup
explicitly refuses Railway administrative tokens and broad Supabase keys.

The user confirmed no other known direct clients and authorized Dashboard-only
database changes. SSL enforcement now reports `database=true` and
`appliedSuccessfully=true`; the update completed in 4.361 seconds. Post-reboot
management SQL/TLS, original catalog/history comparisons and four production
dashboard HTTP checks pass. The private bot-table/history snapshot and actual
managed rollback rehearsals are recorded in [SUPABASE-CUTOVER.md](SUPABASE-CUTOVER.md).
There is no pending client-inventory question.
[SSL enforcement guidance](https://supabase.com/docs/guides/platform/ssl-enforcement).

Any paid subscription or account-wide billing/limit change remains user-managed.
Service limits constrain CPU/RAM, not the account's total bill or provider costs.

### Why these inputs are not all in local .env

A properly parsed private `.env` can hold the Railway token; it already does.
There is no inherent security advantage to a separate file with the same ownership
and permissions. The helper deliberately uses one named, owned mode-0600 token
file so it never loads unrelated app secrets, falls back to shared CLI credentials
or depends on dotenv precedence. Two copies can drift; keep the helper's file
authoritative until a deliberate, tested configuration change. Do not delete or
rotate either copy implicitly.

The downloaded CA is a public certificate, not a private key. Keeping its PEM in
`ssl/prod-ca-2021.crt` preserves the standard certificate format and makes local
trust/expiry checks straightforward. Railway already stores its contents in the
service-specific `VN_DATABASE_CA_PEM` environment variable. Either PEM-in-env or an
explicit certificate file works if parsing and trust validation are correct.

Local `.env` does not configure Railway or Vercel automatically. Those platforms
use their own project/service/environment variables. The deployment token belongs
to the operator; the runtime receives only its narrow database/provider inputs.
Project IDs are nonsecret safety pins in the scoped helpers and AGENTS.md. Moving
them to env would still require checking the allowed immutable IDs and owner.
Database SSL enforcement is a server policy, so adding an env variable cannot
replace that change. Client CA/hostname verification is a separate requirement.

The [official API documentation](https://docs.railway.com/integrations/api) defines
project tokens as scoped to one project's environment. The read-only helper
`python3 scripts/dashboard-railway.py verify` reads only the private file, uses the
Project-Access-Token header and checks its project/environment before resolving the
exact project name/workspace and actual production environment name. `service`
also pins the service and required settings/resource limits. Both commands emit
only metadata and refuse mismatch. An explicit application User-Agent avoids the
403 seen with Python's default header. The helper never touches shared CLI login,
account tokens, agent configuration or billing, and has no remote mutation action.

`export-worker FULL_COMMIT NEW_DIRECTORY` is a separate offline action. It copies
only immutable allowlisted worker blobs into a new Dashboard-named directory under
`/private/tmp`, excludes operator files and normalizes files/directories for the
non-root image. It does not prove review approval or upload anything. The initial
private export used `0600` files/`0700` child directories, which Docker COPY retained;
the first canary failed before networking. The corrected export/image import and
actual hosted deployment pass. Regression coverage includes strict umask, exclusion,
immutable commits, destination refusal, metadata scope and redacted transport errors.

The official Railway CLI **5.63.4** was downloaded only into this task's temporary
directory and verified against the official release SHA-256. Deployment used the
project token only in its child environment and explicit project/environment/service
IDs; no login/link was run. Automatic updates/skills and telemetry were disabled in
that child, with a macOS sandbox denying writes to shared Railway, SSH, Codex, Claude
and configuration directories. The current CLI's SSH command can register shared
account keys; it was not used. A bounded TLS-only startup command probes inside the
actual container and then execs the normal closed entrypoint.

## Historical closed hosted acceptance — 2026-10-07

- Source `9837eb1af2a226b5ee4aa46a0f07731783216306`, 94 allowlisted files,
  1,179,683 bytes; normalized export manifest SHA-256
  `3ebb7c046ca05b39b6937637d4bc0426d23d2bb9decf90b622cd4671343346c1`.
- Exact successful deployment resolves Dockerfile build, one `us-west2` replica,
  no sleeping, restart NEVER, overlap 0 seconds, drain 30 seconds, `/health`
  timeout 60 seconds and outbound IPv6. Applied limits: 0.25 vCPU / 500,000,000 bytes.
- Actual fixed-host IPv6 probe verifies supplied CA/hostname, TLS 1.3, 256-bit
  cipher, peer expiry 2031-03-09. Elapsed 1.048 seconds includes the finite Python
  child; it is one observation, not a native connection percentile or cadence.
  No PostgreSQL StartupMessage, login, SQL or SCRAM/channel-binding test was sent.
- Hosted HTTPS: health 200, unauthenticated status 401, legacy colonies/docs 404,
  foreign Origin 403. At this checkpoint the early foreign-origin rejection
  lacked `Cache-Control: no-store`; HOST-05A subsequently repaired and verified it.
- Nine minute-spaced closed-service samples: maximum memory 0.055648256 GB,
  maximum CPU 0.029888917 vCPU. Startup/failed-canary samples are included; these
  do not size the active controller or database/provider workload.
- Current published rates imply at most about $10/month CPU+RAM if both configured
  limits were fully consumed continuously, before egress/tax/provider charges.
  Hobby's $5 minimum is credit toward usage, not an additional $5 on top of $10.
  This is an arithmetic resource estimate, not an enforced $20 total spending cap.
  [Railway pricing](https://docs.railway.com/pricing).

## Ordered remaining gates for the new paper profile

1. **Repair strict configuration types, then prove complete version 2 semantics.**
   Reject boolean/integer substitutions and other invalid complete configurations;
   compose independent SQL selection/mutation, lineage, economics, source, risk,
   assessments and original same-version prior-chain checks. Offline primitive
   agreement is insufficient for native admission.
2. **Prepare the atomic native compact package.** Original-ID receipt/replay,
   dependency pins, identity uniqueness, journal/history/outbox/provenance, final
   source/lease checks and reserved Stop capacity must pass with limited grants.
   Prepare old/new reader compatibility and evidence-preserving rollback before
   any reviewed forward migration. Never relax TLS or use a broad managed key.
3. **Prove exact restoration and dependency-safe retention.** Verify the full
   next prepared wire, original uncertain-command settlement, held positions,
   archive/readback/lookup and filled-budget Stop behavior before hot pruning.
   Loading a checkpoint does not grant a lease or activate the worker.
4. **Join closed deployment and dashboard compatibility.** Reverify exact
   project/workspace/environment/service and Supabase/Vercel targets; use only
   reviewed allowlisted source, explicit private settings and finite scoped
   credentials. Validate installed catalog/history after COMMIT, non-root image,
   TLS/Auth/owner denial and old/new browser history/control/ancestry. Preserve
   complete owner history while writes remain closed. Preview credentials still
   share production Supabase; they are not a write-test sandbox.
5. **Measure and accept bounded multi-window operation.** Source-age/lease/SQL/
   COMMIT/relay tails, resource/storage/provider budgets, expiry/revocation,
   SIGTERM/SIGKILL, overlapping workers, lost replies and held-position recovery
   must pass for the selected supported profile. Run a bounded acceptance before
   continuous operation, retaining closed cleanup and original-ID reconciliation.
   Calibrate costs/objectives and multi-seed holdouts before trusting rankings.
   A spending stop does not reconcile holdings; the $20 ceiling grants no billing
   authority and live funding/signing/swaps remain disabled.

Research/security/CI, app/API privacy/honesty and infrastructure-maintenance work
can proceed independently. Restoration and retention design may start earlier,
but their final acceptance depends on frozen native/checkpoint contracts. Keep
Supabase linked operations and consequential deployment/credential changes
sequential under the repository's target and isolation rules.

The reviewed [config-as-code reference](https://docs.railway.com/config-as-code/reference)
supports the Dockerfile/health/restart/overlap/drain fields in the worker's
`railway.json`. It does not prove the deployed service has applied them; inspect the
resolved exact deployment and its image/commit before acceptance.
The official IaC page was rechecked on **2026-10-12**: existing legacy
`railway.json`/`railway.toml` files stop being read on **2026-12-01**. Plan and
review the project-only migration before that cutoff, preserving the existing
service and secrets; implementation remains HOST-02C. The actual closed deployment
still resolves its file, which does not prove future compatibility. Reconcile
API-versus-file builder enums: the API's Builder enum lacks DOCKERFILE, while the
resolved file deployment uses it. Do not copy unsupported API flags from examples.
[Current migration guidance](https://docs.railway.com/infrastructure-as-code).

## Hosting roles and rollback

Vercel hosts the dashboard/Auth UI. Railway hosts one closed Python paper
service. Supabase stores fenced command journals, exact accounts/positions,
checkpoints, curated read history, relay identities and archive receipts. Durable
database records outlive an HTTP connection or worker process. There is no automatic
resume; the operator reconciles an interrupted run before any future operation.

If acceptance fails, keep/return the worker to closed mode with native write
admission closed and complete owner history readable. After acknowledged commands,
use original-ID admission retirement and retain DB records/readback; do not drop schemas/rows or restore the
legacy writer. Reverting code is sufficient only before schema/service activation.

**Further substantial research:** provider quota/billing conflicts and retention
rights, aggregate direct connections and handshake/COMMIT/lease tails, actual image
CPU/memory/drain behavior, managed privilege/issuance hooks, CA/native maintenance,
interruption exposure, relay/history retention and compact multi-window checkpoints.


## Historical closed Auth and provider acceptance checkpoint — 2026-10-07

At this checkpoint, Auth-only worker79327b5e-69fa-471e-9565-0a34d6739ccd/source9b387967189ca9197b6a59beb2391835c78ff3c2 verifies real Dashboard user tokens through the exact Supabase Auth project. Only SUPABASE_URL, existing SUPABASE_PUBLISHABLE_KEY, VN_ENVIRONMENT=production and the exact VN_ALLOWED_ORIGINS are added. Real tokens reach the closed-service response; invalid tokens/Origin and docs are denied with no-store. The public CA is already injected as VN_DATABASE_CA_PEM. The Railway project token stays in the operator context and never enters the service.

The subsequent provider-only canary used python -m tools.provider_read_canary, still VN_SERVICE_MODE=closed. Its reviewed plan added only the existing Jupiter/Birdeye keys and an explicit private Helius mainnet RPC URL to this service, preserving unrelated variables. It started closed HTTP immediately and owned one finite background assessment. Twelve prices at5s spacing/90s deadline, a quota margin, no retry and bounded response parsing produced approved timing/counter/resource facts. Restoring /app/start-worker.sh and removing the three provider variables was part of acceptance. This was provider feasibility, not full-tail acceptance; its later completion is recorded below.

The actual unscaled Birdeye multiplier:null startup defect is repaired before this deployment. Current primary billing uses1credit for getBlockTime; older pages use10. Resolve actual account metering/shared quota availability before continuous operation. The $20/month hosting ceiling is a design budget; no account-wide hard limit or billing change has been applied.


The actual provider-only assessment stopped on its shared-quota guard after accepting61warmupbars and one valid price. Ordinary Auth-only closed deployment56e0a351-ac64-4c24-a998-6bc8c7fc0eb4 replaces it; all three provider variables are removed. The legacy API region field is null; the exact resolved deployment's multiRegionConfig is the authoritative one-us-west2-replica evidence. Jupiter plan/shared allowance needs clarification before a new deliberate measurement. No margin reduction, automatic retry, plan purchase or billing change is implied.


## Historical clean history and closed browser selection — 2026-10-07

PR62 applies only the user-rejected old bot data cleanup after review and rollback rehearsal. All five legacy tables are freshly empty, the installed catalog and fifteen migration entries are unchanged, and the existing login account remains. The production paper view now uses the exact Railway HTTPS origin and owner-only Supabase vn_read directory. Its empty history and disabled start/stop/settle controls are verified in the existing owner's browser. The ordinary closed Railway service returns its deliberate closed-service response after valid Auth; active/nonempty browser flow and the finite pilot are still pending.

The local .env contains RAILWAY_TOKEN and currently matches the dedicated ignored mode-0600 operator token file. A carefully parsed private .env could serve as the single canonical source; a separate file is not inherently safer. This helper currently uses the dedicated file to avoid dotenv precedence and loading unrelated credentials. Prefer one documented source over permanent duplicate copies. No shared login or other agent's credentials need changing.

The Supabase CA certificate is public, but ssl also contains private operator tokens and original-outcome records, so the entire directory remains ignored. Local PEM files make certificate hash/expiry verification explicit. The hosted worker already receives the CA contents in VN_DATABASE_CA_PEM, not the macOS file path. A local .env does not configure cloud environments; the exact Railway service and Vercel project have separate environment stores. Never put the Railway deployment token in the worker or browser. Native worker credentials must remain narrowly scoped and finite; operation journals retain original IDs/deadlines/outcomes that a flat .env cannot replace. Supabase's server-side SSL enforcement is separate from the client's CA/hostname verification.


## Historical revised provider acceptance and closed restoration — 2026-10-07

PR64 merge02c0e2d54b8d3d0d85848b1bc1f264899d26719d corrects the finite canary's burst-budget assumption, using recent explicit headroom for one next request plus two reserved slots. This is a reviewed finite-read fix, not an active controller relaxation or approval of account-wide capacity. The user's Developer plan is verified; existing key attribution/one-credit Price V3 request/no matching firewall are proved read-only.

Exact provider-only deployment1697fedb-a752-49e8-ad19-dd454fe2fc89 passes 61 warmup bars/12prices: history1.138719s, complete price/RPC validation0.113060–0.195100s, source age3.225096–5.486115s. Twelve Jupiter/one Birdeye/thirteen RPC calls,57.654938s total, peakRSS75,558,912bytes/CPU0.25s/maxlooplag0.228707s establish finite feasibility only. Headers first show9remaining then98; do deeper window/shared-credit research before an active cadence.

The same merged allowlisted source now serves ordinary Auth-only closed deployment9f606944-1bfd-4b2c-87bc-0855bee00117 SUCCESS. All three temporary provider values are removed; the entire original variable set equals the saved private original. `/app/start-worker.sh`, closed mode, one us-west2 replica,0.25CPU/500MB, no restart/overlap/sleep and IPv6 retain their verified settings. Health200, anonymous status 401, disallowed origin 403 and no-store pass. No native/admin/operator key, paper run, economic write or wallet action is added. [Approved acceptance](supabase/audits/2026-10-07-upgraded-hosted-provider-acceptance.json). Remaining priorities are DATA-01E and D2D2A source/SQL/lease/relay timing, then HOST-03…06 security/interruption/ownership and the bounded HOST-07 pilot.
