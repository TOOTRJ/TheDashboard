# Independent native raw parser research contract

This is a parser-only offline experiment in a new private namespace. It performs
no provider I/O, acquisition, clock read, database admission, journal/identity
registration, receipt issuance, history seal, financial/model mutation or runtime
activation. Existing A1, acquisition, sampled-close, transport, v2/v5 and portable
native packages retain their bytes and semantics. The wider A2 actor/clock/
terminal-closure/control-journal/availability schemas remain separate gates.

The exact reviewed parser descriptor is 3,011 canonical UTF-8 JSON bytes, SHA-256
`e7fb225868e9401e5648487e9836d9c0aff817f2ba2cdd63a20b90b75aadb24e`,
recorded in `R3-03A2A-RAW-PARSER-EXPERIMENT-DESIGN.md`. Root, source and security
peers reviewed that descriptor before implementation. Actual SQL/source hashes
are externally recorded after acceptance; no source file embeds its own hash.

Comparison pins frozen A1 commit `45d2b7aabbb889f4ff628c02a1864e7206192a0d`,
policy `2c48b61440f7d61f9567fa295da1c9c98a4483c2c834ec7074412d261f085640`,
module `b821b469f50b6fe3554851d348822059a33facb5a77e6133290e1c3283fb9bc6`,
acquisition policy `912fd28c718311f9b6f72cf0327a7c6b5f4ec7cc4033744d3306064ed869ac89`
and sampled-close policy
`3be1de572d954859002546e5d525ddb0fbda71a5ca844368381a98395571aad1`.

The new SQL entry is
`vn_jupiter_raw_parser_research_v3.parse_original_trio(bytea[],bytea[])`.
It takes exactly three canonical public request bytes and three original raw
response bytes, ordered Price→genesis→exact-slot block time. Request cap is
4,096 bytes; responses are capped at 131,072/65,536/65,536. Arrays cannot hide
extra/null/nonstandard-indexed originals. No normalized price/candidate/age/
UUID/desired sequence or authority claim is accepted.

Output format is `ga-jupiter-source-raw-parser-projection-research-v3` with exactly
`format,parser_policy_sha256,source_profile,asset,mint,decimals,denomination,
valuation,genesis_hash,price_decimal,block_ref,estimated_source_second,originals,
authority`. Originals is exactly three ordered five-key objects with
`provider_family,request_sha256,request_bytes,response_sha256,response_bytes`.
All counters are canonical decimal strings, hashes lowercase hexadecimal,
output canonical compact UTF-8 JSON and at most 8,192 bytes. All nine authority
fields remain literal false. The result is neither an `AdmissionCandidate`,
`DerivedObservation`, `SourceMark` nor a native readback/capability.

The source is SOL/USD wrapped SOL, decimals 9, USD reference price from Price V3,
pinned mainnet genesis and literal integer `getBlockTime` for the Price block.
The returned second is estimated block production, never Jupiter publication
time, price finality or an executable quote. No OHLCV/volume/history is invented.

Native `json` preserves original number lexemes and duplicate entries before a
complete new private walker validates every decoded key/string/value. JSONB is
not an original type/uniqueness oracle. UTF-8, BOM/NUL/lone-surrogate, decoded
duplicate, container/depth/node and numeric lexeme limits are checked, including
unused values. Each private helper explicitly searches `pg_catalog,pg_temp`;
the public parser is a limited-installer-owned security definer with no data
tables and no PUBLIC/helper execution grant to the fixture reader. The installer
marker enables only the isolated fixture; it authenticates no production caller.

Integer token type is distinct from decimal/exponent, Boolean and string. Exact
Decimal-like normalization preserves field-specific sign rules and effective
tuple exponent/expanded-length limits, then the positive scale-18 price grid
and inclusive human price maximum `10**36` (scaled maximum `10**54`). There is no
float or rounding. Ignored `priceChange24h:null` and bounded signed numeric change
remain supported; invalid optional fields still refuse. Original bytes and their
hashes remain unchanged even when a value has another equivalent numeric spelling.

