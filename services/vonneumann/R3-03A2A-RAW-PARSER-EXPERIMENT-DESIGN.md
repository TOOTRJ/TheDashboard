# R3-03A2A independent native raw-parser experiment design

Status: proposal only, 2026-10-13. This is the first independently reviewable A2
slice. No implementation or fixture has been run. Root may authorize it after
source/security review even while the wider native principal, terminal-closure,
control-journal and availability schemas remain open. It confers no admission,
recorder authentication, clock, registry, seal, engine or runtime authority.

The experiment installs new private functions only in an owned, isolated
PostgreSQL 17.6 fixture. It does not edit or call a v2/v5/portable admission
package, create production roles, install a migration, acquire provider data,
read environment/credentials or change shared tools/processes. Frozen A1 and
acquisition/source/transport policies retain their meaning and false flags.

Freeze comparison against reviewed A1 commit
`45d2b7aabbb889f4ff628c02a1864e7206192a0d`, descriptor digest
`2c48b61440f7d61f9567fa295da1c9c98a4483c2c834ec7074412d261f085640`
and module SHA-256
`b821b469f50b6fe3554851d348822059a33facb5a77e6133290e1c3283fb9bc6`.
The dependency pins and exact policy/contract byte hashes are recorded in
`R3-03A2-NATIVE-EXPERIMENT-PLAN.md`. The independently implemented native parser
must get its own reviewed descriptor/source digest; equality to A1's value
semantics is not a claim of identical code or native authority.

## Proposed files and interface

| New file | Responsibility |
| --- | --- |
| `db-contract/research/jupiter_raw_parser_v3.sql` | New `vn_jupiter_raw_parser_research_v3` private scalar/UTF-8/JSON/number/request/trio helpers and narrowly callable experiment entry. No data tables, sequences, actors or clock functions. |
| `tests/postgres/test_jupiter_raw_parser_v3.py` | Owned cached PostgreSQL fixture, direct actual SQL positives/negatives and differential checks against frozen A1 raw semantics. Synthetic public bytes only. |
| `JUPITER-RAW-PARSER-V3-CONTRACT.md` | Accepted precise grammar, final source/policy hashes, actual case receipt and unimplemented scalar/authority limits. |

Use the existing owned fixture/installer lifecycle after reading its current
instructions; avoid a new shared environment or second heavyweight driver
container. Whether a small dedicated fixture helper is needed is decided only
after inspecting the existing helper, not by broadening its source copy or
privileges. The new SQL installer has a clearly named offline opt-in context and
UTF-8/standard-string requirements, with no grant to PUBLIC. Every new helper
sets `search_path=pg_catalog,pg_temp`; catalog/application names are explicit.
Caller settings only enable an isolated test installation, never authenticate
production or a provider.

Proposed entry `parse_original_trio(public_request_wires bytea[], raw_bodies
bytea[])` receives exactly three original public request bodies and exactly
three original response bodies in Price→genesis→block-time order. Each request
is bounded to 4,096 bytes; response caps are 131,072/65,536/65,536 bytes. It
accepts no normalized price, supplied candidate, age, native sequence, ownership,
desired acceptance time or authentication claim. Private lower-level helpers
have fixed internal budgets; callers cannot disable validation or raise limits.

The output is a separately frozen research parser projection, proposed
`ga-jupiter-source-raw-parser-projection-research-v3`, with explicit parser policy
and implementation contract pins; source profile/network/mint/decimals/valuation;
canonical reference price, block and estimated source second; ordered original
request/body SHA-256 and byte counts; and all nine A1 authority fields literally
false. It returns no `AdmissionCandidate`, `DerivedObservation`, `SourceMark`,
receipt, freshness or native-ID claim. This is a value/byte association result,
not a capability. Exact output schema/hashing must receive root review before
code. Retained original inputs remain the fixture's byte oracle; hashes alone
are never input replacements.

Raw public requests use the current canonical acquisition request format with
exact fields `format,method,endpoint,chain,parameters,body_wire`. Price requires
GET `https://api.jup.ag/price/v3`, exact wrapped-SOL ID and no body; RPC requires
POST `operator-bound-solana-rpc`, empty public parameters and exact canonical
JSON-RPC body. Do not accept a private RPC URL, authentication data or headers.
Genesis and block-time RPC IDs are distinct positive integer tokens through
`2**31-1`; block-time params contain precisely the Price reply's block.

