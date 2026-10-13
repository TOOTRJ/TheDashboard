# Conservative retained-artifact report scaffold

`retention_manifest.py` is pure, bounded inventory/report code. It makes no file,
database, provider or credential calls and implements **no pruning**. Every
supplied artifact remains protected and ineligible for deletion, including
older or apparently unreferenced artifacts. A report cannot authorize worker
continuation, restoration, live activity, or hosted deletion.

The descriptor classes cover the full original command bytes and receipts;
checkpoint manifests and all immutable referenced components/pins; identity
allocation evidence; holdings/reconciliation evidence; the original unresolved
request bytes; and the original Start/Stop identities. Callers retain those
exact blobs outside the report. A digest/report is never a replacement for the
original command, pending request, component, receipt or identity rows.

The initial native formats being investigated are the original v2 compact
command/manifest/component formats and
`ga-portable-native-command-readback-lab-v1`,
`ga-portable-native-checkpoint-readback-lab-v1`,
`ga-portable-native-receipt-lab-v1`, and
`ga-portable-native-identity-lookup-lab-v1`. This scaffold does **not** parse or
authenticate those formats. Its artifact classes are report metadata, not a new
native wire format. A validated adapter may supply their complete exact bytes;
until then the report explicitly says schema/owner authority and inventory
completeness are unverified. In particular, bounded identity lookups do not
prove that the complete allocation ledger was enumerated, and there is no
separately accepted native pending-request-set format yet.

References are exact SHA-256 digests of other retained supplied blobs. Missing
links and absent artifact classes appear as evidence gaps and never become
deletion candidates. Multiple classes may describe one blob, for example an
unresolved original request. The report distinguishes summed descriptor bytes
from deduplicated unique blob bytes. Both are exact measures of the supplied
wire bytes; neither estimates actual table tuples, TOAST, indexes, WAL,
replication copies or provider billing. Those physical storage figures remain
unknown. Content hashes and canonical report ordering provide byte identity,
not authenticated provenance or a completeness proof.

Limits are 4,096 descriptors, 8,192 aggregate references, 589,824 bytes per blob,
32 MiB summed input bytes, and 1 MiB report bytes. Inputs use immutable byte strings and explicit unique
references. Reports return fresh decoded values. Code and property checks keep
all authority/deletion flags false regardless of inventory size, order, missing
references or sharing.

The next integration must bind authenticated owner/run, current head and exact
package/validator digest; complete command receipts, immutable dependency pins,
identity allocation history, open holdings and reconciliation; and all original
pending Start/Stop/command IDs and bytes. Joined native restoration and original-ID
reconciliation tests must prove that retaining this closure preserves the exact
next command. Only after a separately reviewed retention transaction, lock
contract, archive semantics, storage measurement and failed-cleanup tests can
pruning eligibility be considered. No hosted deletion readiness is claimed.
