# Runtime-content image export prototype: working implementation

This new private branch starts at
`81474c1f9b65ac0defe0da4a1c061aa88c417561`. Root selected the separately
versioned B runtime-content export experiment. Root and security peer approved
the closed descriptor before the pure working implementation. No Docker pull/run/load/export,
provider operation, hosted job, workflow change, cache/mirror/publisher,
credential, billing, stage or commit has been performed here. The old direct
RepoDigest verifier, exact three image pins, fixtures, clocks, test coverage and
all deadlines remain unchanged.

The exact new file scope is `scripts/check-ci-runtime-export.py`,
`scripts/tests/test_ci_runtime_export.py`, `CI-RUNTIME-EXPORT-POLICY.json` and
this contract. All four are now new working files, pending concrete code/receipt
review with an empty index. No current installation or runtime result is claimed.
The descriptor has7,016 canonical UTF-8 bytes, SHA256
`613edd678d372ff40890b5075cbee00e822745c1ed5e17aa96f63a8c6675d4c7`;
its pretty file is externally hashed separately. The descriptor contains no own
digest or implementation digest value.

## What this policy would prove

The pure verifier would check a single closed normalized archive against a
separately held canonical ExpectedManifest and the existing reviewed pin tuples.
Each original platform-manifest raw byte hash must match the reviewed manifest
pin; its original config descriptor must match the reviewed config pin. Each
original config raw byte hash must independently match that pin and declare
Linux amd64 plus the complete ordered `rootfs.diff_ids`. Every real exported
uncompressed layer byte stream must match its corresponding ordered DiffID.
The normalized image mapping retains every ordered original layer association,
including distinct images sharing the same content. The original registry
manifest's compressed-layer hashes remain original facts, without a claim that
the normalized uncompressed payload preserves those compressed bytes.

