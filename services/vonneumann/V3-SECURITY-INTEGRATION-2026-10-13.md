# V3 source and HTTP security offline integration

This private integration starts from
`41d4ed00e40956736e1564ebd1e048c629894f6f` on
`codex/dashboard-v3-security-integration`. It combines exactly 28 previously
reviewed frozen files and adds only this contract and a new source-bound receipt.
Root and source peer reviews approved the exact candidate for a private scoped
local commit; adoption and hosted acceptance remain separate.
No provider acquisition, SQL/native fixture, hosted project change, worker
activation or remote operation is part of this slice.

## Frozen adoption and dependency boundary

SEC06 commit `b1ab59f4e6d5ae9a134a21235ba9a7f4343332fd` contributes exactly
eight files: the manual pinned-CA TLS helper, five legacy HTTP adapter/auth
repairs, focused tests and its original contract. The five existing adapters
were byte-identical between that repair's parent and this integration base;
there was no conflicting implementation to resolve. The three new SEC06 files
were absent. No library, requirements or global TLS configuration changes were
needed.

The source chain contributes 20 unique files at final frozen commit
`45d2b7aabbb889f4ff628c02a1864e7206192a0d`, all absent from the integration base:

| Frozen source commit | Reviewed addition/refinement |
| --- | --- |
| `737453957def9b91f446f70060b978337251b48b` | Original acquisition capsules and exact offline derivation |
| `ee5515eda7eaad38e4f97f9c0b7947fecd740e18` | Signed quota diagnostics and original history-record identity |
| `a78e7348603cc58498c9b6c03a19149de5755b3a` | Prospective Jupiter sampled-close contract |
| `282c08722f886cde8bb89aa6932032ecc4e20d25` | Explicit nullable Price metadata policy and source parser binding |
| `0785ab48c605d3b9468154773eb5ceb7a49d0c61` | Bounded disconnected original Price/RPC transport |
| `45d2b7aabbb889f4ff628c02a1864e7206192a0d` | Independent supplied-witness A1 source admission/sealing research |

Every adopted file is byte-for-byte equal to its applicable frozen Git blob.
The original eight-file SEC06 and source-chain contracts, historical receipts
and archival schema draft were preserved without rewriting their dates, hashes,
scope or outcomes. Their older observations describe their original code/run;
the new joined receipt describes this particular integration. Nothing labels
earlier native, model, restore or storage receipts as acceptance of these files.

The [joined receipt](research/v3-security-integration-2026-10-13.json) records
all 28 paths, frozen origins and current SHA256 values. Its SHA256 is
`7c2ea0ae6c4be4b5bccc2623d743b44f5908dc541c879101a6e557d4e027ba0e`.
The canonical sorted-key compact JSON array of its `frozen_files` entries has
SHA256 `942f5f1d4004ec225af22382f690eebfea20709c73c465b20c5c08a3638dc843`.
Neither digest is an internal self-hash field or authentication grant.

Model commit `760f1553` and native raw parser commit `5410e914` remain separate
next joins. No model/native source, migration, checkpoint wire, API, dashboard
route, worker start path or configuration was copied from those branches.
The recorded transport stays disconnected and requires its existing explicit
operator opt-in/configuration; importing it does not collect a live packet.
The Birdeye decoder remains an offline format contract, without a new provider
key, rights verification or acquisition request. Jupiter retention approval is
preserved, while authenticated acquisition/retention and native ancestry remain
their own implementation gates.

## Joined offline verification

One actual child ran the following complete selected modules under the existing
CPython3.12.14 environment. It passed **308 tests in 454.440 seconds, zero skips,
exit0**. No failed case was omitted or rewritten and no dependency was installed.

| Test module | Cases |
| --- | ---: |
| `tests.test_http_tls_inheritance` | 14 |
| `tests.test_command_http` | 15 |
| `tests.test_auth_security` | 16 |
| `tests.test_birdeye_candles` | 23 |
| `tests.test_feed_reliability` | 16 |
| `tests.test_quote_source_feed` | 28 |
| `tests.test_exact_provider_feeds` | 22 |
| `tests.test_swap_quote` | 16 |
| `tests.test_worker_admission_http` | 10 |
| `tests.test_provider_acquisition_v3` | 31 |
| `tests.test_provider_optional_metadata_v3` | 7 |
| `tests.test_prospective_source_v3` | 36 |
| `tests.test_provider_recorded_transport_v3` | 33 |
| `tests.test_source_admission_v3` | 40 |
| `tests.test_original_packet_reserve_v3` | 1 |

