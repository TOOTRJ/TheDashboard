# Helius MCP for The Dashboard

Reviewed and installed locally on 2026-10-21. This is a development tool for
`TOOTRJ/TheDashboard`; installing it does not change the Railway worker, Vercel,
Supabase, the application's package lock, or trading permissions.

## Installed artifact and local boundaries

The official [Helius MCP](https://www.helius.dev/docs/agents/mcp) is pinned to
`helius-mcp@2.3.0`, using its
[official npm registry artifact](https://registry.npmjs.org/helius-mcp/2.3.0).
The public package was downloaded and inspected before installation. All 136
published files matched after installation. The tarball's registry SHA-512 and
SHA-1 were checked; registry provenance signatures were not independently
verified. Cached documentation/npm pages still describe older releases.

| Component | Dashboard-only location |
| --- | --- |
| Launcher | `scripts/dashboard-helius-mcp.py` |
| Reviewed analytics suppression | `scripts/dashboard-helius-no-telemetry.mjs` |
| Private API-key assignment | ignored `ssl/helius-mcp.env` |
| Installed package and dependency lock | ignored `ssl/helius-mcp-runtime/` |
| Verified Node 24.19.0 for macOS ARM64 | `ssl/helius-mcp-runtime/bin/node` |
| Child home | `ssl/helius-mcp-runtime/home/` |
| Child temporary files | `ssl/helius-mcp-runtime/tmp/` |
| Installation-only npm cache | `ssl/helius-mcp-runtime/npm-cache/` |
| Installed tree hashes | `ssl/helius-mcp-runtime/runtime-integrity.json` |
| Install/audit/dependency evidence | `ssl/helius-mcp-runtime/installation-receipt.json`, `audit.json`, `dependency-tree.json` |

The runtime root and its bin/home/tmp/npm-cache directories are owned mode 0700.
Installed npm subdirectories normally use mode 0755 under that private root; none
are group/world writable. The key file and integrity manifest are owned mode 0600. Nothing under `ssl/` belongs in Git, Vercel build
artifacts, Railway uploads, screenshots, or reports. `ssl/` was already ignored.
No shared CLI installation, user MCP configuration, `.claude/` file, shell
profile, or another project's settings were changed for this installation.

The launcher uses the system Python 3.9 standard library. The project MCP entry
must run `/usr/bin/python3` with arguments:

```text
-I -B /Users/redjester/Projects/Next/TheDashboard/scripts/dashboard-helius-mcp.py
```

Use the exact Dashboard working directory. `-I` prevents inherited Python paths
and user-site startup code from loading before isolation; `-B` avoids bytecode
writes. No argument defaults to stdio; an explicit trailing `stdio` is also
accepted. Run only through the reviewed project MCP configuration so its tool
allowlist applies. A bare `npx helius-mcp@latest` does not provide those controls.

For a **credential-free local integrity check**, run:

```sh
/usr/bin/python3 -I -B /Users/redjester/Projects/Next/TheDashboard/scripts/dashboard-helius-mcp.py verify-runtime
```

That operation checks the pinned Node binary, lock, manifest, complete installed
file tree, relative package-bin links and public preload path. It reads no key,
starts no process and makes no network request. Runtime integrity does not
verify a provider account or authorize a trade. A different machine needs its
own reviewed platform runtime and pins; these paths and Node hash are specific
to this macOS ARM64 checkout.

The private key file accepts blank lines and comments plus exactly one line:

```dotenv
HELIUS_API_KEY=<Dashboard-only key>
```

Use an unquoted value. Other assignments, duplicate keys, `export`, shell
substitution, malformed values, oversized files, symbolic/hard links, foreign
ownership and permissions other than 0600 are refused. The launcher opens the
parent directory and final file without following links and validates the
opened descriptors. It reads no general `.env`, fallback Helius configuration,
shared wallet, Keychain item, or other provider credential. It verifies the
runtime before reading the key and passes the key only in the Node child
environment, never in command arguments or diagnostic output.

The child environment is built from explicit values: the private home/temp
directories, a fixed PATH, locale/color settings, the one API key,
`HELIUS_NETWORK=mainnet-beta`, and `HELIUS_MCP_SHARED_CREDENTIAL=1`. It does not
inherit `NODE_OPTIONS`, proxy configuration, GitHub tokens, Vercel tokens,
database URLs, dynamic-library settings, or another project's variables. Launch
uses the installed Node entrypoint directly; npm and npx do not run at startup.
This environment/home isolation is not an operating-system filesystem sandbox.

## Tool scope

The upstream package registers ten public tools and 95 actions. The
[public tool documentation](https://www.helius.dev/docs/agents/mcp/tools) is a
navigator; the installed 2.3.0 source/catalog is the reviewed action inventory.
The **project MCP client must enable exactly these six tool names**:

| Enabled tool | Purpose |
| --- | --- |
| `heliusWallet` | Balances, holdings, public wallet history/identity/funding reads |
| `heliusAsset` | Asset/ownership metadata, proofs, holders and signatures |
| `heliusTransaction` | Parse transactions and read transaction/transfer history |
| `heliusChain` | Account/block/network state, fee estimates, stake reads and simulation |
| `heliusCompression` | Compressed-state/proof/history/indexer reads; optional for current bot research |
| `expandResult` | Expand a result from an allowed read; can repeat the underlying request |

Exclude `heliusAccount`, `heliusWrite`, `heliusStreaming` and `heliusKnowledge`.
Account operations mix local configuration, account provisioning and billing.
Write includes transfers and stake/unstake/withdraw operations. Streaming mixes
configuration examples with webhook create/update/delete actions. Knowledge
includes `recommendStack`, which can persist preferences and inspect a locally
saved dashboard session; official documentation remains accessible directly.

`HELIUS_MCP_SHARED_CREDENTIAL=1` adds upstream response key scrubbing, skips
startup keypair loading, and refuses signing/runtime credential changes. It
does **not** remove registered tools or prevent webhook mutation on its own.
The launcher recommends the allowlist; the project client configuration enforces
it. Do not enable the four excluded groups as a troubleshooting shortcut.

These are provider reads, which can consume quota. Keep requests bounded and
measure usage before considering an account upgrade. `expandResult` re-executes
the stored read; it can consume another request and return newer data rather
than an immutable snapshot. Simulation does not submit a transaction. No wallet
funding, signing, broadcasting, live swaps, paid upgrades, or shared-account
changes are authorized by this setup.

## Reviewed telemetry endpoint suppression

Upstream 2.3.0 imports a feedback module that maintains `.helius/anon-id` under
its home. Ordinary startup also looks for a local signing keypair, even when an
API key is supplied. The isolated home and shared-credential flag prevent use
of the user's existing Helius files. The anonymous-ID file remains confined
to the Dashboard child home.

Upstream requires `_feedback`, `_feedbackTool` and `_model` strings on routed
calls. It otherwise sends a PostHog event containing those values, tool/client
identity and its anonymous ID, but does not automatically attach ordinary tool
arguments, results or the Helius API key. Loading an existing wallet can also
send an identity-link event in ordinary mode. No upstream telemetry opt-out was
found in the inspected package.

Before importing that package, the launcher loads
`scripts/dashboard-helius-no-telemetry.mjs`. It returns a local empty HTTP 204
for `globalThis.fetch` calls to the exact reviewed origin/path:

```text
https://www.helius.dev/relay-RMqE/capture/
```

It handles URL strings, URL objects and Requests, including query strings on
that path, without reading/logging the payload or headers. All other fetches
delegate unchanged. This suppresses the analytics path used by the pinned
package; it is **not** a general network firewall or a guarantee about future
versions, alternate transports, or arbitrary outbound requests. Reinspect the
feedback implementation before updating the package pin.

Keep required metadata neutral even with this suppression: use
`_feedback="read-only request"`, `_feedbackTool="dashboard-read"`, and
`_model="local-client"`. Never put private reasoning, credentials, account
details, wallet analysis or previous-result narratives in those fields.

## Installation evidence and remaining limits

The runtime was installed with `npm install --ignore-scripts --no-audit
--no-fund --save-exact`, using only its private home, npm configuration files,
cache and temp directory. The exact lock covers 193 installed packages. A
separate bounded npm audit completed with zero known vulnerabilities at every
severity on 2026-10-21. An initial audit request timed out; that was not treated
as a passing result. No audit fix, force option, or dependency override ran.

`npm ls --all` still reports two upstream peer-range conflicts:
`helius-sdk@3.3.0` requests older `@solana-program/system` and
`@solana-program/token` ranges than `helius-mcp@2.3.0` supplies. Installed
versions are system 0.14.1 and token 0.16.1. Do not describe the dependency
graph as clean or infer transaction/signing compatibility from the successful
catalog handshake. The SDK's writing paths remain excluded.

| Artifact | SHA-256 |
| --- | --- |
| Official MCP tarball | `30c0f72d32f1f5cf805ee0f68debd06d0c2e556cfd481130ca89a7fe001aaa3f` |
| Verified Node 24.19.0 binary | `27db838bb204ef7c21df2931f5656e4c8fb32e6e947f363a402b49714d32b5b1` |
| Dependency lock | `065fb9500e575103b2edc5c0dab4f63c0f2d620d1044d2a06c577488e000d811` |
| Installed-tree manifest | `4ba1ca4dc58a75f58997bab30d4f5d9c50e4419a5374df4b6cb1f187f6566659` |

The manifest covers 9,736 installed files and four relative package-bin links.
The launcher refuses changed, missing or added dependency files before loading
the credential. Do not modify the ignored runtime in place, run `npm update`,
or repin its manifest merely to clear a refusal. Stage and inspect a new
version/lock, audit it, rerun the boundary checks and review the corresponding
launcher pins before replacing this runtime.

Focused tests cover private-file refusal, key parsing, environment isolation,
artifact tampering, invocation arguments and the analytics suppression/delegation
behavior. A fake-key initialize/tools-list handshake passed with a test-only
preload denying fetch, HTTP(S), sockets and DNS and reporting zero outbound
network attempts. No provider action was called in that test. Nested macOS
`sandbox-exec` was unavailable, so the protocol test is not described as an OS
sandbox. Actual provider read acceptance, effective client tool filtering and
activation are separate checks performed by the release operator.

## Root connection acceptance

The project entry is now configured in `.codex/config.toml`. `codex mcp get
helius --json` resolves `/usr/bin/python3 -I -B`, the exact Dashboard launcher
and working directory, no inline environment credential, and exactly the six
reviewed read tool groups. Global Codex and Claude configurations are unchanged.
The running chat's tool catalog is a separate reload concern; this observation
does not claim that an existing chat hot-loaded the new server.

At 2026-10-22T03:10:27.281Z, root connected an MCP SDK client through that exact
configured launcher using the saved private key. Initialize and tools/list pass;
the server registers its expected ten tools, while Codex's client allowlist
selects the six above. One `heliusChain.getAccountInfo` read of Solana's public
System Program returns the expected owner/executable fields. Required telemetry
fields use the fixed neutral values above, and the reviewed preload is loaded
before upstream code. There are zero write actions, zero stderr bytes, and the
owned MCP child closes after the test. The separate direct mainnet getHealth
request also returns HTTP 200 and `ok`. No other provider actions, wallet
operations, cloud deployment or application credential rotation is performed.

The secret-free MCP acceptance receipt has SHA-256 `03d4209b1a04253c9af27311040f12ab3200b2465ed0acaf962fa2ac15c948b3`. This is bounded
connection/read evidence; it does not establish every allowed action, high-load
performance, universal SDK compatibility or trading readiness. The upstream peer
range warnings remain open. The credential remains in ignored mode-0600
`ssl/helius-mcp.env`; no Vercel or Railway variable is required for this local MCP.
