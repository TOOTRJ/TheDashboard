# Dashboard project boundaries

The user runs another coding agent on a different project under the same macOS user and the same Vercel/Supabase accounts. Preserve that agent's work, credentials, tools, and processes. These instructions apply to this repository only.

## Allowed remote targets

GitHub repository: `TOOTRJ/TheDashboard`, immutable repository ID `1141090963`, canonical origin `https://github.com/TOOTRJ/TheDashboard.git`. Use `codex/` branches and pull requests for reviewed changes. The former `biggrizzly11/TheDashboard` address redirects to this same repository; use the canonical address for future operations. Do not push directly to `main` or merge a pull request without authorization.

The `codex/dashboard-security-reliability` branch has automatic Vercel Git deployments disabled in `vercel.json` so review can proceed before preview isolation and release readiness are resolved. Keep that branch guard until deployment is deliberately reviewed; a draft PR alone does not prevent deployment. Other branches retain their existing behavior.

| Provider | Project | Immutable ID | Owner |
|---|---|---|---|
| Vercel | `the-dashboard` | `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` | Team `team_8iNNxiNjrOseD4gdSCHkQEzF`, slug `orderoftheredjester` |
| Supabase | `The Dashboard` | `fxpxsciltakyypunglzr` | Organization `cqfnnaunmupdyobkyqfo`, name `Valentine Jester` |
| Railway | `The Dashboard Worker` | `38facb49-4de9-4d66-85aa-2861e0306dcf` | Workspace `f3fcd4b2-e424-4c6b-ac33-91196ccc96e1`, name `Red Jester's Projects` |

Verify the exact project name, immutable ID, and owner before consequential remote operations. Stop on a mismatch; do not select a similarly named project or create a replacement. Do not modify another project, organization/team-wide configuration, shared environment variables, billing, shared credentials, domains belonging to other projects, or other repositories. Identity metadata needed to resolve the authorized target is distinct from permission to inspect another project's contents.

Railway additionally pins production environment `9bbe52c6-2305-467a-bf39-8d5e1a98e4e4`
and service `dashboard-paper-worker` / `8e78ad4b-1d8f-43e7-898a-3882ac5053d7`.
Use `python3 scripts/dashboard-railway.py verify` and `service` for read-only checks;
the helper reads only ignored mode-0600 `ssl/railway-project-token.txt`. Never print
the token or upload `.env`/`ssl`; a saved `.env` copy is not a runtime credential.
Keep the worker closed until the remaining gates in `RAILWAY-SETUP.md` pass.
The approved $20/month pilot ceiling does not authorize billing/account-wide changes.
Do not run shared Railway login/link or default SSH key registration. Official CLI
5.63.4 is isolated in the task's temporary directory; project-token child environment,
explicit target IDs, disabled automatic updates/telemetry and a sandbox denying shared
Railway/SSH/agent/config writes were used for the closed canary. Prefer pinned API
operations; inspect source/flags before adopting a later CLI or IaC workflow.

## Isolated CLI context

Use working directory `/Users/redjester/Projects/Next/TheDashboard` explicitly.

For dashboard GitHub operations, use `python3 scripts/dashboard-github.py`: `verify`, `fetch`, `push`, `pr <subcommand> ...`, or `api <repository-path>`. The helper reads only Keychain service `codex-dashboard-github-biggrizzly11` / account `biggrizzly11`, verifies user ID `16749816` and repository ID `1141090963`, and authenticates its own child processes. It pins repository operations and fails closed if the credential or identity is wrong. Never print/retrieve the token into tool output or put it in command arguments, shell startup files, remote URLs, or Git configuration. Do not use shared `gh auth login`, `switch`, `logout`, or `setup-git`; even a different GH_CONFIG_DIR can share GitHub CLI Keychain state. Plain `gh` may still use the other account. The limited token may not read the GitHub Checks API or combined statusCheckRollup; verify the exact deployment directly through the dedicated Vercel profile rather than widening the token. The helper disables local hooks, submodule recursion, and automatic maintenance for credential-bearing Git fetch/push processes, so complete relevant project checks explicitly before pushing.

New dashboard commits use repository-local `user.name` / `user.email` for verified **biggrizzly11**; the email was confirmed through an existing GitHub-attributed commit rather than guessed. Preserve global Git settings and historical authors. Clear inherited GIT_AUTHOR_NAME/EMAIL and GIT_COMMITTER_NAME/EMAIL in this task's commit child process, and verify resulting author/committer attribution. Do not rewrite old commits or bypass a Vercel authorization block with an alternate upload.

For every Vercel command, use global configuration directory `/Users/redjester/.config/vercel-dashboard-codex`. Remove inherited `VERCEL_TOKEN`, `VERCEL_ORG_ID`, and `VERCEL_PROJECT_ID` from the command's child-process environment. Do not unset variables in another running process or alter shell startup files. Use the verified `--scope` and `--project` IDs wherever the command supports them; inspect installed command help instead of guessing flags.

