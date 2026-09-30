# Dependency security review — 2026-09-29

The local dependency repair is implemented. Fresh npm audits report **zero known vulnerabilities** for both the full installed graph and the production graph. Both Python lock files contain **49 exact, hashed packages**, and their PyPI advisory scans report **zero known vulnerabilities**. These results describe the advisory databases and versions checked today; they are not a claim that the application is secure or ready to deploy.

**An additional Next.js security update remains an open security follow-up.** The official [September security notice](https://nextjs.org/blog/upcoming-nextjs-security-release-september-2026), updated September 29, says that 16.3.7 contains a bug fix but **does not include** the security fixes scheduled for September 30. The announced versions are now **16.3.8 and 15.5.27**, covering nine vulnerabilities: one critical, two high, five medium, and one low. Their full affected ranges and impact are not published in that notice. The user-authorized dashboard release uses the latest published 16.3.7; the announced patches were unavailable at the release check. Recheck the actual published advisories and registry, upgrade when the reviewed fix is available, and rerun validation. No future version was assumed available or installed.

## Scope and isolation

Only this checkout's dependency manifests/locks and this report were changed for SEC-05. Application fixes are separate work by the other agents. No cloud configuration, credentials, environment files, migrations, shared tool installations, or other project's dependencies were changed. No development server or trading worker was started for dependency verification.

The dependency cache and two Python virtual environments live under `/private/tmp/dashboard-sec05`. npm used separate empty user/global config files, an explicit public registry, a task-specific cache, and `--ignore-scripts`. No package lifecycle hook or force upgrade ran. Python installations used public PyPI, wheels only, and an isolated virtual environment; source distribution build hooks were not run. The compiler's first attempt to use a shared default cache was denied by the sandbox; it was rerun with a task-specific cache and did not modify the shared cache.

The repository's pre-existing changes were preserved. The other frontend agent confirmed that it was not running tests or a development server before `node_modules` changed. Listening-port inspection found no ordinary dashboard development listener; no process was stopped.

## JavaScript changes and impact

The original fresh audit reproduced **15 vulnerable packages: 1 critical, 10 high, 3 moderate, 1 low**. These are package counts, not 15 individual CVEs: some packages carried multiple advisories.

| Direct dependency | Before | Selected | Reason |
|---|---|---|---|
| `next` | 16.1.4 | **16.3.7** | Current published stable 16.x, verified against npm metadata. Fixes published framework, image-processing, and bundled PostCSS advisories that cannot all be addressed by staying on 16.1. |
| `eslint-config-next` | 16.1.4 | **16.3.7** | Keep framework configuration and plugin aligned with Next. |
| `react`, `react-dom` | 19.2.3 | **19.2.8** | Latest published patch on the existing 19.2 line; avoid an unnecessary 19.3 feature upgrade. Next's declared peers accept this version. |
| `eslint` | 9.39.2 installed, `^9` declared | **9.39.5** | Latest 9.x patch, exact-pinned. Existing React/import/accessibility/hooks plugins declare support through ESLint 9, so an unreviewed ESLint 10 upgrade would violate peer ranges. |

In this initial security batch, other direct version declarations remained unchanged; the later dependency follow-up below supersedes that baseline. `package-lock.json` pins their resolved graph. After the direct updates, `npm audit fix` **without `--force`**, with lifecycle scripts disabled, updated compatible transitive dependencies. Its resulting lock diff was reviewed: no unrelated direct package upgrade or peer override was introduced.

| Previously flagged package/group | Main resulting versions | Reachability assessment |
|---|---|---|
| Next framework | 16.3.7 | App Router and `src/proxy.ts` make framework/RSC/proxy advisories relevant. Do not treat a login redirect as a sufficient workaround. The audit also included conditional Windows, image, custom-server, rewrite, PPR, and Server Action cases; not every listed exploit was demonstrated in this app. |
| `sharp` and native image libraries | sharp 0.35.5; libvips package 1.3.4 | Next's image implementation brings native decoders into the dependency graph. Source review found no current `next/image` usage or custom remote-image configuration, which narrows demonstrated reachability but is not a reason to retain vulnerable decoders. |
| `postcss`, `nanoid` | 8.5.23, 3.3.19 | Primarily CSS/build processing here. No application path accepting attacker-supplied CSS was identified. |
| `ws` | 8.22.0 | Transitive Supabase realtime/server transport. No direct Node `ws` server was identified in this application; the custom worker socket is Python. Patched despite conditional reachability. |
| `@babel/core`, `browserslist`, `baseline-browser-mapping` | 7.29.7, 4.29.3, 2.11.26 | Build/configuration processing, including source-map reads and malformed input/resource exhaustion. Project source/configuration is the likely input boundary here. |
| `@humanfs/node`, `ajv`, `flatted`, `js-yaml` | 0.16.8, 6.15.0, 3.4.4, 4.3.2 | Lint/tooling graph. Filesystem-copy, parser, prototype, and resource-exhaustion advisories are mainly development/CI exposure in this repository. |
| `brace-expansion`, `minimatch`, `picomatch` | 1.1.21 / 2.1.7; 3.1.5 / 9.0.9; 2.3.2 / 4.0.7 | Pattern-processing denial-of-service fixes within existing major ranges. Multiple versions remain because different consumers require different major lines. |

Representative advisory evidence: [Next RSC DoS](https://github.com/vercel/next.js/security/advisories/GHSA-h25m-26qc-wcjf), [Next App Router proxy bypass](https://github.com/vercel/next.js/security/advisories/GHSA-26hh-7cqf-hhc6), [Next image AVIF RCE](https://github.com/vercel/next.js/security/advisories/GHSA-2xp9-vwfh-vxw4), [PostCSS source-map read](https://github.com/advisories/GHSA-fxqj-rqcc-2cmp), [sharp native-library vulnerabilities](https://github.com/advisories/GHSA-rgj7-g3m4-5g8c), [ws resource exhaustion](https://github.com/advisories/GHSA-96hv-2xvq-fx4p). The fresh npm registry audit supplied the affected ranges, severity, and compatible fix decisions used above.

Registry version/peer evidence: [Next 16.3.7](https://registry.npmjs.org/next/16.3.7), [React 19.2.8](https://registry.npmjs.org/react/19.2.8), [React DOM 19.2.8](https://registry.npmjs.org/react-dom/19.2.8), [ESLint 9.39.5](https://registry.npmjs.org/eslint/9.39.5), [matching Next ESLint configuration](https://registry.npmjs.org/eslint-config-next/16.3.7). The [React security update](https://react.dev/blog/2025/12/11/denial-of-service-and-source-code-exposure-in-react-server-components) explains why earlier fixes were insufficient; framework-bundled RSC code must be updated alongside React.

**Maintenance decision:** ESLint 9.39.5 is marked unsupported/deprecated upstream. This local security pass leaves it as a documented development-tool exception because the installed plugin peer ranges do not accept 10. Plan a coordinated, tested plugin/ESLint upgrade; do not use `--force` or `--legacy-peer-deps` to hide incompatibility. This is separate from the zero-advisory result. The test runner used the existing Node 25.6.1; a supported production Node LTS and the configured deployment runtime still need release verification. No global Node installation was changed.

## Python runtime and reproducibility

The prior `requirements.txt` consisted only of unbounded minimums and did not reproduce the worker environment. The incidental system Python was 3.9 with LibreSSL; it is no longer the validation runtime for this lock.

The selected runtime is **CPython 3.12.14**, recorded in `services/vonneumann/.python-version`. The available bundled interpreter reports **OpenSSL 3.5.8**. A fresh virtual environment contains only the worker's resolved dependencies and bootstrap pip; no global `pip freeze` was used. `.python-version` documents the intended runtime, but deployment tooling must actually provision it.

| Direct worker dependency | Exact version | Review decision |
|---|---|---|
| aiohttp | 3.14.3 | Includes the client C-parser fix for malformed responses. The worker calls remote feeds and Auth, so client parser robustness matters. |
| Supabase | 2.31.0 | Current compatible 2.x release; its related Auth/PostgREST/storage/realtime packages are consistently locked at 2.31.0. |
| FastAPI | 0.142.1 | Allows a patched current Starlette; lock resolves Starlette 1.7.0. |
| Uvicorn with standard extras | 0.54.0 | Current Python 3.12-compatible ASGI runtime, with explicit locked native/transport dependencies. |
| WebSockets | 15.0.1 | Retained compatible major: Supabase realtime 2.31.0 requires `>=11,<16`. Latest WebSockets 17.1 is therefore unsuitable for this graph. |
| Pydantic | 2.13.5 | Current 2.x; validation/schema code must be tested under this exact version. |
| NumPy | 2.5.3 | Current 2.x compatible with Python 3.12. Numerical engine invariants still require the algorithm repair tests; dependency installation does not establish trading correctness. |
| CMAes | 0.13.1 | Patch update within the already installed 0.13 line. |
| python-dotenv | 1.2.3 | Current compatible release; test commands disable dotenv loading. |
| HTTPX — explicit test input | 0.28.1 | FastAPI TestClient dependency, already required by Supabase at runtime. Kept explicit in `requirements-dev.in`; the current runtime and test dependency sets therefore both contain 49 packages. |

The installed baseline sample included aiohttp 3.13.5 and Starlette 0.49.3. PyPI version-specific advisory data flags both. The upstream [aiohttp response-parser advisory](https://github.com/aio-libs/aiohttp/security/advisories/GHSA-cq5v-8q36-5273) identifies 3.14.3 as the fix; [Starlette advisory data](https://pypi.org/pypi/starlette/0.49.3/json) includes Host/path handling and later fixes through 1.3.1. No claim is made that every advisory was exploitable through this service's endpoint-level authentication. The chosen graph removes the known vulnerable versions instead of relying on reachability assumptions.

Primary package metadata: [aiohttp](https://pypi.org/pypi/aiohttp/3.14.3/json), [FastAPI](https://pypi.org/pypi/fastapi/0.142.1/json), [Supabase](https://pypi.org/pypi/supabase/2.31.0/json), [realtime constraint](https://pypi.org/pypi/realtime/2.31.0/json), [pip-tools](https://pypi.org/project/pip-tools/7.6.1/), [pip-audit](https://pypi.org/project/pip-audit/2.10.1/).

`requirements.in` and `requirements-dev.in` record intentional direct inputs. Generated `requirements.txt` and `requirements-dev.txt` pin the entire resolved closure and include SHA-256 wheel hashes. They were compiled with pip-tools 7.6.1 and pip 25.0.1 under Python 3.12. The locks were installed and tested on macOS ARM64. Their hashes cover multiple wheel platforms, but the resolution is for Python 3.12 on Unix; validate the target Linux image before deployment. Windows is not claimed supported by this lock because the resolved standard Uvicorn extras include uvloop.

## Reproduction commands

Run from `/Users/redjester/Projects/Next/TheDashboard`. Use a supported Python 3.12.14 interpreter for `python3.12` below. Choose a fresh task-specific temporary directory; none of these commands requires a global package installation.

```sh
TASK_DEPS=$(mktemp -d /tmp/dashboard-deps.XXXXXX)
touch "$TASK_DEPS/npm-user-config" "$TASK_DEPS/npm-global-config"
npm ci --ignore-scripts --no-fund --no-audit \
  --registry=https://registry.npmjs.org \
  --userconfig="$TASK_DEPS/npm-user-config" \
  --globalconfig="$TASK_DEPS/npm-global-config" \
  --cache="$TASK_DEPS/npm-cache"
npm audit --registry=https://registry.npmjs.org \
  --userconfig="$TASK_DEPS/npm-user-config" \
  --globalconfig="$TASK_DEPS/npm-global-config" \
  --cache="$TASK_DEPS/npm-cache"

python3.12 -m venv "$TASK_DEPS/worker"
PIP_CONFIG_FILE=/dev/null "$TASK_DEPS/worker/bin/python" -m pip --isolated install \
  --require-hashes --only-binary=:all: --index-url=https://pypi.org/simple \
  --cache-dir="$TASK_DEPS/pip-cache" \
  -r services/vonneumann/requirements-dev.txt
PIP_CACHE_DIR="$TASK_DEPS/pip-cache" "$TASK_DEPS/worker/bin/python" -m pip check
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 PYTHONPATH=services/vonneumann \
  "$TASK_DEPS/worker/bin/python" -m unittest discover \
  -s services/vonneumann/tests -t services/vonneumann

python3.12 -m venv "$TASK_DEPS/tools"
PIP_CONFIG_FILE=/dev/null "$TASK_DEPS/tools/bin/python" -m pip --isolated install \
  --only-binary=:all: --index-url=https://pypi.org/simple \
  --cache-dir="$TASK_DEPS/pip-cache" pip==25.0.1 pip-tools==7.6.1 pip-audit==2.10.1
"$TASK_DEPS/tools/bin/python" -m pip_audit \
  -r services/vonneumann/requirements.txt --require-hashes --disable-pip \
  --strict --progress-spinner=off --cache-dir="$TASK_DEPS/audit-cache"
```

`npm ci` replaces this project's `node_modules`; coordinate it with local tests/dev servers first. For production-only npm results add `--omit=dev`. For test dependency advisory results audit `requirements-dev.txt` as well. `pip-audit --disable-pip` reads the fully pinned lock without invoking dependency resolution or installing project packages; its network traffic is public advisory lookups, not application traffic. Known-advisory scanners do not detect all malicious packages or every vulnerability in vendored native libraries.

To intentionally update Python inputs, review new versions first, edit the `.in` file, and run the header's `piptools compile` command from `services/vonneumann` with `PIP_CONFIG_FILE=/dev/null`, a task-specific `PIP_CACHE_DIR`, and a task-specific `--cache-dir`. Regenerate both locks together and rerun hash installation, `pip check`, advisory checks, and the complete offline test suite. Tool environment transitive packages are disposable and are not part of the worker lock.

## Validation and remaining release work

- Full npm graph: **0 known vulnerabilities**; production-only graph: **0**.
- Runtime Python lock: **49 packages, 0 known vulnerabilities**; test Python lock: **49 packages, 0**.
- Hash-verified wheel installation into a clean Python 3.12.14 environment: passed. `pip check`: no broken requirements.
- Existing backend security suite under the new lock: **50 tests passed**. Tests disable dotenv, use fake configuration, and block unexpected network operations.
- Final combined backend suite under the lock: **107 tests passed** (including the 50 existing security tests). Final frontend suite: **35 tests passed**; **142 total** offline tests. TypeScript passes. Broad source/test lint passes with zero errors and 34 existing warnings. The final isolated production build with default Turbopack passes; an earlier webpack build also passed. Builds used fake application credentials, no environment files, and temporary source/dependency copies, preserving the checkout’s existing `.next` output. `git diff --check` passes. These are local checks, not a diagnosis or repair of the earlier remote deployment failures.

The updated Starlette TestClient emits a deprecation warning recommending HTTPX2. HTTPX 0.28.1 remains supported by the installed compatibility path and is required by Supabase; tests pass. Plan a separately verified test-client migration rather than suppressing the warning or replacing Supabase's HTTP client blindly.

Release still requires the announced Next security fix review, supported deployment runtime selection, target-platform lock installation, real-session auth/routing checks, browser integration, and a reviewed deployment against the authorized project. Passing offline tests or package audits does not verify remote database policies, credentials, worker hosting, strategy economics, or trading safety.


## Dependency follow-up after PR #1 (2026-09-30 UTC)

The user authorized merging the tested work to `main`, production deployment, and a separate dependency follow-up before further engine changes. PR #1 merged as `80391b4763ae2479c12f524875f5eae25b5ecfe6`. This follow-up changes the published compatible package set and the chart typing required by Recharts. It does not include the untracked ENG-02 test draft, migrations, or trading-engine changes.

The registry and official notice were rechecked on September 30 UTC (September 29 in Denver): **Next.js and eslint-config-next 16.3.7 remain the latest published stable versions**. Both announced `next@16.3.8` and `next@15.5.27` returned HTTP 404. Their pending security fixes remain open under SEC-05. There is no published mitigation in the announcement that can be assumed to cover this application. The user's production authorization permits this release; it does not make the unpublished fixes available or establish their impact. Sources: [official announcement](https://nextjs.org/blog/upcoming-nextjs-security-release-september-2026), [npm version tags](https://registry.npmjs.org/-/package/next/dist-tags).

| Package group | Updated version(s) | Compatibility decision |
|---|---|---|
| Supabase JavaScript SDK | 2.91.0 → 2.117.2 | Includes relevant authentication refresh fixes; requires Node ≥22. The app now declares Node 24.x to match the already configured Vercel runtime. |
| Radix primitives | Avatar 1.2.6; checkbox 1.3.11; dialog 1.1.23; dropdown 2.1.24; label 2.1.15; select 2.3.7; separator 1.1.15; slider 1.4.7; slot 1.3.3; switch 1.3.7; tabs 1.1.21; tooltip 1.2.16 | Compatible existing major lines; current ref, keyboard, and accessibility fixes without changing wrappers. |
| Recharts | 3.7.0 → 3.10.1 | New readonly tooltip payloads and chart generics require small typing changes in the two Nestegg charts. Calculations are unchanged. |
| react-is | Explicit 19.2.8 dependency | Match React/React DOM 19.2.8. Recharts otherwise resolved an old 16.13.1 peer that failed to recognize React 19 fragments used around chart series. The older copy may remain nested under its separate legacy consumer. |
| Tailwind / PostCSS plugin | 4.1.18 → 4.3.3 together | Preserve the existing PostCSS pipeline and v4 styling approach. |
| tailwind-merge / Sonner | 3.4.0 → 3.7.0 / 2.0.7 → 2.0.8 | Compatible utility and notification updates. |
| Type declarations | Node 24.19.0; React 19.2.18; React DOM 19.2.7 | Node declarations match the production major. React declaration ranges stay on the installed 19.2 runtime line. |

[Supabase SDK release notes](https://github.com/supabase/supabase-js/blob/master/packages/core/supabase-js/CHANGELOG.md), [Radix release notes](https://www.radix-ui.com/primitives/docs/overview/releases), [Recharts releases](https://github.com/recharts/recharts/releases), [Tailwind changelog](https://github.com/tailwindlabs/tailwindcss/blob/main/CHANGELOG.md), and [Tailwind Merge release notes](https://github.com/dcastil/tailwind-merge/releases/tag/tailwind-merge%403.7.0) informed this selection. The lock file records the complete resolved versions and integrity values.

React/DOM stay at 19.2.8. React 19.3's hydration/effect changes deserve separate verification. Supabase SSR stays at 0.8.0: its available 0.12.7 update needs deliberate cookie/cache-header adapter work in the proxy and server client. TypeScript 7, ESLint 10, and Lucide 1 are separate major migrations; no `--force` or peer-compatibility override was used. The existing Python locks were already reviewed and are outside this JavaScript follow-up.

Validation uses an isolated official Node **24.21.0** Darwin ARM64 runtime, verified against Node.js's published SHA-256 manifest, without modifying global runtimes or shell profiles. npm uses separate empty config files and a task-specific cache under `/private/tmp/dashboard-dependency-followup`; install and clean-lock verification disable package lifecycle scripts. The shared npm cache was not repaired or changed. The production build uses a temporary source/dependency copy with fake application credentials and no environment files, preserving the checkout's existing build output.

**Final local verification:** 36 Node tests pass under Node 24.21.0, including the actual Recharts dependency-resolution regression. Full TypeScript and the isolated default-Turbopack production build pass (18 routes/pages generated). Source/test lint has zero errors and 33 existing warnings. Full and production-only npm audits both report zero known vulnerabilities. Clean locked installation succeeded; the reviewed graph has no non-optional dependency/peer problems. The initial build correctly failed on the newly strict Recharts types, and the final build passed after the minimal chart fixes. This is not a claim of authenticated browser testing or visual verification of every chart mode. Python was unchanged; its previous 137 passing tests remain the worker evidence, and the untracked unfinished ENG-02 test draft is excluded from this PR.
