# V18 repeated Renew position reserve

This candidate extends the accepted V16/V17 laboratory with one path from
Resume through twelve Renew originals. The last Renew commits at position
15 with fence revision 13. The following ordinary attempt at 16 reaches
the budget with the same well-formed shape and live hold. Reserved Stop
then commits at position 16 and advances the revision to 14.

## Independent position and capacity proof

The closed ledger at 15 adds twelve Renew increments of 11 retained rows,
12 logical writes, 24 logical keys and 7 dependencies to the prior
Install, Acquire and Resume vector. The remaining ordinary attempt would
add one position and the reserved Stop would require another.

| Budget dimension | Existing at 15 | Attempted Renew | Reserved Stop | Result | Cap |
| --- | ---: | ---: | ---: | ---: | ---: |
| Positions | 15 | 1 | 1 | 17 | 16 |
| Retained rows | 180 | 11 | 9 | 200 | 271 |
| Identity rows | 30 | 1 | 0 | 31 | 96 |
| Domain rows | 16 | 1 | 0 | 17 | 25 |
| Dependency rows | 98 | 7 | 7 | 112 | 112 |
| Logical writes | 189 | 12 | 10 | 211 | 512 |
| Logical keys | 378 | 24 | 20 | 422 | 1024 |
| Staged row touches | 204 | 13 | 11 | 228 | 1024 |
| Staged key touches | 423 | 27 | 23 | 473 | 2048 |

The test derives the prospective byte inequalities independently of
`_cost`. It adds the full wire caps for Command, Result, Receipt, Journal,
ScopeHead, Accounting and one fence fact, plus 4,096 bytes for each of the
12 logical rows. The latter covers closed row metadata, declared key arrays,
and the one identity wire. The largest metadata component in the prior
independent worksheet is the final original at 853 bytes with its closed
three key arrays around 224 bytes. Each other row uses at most one scope,
fixed UUIDs/digests and bounded decimal fields, and carries fewer metadata
fields. The identity wire also uses only fixed scope association fields,
UUID, closed role, Command digest and bounded position. This deliberately
loose ordinary logical upper bound is 206,848 bytes. Each additional pending
original is at most 151,552 bytes from Command and Result caps plus its
metadata/key allowance. At the attempt there are fifteen historical and
one prospective pending charges.

The test checks observed existing logical accounting plus 206,848 and the
76,533-byte logical Stop reserve against 4,194,304. It checks existing
logical accounting plus 206,848, sixteen times 151,552, and the 144,142-byte
staged Stop reserve against 8,388,608. It requires the exact budget refusal
and identical snapshots. These bounds cover the prospective encoded
charges without relying on a cost-calculator result as an oracle.

The final original Stop adds nine retained rows, ten logical writes and
twenty keys. Complete actual witness expectations are 189 retained rows,
199 logical writes and 398 keys, with 215 row and 446 key touches including
staging. The target's direct dependencies are the three fixed facts, Install
C, Resume C, latest Renew C and the latest fence fact. The getter reads back
45 ancestor Command/Result/Receipt pins and sixteen domain facts. It checks
the complete canonical scalar and final LF, then exact replay and unchanged
table snapshots. These are logical charges rather than physical storage
measurements.

## Exact root-only run

Verify the [candidate manifest](candidate-manifest.json) at SHA-256
`589dae6165a38db4375a8a3f5bc2ff167d05b57b30e1d28149921edca5dd00d7`.
The [forward patch](candidate-forward.patch) SHA-256 is
`820f2e6919472760dcfea6d558a52b780948ee11871ee017def192a5f4b5348c`.
Reconstruct all six accepted V17 postimages in an owned temporary directory
and apply the patch. Compare all six V18 postimage lengths and SHA-256 hashes
with the manifest. The verification already reproduced all six exact files.

The repeated reference composition is 930 tracked ordinary blobs from
PR113 commit `7ff9b886a2d19de5388b86a5c3985a8705567edc`, tree
`9d6c512e6ea6f9b036cf82f7cc67199cc57dc4ae`, plus six private postimages.
All destinations are absent from that Git tree. Pin every file in the 936-file
snapshot. Reverify a newer base separately before choosing it.

After independent review, reuse the accepted V17 owned runner policy. Pin
the exact one test ID in the manifest, the same CPython 3.12.14, explicit
local Unix Docker socket, cached immutable PostgreSQL 17.6 ARM64 image,
allowlisted child environment, network none and unchanged 240-second
outer limit. Verify exact snapshot bytes before and after and normal exact
owned cleanup. The new one-case result and any separately reviewed V16/V17
regression run against this changed SQL are distinct receipts. Preserve the
raw result and log on any refusal or timeout.
