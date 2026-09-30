# Dashboard project boundaries

The user runs another coding agent on a different project under the same macOS user and the same Vercel/Supabase accounts. Preserve that agent's work, credentials, tools, and processes. These instructions apply to this repository only.

## Allowed remote targets

GitHub repository: `TOOTRJ/TheDashboard`, immutable repository ID `1141090963`, canonical origin `https://github.com/TOOTRJ/TheDashboard.git`. Use `codex/` branches and pull requests for reviewed changes. The former `biggrizzly11/TheDashboard` address redirects to this same repository; use the canonical address for future operations. Do not push directly to `main` or merge a pull request without authorization.

The `codex/dashboard-security-reliability` branch has automatic Vercel Git deployments disabled in `vercel.json` so review can proceed before preview isolation and release readiness are resolved. Keep that branch guard until deployment is deliberately reviewed; a draft PR alone does not prevent deployment. Other branches retain their existing behavior.

| Provider | Project | Immutable ID | Owner |
|---|---|---|---|
| Vercel | `the-dashboard` | `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` | Team `team_8iNNxiNjrOseD4gdSCHkQEzF`, slug `orderoftheredjester` |
| Supabase | `The Dashboard` | `fxpxsciltakyypunglzr` | Organization `cqfnnaunmupdyobkyqfo`, name `Valentine Jester` |

Verify the exact project name, immutable ID, and owner before consequential remote operations. Stop on a mismatch; do not select a similarly named project or create a replacement. Do not modify another project, organization/team-wide configuration, shared environment variables, billing, shared credentials, domains belonging to other projects, or other repositories. Identity metadata needed to resolve the authorized target is distinct from permission to inspect another project's contents.

## Isolated CLI context

Use working directory `/Users/redjester/Projects/Next/TheDashboard` explicitly.

For every Vercel command, use global configuration directory `/Users/redjester/.config/vercel-dashboard-codex`. Remove inherited `VERCEL_TOKEN`, `VERCEL_ORG_ID`, and `VERCEL_PROJECT_ID` from the command's child-process environment. Do not unset variables in another running process or alter shell startup files. Use the verified `--scope` and `--project` IDs wherever the command supports them; inspect installed command help instead of guessing flags.

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
