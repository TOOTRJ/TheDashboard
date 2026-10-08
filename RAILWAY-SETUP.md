# Dashboard-only Railway setup and remaining acceptance

The user approved a **$20/month ceiling for the initial paper pilot** on 2026-10-07.
This is a spending constraint, not a selected paid subscription, resource estimate,
production cadence or approval to change account-wide billing for other projects.

## Exact target

| Scope | Name | Immutable ID |
| --- | --- | --- |
| Workspace | Red Jester's Projects | `f3fcd4b2-e424-4c6b-ac33-91196ccc96e1` |
| Project | The Dashboard Worker | `38facb49-4de9-4d66-85aa-2861e0306dcf` |
| Environment | production | `9bbe52c6-2305-467a-bf39-8d5e1a98e4e4` |
| Service | dashboard-paper-worker | `8e78ad4b-1d8f-43e7-898a-3882ac5053d7` |
| Region / replicas | US West / one | `us-west2` |
| Healthy closed deployment | SUCCESS | `d2946105-6ed6-4adc-bf63-23adab188c4a` |

The production-scoped token and actual project/environment names and workspace
were verified through the API on 2026-10-07. The dedicated service is now hosted
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

## Closed hosted acceptance — 2026-10-07

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
  foreign Origin 403. Normal responses have `Cache-Control: no-store`; the early
  foreign-origin rejection currently lacks that header and is recorded for repair.
- Nine minute-spaced closed-service samples: maximum memory 0.055648256 GB,
  maximum CPU 0.029888917 vCPU. Startup/failed-canary samples are included; these
  do not size the active controller or database/provider workload.
- Current published rates imply at most about $10/month CPU+RAM if both configured
  limits were fully consumed continuously, before egress/tax/provider charges.
  Hobby's $5 minimum is credit toward usage, not an additional $5 on top of $10.
  This is an arithmetic resource estimate, not an enforced $20 total spending cap.
  [Railway pricing](https://docs.railway.com/pricing).

## Ordered work after scoped access

1. **Closed service and selected-host TLS: complete.** Retain the pins/evidence
   above and reverify before each later operation. Keep `VN_SERVICE_MODE=closed`
   until all remaining acceptance passes.
2. **Finish actual committed/native managed acceptance.** The client inventory
   is resolved by the user's confirmation. Exact-project SSL enforcement is now
   applied, and post-reboot database/dashboard checks pass. Actual installer,
   issuer and production/history wrapper rollback rehearsals pass after repairing
   the managed-role/Auth/deparser mismatches. Prove committed postflight and real
   native scoped Railway sessions next. Never relax CA/hostname validation or
   borrow a broad managed credential for the worker. [Cutover and recovery](SUPABASE-CUTOVER.md).
3. **C3B managed installer/issuer and A3 forward application.** Reverify The Dashboard
   Supabase ID/org, installer/auth/default/catalog/migration state and actual DDL/role
   capability. Prepare independent target/history digests, backup/recovery evidence,
   writer drain and additive retirement procedure. Apply only the reviewed complete
   forward candidate in a bounded transaction, initially closed; verify final and
   fresh-session post-COMMIT manifest. The package remains outside migrations until
   this target-specific execution/history wrapper is reviewed. Do not run a blind
   `db push`, apply the historical local draft or borrow broader managed credentials.
4. **Credentials and curated browser reads.** After package prerequisites, issue one
   private economic/relay pair bound to the chosen owner/run and finite validity.
   Prove actual SCRAM/verify-full/channel binding/owner/capability canaries. Inject
   only into the exact private worker service. Expose only `vn_read` for authenticated
   curated reads; never expose core/access/owner schemas or raw tables. Recheck owner
   and second-user browser/API/database denial through hosted TLS. Configure Vercel
   public worker origin/mode only on the allowed project and reviewed environment;
   previews still share production DB and are not safe integration-test sandboxes.
5. **Measure and launch a finite paper pilot.** Source-age/lease/SQL/COMMIT/relay/browser
   tails, resource use, shared provider quotas, expiry/revocation, SIGTERM/SIGKILL,
   restart refusal, overlap and additive retirement must pass before active selection.
   Begin with a short explicit smoke, then extend only within the one-window cap and
   $20/month ceiling supported by measurements. A spending hard stop is an interruption,
   not proof that open holdings were reconciled. Live funding/signing/swaps stay disabled.

The reviewed [config-as-code reference](https://docs.railway.com/config-as-code/reference)
supports the Dockerfile/health/restart/overlap/drain fields in the worker's
`railway.json`. It does not prove the deployed service has applied them; inspect the
resolved exact deployment and its image/commit before acceptance.
Current documentation marks Config as Code deprecated, with legacy support through
**2026-12-01**. The actual deployment does resolve this file correctly, but migrate
to reviewed project-only Infrastructure as Code before that deadline. Reconcile
API-versus-file builder enums: the API's Builder enum lacks DOCKERFILE, while the
resolved file deployment uses it. Do not copy unsupported API flags from examples.
[Current migration guidance](https://docs.railway.com/infrastructure-as-code).

## Hosting roles and rollback

Vercel hosts the dashboard/Auth UI. Railway will run one supervised Python paper
service. Supabase stores fenced command journals, exact accounts/positions,
checkpoints, curated read history, relay identities and archive receipts. Durable
database records outlive an HTTP connection or worker process. There is no automatic
resume; the operator reconciles an interrupted run before any future operation.

If acceptance fails, keep/return the worker to closed mode and leave public v5
selection disabled. After acknowledged commands, use original-ID admission
retirement and retain DB records/readback; do not drop schemas/rows or restore the
legacy writer. Reverting code is sufficient only before schema/service activation.

**Further substantial research:** provider quota/billing conflicts and retention
rights, aggregate direct connections and handshake/COMMIT/lease tails, actual image
CPU/memory/drain behavior, managed privilege/issuance hooks, CA/native maintenance,
interruption exposure, relay/history retention and compact multi-window checkpoints.


## Closed Auth and provider acceptance checkpoint — 2026-10-07

Current Auth-only worker79327b5e-69fa-471e-9565-0a34d6739ccd/source9b387967189ca9197b6a59beb2391835c78ff3c2 verifies real Dashboard user tokens through the exact Supabase Auth project. Only SUPABASE_URL, existing SUPABASE_PUBLISHABLE_KEY, VN_ENVIRONMENT=production and the exact VN_ALLOWED_ORIGINS are added. Real tokens reach the closed-service response; invalid tokens/Origin and docs are denied with no-store. The public CA is already injected as VN_DATABASE_CA_PEM. The Railway project token stays in the operator context and never enters the service.

Next explicit provider-only canary uses python -m tools.provider_read_canary, still VN_SERVICE_MODE=closed. Add only the existing Jupiter/Birdeye keys and an explicit private Helius mainnet RPC URL to this service, preserving unrelated variables. It starts closed HTTP immediately and owns one finite background assessment. Twelve prices at5s spacing/90s deadline, a shared-quota margin, no retry and bounded response parsing produce only approved timing/counter/resource facts. Restore /app/start-worker.sh and remove the three provider variables after acceptance. This is read-only provider feasibility, not active SQL/lease/relay/pilot or full-tail acceptance.

The actual unscaled Birdeye multiplier:null startup defect is repaired before this deployment. Current primary billing uses1credit for getBlockTime; older pages use10. Resolve actual account metering/shared quota availability before continuous operation. The $20/month hosting ceiling is a design budget; no account-wide hard limit or billing change has been applied.
