# Jupiter tools for The Dashboard

Reviewed 2026-09-30; endpoint/tool reassessment 2026-10-07. This setup supports development/research for
`TOOTRJ/TheDashboard`; it adds no application dependencies or trading execution.

## Installed

| Component | Local installation | Purpose |
| --- | --- | --- |
| Official `integrating-jupiter` skill, metadata version 1.2.0 | `.agents/skills/integrating-jupiter/` | API selection, integration guidance, error handling and linked references |
| Official `jupiter-swap-migration` skill, metadata version 1.1.0 | `.agents/skills/jupiter-swap-migration/` | Guide the tested quote-only V2 migration and future contract review |
| Jupiter documentation MCP | `.codex/config.toml`, server `jupiter_docs` | Search published docs and read documentation/OpenAPI specifications |

Both skills come from [Jupiter's official repository](https://github.com/jup-ag/agent-skills/tree/a2211e3f6a7caa03310c7a9a8d816e723b0bdc5f),
at commit `a2211e3f6a7caa03310c7a9a8d816e723b0bdc5f`. The official Jupiter
[AI skill page](https://developers.jup.ag/docs/ai/skills) links that repository.
Their complete directories, including examples, are copied unchanged. The root
MIT license is copied into each directory. `jupiter-skills.lock.json` records
versions, provenance and SHA-256 for every installed file. Review updates before
changing the pin; do not automatically track `main`.

The documentation MCP uses `https://developers.jup.ag/docs/mcp`. Only these
two tools are enabled:

- `search_jupiter`: documentation search.
- `query_docs_filesystem_jupiter`: read-only queries over the provider's virtual
  documentation filesystem, including OpenAPI specifications; not a local shell.

The actual server also exposes `submit_feedback`. It is excluded because it
sends a message to the documentation team. No credentials are configured. Public
documentation queries are sent to Jupiter's docs service; never put credentials,
private wallet data or unrelated project content in those queries.

## Scope, activation and verification

The skills and MCP configuration live only inside this repository. No global
Codex files, `.claude/`, Claude MCP files, shell profiles, shared account settings,
package managers, or user-level wallet configuration were changed.

[Codex project configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
loads `.codex/config.toml` for trusted projects. `codex mcp get jupiter_docs --json`
successfully resolved this project's URL, two-tool allowlist and timeout settings.
The server passed MCP initialize, tools/list, a documentation search, and a
Price V3 OpenAPI retrieval, without an API key. Those calls returned no market
dataset and made no trading request. The hosted server is not version-pinned;
the explicit tool allowlist prevents newly added tool names from being enabled.

Skills become available on the next turn; if they do not appear, restart Codex.
Reconnect/restart the Codex client if the new MCP is absent from its connected
server list. Do not change Claude's settings to activate this configuration.
Current-turn MCP checks used direct protocol requests; they do not prove the
running conversation has hot-loaded a new tool catalog.

## Known upstream discrepancies and project overrides

The official skills are useful navigators, but their frozen text is not an API
contract. Follow current official documentation and the root `AGENTS.md`:

- The integration skill's volume-based Swap quota table and 10-second window
  conflict with the current [portal limits](https://developers.jup.ag/docs/portal/rate-limits).
  Current quotas are organization-wide, with a separate execute bucket.
- Its universal API-key requirement differs from the portal's limited keyless
  access. The Price OpenAPI still declares API-key security. Confirm each endpoint
  and retain the worker's private API key rather than broadly removing auth.
- The AI skills landing page labels Price as historical, but the current Price V3
  specification only documents a present-price request by mint. Do not invent a
  history endpoint from that summary; see the [data research decision](services/vonneumann/JUPITER-DATA-RESEARCH.md).
- Recurring/Portfolio/RFQ descriptions also need fresh product-specific review.
  Installing a broad skill does not approve those features for the trading bot.
- Floating-point amount conversion in examples is unsuitable for general token
  atomic precision. Validate mint decimals and use exact conversion.
- The migration skill's review-by date has passed. Its small live-swap test is
  outside current authorization. Use mocked endpoint contracts, explicit quote
  semantics and read-only validation; signing and broadcast remain gated.
- Retry snippets cannot replace durable idempotency and confirmation/reconciliation
  after an uncertain transaction result.
- Future accounting must distinguish V2 wallet flows `totalInputAmount` /
  `totalOutputAmount` from route amounts `inputAmountResult` / `outputAmountResult`.
  Those wallet totals belong to the execute response. Skill examples that return
  only route amounts do not establish net wallet P&L.

## Current index and contracts (2026-10-07)

The complete [llms.txt index](https://developers.jup.ag/docs/llms.txt) was fetched
before selecting current endpoint pages. Actual versioned Price V3, Tokens V2
and Swap V2 YAML files were retrieved and hashed in the
[review manifest](services/vonneumann/jupiter-api-review-20261007.json).
Use those URLs: the older unversioned Swap YAML link still returns a legacy V1
contract; analogous old unversioned Price/Tokens links are unavailable. Preserve
the pinned upstream skill text and apply these project overrides.

Runtime source already uses `api.jup.ag/price/v3` and quote-only
`api.jup.ag/swap/v2/order`. No deprecated Jupiter host/V1/Ultra runtime call was
found. Price `createdAt` is token creation, not price freshness; `blockId` remains
the required source reference. Current Tokens rolling statistics do not provide
historical candles. Neither the reviewed index nor Price schema documents a
general historical range endpoint. [Detailed review and feature decisions](services/vonneumann/JUPITER-DATA-RESEARCH.md).

The signed-in portal confirms the user's Developer upgrade and identifies a
fresh Dashboard Price V3 request under the existing configured key. Actual
headers still report `current=1`, `remaining=9` and roughly ten seconds to reset,
rather than establishing the documented Developer sixty-second capacity. No
firewall rule matched that request. Keep this discrepancy open in DATA-01E;
do not infer quota from the badge, assume a reset replenishes a full window,
or change account-wide settings used by another project.

New useful research surfaces include key permissions/request-credit logs,
Tokens audit/liquidity fields, managed Swap V2 execution and optional transaction
V1 support. Beta `/build?mode=fast` is a later measured live-routing alternative,
with different route/fee tradeoffs. Trigger V2 needs a separate custody/order
model; RFQ streaming and AMM test-kit tools serve liquidity/DEX integrators.
None solves this pilot's historical warmup requirement.

The user's AI-tool excerpt distinguishes documentation from operations. Local
skills/index are sufficient for this HTTP-adapter development, with the existing
two-tool documentation MCP as an optional research aid. The current conversation
does not expose those MCP calls, so official HTTP documentation was used without
changing any agent configuration. No CLI, trading MCP, wallet kit or broad
installer is required for the paper MVP.

## Reviewed and deferred

The unused worker swap helper has now migrated to V2 `/order` without `taker`,
with exact atomic integer inputs, a validated immutable quote, bounded I/O and
offline contract tests. It exposes no execution path. See the
[quote adapter contract](services/vonneumann/JUPITER-SWAP-CONTRACT.md).

**Jupiter CLI (`@jup-ag/cli` 0.10.1):** official, but described as early alpha in
the [CLI documentation](https://developers.jup.ag/docs/ai/cli). Source reviewed at
[`d8d7386691535469f7d17705ebfc5f432b96feba`](https://github.com/jup-ag/cli/tree/d8d7386691535469f7d17705ebfc5f432b96feba).
`src/index.ts` invokes `Config.init()` before parsing `--help`/`--version`;
`src/lib/Config.ts` hardcodes `~/.config/jup`, creates a keys directory and writes
default settings. Client initialization can read shared settings. A local npm
prefix alone therefore does not isolate runtime configuration. Some swap dry-run
paths initialize a signer before their dry-run branch. It was not installed or
executed. Reassess only for a concrete workflow with a proven isolated runtime;
keep the Python worker on explicit, versioned HTTP adapters.

**Trading MCP (`https://mcp.jup.ag`):** distinct from the documentation MCP. It
offers market/account operations and transaction execution across many products.
The offline strategy work needs none of its write tools. Defer it; if later
needed, audit the actual schemas and add a narrow read-only allowlist first.
[Official distinction](https://developers.jup.ag/docs/ai/trading-mcp).

**Lend, token-verification and unrelated skills:** no current lending, token
listing, perps or token-launch requirement. Do not install them just because
they are available. The upstream universal installer may target multiple agents;
the OpenAI skill-installer was used with an explicit project destination instead.

## Updating safely

Read and compare the selected upstream commit, current docs and examples. Stage
the replacement in a task-owned temporary directory, check local file hashes
against `jupiter-skills.lock.json`, and review any local differences before
replacing either installed folder. Preserve licenses and update the manifest.
Never overwrite an existing skill merely because the installer reports a conflict.
For MCP changes, inspect the actual server tool list and test only allowed reads.