This is 160 legacy/TLS regressions, 107 acquisition/metadata/sampled-source/
transport cases and 41 independent A1/reserve cases. Separate discovery under
network denial confirmed the same count. It is not the complete ordinary
worker suite, a new golden-model result, native SQL acceptance or complete
seven-check hosted CI result. Its suite duration includes fixture construction
and repeated positive/adversarial history validation. The direct unittest
invocation had no additional whole-process wall-clock supervisor; existing
test-owned I/O/request/cleanup limits remain. No hard total-runtime,
single-admission five-second latency or continuous cadence claim follows.

The launch child environment was empty except PATH, fixed PYTHONPATH,
`PYTHON_DOTENV_DISABLED=1` and `PYTHONDONTWRITEBYTECODE=1`. Existing security
fixtures supply only explicitly fake settings/keys. Cold-import tests add
their own fake keylog/CA/proxy paths in their own children. Mocked requests and
the existing exclusively owned 127.0.0.1 port0 HTTP/TLS fixtures are the only
I/O exercised; there is no provider DNS/TCP, database or account operation.
No environment/credential file, shared profile, another agent's process or
runtime installation was changed. Existing fixture cleanup finished with the
successful child exit; no new server or collector was started.

The existing Starlette deprecation warning and asyncio slow-callback notices
appeared, including deliberately blocking transport refusal fixtures. They were
not suppressed or repaired by widening deadlines. An initial metadata-only
inspection queried irrelevant absent pandas; the inventory was corrected to
the dependencies actually used, without a code/test change or installation.
That metadata inspection is distinct from the successful 308-case test run.

Observed runtime: CPython3.12.14, OpenSSL3.5.8 (25 Aug2026), aiohttp3.14.3,
HTTPX0.28.1, httpcore1.0.9, anyio4.15.1, certifi2026.7.22,
cryptography50.0.1, NumPy2.5.3 and pydantic2.13.5. The CA bytes have the same
reviewed digest `9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f`.
Both requirements files are unchanged and their hashes are in the receipt.
Installed version/CA observations are not full installed-wheel, binary or
hosted-image attestation. Own fixture certificates authenticate only the fake
loopback endpoint, never Jupiter or a real Solana RPC provider.

## Authority and release limits

The unchanged policy hashes remain acquisition `912fd28c…`, prospective
source `3be1de57…`, recorded transport `a62184b9…` and A1 admission `2c48b614…`;
the receipt carries their full hashes. A1's exact nine authority fields remain
false: authenticated principal, calibrated clock, committed readback, hosted
authority, lease authority, live trading authority, native admission, provider
attestation and running authority. The other source/transport false-authority
boundaries are preserved in the exact frozen code and controlled assertions.

Shape/hash consistency of supplied raw bytes, clocks, registries, original
readback or availability does not authenticate a real recorder or database.
The reviewed native actor/catalog, complete journal/original-ID reconciliation,
clock/fence, deferred-commit receipt, archive/seal, reader-origin and model joins
remain required. The sampled-close profile still requires genuine prospective
history and measured gaps/latency/quota/resource/cost/reserve budgets before
hosting or paper activation. This integration does not revive synthetic old
data, mint a new original ID to retry an uncertain write, or authorize a swap.

Root and source peer reviews verified the exact 30-file joined candidate and
authorized its private scoped local commit. Any adoption/release must retain the actual old failures and
dated source evidence, require the new head's full ordinary/native/CI gates,
and verify the exact allowed hosted targets separately. No production/live
authority or complete audit claim is made. A reviewed code revert can remove
this disconnected source/TLS slice; no database or account rollback is needed
because neither was changed, and removing SEC06 restores its documented
inheritance limitation.