## Native JSON option to prove, not assume

Use PostgreSQL `json`, not `jsonb`, as a lossless structural representation only
after byte/UTF-8/depth prechecks. Native `json_each` and `json_array_elements`
can expose duplicate object entries and preserve numeric-token spellings in
their JSON values. A new complete walker validates every node and every decoded
key/string before any normalized use. It detects decoded duplicate keys even
when their raw escape spellings differ. JSONB may later be a local validated
view, never the source of original numeric type or uniqueness.

This option must be demonstrated on the actual pinned PostgreSQL binary. An
early PG cast/refusal is acceptable for malformed input, provided it is mapped
to a fixed safe error and never accepted as a normalized valid result. Success
must match the frozen supported grammar; loss of token/string/duplicate evidence
or unintended refusal of a supported valid input remains a parser gap.

Before casting, require nonempty original `bytea` within the fixed family cap,
strict UTF-8 and no BOM. Scan braces/brackets while honoring quoted/escaped
strings to refuse nesting beyond 32 before native parser recursion. Then fully
traverse with explicit depth, visits and aggregate counters: at most 1,024
members per object, 5,000 elements per array and 200,000 visits including decoded
object keys as in the Python reference. Validate unused optional field values
too. Check NUL and unpaired surrogate escapes/decoded strings; a valid paired
supplementary scalar must survive and duplicate detection must use decoded
Unicode text without Unicode normalization or locale/collation equivalence.
Native parser behavior alone is not the proof.

Numeric tokens are at most 128 bytes, with at most 80 significand digits and
exponent −80…80, with literal `-0` refused. Bound lexical exponent/coefficient
before calling PostgreSQL numeric operations. Preserve integer-token versus
decimal/exponent-token versus Boolean/string/null. `1`, `1.0`, `1e0`, `true` and
`"1"` cannot be conflated in block/RPC/source integer fields. Negative/fractional
tokens in unused `priceChange24h` are allowed by the generic JSON number grammar;
do not accidentally apply positive-price rules to every numeric token.

No binary64 intermediate, locale-dependent digit regex, numeric rounding or
ambient Decimal context is used. Convert Decimal-like lexemes by bounded exact
coefficient/exponent arithmetic; preserve sign long enough to apply each field's
correct negative-zero policy. Match `decimal_text` generic coefficient/exponent/
expanded-length restrictions and then the price's stricter scale-18 grid,
positive value and `10**36` economic range. A too-small/too-large/off-grid price
refuses rather than rounds. All derived counters use canonical decimal strings.

Public request outer canonical bytes require exact UTF-8 JSON key sorting and
escaping equivalent to the current acquisition serializer, with no JSON
numeric tokens in the outer envelope. The nested RPC `body_wire` independently
uses numeric JSON. Do not hash `jsonb::text`, whose order/spacing differs. Test
the serializer independently with strings/escaping before using generated bytes
as an original request hash.