OCI explicitly distinguishes uncompressed layer DiffIDs from manifest layer
digests and defines the image configuration's relationship to the ordered
filesystem chain. This motivates B's runtime-content identity rather than an
invented RepoDigest marker. [OCI configuration](https://github.com/opencontainers/image-spec/blob/main/config.md).

All eight authority fields stay literal false in the descriptor, transport and
report. A successful pure check proves bounded internal/context/content
consistency under its supplied independent expectations; it does not authenticate
a GitHub signer/runner, prove a Docker export mapping, load an image, preserve
RepoDigests, execute SQL, activate the worker or authorize trading.

## Closed outer archive and inner layer distinction

The normalized outer archive is an uncompressed USTAR tar with exactly:

1. Canonical compact sorted-key UTF-8 `manifest.json`.
2. `images/0/platform-manifest.json`, `images/0/config.json`, and the corresponding
   pair for images 1 and 2, in the current postgres/PostgREST/Python pin order.
3. One `layers/{diffID-hex}.tar` member per unique DiffID, sorted by hex name.

Each image's manifest retains its full original layer order even though the
physical unique member set is sorted and may be shared. Shared references must
agree on DiffID and byte length. All headers are canonical regular-file USTAR
headers with type `0`, mode0600, uid/gid/mtime0, empty uname/gname/linkname/prefix,
fixed octal integers and checksum syntax. Member padding is zero. Exactly two
zero blocks plus zero padding to the next 10,240-byte record boundary terminate
the archive, followed by exact EOF. No PAX/GNU extensions, links, devices,
directories, sparse records, base-256 sizes, additional roots, duplicate members,
traversal, alternate spellings or trailing nonzero data are accepted.

The inner approved filesystem layer is an exact hashed byte stream; it is never
extracted or reinterpreted on the host. Legitimate filesystem symlinks and
whiteouts inside a layer are not confused with dangerous outer transport links.
Later Docker ingestion is a separate declared boundary. No generic tar extraction
library or load command is included in the pure prototype.

The normalized mapping format is our closed transport format, not a claim that
an actual Docker engine produces it directly. A separately expected export-profile
SHA records the future source declaration. Matching that SHA is metadata/context
consistency, not proof the source profile was observed. Before any producer or
loader, the actual Docker engine/store/API/export format must be measured,
reviewed and pinned; an unknown source format cannot silently select a parser.
The reviewed normalization adapter is a later source version.

## Independent expectations and no hash cycle

The transport embeds only its preallocated producer context, source declaration,
image mapping, descriptor digest and false flags. It deliberately omits archive
hash/length, its own manifest hash, and the artifact ID assigned after upload.
Those values belong to the separate ExpectedManifest, along with the same
independently held context/source declaration. No digest is recovered from the
untrusted archive and adopted as its own expected value.

Context fixes repository ID1141090963, workflow path, exact workflow/source
hashes, actual checkout commit and PR head separately, ref, run ID/attempt,
producer job and a derived unique artifact name. The actual checkout commit may
be the normal PR merge commit; it must agree across producer and consumers.
Artifact ID/hash/bytes and canonical transport-manifest SHA arrive through the
separate reviewed same-run output selection. Run/attempt mismatches refuse,
including a consumer-only rerun attempting to reuse a prior-attempt artifact.
No latest-run or all-artifacts lookup is permitted.

Source hashes are externally held expectations and are not embedded in their
own Python/descriptor sources. The pure prototype does not magically establish
the caller's independent source provenance; the later workflow must supply it
from the reviewed checkout and exact intended producer output, never from a
field in the artifact. The ExpectedManifest remains a lexical/context binding,
without a new authenticated capability. Actions artifact digest warnings do not
replace our hard archive/content mismatch refusal.
[GitHub artifact validation](https://docs.github.com/en/actions/tutorials/store-and-share-data#validating-artifacts).

## Candidate bounds and file ownership

The explicit refusal candidates are three images, 1–64 layers per image,
1MiB per JSON document, 4GiB archive bytes, 8GiB total logical layer bytes,
1MiB streaming buffers, and 240 seconds of actual monotonic validation.
ExpectedManifest is capped at64KiB and the safe report at8KiB. Full JSON validation
has depth32/node100,000 and numeric-token128-byte bounds. Keys/strings include
full duplicate/UTF-8/NUL/lone-surrogate checks and parsed numbers must be finite.
Original source JSON is kept byte-exact; only transport/expected JSON must be
canonical. No outer decompression is supported. Config SHA and ordered raw-layer
hashes are checked before typed output, without numeric rounding or source
metadata normalization.

These are unmeasured refusal limits, not proof the current images fit, complete
within240seconds or cost nothing. The8GiB layer cap charges every original
ordered reference, including repeated/shared members; physical deduplication
cannot conceal the logical layer application size. The independent4GiB outer
archive cap remains, without permission to produce a larger archive.
The eventual proposed240-second validation/load total and one-day artifact
retention remain separate measured/reviewed gates. No auto-widening is allowed.

Read only exclusive owned regular mode0600 nlink1 archive/expectation files
inside one exclusive mode0700 owned directory. No-follow descriptors and held
parent/directory descriptors bind device/inode, ownership/mode, size and path
before and after reading. Refuse preexisting/replaced/linked/foreign resources;
cleanup only exact created inodes through their pinned directory descriptor.
No recursive foreign deletion or shared cache/daemon/configuration access.
These checks detect ordinary observed replacement, not a hostile same-user or
compromised host/process. Real monotonic checks reject late completion; bounded
regular-file reads do not create a hard OS-blocking scheduling guarantee.

## Proposed meaningful acceptance before adoption

Pure controlled fixtures use explicit synthetic manifests/configs/layers and
independent expected records; they must never be relabeled as these real image
bytes or an authenticated hosted producer. Proposed cases cover:

- Full three-image positive chain, preserved original JSON spacing/bytes,
  complete layer order, legitimate inner links/whiteouts as opaque bytes, and
  shared layer dedup with every image reference retained.
- Byte corruption, substituted original manifest/config, altered ordered DiffID,
  missing/extra/reordered/shared-size-mismatched layers, foreign repository/tag/
  platform/source declaration, metadata-only hash shortcuts and forged true flags.
- Duplicate decoded JSON keys, nonfinite/boolean/wrong counter/type, NUL/lone
  surrogate, canonical transport/expected byte differences and all depth/node/
  size/member/number bounds, including genuine boundary values without huge RAM
  allocations.
- Outer header checksum/type/name/size/padding/terminal violations, traversal,
  symlinks/hardlinks/devices/sparse/PAX/GNU entries, duplicate/extraneous roots,
  truncated streams, compressed outer input, excess trailing bytes and actual
  layer hash verification before any later loading capability.
- Independent expected source/workflow/checkout/head/ref/run/attempt/artifact
  identity mismatch, unavailable original expectations, archive digest warnings
  converted to our hard failure, and no self-embedded archive/artifact identity.
- Exact owned inode/parent/file-mode/link-count replacement refusal and own-only
  cleanup, cancellation/late return and resource-cap refusal with fixed safe
  errors. Invalid expectations refuse before archive reads or network/process work.

The pure check does not implement GitHub producer failure propagation or Docker
load. Later adoption must keep all seven actual test results and add a required
producer result with explicit failed/missing/cancelled/corrupt setup refusal.
Bare `needs` skips are insufficient. The workflow capability checker currently
rejects new jobs, conditions, actions and environments; a future policy requires
exact narrow allowances and mutation tests, not disabling that checker.

First require an authorized disposable round trip measuring raw sidecar hashes,
archive bytes, actual engine/store/API, full validation and load times, loaded
original config/platform/ordered RootFS, existing fixture smoke and storage
byte-hours. Docker's docs promise restoring images and tags; they do not establish
the original RepoDigest across this round trip, and platform filtering requires
API1.48+. [Docker save](https://docs.docker.com/reference/cli/docker/image/save/),
[Docker load](https://docs.docker.com/reference/cli/docker/image/load/).
No registry mirror, publisher role, credential fallback, cache, account/billing
change or current workflow replacement is authorized by this proposal.

## Source-bound synthetic working acceptance

The new public `verify_capture(source, expected_wire, parent)` has no public pin
or clock override and no constructor adopting an existing input file. It first
validates the independently supplied ExpectedManifest and the actual verifier,
direct-pin and workflow file hashes before creating an archive file or calling
the archive source. Producer-source and export-profile hashes are independently
supplied metadata/context only; no producer/adapter file exists or is read by this
prototype. The existing
direct pin source is read bounded/no-follow and parsed with AST/literal evaluation
without executing it; the resulting four-field tuples must exactly equal the
verifier's fixed three approved tuples. Caller fields cannot substitute those
tuples. No default direct-verifier branch, workflow or fixture behavior changes.

Only after expectation validation does the controller exclusively create one
private directory and its two input files. Both source-read requests and accepted
chunks are bounded before writes, including source overflow beyond the independently
expected archive size. It captures/hash-checks, reads the exact normalized archive
through its held descriptor, then removes only same-inode created files and the
same created directory. Replaced/linked/modified/foreign resources fail validation
and cleanup without removal. A final monotonic check includes successful cleanup;
no stage restarts its deadline. No successful report is returned after cleanup
refusal. These are observed binding checks, without a hostile same-user claim.

Final affected working source passed **34 cases, zero failures/skips, 0.212 seconds**
under pinned CPython3.12.14, `env -i`, dotenv disabled and bytecode writes disabled.
It ran only `scripts/tests/test_ci_runtime_export.py`. Fixtures contain three
synthetic configs/manifests and three synthetic filesystem layers; two ordered
references per image share the physical members. The positive test includes inner
symlinks and whiteouts as unchanged hashed bytes. An explicit private mock replaces
only the test pin resolver for synthetic positives. The default real-pin path
rejects the synthetic bundle, and an attempted caller `pins` key refuses before
source read/file creation. No synthetic body is represented as an actual Supabase
or Python registry image.

The initial30-case run reported one assertion mismatch in0.266 seconds: adding a
byte to the config was refused earlier by its already-pinned original size, while
the test expected the later hash refusal. The final test changes a valid unused
numeric value at the same original length to isolate the independent config hash.
No parser, resource limit, original pin, clock or authority rule was relaxed.
The intermediate30-case corrected run passed0.260seconds; two targeted
regressions then verified no late success after cleanup and per-leaf ownership
rechecking after the first own unlink (32/0.214s). A self-review replaced eager
private-directory enumeration with a bounded streaming scan that refuses the
first unknown entry (33/0.260s). Peer review repaired the test-only temporary
anchor to exact Darwin`/private/tmp` or Linux`/tmp`, with unsupported OS refusal
and no environment-driven fallback (33/0.245s). Peer review also added a final
no-follow source-path comparison against the opened inode. Its benign owned
parent-directory replacement regression leaves the original opened leaf metadata
unchanged, creates a different source at the prior path and requires refusal.
The final34-case source supersedes those intermediate local receipts. No actual
Linux execution, hosted job or engine compatibility is claimed by this Darwin run.

The finite suite also covers independent source/workflow hashes and context,
original raw-byte corruption, all eight attempted true-flag promotions, typed
source/unused JSON checks, both supplementary Unicode encodings, exact layer
order/shared-size charging, outer header/type/member/padding/terminal violations,
bounded capture overflow/truncation, fixed private-safe source errors, actual owned
path/inode/mode/link/content changes and preexisting-resource preservation.
Deadline behavior is a controlled private monotonic mock, not a240-second wall
measurement or runtime speed guarantee. Physical4GiB/8GiB processing, full RSS,
real registry bodies and engine/load/artifact service behavior are unmeasured.
AST compilation and whitespace/diff checks of all four new files pass; no broader
worker/SQL/build suite ran.

| Source | SHA256 |
| --- | --- |
| `scripts/check-ci-runtime-export.py` | `8299be9b0b7b64bf8875f885d7ff8f8826b5d291350c7d40a13500a12b2ef56b` |
| `scripts/tests/test_ci_runtime_export.py` | `57b2ddaad646d0b284a1ff6b45eae7efd1d2efebfc2e68decf27ffec8de75c88` |
| `CI-RUNTIME-EXPORT-POLICY.json` | `f8741ab1823d49ecaab6857aa64abb28a78471f8421a55ccf31af93442d38c3c` |
| unchanged `scripts/check-ci-images.py` | `1d28e16d3db54c5ed5f709c872f0e0b6470e2c85a2a9cdda8d02b2618efc3d5f` |
| unchanged `.github/workflows/verification.yml` | `637aec26b0cf858c5844ae6ddbe8eab19450c29b3aa9566dd0a81050a2b423fb` |

Concrete root and independent security-peer implementation reviews completed on
2026-10-13 without a remaining blocker in this pure synthetic scope. Root
authorized an exact local four-file commit, without a producer, adapter, workflow,
image pull/export/load or hosted operation. The current eight false authority
flags, unmeasured real-source/capacity/adapter/runner/loaded-runtime gates and
unchanged current CI requirements remain in force.