CreatedAt compatibility is independently implemented from pinned CPython 3.12.14
ISO parsing semantics, with full-body Unicode validation preceding it. Ordinary
PostgreSQL timestamp casts are not used. A partial successful parser cannot
close the source/native gate if a supported valid timestamp form still fails.
Primary references: [PostgreSQL 17 JSON types](https://www.postgresql.org/docs/17/datatype-json.html),
[JSON functions](https://www.postgresql.org/docs/17/functions-json.html), and
[pinned CPython 3.12.14 datetime implementation](https://github.com/python/cpython/blob/v3.12.14/Modules/_datetimemodule.c).

## Actual verification status

The final full focused actual SQL run passes 16 cases in 5.618 seconds, zero
skips, under pinned CPython 3.12.14 and an owned cached PostgreSQL 17.6 fixture.
The command used sanitized `env -i`, bytecode/dotenv disabled, explicit owned
cwd and only the isolated PostgreSQL opt-in. The fixture had no network, host
ports, host mounts or application secrets, one CPU, 512 MiB and owned tmpfs.
Exact image ID was
`sha256:965e2dfb5a23a0d6541b6106541e777b303656ebabd4e878746b189d550c0a66`.
The existing UUID-owned harness completed normal cleanup on class teardown;
no other container/process/credential was inspected or stopped.

The suite verifies private installation and helper denial, exact closed output,
original body/request byte hashes, canonical requests, token types/signs/decimal
grid/ranges, nullable ignored change, full unused Unicode/number checking,
decoded duplicate keys, structural budgets, fixed family caps and source/RPC
identity. Timestamp comparison checks 148 independently evaluated pinned-CPython
date/time/separator samples and three full original-trio timestamp positives.
That is finite compatibility evidence, not exhaustive proof over every possible
64-character string. Any additional supported valid mismatch remains a blocker
to complete parser acceptance and must be repaired without policy narrowing.

Selected exact-body-cap observations (semantically valid replies padded with
original JSON whitespace) were:

| Original body | Bytes | Client SQL elapsed seconds | Projection bytes |
| --- | --- | --- | --- |
| Price | 131,072 | 0.061002125 | 1,538 |
| Genesis RPC | 65,536 | 0.049717250 | 1,538 |
| Block-time RPC | 65,536 | 0.051734708 | 1,538 |

These include the local Docker/psql call and parse, and are selected byte-cap
observations. They do not bound worst-case nested traversal, CPU/RSS tails,
production latency or admission headroom. An earlier minimal/full/whitespace
single-case run passed in 0.952 seconds, followed by the first full16 run in
5.503 seconds. Security review then replaced an implicitly overloaded `power`
call used only for timestamp fractional padding with an explicit integer lookup.
The final full16 run above proves the corrected source; earlier observations are
historical and do not establish this newer source binding. No price/grid/parser
policy or clock allowance changed.
No five-second admission, calibrated clock, genuine native warmup, provider TLS,
production CPU/RSS, Railway cost or profitability claim follows from either run.

External implementation binding for this observed run:

- SQL SHA-256: `1bcfa71e652f5c462e61bb891828d0d756e70d60a0141a1d203530e17f5e3a94`.
- Test SHA-256: `da238eecfae894350bb9c7017fded1b8d0f36320d86b2534372468cce8c0e85e`.
  These are the precise implementation/test bytes observed, independent of this
  documentation; parser-only implementation and contract review is complete.

Root, source-owner and security-peer implementation/contract reviews are complete
within this parser-only laboratory scope. The finite timestamp examples and
selected byte-cap observations retain their limits above. A reviewed local
source commit does not authorize remote installation or provide an operational
capability.

The native admission experiment remains dependent on independently authenticated
principal/package/epoch/ID registries, real clock/guard policy, exact original
reconciliation, full control/closure journal mapping, trusted original reader
availability, complete immutable seals and the full source/model/native join.
