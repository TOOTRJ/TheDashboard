# Worker TLS and prospective-source adoption acceptance — 2026-10-17

This receipt supports two ordered, scoped code adoptions after the accepted API
foundation: first the eight TLS files, then the 33 new source/model/parser
files. It records local offline and owned parser evidence. Final acceptance of
the resulting combined source through all seven required CI jobs, followed by
the exact production release checks, remains pending until root records those
facts. This document grants no worker activation or trading authority.

## Source lineage and scope

The local validation base was exactly
`2bf1485f3603fda0e162c7cc91947d3738dcd54f`. Its tracked-files-only Git archive
contained 829 regular files, with archive SHA256
`71feb791f34f927b4d053b7db15fbb897d95dfe979ae2b238f7ccfe58a4bbc15`.
No uncommitted migration, credentials, environment file, `ssl` directory,
symlink, or `.git` directory entered either snapshot. Source examples remained
ordinary tracked examples. The API foundation is accepted and merged as
`89c7979d278ba7d14c9157248eb5a152fc00a06b`, with the identical tested tree.
The ordered local adoption commits are TLS
`eae6f3ebe6466ec0e45d5f87dbef0d5e22ff8dd7`, then source/model/parser
`65f9236ae058740f40618a10b71ab48f3c0d8fec`. Final-head CI and release
identities must still be recorded; these local commits are not release proof.

The first adoption contains exactly the eight SEC-06 files from
`b1ab59f4e6d5ae9a134a21235ba9a7f4343332fd`. Every overlaid byte also matches
the corresponding file in `028d39c840d718f9abd918a7625e810f2aa476a3`.
Before overlay, all five modified existing files matched the reviewed TLS
patch's parent. Three additional files brought the snapshot to 832 files.
The changes add the isolated HTTP TLS helper, its regression module and
contract, and apply the helper to command HTTP, authentication, Jupiter feed,
Birdeye feed, and Birdeye candle clients. They refuse inherited TLS key logging
and construct verification using the reviewed certifi bundle.

The second adoption adds only 22 previously absent non-TLS paths from
`028d39c840d718f9abd918a7625e810f2aa476a3`, followed by 11 previously absent
paths from `7cdecab83bda85c0f53b1200204bb3df2a9df30e`. No existing snapshot
file is replaced. The latter commit preserves the four model files originally
frozen at `760f1553c9cc47fef6d7aa2a0410607c83bc7197` and five parser files
originally frozen at `5410e914d16f0ec906a471007e5fe8a345c8f012`, plus its
two dated adoption documents. Historical contracts and receipts remain unchanged.
The complete prospective snapshot contains 865 regular files.

The exact path, source-commit and file-hash inventories are retained privately:

| Artifact | SHA256 |
| --- | --- |
| TLS `snapshot-manifest.json` | `a746e9acaab9b61b7c05ff282a8e02b5c1b84c4118e28e91b596a843a6bfc0a7` |
| TLS `full-offline-summary.json` | `0be6588d42c8f6b8e9a42ea6565680583413dbc9e682922616c95ef2fd1bd757` |
| 865-file `snapshot-manifest.json` | `0ffd968fb51a672a0c2f130c55ebd5131e5f51d59820335122aa2b2abebbd80d` |
| 865-file `full-offline-summary.json` | `370d83e29219ff55b5a37a6812ce9fe60e6e84da40542a476c504829becc82f7` |

The respective private archive directories are
`dashboard-sec06-offline-20261017-_4m13nag` and
`dashboard-source-model-offline-20261017-wf5tyo_p`. These hashes identify
retained evidence; they do not imply that private artifacts are repository
files or independently authenticate a provider or runtime.

## Actual local verification

All runs used the existing pinned CPython 3.12.14 environment. Actual package
metadata recorded certifi 2026.7.22, cryptography 50.0.1, httpx 0.28.1,
httpcore 1.0.9, and aiohttp 3.14.3. Requirements and the reviewed runner were
unchanged. The runner SHA256 remained
`be75136c0592a7a2da26707a3d7e4c1e7e740dda639776f6759d23ed64357af1`.
Child environments disabled dotenv and bytecode, supplied no credentials or
provider configuration, and omitted PostgreSQL/Docker opt-in. Test fixtures
used mocked transport and owned loopback connections where required.

The focused TLS/auth/feed/command regression run passed **160 tests, zero
skips**, in 2.889 seconds; its controller took 3.297 seconds. Both full ordinary
shards subsequently ran once, without repair, retry, or changed bounds:

| Snapshot and shard | Actually executed | Reported | Approved SQL skip entries | Test seconds | Wall seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| TLS, 1 | 807 | 981 | 182 | 400.894 | 402.742 |
| TLS, 2 | 1,094 | 1,407 | 320 | 297.294 | 299.039 |
| Source/model/parser, 1 | 808 | 982 | 182 | 402.138 | 403.684 |
| Source/model/parser, 2 | 1,261 | 1,590 | 336 | 699.879 | 701.679 |

