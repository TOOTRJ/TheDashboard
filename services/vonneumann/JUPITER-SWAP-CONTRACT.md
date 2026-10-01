# Jupiter quote-only Swap V2 contract

Reviewed and implemented 2026-09-30 as DATA-03A. The current official
[Order & Execute documentation](https://developers.jup.ag/docs/swap/order-and-execute)
and [Order reference](https://developers.jup.ag/docs/api-reference/swap/order) take
precedence over the pinned migration skill's older examples.

## Deliberately bounded adapter

The unused `JupiterFeed.get_swap_quote` helper now requests
`https://api.jup.ag/swap/v2/order` without `taker`. Jupiter documents that this
returns a quote with `transaction: null`. The helper has no wallet, payer,
signature, execute, broadcast or retry API. It is not connected to the research
fill engine and does not change Price V3 ingestion or create an execution path.

Inputs are two different canonical base58 encodings of 32-byte public keys and a
positive uint64 **integer in input-token atomic units**. The adapter does not
convert floating-point human amounts or infer token decimals/security. Optional
slippage is an integer from 0 to 10,000 basis points. Its default is omitted to
retain Jupiter's managed selection; an explicit value, including zero, is passed
as requested. Optional request parameters may affect routing. Mint validation is
syntactic, not a token allowlist or token-extension audit.

The existing private API key is supplied through the request header. Current
[portal quotas](https://developers.jup.ag/docs/portal/rate-limits) are shared at
organization scope; installing another key does not create more capacity.
No provider request was needed to implement or test this adapter.

## Validated result and failure behavior

The response must agree with the requested mints, ExactIn mode, input amount and
any explicit slippage. It must have `transaction: null`, no taker, a recognized
router/mode, canonical bounded atomic amount strings, a positive expected output
and a minimum output between zero and expected output. Provider error fields,
duplicate JSON keys, nonfinite numbers, wrong schemas and contradictions fail.
New upstream routing values require contract review before acceptance.

An immutable `SwapQuote` retains indicative amounts, slippage, router/mode, local
UTC/monotonic receipt times and a SHA-256 response fingerprint. It discards raw
response content, request IDs and transaction-related fields. Local receipt time
is not source freshness or finality. Route amounts and minimum-output constraints
are not fills, wallet balances, dollar prices or realized costs. A fingerprint
alone is not a replay dataset: bounded acquisition must separately persist
authorized raw evidence and request metadata before any empirical experiment.

The entire operation has a five-second deadline and a 256 KiB decompressed body
limit. Redirects are forbidden. It makes one transport attempt: a request-local
middleware guard also blocks aiohttp's automatic reconnect retry for GET, without
changing other requests on the shared session. Errors expose only stable local
codes for invalid requests/responses, authorization, throttling, redirects,
rejection, timeout or provider unavailability. Provider bodies and credentials
are not included in errors. Cancellation propagates normally.

## Validation and remaining gates

Offline tests cover valid amounts/metadata, canonical mints, exact integer
boundaries, schema and pair/amount contradictions, transaction/taker rejection,
body limits, redirects, deadlines, safe errors, cancellation and the actual
aiohttp reconnect loop with a mocked connector. They make no network requests.

DATA-03 remains open for broader execution/accounting integration: distinguish
`totalInputAmount` / `totalOutputAmount` wallet flows from route amounts, validate
fees/tips/rent/token extensions, settle USD versus USDC valuation, and reconcile
uncertain transaction results before any future authorized retry. FILL-01B must
calibrate execution against observations. DB-02/DB-03 must provide durable
idempotency and recovery. No signing or live trading is authorized by this
quote-only migration. See [tooling limitations](../../JUPITER-TOOLING.md).
