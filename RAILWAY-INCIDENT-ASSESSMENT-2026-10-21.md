# Dashboard Railway incident assessment — 2026-10-21

The replacement token works through the isolated helper. The exact allowed project, workspace, production environment and worker service match; the latest deployment remains `cf05895d-adc5-427f-873e-82ad6606e5a1` / SUCCESS. At October 22 01:52 UTC (October 21 Denver), read-only configuration queries show closed mode and both dotenv-disable flags set. No remote mutation or rotation accompanies this assessment. [Machine-readable evidence](RAILWAY-INCIDENT-ASSESSMENT-2026-10-21.json).

## Provider incident and the earlier failure

Railway's [official status](https://status.railway.com/) reports a major outage with builds/deployments paused; its latest visible update was October 22 01:22 UTC. The [October 21 disclosure](https://blog.railway.com/p/security-disclosure-wednesday-october-21st) describes possible unauthorized access to stored environment variables and recommends rotating stored credentials and reviewing unusual activity. The provider has not confirmed that this Dashboard project was affected. Successful metadata queries during this assessment do not establish that builds have recovered.

The earlier request returned `project_token_not_found`; the replacement succeeds. Those observations do not distinguish an invalidated token from other incident-related backend behavior. Do not label the old token expired, attribute its rejection conclusively to the outage, or keep retrying it.

## Current and historical inventory

The current exact-service inventory contains 19 names: 11 Railway-generated metadata variables and these eight explicit inputs:

- `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` and `VN_DATABASE_CA_PEM`: public URL, publishable client key and public CA certificate.
- `VN_ALLOWED_ORIGINS`, `VN_ENVIRONMENT` and `VN_SERVICE_MODE`: service configuration; mode is configured closed.
- `PYTHON_DOTENV_DISABLED` and `VN_DOTENV_DISABLED`: both configured enabled to disable dotenv loading.

There are no current runtime variables for database/native passwords, Jupiter/Birdeye/Helius credentials or the Railway management token. This is a configuration-store observation, not fresh in-container image, Auth, TLS or deployment acceptance. It does not establish that deleted variables or previous deployments were outside the incident's scope.

Earlier finite canaries did use `JUPITER_API_KEY`, `BIRDEYE_API_KEY` and a credential-bearing `VN_SOLANA_RPC_URL`; their removal and closed restoration are recorded in [Railway setup](RAILWAY-SETUP.md). The owner-hour pilot also used finite native economic/relay credentials. Its [cleanup receipt](supabase/audits/2026-10-08-owner-hour-first-replacement.json) records removal of all 16 temporary variables and revoked/NOLOGIN finite identities. That is historical cleanup evidence, not a new database check or proof of incident nonexposure.

Reviewed records do not show the operator Railway token, Supabase service-role/secret key or master database password, GitHub/Vercel credentials, or wallet signing keys as Railway runtime inputs. Source code mentioning a fallback is not evidence that the credential was uploaded. This review does not certify provider logs or all historical deployment storage.

## Actions in order

1. Review the still-valid Dashboard-specific provider keys used by earlier canaries and their usage/audit activity. Record names, dependency results and sanitized outcomes; never output values or raw logs containing credentials. The user previously confirmed no other application uses Jupiter under TheOrder; Helius/Birdeye cross-project use must still be established before revocation.
2. Replace and revoke any still-valid private credentials previously hosted, after their dependencies are known. Keep actions within the exact Dashboard project/provider-key scope. Avoid account-wide key resets, Supabase signing-secret rotation or shared-credential changes. If a key also serves the other agent's project, coordinate that specific dependency with the user before changing it.
3. Before a later database action, separately verify the exact Dashboard project, original finite identities' registry revocation/NOLOGIN/expiry and any sessions belonging to those exact identities. NOLOGIN alone does not end an existing connection. Historical accepted cleanup does not replace a fresh scoped check. Never re-enable the old pair or terminate unrelated sessions.
4. Wait for restored deployments, then reverify the exact closed worker source/settings and Auth/TLS after any reviewed updates. The native/recovery/reader and sustained-paper gates in [TODO](TODO.md) still apply. Offline B2 accounting/concurrency work can proceed while the provider is unavailable.

## Token location

Keep the replacement only in the ignored owned mode-0600 `ssl/railway-project-token.txt` used by the helper. No `.env` update or Vercel variable is needed. The management token is an operator credential, not application configuration; adding it to either hosted runtime would expand its exposure without supporting a runtime requirement. An older `.env` copy is unused by this helper and does not need to be synchronized. No shared login/profile change or new subscription is needed.