The TLS snapshot therefore executed **1,901 tests**. The 865-file snapshot
executed **2,069**, reported **2,572**, and recorded **518 approved PostgreSQL
opt-in skip entries**, with **zero unexpected skips**. Class-setup skips have
different counting semantics; the runner's actual-execution count is the
appropriate evidence. Every skip remained unexecuted in these ordinary runs.

Both 865-file shard manifests agreed on **2,706 discovered occurrences**,
partitioned exhaustively and disjointly into 1,065 and 1,641 occurrences. The
original **54 repeated IDs** were preserved rather than deduplicated. The
discovery SHA256 was
`29d2aa28a0c2f7d6662d400071832a98068322b796c040b2aa4c06dfe786223f`.
All source hashes matched before and after each complete run.

The 168 additional ordinary passes comprise packet reservation 1, prospective
source 36, acquisition 31, optional metadata 7, recorded transport 33, source
admission 40, and prospective GA model 20. The 16 new raw-parser SQL cases were
explicitly opt-in skipped there. Root subsequently ran those **16 native parser
cases successfully, zero skips, in 5.547 seconds** in an owned fixture. That
separate receipt has SHA256
`68b5732ff926205c58d3465f02ff341a90ea32b6f914470599e91c7acbd4a8fa`;
its log has SHA256
`678eb222a9f344fdef30e0c7b82691fd6085d9b15641ba98b02962e621f02104`.
It is parser evidence, not full native source-admission acceptance.

## Semantics and remaining acceptance

Root independently reviewed the proposed source adoption, and two peer reviews
reported no integration blocker within the reviewed scope. The new files
remain disconnected research and transport components. The A1 supplied-witness
candidate, parser projection, and model `SourceMark` are distinct formats. No
adapter supplies missing authority between them. The parser and its independent
reference reparse original public fake Price/genesis/block-time bytes. The
prospective model uses literal sampled-source records, supplied trust
references, and an offline ledger. Its economic assumptions remain explicitly
uncalibrated; mechanical parity and mutation tests establish neither profitable
strategies nor realistic fills.

No B1 actor/catalog files are included. Native principal, lease, calibrated
clock, original journal, commit/readback, reader-origin, continuous acquisition
and warmup joins remain separate. No hosted worker, new worker image, native
admission authority, continuous warmup, funded wallet, signature or swap is
accepted by this receipt. Local file hashes and runtime-version guards establish
which local bytes were checked; they do not prove an actual hosted image
contains or executes those bytes.

The unchanged ordinary child limit is 1,500 seconds. The expanded second shard
took 701.679 seconds locally versus 299.039 seconds for TLS alone. This is useful
capacity evidence, not a shared amd64-runner guarantee. All seven required jobs
must pass on the actual combined head without weakening deadlines, discovery,
fixtures, source pins, or skip audits. Root must then record the exact verified
Dashboard production target, source/deployment identity and release checks.

Rollback is a reviewed same-version code revert of the two scoped adoptions in
reverse order, with normal CI and release verification. Dependencies and
framework/runtime versions are not changed by these additions. No database
rollback is required: the parser SQL was exercised only in an owned research
fixture, and this slice installs no hosted schema or worker state. Preserve the
accepted API foundation and keep the worker closed. Later native or runtime
adoptions require their own rollback review rather than assuming this scope.

## Actual CI deadline and forward workload repair

The exact combined PR107 head `dd2332dcdc1bb0b63153fabe267c8863fa25b7fb`
finishes [run39014680277](https://github.com/TOOTRJ/TheDashboard/actions/runs/39014680277)
with six passing jobs: frontend, ordinary1 and all four required PostgreSQL
shards. Ordinary2 reaches its unchanged 1,500-second deadline late in the
synthetic source-seal inventory. Its incomplete result is not accepted, and
the head remains unmerged. All sixteen parser cases belong to the passed
required SQL4 workload; no full native-source or hosted authority follows.

The separately reviewed two-file redistribution keeps the complete prospective
model opposite source admission. Eleven partition cases and a separate
60-case timing diagnostic pass. The full balanced composition also passes: 2,084
executed cases, zero unexpected skips, in 562.709/628.682 test seconds. Its
private B1-inclusive source composition is distinct from PR107; actual final-head
CI remains required.
[Exact evidence and required new-head acceptance](CI-WORKLOAD-REPAIR-ACCEPTANCE-2026-10-17.md).
The original local source inventories, runner hashes and results above remain
historical facts; they are not relabeled as results of the changed runner.
No B1 or UI repair is added to PR107 by this scheduling correction.
