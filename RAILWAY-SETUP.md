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
| Service/region/deployment | Not created or selected | Must verify before deployment |

The private empty project was created and its name/project/workspace verified in
Railway UI. No service, secrets, GitHub integration, deployment or billing was changed.
API verification with the scoped token remains pending. A later read-only account observation now shows **Hobby**, so a subscription prompt may no longer be necessary; recheck plan access before the canary. Do not create a replacement,
choose a similarly named project or use another project's credentials.

## User setup still needed

1. Open [The Dashboard Worker settings](https://railway.com/project/38facb49-4de9-4d66-85aa-2861e0306dcf/settings?environmentId=9bbe52c6-2305-467a-bf39-8d5e1a98e4e4).
2. Under **Tokens**, create `Dashboard Codex`, scoped only to **production**.
   Use project settings, not the account/workspace token page. Do not post it in chat.
3. Save only that token in
   `/Users/redjester/Projects/Next/TheDashboard/ssl/railway-project-token.txt`.
   The repository already ignores all of `ssl/`; set file permissions to `0600`.
   Codex can correct the local permissions without displaying the token.
4. If Trial restrictions prevent outbound access or a required resource, complete
   the intended subscription yourself. Do not upgrade merely because a worker
   image built. Any subscription affects billing; remain within the approved ceiling
   and review whether the workspace has unrelated projects before changing limits.

The [official API documentation](https://docs.railway.com/integrations/api) defines
project tokens as scoped to one project's environment. The read-only helper
`python3 scripts/dashboard-railway.py verify` reads only the private file, uses the
Project-Access-Token header and checks its project/environment before resolving the
exact project name/workspace. It emits only identity metadata and refuses mismatch.
It never touches `~/.railway`, shared login, account tokens, Claude/Codex configuration
or billing. Future mutations need their own reviewed exact service/environment pins.

## Ordered work after scoped access

1. **Create only the dedicated closed worker service.** Verify target first, then
   record immutable service ID and region. Review actual schema/CLI capabilities,
   one replica, no sleeping, restart NEVER, zero overlap and sufficient drain.
   Deploy only the allowlisted worker context/image; never upload repository env/ssl
   or other agents' files. Keep `VN_SERVICE_MODE=closed` with no native credentials.
2. **Prove the selected host's connection.** Enable outbound IPv6 on that exact
   service and apply/redeploy. Railway's [outbound networking docs](https://docs.railway.com/networking/outbound-networking)
   make this opt-in and service-specific. Run the fixed-host, supplied-CA TLS preflight
   without PostgreSQL authentication first. Record DNS family, certificate/hostname
   verification and bounded timing. No insecure SSL/pooler/paid IPv4 fallback.
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
