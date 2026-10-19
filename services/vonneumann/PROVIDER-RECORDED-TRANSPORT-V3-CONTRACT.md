# Original read-only Price/RPC transport — inert R3-02A slice

This disconnected module records one original Jupiter Price V3, mainnet genesis,
and exact referenced-block-time packet. It has no startup or worker wiring,
environment credential loader, UUID allocator, datastore, issuer authentication,
native admission, lease, SourceMark, history seal, trading action, retry or running
authority. Construction requires an explicit `read_only_opt_in=True`; that
parameter is a code gate, not authorization to contact a provider. All actual
provider requests, hosted activation and native writes remain closed for this
slice. Synthetic v2, existing provider v5 and their stored-state meanings are
unchanged.

## Endpoint and parser decisions

The official [Jupiter documentation index](https://developers.jup.ag/docs/llms.txt),
[Price V3 reference](https://developers.jup.ag/docs/api-reference/price), and
[versioned Price V3 OpenAPI YAML](https://developers.jup.ag/docs/openapi-spec/price/v3/price.yaml)
were checked on 2026-10-13. The exact YAML is 3,154 bytes, SHA-256
`bc798556d98db9f5f5586cbd4deadd3c0839e167c2fffe93f8df9308acc7e029`.
This was public documentation retrieval, not a market/key/account request.
The frozen transport reads `https://api.jup.ag/price/v3` with exactly the SOL mint
and the private Jupiter API key. It supplies the key only in that request's
`x-api-key` header. No key is sent to the RPC endpoint.

The separately provided private HTTPS RPC endpoint receives a fresh
[`getGenesisHash`](https://solana.com/docs/rpc/http/getgenesishash) request for
each packet and a [`getBlockTime`](https://solana.com/docs/rpc/http/getblocktime)
request for exactly the usable Price V3 block reference. The genesis must equal
mainnet's pinned genesis. RPC IDs, JSON-RPC version and exact slot are validated.
Null block reference or null block time refuses the packet. Block time is an
estimated block production time, not an exact trade execution timestamp.

The current acquisition parser policy is
`ga-provider-acquisition-parser-policy-research-v3-quota-v2-nullable-change-v1`,
digest `912fd28c718311f9b6f72cf0327a7c6b5f4ec7cc4033744d3306064ed869ac89`.
Nullable 24-hour change is ignored while original bytes remain intact; null block
is still unusable. The deliberate optional-metadata subset is documented in
`PROVIDER-METADATA-POLICY-2026-10-13.md`. No historical OHLCV, volume, executable
quote or backfill is manufactured. This is the prospective sampled-close profile
described in `JUPITER-PROSPECTIVE-SOURCE-V3-CONTRACT.md`.

The new transport policy descriptor is canonical immutable bytes. Its digest is
`a62184b94f88dbc248a6f3569e171a60e8a0a530addf8ed8aa943b10433f055e`.
It binds the current acquisition parser, exact HTTP libraries and CA bundle,
manual TLS construction, serialized original requests, integer clocks,
whole-packet deadline, logger isolation, credential-echo refusal and bounded
original retention. Prepared-packet bytes and result summaries bind this policy.
Old policies remain available only in their original immutable Git packages;
there is no archival policy dispatcher and no silent relabeling of old records.
Policy hashes express byte consistency. They do not authenticate the issuer,
endpoint configuration, runtime or provider.

## Public interface and original evidence

`PreparedPacket` contains an explicit `IssuerBinding`, three original raw-record
UUIDs, one original observation UUID, and two distinct bounded RPC IDs. The four
UUIDs must be distinct and are supplied before any I/O. The transport allocates
none. The binding includes scope, market/acquisition epochs, endpoint-binding
IDs and parser-policy hash. The opaque endpoint-binding IDs require a separately
authenticated mapping to the private endpoint/configuration; their lexical
validity is not proof of that mapping.

`ProviderRecordedTransport(key, rpc_url, read_only_opt_in=True, bounds=...)` owns
one event loop and at most one active original packet. Its production constructor
has no backend, context, trace, hook or caller request-extension parameter. Tests
patch private factories/constants only in their owned fixture process.

`await collect(prepared)` returns `PacketResult`. Each captured `Capsule` preserves
the original raw body, its hash, public canonical request/hash, original record
ID, binding, HTTP status, bounded whitelisted response metadata, and original
integer UTC/monotonic start and complete-body receipt times. Whitelisted quota
headers are diagnostic counters, including signed remaining capacity; they do
not alter an order or grant a rate-limit permission. A non-200 response is retained
when its body/metadata are safe, and the packet stops. No redirect is followed,
including to a similarly named endpoint. Null/malformed/wrong-network responses
retain captured original capsules and refuse the packet.

An incomplete attempted request produces only fixed-code diagnostic metadata:
its original ID, provider family, endpoint-binding ID, public request hash,
start time and, when known, receipt time/status. Unattempted reserved IDs remain
visible in `PreparedPacket`; they are not described as completed requests.
Private endpoint URLs, request keys, exception strings, response trace headers
and raw unsafe bodies are never printed by this interface. If raw response bytes
or whitelisted metadata contain an actual provided credential value, the
offending body is withheld and the diagnostic is explicitly incomplete. Bounded
strict decoded JSON keys/strings are inspected as well as literal bytes, including
ordinary Unicode/slash escapes. An unparseable, duplicate-key, excessively nested
or otherwise unsafe JSON body is withheld with an incomplete scan diagnostic.
The transport does not redact, normalize or re-encode that body and claim the
result is original evidence. This conservative check is not a general secret-classification system
or protection against arbitrary encoded/malicious in-process disclosure.

`completed=True` means this bounded transport packet captured and structurally
checked the three original responses. It does not prove source freshness under a
trusted current clock, datastore commit, causal availability, complete-history
inventory, an authenticated native receipt, usable trading price, or model/action
permission. `provider_authenticated`, `native_admission` and `running_authority`
are false. Ordinary TLS validation is a required transport property, not provider
signed attestation or a self-issued native proof.

## Timing, cleanup and original reconciliation

Clocks use `time.time_ns() // 1000` and `time.monotonic_ns() // 1000`. No floating
point timestamp conversion, receipt restamping or invented zero-uncertainty clock
bound occurs. Complete-body receipt is sampled before metadata normalization,
JSON parsing and cleanup. Integer precision does not establish UTC accuracy,
clock calibration or accepted acquisition-epoch ownership. A future native join
must supply those independent inputs and perform all current/source-age checks.

Price, fresh genesis and exact block-time requests are serialized under one
maximum five-second packet budget. Connect/read/write/pool phases have explicit
positive bounded timeouts and no retry. The whole async deadline also covers
body streaming and parsing; post-CPU integer monotonic guards reject synchronous
processing, including result-summary/retention bookkeeping, that crosses the
budget or reports an elapsed sample before the
packet's original start. They do not check every intermediate sample against
the last sample; the unchanged OS `monotonic_ns` implementation is trusted to
be monotonic. Float seconds are used
only to control library timeouts, never to construct artifact timestamps.
Cleanup owns a separate bounded waiter and a retained task. A slow cleanup cannot
make a late packet successful. An already captured original capsule and its
diagnostic pins remain retained when cleanup/deadline causes refusal.
The owner context spans result-summary/charge calculation and a final guard
checks the unchanged original packet start after that work. Late or failed
bookkeeping retains a closed failed original result and conservatively charges
the one MiB already reserved before I/O; it does not retry summary serialization,
rebase the start or generate fresh receipts/IDs. Synchronous work can be refused
after it finishes, not preempted by an async timeout.

Canceling the caller's collection waiter leaves the owned original packet alive
under its existing bound. A different prepared packet cannot replace it. Reusing
the identical original prepared bytes waits for or returns the retained original
result; it never refreshes the original body or times. A changed payload under
the same observation ID, or any reused original UUID, refuses. Canceled/late
cleanup retains the owner context and filters until the exact owned close
finishes. `close()` never broadly cancels another task or closes another transport;
it retains unresolved cleanup and returns a fixed refusal rather than claiming
completion. Unsupported logging/TLS runtime changes leave the module closed; it
does not disable verification or alter shared settings to force cleanup.

The in-memory result cache is finite: default eight MiB of charged encoded
evidence and 4,000 packets, with one MiB reserved before each new packet. Those
are engineering caps, not measured Python RSS or durable-retention guarantees.
Capacity refuses before another request and preserves existing original results.
There is no pruning, restart recovery or native write reconciliation. A future
recorder must retain the same original packet/IDs across an uncertain datastore
write, authenticate its original committed readback, and block fresh observation
allocation until that original is reconciled. Transport completion alone cannot
make a fresh ID safe after native uncertainty.

## TLS and process-local logging boundary

The implementation uses low-level HTTPX `AsyncHTTPTransport.handle_async_request`
with HTTPX 0.28.1 and httpcore 1.0.9. It does not construct `AsyncClient`, whose
installed INFO logger includes the full request URL. There are no cookies,
ambient proxy/netrc credentials, event hooks, foreign trace callbacks, caller
extensions or custom production backend. HTTP/1.1 is enabled, HTTP/2 disabled,
one connection is allowed, retries are zero and `trust_env=False`. Library behavior
was checked against installed sources and the official
[HTTPX transport](https://www.python-httpx.org/advanced/transports/),
[environment](https://www.python-httpx.org/environment_variables/) and
[TLS documentation](https://www.python-httpx.org/advanced/ssl/).

`trust_env=False` alone does not remove inherited key logging: Python's
[`create_default_context`](https://docs.python.org/3.12/library/ssl.html)
honors `SSLKEYLOGFILE`. The new code constructs
`SSLContext(PROTOCOL_TLS_CLIENT)` directly, requires `CERT_REQUIRED`, hostname
verification and TLS 1.2 or newer, and requires `keylog_filename is None` before
I/O and through cleanup. It never creates a default context and then disables
logging after a file may already have opened. It does not unset the user's
environment. The exact certifi 2026.7.22 public bundle digest is
`9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f`.
PEM bytes are read once with a bound, digest-verified, and loaded from those exact
bytes as `cadata`; there is no second file read or ambient CA fallback.

The reviewed logger inventory is `httpx`, `httpcore.connection`,
`httpcore.http11`, `httpcore.http2`, `httpcore.proxy`, and `httpcore.socks`.
An owned ContextVar filter is prepended to each exact leaf logger. It rejects
only this transport's owned-context records before existing filter callbacks can
inspect them; unrelated tasks and other owned transports retain their logging.
Existing filters keep their relative order. Cleanup removes only the owned
filter objects by identity, avoiding custom equality accidentally removing an
unrelated filter. There are no production changes to logger levels, handlers,
root configuration, record factory or another process's environment.

The default `logging.LogRecord` factory and ordinary Logger classes are required
before I/O and through cleanup. A record factory runs before logger filters, so
a custom factory is unsupported. Context ownership spans request execution,
body iteration, errors, cleanup tasks and shutdown. This is a trusted, pinned
runtime boundary; it is not a sandbox or race-proof defense against arbitrary
monkeypatching, debuggers, signal handlers or malicious code in the same process.
Guards before/after awaits cannot atomically prevent another same-process
component changing the factory/configuration during I/O; a frozen trusted runtime
is required. The module does not mutate shared factories to hide that limitation.
The future release must independently authenticate/freeze package/configuration,
CA/library/runtime manifests and recorder principal rather than infer authority
from this code's own hashes.

## Verification and remaining join

Focused transport acceptance currently covers 33 cases with zero skips. Twenty-nine
cases use fake endpoints with foreign networking denied; four use the actual
HTTPX/httpcore/OpenSSL stack with test-only routing to an owned ephemeral
127.0.0.1 TLS port. Provider DNS/TCP is refused by the fixture. The owned fixture
CA and leaf never authenticate Jupiter or a real RPC provider. Positive TLS
checks the original trio and exact request body/key scope; wrong CA, wrong
hostname and truncated HTTP body refuse without retry. An actual handshake
under inherited `SSLKEYLOGFILE` creates no keylog file. Fake tests cover pinned
CA/version refusal before I/O, original UUID/wire conflicts and replay,
metadata/body limits, credential echoes, network exceptions, deadlines,
elapsed-before-packet-start refusal, caller/cleanup cancellation, logging spies, unrelated tasks,
custom factory refusal, exact filter ownership and finite retention.
Slow result bookkeeping refuses transport success while retaining the exact
original trio and returning that same refused result on original-ID replay.
Thrown result bookkeeping preserves that original, closes fresh collection,
uses the conservative reserved charge and never retries the failed summary.
Old/future block times deliberately complete structurally valid transport packets
and are then refused by pure observation derivation, proving that transport
completion cannot substitute for source freshness/future eligibility.

Combined final acceptance on 2026-10-13: **107 cases passed, zero skips, 90.011 seconds**
under `PYTHON_DOTENV_DISABLED=1` and `PYTHONDONTWRITEBYTECODE=1`: 33 transport,
seven nullable-metadata, 31 acquisition and 36 prospective-source cases. All
existing tracked acquisition/source/parser files remain unchanged from the
reviewed metadata-policy commit. The synchronous-parser and slow-summary deadline
fixtures deliberately block for 0.1 second and produce the test loop's slow-task
notices; their assertions verify refusal after that work, not event-loop
preemption. The 33 focused transport cases separately passed with zero skips in
1.658 seconds.

The observed test runtime is Python 3.12.14, OpenSSL 3.5.8 (25 Aug 2026),
HTTPX 0.28.1, httpcore 1.0.9, anyio 4.15.1 and certifi 2026.7.22;
cryptography 50.0.1 creates only ephemeral fixture certificates.
No actual provider call, account quota verification, database migration/native
write, authenticated issuer/clock, real receipt availability, history collection,
hosting or live trading has been tested or enabled.

Next ordered work is the independently authenticated recorder/native source join:
reserve original identities and epochs; acquire under the accepted private
principal/runtime; derive under a real calibrated ClockBound; retain all raw
originals; reconcile unknown native writes under those same IDs; observe the
authenticated committed original readback and its availability upper bound;
freeze complete inventories; and prove append-only sampled history/model
transitions. Hosted cadence, source age, close offsets, late/gap fraction, raw
retention/RSS/CPU/quota and the approved pilot budget must be measured before
activating the prospective profile. The five-second seal margin and minute
sampling policy remain unmeasured activation gates. Nothing in this transport
reopens synthetic v2 or provider v5 source/trust meaning.