Reference boundary research supplied by root:
[PostgreSQL 17 JSON types](https://www.postgresql.org/docs/17/datatype-json.html)
distinguishes JSON text/duplicate retention from JSONB normalization and warns
that JSON Unicode escape processing may fail when values are decoded;
[JSON processing functions](https://www.postgresql.org/docs/17/functions-json.html)
describes the traversal primitives. These support the investigation, not an
assumption of exact Python grammar parity. Generated key order follows Python
Unicode codepoint order with UTF-8 `ensure_ascii=False`; review/test any native
sort/escaping strategy without relying on database locale equivalence.

## Exact source-specific scalar rules

Price top-level object has only the pinned wrapped-SOL mint. Its object requires
`usdPrice,blockId,decimals`; optional fields are only
`createdAt,liquidity,priceChange24h`. Price is an exact positive JSON number on
the canonical 18-place grid. Block is an integer token within `0…2**64-1`;
decimals is literal integer 9. RPC replies have exactly `jsonrpc,id,result`,
JSON-RPC `2.0`, matching original request ID, pinned mainnet genesis string or
integer block time within `0…10,000,000,000`. Null/error/wrong-slot/network/mint/
ID or additional RPC fields refuse. No block finality or published-price time
is inferred.

Optional liquidity uses the reference's nonnegative generic exact decimal
normalization, including its signed-Decimal refusal. `priceChange24h:null` is
valid and ignored, while original raw bytes remain unchanged; non-null change
must have genuine JSON numeric type and generic grammar. Optional metadata does
not authorize a source value, but malformed metadata still refuses where A1
currently checks it.

`createdAt` is the main scalar feasibility gate. A1 currently accepts a nonempty
string of at most 64 characters when pinned CPython 3.12.14
`datetime.fromisoformat(stamp.replace('Z','+00:00'))` parses an aware UTC value.
PostgreSQL `timestamptz` accepts a different language and session/calendar forms;
a blind cast is insufficient. Before declaring full parser coverage, enumerate
and port the supported CPython calendar/basic/week-date, time separator,
fraction and zero-offset rules, with exact invalid-day/time and Unicode tests.
An approved forward narrower provider timestamp grammar would require an
explicit separately reviewed policy change; it must not silently reinterpret
current A1 originals. If this parity cannot be demonstrated, label the first
parser fixture partial and keep complete raw-source/native admission closed.
Do not change the existing A1/source/parser files to make the test pass.

The [Python 3.12 datetime documentation](https://docs.python.org/3.12/library/datetime.html#datetime.datetime.fromisoformat)
describes the broad ISO parser, but the current documentation patch version is
not a substitute for pinned CPython 3.12.14 source and actual compatibility
fixtures. Preserve that version distinction in the final evidence.

## Bounded actual test plan

Ordinary parser tests have no source-clock race. Stage whole fixture snapshots
and inputs before executing SQL, with one bounded case per adversarial original,
and compare exact bytes/pins/results against the independent frozen Python raw
reference. Root coordinates a single owned cached PG image, no pull/tag/prune,
network none, no application env/SSL/provider token. Test only UUID-owned schema/
roles/container resources and clean exactly those; no other process is stopped.

| Test group | Meaningful evidence |
| --- | --- |
| Minimal/full valid trio | Exact price/uint64 block/source seconds, request and body pins; optional null-change, fractional/exponent price, maximum representable grid and valid UTC metadata. No new source header or age claim. |
| Raw JSON/Unicode | Literal and escaped duplicate keys at every depth, optional-unused nested duplicate, valid supplementary pair, lone high/low surrogate, NUL/BOM/invalid UTF-8, escaped quote/backslash depth scanning, trailing input/invalid JSON. |
| Type/number | Boolean/int/decimal/exponent/string substitutions; negative/zero/off-grid/oversized prices; integer bounds; literal negative zero versus permitted generic signed decimals; 128/129 token and 80/81 coefficient/exponent boundaries before numeric arithmetic. |
| Source/request | Wrong mint/network/genesis, null/wrong block/time, wrong reply/request/RPC ID/slot/method, private endpoint/unknown outer fields, canonical byte mismatch, duplicate request fields, two equal RPC IDs. |
| Structural/byte limits | Below/equal/above each family byte cap, depths 32/33, member 1,024/1,025, array 5,000/5,001 and controlled visit budget. Semantically valid unused metadata cases remain distinct from generic walker tests. |
| Optional timestamp parity | Explicit frozen CPython-derived valid/invalid fixtures; reject PG-only aliases, invalid calendar/time, naive/non-UTC offsets, unsupported scalar type. No change to upstream grammar without review. |
| Error/private package | Fixed safe error without body/private URL/exception dump; no dynamic SQL/callback; benign temp sentinel ignored; no accidental public execute/table/clock/provider operation. Source hash proves old package files unchanged. |

Do not batch every theoretical maximum together: the bounds' product is not a
memory budget. Measure observed SQL parse/traversal time, output bytes and owned
fixture resource envelope on separate selected maximum cases. Record actual
PostgreSQL/runtime/source/policy pins and case count/zero skips. This is not an
SLA, five-second admission, 915-minute inventory, production CPU/RSS or monthly
cost proof. Stop and report incomplete parity/performance instead of widening
limits, skipping a required case or normalizing an unsupported original.

After native parser review, the unresolved A2 principal/catalog/epoch/closure/
complete-journal/availability schema must freeze independently. Only then can
the parser become a component of a new native admission experiment; parser
success never supplies those capabilities by itself.

## Exact projection and semantic descriptor proposed for freeze

The closed descriptor below fixes the projection requested by root. It is
canonical UTF-8 JSON with sorted codepoint keys, no whitespace and literal
counters as strings. All nine output authority values are false. The output
is capped at 8,192 UTF-8 bytes; this is an output envelope cap, not an input
capacity or memory claim. SHA-256 of the exact one-line JSON below is
`e7fb225868e9401e5648487e9836d9c0aff817f2ba2cdd63a20b90b75aadb24e`. The SQL implementation and external contract
must agree on these semantics; its actual source hashes remain external.

```json
{"bounds":{"array_items":"5000","block_ref_max":"18446744073709551615","coefficient_digits":"80","created_at_characters":"64","depth":"32","estimated_source_second_max":"10000000000","exponent_max":"80","exponent_min":"-80","number_token_bytes":"128","object_members":"1024","price_body_bytes":"131072","price_max":"1000000000000000000000000000000000000","price_scale":"18","projection_bytes":"8192","request_bytes":"4096","rpc_body_bytes":"65536","rpc_id_max":"2147483647","visited_nodes":"200000"},"dependencies":{"a1":"2c48b61440f7d61f9567fa295da1c9c98a4483c2c834ec7074412d261f085640","acquisition":"912fd28c718311f9b6f72cf0327a7c6b5f4ec7cc4033744d3306064ed869ac89","sampled_close":"3be1de572d954859002546e5d525ddb0fbda71a5ca844368381a98395571aad1"},"fields":{"authority":["authenticated_principal","calibrated_clock","committed_readback","hosted_authority","lease_authority","live_trading_authority","native_admission","provider_attested","running_authority"],"original":["provider_family","request_sha256","request_bytes","response_sha256","response_bytes"],"projection":["format","parser_policy_sha256","source_profile","asset","mint","decimals","denomination","valuation","genesis_hash","price_decimal","block_ref","estimated_source_second","originals","authority"]},"format":"ga-jupiter-source-raw-parser-policy-research-v3-v1","identity":{"asset":"SOL/USD","decimals":"9","denomination":"USD","genesis_hash":"5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d","mint":"So11111111111111111111111111111111111111112","source_profile":"jupiter-price-v3-prospective-minute-sampled-close-v1","valuation":"reference_mark"},"projection_format":"ga-jupiter-source-raw-parser-projection-research-v3","rules":{"authority":"exact-nine-literal-false-no-age-clock-uuid-auth-head-receipt-eligibility-native-runtime-claim","created_at":"CPython-3.12.14-datetime.fromisoformat-replace-all-Z-with-plus00colon00-aware-zero-utcoffset","implementation_binding":"external-source-bound-contract-not-self-embedded-source-hash","input":"exact-three-original-public-request-bytes-and-three-raw-body-bytes-ordered-price-genesis-blocktime","json":"strict-utf8-no-bom-nul-lone-surrogate-decoded-duplicate-keys-full-unused-field-validation","negative_zero":"literal-minus-zero-refused-generically-signed-decimal-refused-for-price-liquidity-allowed-for-ignored-change","numeric":"original-integer-token-vs-decimal-exponent-vs-bool-no-coercion-bound-before-exact-arithmetic","output":"closed-fields-all-counters-canonical-decimal-strings-all-sha256-lowercase-hex-exact-three-ordered-original-pins","price":"positive-exact-decimal_text-then-canonical-integer-scale18-economic-grid-no-rounding","requests":"canonical-acquisition-public-request-bytes-exact-field-method-endpoint-chain-parameters-body-identity-distinct-positive-rpc-ids","rpc":"exact-jsonrpc2.0-id-result-genesis-and-literal-integer-exact-slot-blocktime","serialization":"Python-codepoint-key-order-utf8-ensure_ascii_false-compact-json-exact-escaping-no-locale-normalization"}}
```
