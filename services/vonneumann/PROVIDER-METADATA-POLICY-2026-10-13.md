# Current Price V3 nullable metadata — explicit research parser policy

The official [complete Jupiter index](https://developers.jup.ag/docs/llms.txt)
and [Price reference](https://developers.jup.ag/docs/api-reference/price) were
reviewed 2026-10-13. Unlike the earlier browser-only review, the exact
[versioned Price V3 YAML](https://developers.jup.ag/docs/openapi-spec/price/v3/price.yaml)
was successfully retrieved: **3,154 bytes**, SHA-256
`bc798556d98db9f5f5586cbd4deadd3c0839e167c2fffe93f8df9308acc7e029`.
This is public documentation retrieval, not a market/provider request or
verification of this account's endpoint, key, quota or actual response.

The schema names six required response fields, including token creation time,
liquidity and 24-hour change, in addition to USD price, block reference and mint
decimals. It explicitly permits a null block reference and null 24-hour change.
The current research profile requires a usable non-null block reference to
resolve source time; null remains a safe refusal, not zero or receipt-time
substitution. The 24-hour change is nonessential metadata for the two-EMA source.
Its documented null value must not reject an otherwise usable observation.

The new explicit parser policy is
`ga-provider-acquisition-parser-policy-research-v3-quota-v2-nullable-change-v1`.
The policy descriptor names nullable change handling and its digest changes.
Price parsing accepts absent, null, integer or exact Decimal change metadata;
boolean, string, array and object values still refuse. Preserve original raw
bytes/hash and ignore that metadata in price/model calculations. Price, decimals,
source block/genesis/RPC identity, all original clock/age bounds, quota diagnostic
types, numerical grids, record identities and false authority remain unchanged.
The profile's existing optional metadata subset is deliberate; accepting absent
nonessential fields does not claim complete OpenAPI conformance.

The prospective source policy now explicitly includes the actual acquisition
parser-policy digest. Its own hash therefore changes when that dependency changes.
Old research capsule/mark policy hashes are unsupported by this new reader;
they are not stripped, relabeled, rewritten or interpreted as current evidence.
The previous immutable decoder/package remains available at the prior Git commit
for an explicitly version-bound archival reader. No native/archive reader dispatch
or data migration is implemented here. Synthetic v2 and provider-v5 source,
model, SQL and existing immutable states are untouched.

Previous acquisition policy:
`6aee49826901fcb3730133e8611e4b9879d7717ac0d043565fca9a461dcc9244`.
Previous prospective source policy:
`70a052bed268a16eb4506724457b142df0739fc598bc8ebb47bf054a87ddd4a5`.
New acquisition policy:
`912fd28c718311f9b6f72cf0327a7c6b5f4ec7cc4033744d3306064ed869ac89`.
New prospective source policy:
`3be1de572d954859002546e5d525ddb0fbda71a5ca844368381a98395571aad1`.
Tests preserve literal null-metadata bodies, verify unchanged essential price
values, reject null block and malformed metadata, refuse previous policy bindings,
and prove that the new source descriptor binds its parser dependency. They use
explicit synthetic original-record fixtures under network denial. No real data,
transport, authentication, native admission, source sequence, lease or runtime
authority is acquired.

Focused verification: **74 cases, zero skips, 51.869 seconds** under isolated
Python 3.12.14 with `PYTHON_DOTENV_DISABLED=1` and network denial: seven new nullable
metadata cases, 31 acquisition cases and 36 prospective source cases. The existing
acquisition test's exact current-policy-name assertion was updated to the new
explicit version; its old-policy refusal remains unchanged. The earlier 67-case
source acceptance in its contract describes the previous source-policy pin.