Set `NO_UPDATE_NOTIFIER=1` and `VERCEL_TOKEN_STORAGE=file` only in each Dashboard
Vercel child process. The dedicated profile was observed with automatic CLI
updates enabled; disable those checks per command without changing shared
settings. CLI 62.0.0's native credential read failed during DB-03A1 release
verification, and the dedicated profile's auth file/Keychain item were absent.
File storage must remain inside the exact Dashboard global-config directory;
never fall back to the default profile, copy shared credentials, or print tokens.
If Dashboard authentication is missing, request a login to that exact profile.

The ignored `.vercel/project.json` pins the verified IDs locally. Reinspect resolved context before using it. Do not run a shared/default-profile login, logout, or team switch. A separate profile isolates local state; it does not reduce the account's cloud permissions.

Installed Vercel CLI 60.0.0 `link` can refresh `.env.local` OIDC data and perform a configuration migration. Do not use it as an assumed metadata-only operation. Avoid environment pulls that overwrite local files. Capture environment API responses in memory and output only approved metadata/comparison results. `env ls --json` can return encrypted envelopes, so a returned value string is not proof of plaintext or a credential mismatch.

For Supabase CLI, use this repository's explicit `--workdir` and the verified project reference where supported. Preserve the shared CLI login. Run linked database CLI commands sequentially: overlapping commands can refresh the same project temporary-login role and cause authentication retries. Do not resolve this by changing shared credentials or stopping another agent's process. The Supabase connector observed during preflight pointed to a different project; do not use its data or mutation tools unless a fresh identity check proves it now targets `fxpxsciltakyypunglzr`.

## Local isolation and implementation

- Preserve existing uncommitted edits and untracked files. Do not reset/clean the checkout or alter `.claude/` configuration to perform dashboard work.
- Do not globally upgrade CLIs, Node, Python, or packages while coordinating this task. Prefer project-local dependencies and an isolated worker environment.
- Check ports before starting services. Track and stop only this task's processes. Do not use broad process termination, Docker pruning, or `supabase stop --all`.
- Keep application credentials and environment files private and out of source control, logs, and reports. Do not revoke or rotate a credential without determining whether other projects depend on it.
- Current Vercel preview/development configuration uses the same Supabase values as production. A preview deployment is not an isolated database test environment. Use mocked/offline tests for initial repairs; review database targets before any integration test that writes.
- Follow `TODO.md` dependencies and keep `CONFIGURATION-PREFLIGHT.md` current. Target verification does not mean the bot is ready to deploy or trade.
- Review migrations as forward changes against the exact allowed Supabase project. Prepare deployment/migration validation and rollback steps before the corresponding action. Follow the user's actual authorization; do not infer permission for unrelated cloud changes.
- Live wallet funding, transaction signing, swaps, and live trading are outside the current work's authorization.

## Jupiter research tools

Official Jupiter skills are pinned under `.agents/skills`; their upstream text is unmodified. Read `JUPITER-TOOLING.md` before applying them. Their examples are reference material, not permission to sign, fund, broadcast, submit feedback, install global tools, or change another agent's configuration. The migration skill's live-swap test checklist is outside this task's authorization; use mocked contract tests and authorized read-only requests.

Prefer current official endpoint documentation/OpenAPI over cached skill claims. The pinned integration skill contains an obsolete volume-based rate-limit table and overly broad authentication statements; the current portal describes organization-wide quotas and limited keyless access. Recheck endpoint-specific authentication, fees, routing, and rate limits before coding. Use decimal/integer token-atomic conversion rather than copying floating-point `Math.round(human * 10 ** decimals)`. Reconcile uncertain submissions before any future authorized retry; a fresh order is not a safe substitute for transaction-state reconciliation.

The project-only `.codex/config.toml` enables `jupiter_docs` with just `search_jupiter` and `query_docs_filesystem_jupiter`. It excludes `submit_feedback`; do not send unsolicited messages to Jupiter. Do not add the trading MCP, run the Jupiter CLI, or invoke the upstream all-agent installer as an implicit extension of this documentation setup. Consult the documented isolation and deferred-tool decisions first.

## Helius research tools

The user explicitly requested the Helius MCP. Read `HELIUS-TOOLING.md` before use.
The project-only Codex configuration launches the pinned local package through
`/usr/bin/python3 -I -B scripts/dashboard-helius-mcp.py`; do not replace it with a
floating `npx` invocation or add a global/Claude configuration. Its private key,
Node runtime, dependency lock, HOME and cache stay under ignored `ssl/`. Never
print the key, pass it in command arguments, upload this directory, or fall back
to shared Helius config, wallet files, shell environment or credentials.

Only the six configured read tool groups are enabled. Account/billing, signing,
transfers, staking, webhook management and local preference/JWT tools remain
excluded. Read calls still consume provider quota; keep them bounded. The
version-specific Node preload suppresses the reviewed Helius feedback endpoint;
it is not a general network or filesystem sandbox. Keep required telemetry fields
neutral (`_feedback="read-only request"`, `_feedbackTool="dashboard-read"`,
`_model="local-client"`), and never include private task context or reasoning.
Re-review package code, tool domains, dependency/advisory results and the preload
before any version update. MCP access does not authorize wallet funding, signing,
transaction broadcast, live trading, paid upgrades or account-wide changes.
