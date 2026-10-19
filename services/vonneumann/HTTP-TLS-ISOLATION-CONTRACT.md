# HTTP TLS inheritance isolation — SEC06

This slice changes HTTP TLS configuration in five existing worker clients. It
does not activate a worker, call a provider, migrate a database, change an
endpoint or alter the original model, source policy or native SQL package. Its
review base is `360d4a2ea490eabf53bfa2709495f89b725a368e`.

## Confirmed conditional exposure

CPython 3.12.14's `create_default_context` consults `SSLKEYLOGFILE`; a nonempty
value can open a file during context construction and permit TLS session-secret
logging during a handshake. HTTPX 0.28.1's `verify=True, trust_env=False` still
calls that helper for its certifi trust context. `trust_env=False` alone therefore
does not close this inheritance path. These are source findings, not evidence
that the user's environment contained that variable or that a secret was logged.
[CPython 3.12.14 source](https://github.com/python/cpython/blob/v3.12.14/Lib/ssl.py),
[HTTPX 0.28.1 context source](https://github.com/encode/httpx/blob/0.28.1/httpx/_config.py).

Aiohttp 3.14.3 constructs default verified and unverified contexts at module
import. Supplying a secure connector afterward cannot undo a file opened by that
earlier import. The guard must run before the first aiohttp import in a new
supported worker process.
[Aiohttp 3.14.3 connector source](https://github.com/aio-libs/aiohttp/blob/v3.14.3/aiohttp/connector.py).

## Implemented boundary

`vonneumann.http_tls.require_no_keylog` rejects the **presence** of
`SSLKEYLOGFILE`, including an empty value. It checks only the variable name;
it does not read, print, remove or replace its value. The fixed refusal is
`unsupported_tls_keylog_environment`. The four aiohttp modules invoke this guard
before importing that dependency: `market.jupiter_feed`, `market.birdeye_candles`,
`market.birdeye_feed` and `server.auth`. Transitive `core.provider_acquisition`
and `server.app` cold imports are covered by the regression tests.

`verified_http_context` repeats the guard before creating a new context. It
constructs `SSLContext(PROTOCOL_TLS_CLIENT)` directly, sets `CERT_REQUIRED`,
hostname checking, a TLS 1.2 minimum and `keylog_filename=None`, and loads only
the reviewed certifi PEM bytes through `cadata`. It does not use
`create_default_context`, `load_default_certs`, ambient CA paths or a system-root
fallback for the owned context.

The locked certifi release is `2026.7.22`; its package reports `2026.07.22`.
Its PEM SHA256 is
`9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f`.
The helper reads at most 1 MiB plus one overflow byte and checks that digest
before creating the context. A missing, different, oversized or invalid bundle
refuses with a fixed diagnostic. Updating certifi requires an explicit review
of this pin and the focused tests. The verified bytes are loaded directly, so
there is no second CA-file read between verification and context loading.

Each owned aiohttp session receives `TCPConnector(ssl=verified_http_context())`
and retains `trust_env=False`. This explicitly adds that setting to the older
BirdeyeFeed as well. DashboardCommandHTTPTransport passes the same explicit
context to its AsyncHTTPTransport and AsyncClient, preserving its fixed
origin/schema, zero retries, absent proxy, redirect refusal, request deadlines,
response caps, ownership and cleanup behavior. No logging configuration or
environment file changes are part of this slice.

For configuration refusal during use, Auth maps only `HTTPTLSError` to its
existing fixed HTTP 503 unavailable response; the HTTP command constructor maps
only that error to `CommandHTTPError('tls_configuration_unavailable')`. Both
suppress the underlying diagnostic and stop before constructing a connector or
transport. The cold aiohttp import refusal remains `HTTPTLSError` so startup
stops before that dependency is imported. No request is dispatched or retried.

## Verification

The new `tests.test_http_tls_inheritance` module defines **14 focused tests**.
They passed as part of the final 160-case run below, using the locked Python
3.12.14 environment and an empty credential environment with dotenv disabled.
An independent reviewer reran all 14 focused tests against these final code
bytes: **14 passed in 1.742 seconds, zero skips**.
The tests check:

- Actual context properties and refusal before CA lookup/context construction;
  exact CA mismatch, missing/overflow/invalid material and sanitized errors.
- Cold imports of each guarded module and the two transitive entry paths with
  a task-owned fake key-log destination, fake CA paths and a fake proxy. Child
  environments remain unchanged and none of those paths is created. Tests use
  the current verified interpreter without `-I`, which would mask the CPython
  inheritance behavior being tested.
- Explicit connector injection for all four aiohttp clients and explicit
  verified HTTPX transport configuration with zero retries; fixed Auth/command
  configuration errors before transport construction without private diagnostics.
- Real OpenSSL handshakes against an exclusively owned kernel-assigned
  `127.0.0.1` listener: accepted local CA/hostname, refused wrong hostname,
  expired leaf and untrusted CA. Private test keys exist only in a temporary
  directory; the listener, socket and thread are closed before cleanup.

The combined new/existing scoped regression run passed **160 tests in 2.881
seconds, zero skips**: HTTP TLS inheritance, command HTTP, authentication,
Birdeye candles, feed reliability, quote source feed, exact provider feeds,
swap quote and worker HTTP admission. It exercised existing owned loopback
HTTP and mocked provider/Auth behavior; it made no provider or database calls.
An existing Starlette deprecation warning and asyncio slow-callback diagnostic
appeared. No package upgrade or timeout change was used to pass these checks.

## Limits and remaining gates

This is a supported cold-import/client configuration boundary, not an OS
sandbox. It cannot undo an aiohttp import performed earlier by an unrelated
caller, prevent a hostile process from rewriting Python objects or the runtime,
or atomically constrain another same-user process changing the environment.
Aiohttp may still initialize its own unused default contexts during a permitted
import; the application-owned connectors use the explicit pinned context.
The tests demonstrate no creation of the fake paths, not that a third-party
import never inspects an ambient CA configuration.

This slice does not establish privacy for custom logging handlers, LogRecord
factories, TLS interception, OpenSSL configuration/plugins, or a different
runtime/library build. Provider authentication, actual remote certificates,
hosted isolation and the closed worker's release gates remain separate. No
existing native receipt is relabeled as acceptance of this HTTP change.

Before a hosted release, run the required complete suite at the integrated
commit, verify the locked runtime/certifi trust bundle in the owned image, and
confirm the supported entrypoint reaches the guard before aiohttp. If an
unsupported key-log configuration is present, stop that worker child with the
fixed error; do not change a shared shell, account or another project's
environment. Rollback is a reviewed code revert of this slice; it restores the
documented conditional inheritance gap rather than fixing configuration.
