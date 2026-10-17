"""Pure bounded retention inventory. No reads, writes, pruning, or authority.

Descriptors preserve exact supplied artifact bytes; the report names their
digests and protected reasons. Its inventory is not an authenticated database
scan and cannot establish that all retained artifacts were supplied.
"""
from dataclasses import dataclass
import hashlib
import json
import re
from types import MappingProxyType
from uuid import UUID

FORMAT = 'ga-retained-artifact-report-research-v1'
MAX_ARTIFACTS = 4096
MAX_ARTIFACT_BYTES = 589824
MAX_INPUT_BYTES = 33554432
MAX_REPORT_BYTES = 1048576
MAX_REFERENCES = 8192
KINDS = MappingProxyType({
    'original_command': 'original_command_and_delivery_replay',
    'receipt': 'committed_or_provisional_delivery_evidence',
    'checkpoint_manifest': 'checkpoint_and_accepted_prior_continuity',
    'dependency_component': 'immutable_checkpoint_dependency',
    'identity_ledger': 'identity_allocation_continuity',
    'holdings_state': 'holdings_and_reconciliation_evidence',
    'pending_request': 'original_unresolved_request_bytes',
    'worker_control_identity': 'original_start_and_stop_identity',
})
GATE_REASONS = ('inventory_completeness_unproved', 'native_restoration_unaccepted',
                'native_pruning_unaccepted')


class RetentionReportError(ValueError):
    pass


def _require(condition):
    if not condition:
        raise RetentionReportError('Invalid or over-capacity retention inventory')


def _uuid(value):
    _require(type(value) is str)
    try:
        _require(str(UUID(value)) == value)
    except (ValueError, AttributeError):
        raise RetentionReportError('Invalid retention scope') from None
    return value


def _digest(value):
    _require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None)


def _canonical(value):
    wire = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')
    _require(len(wire) <= MAX_REPORT_BYTES)
    return wire


@dataclass(frozen=True, slots=True)
class RetainedArtifact:
    kind: str
    wire: bytes
    references: tuple[str, ...] = ()

    def __post_init__(self):
        _require(type(self.kind) is str and self.kind in KINDS
                 and type(self.wire) is bytes and 0 < len(self.wire) <= MAX_ARTIFACT_BYTES
                 and type(self.references) is tuple and len(self.references) <= MAX_ARTIFACTS)
        for digest in self.references:
            _digest(digest)
        _require(len(set(self.references)) == len(self.references))

    @property
    def sha256(self):
        return hashlib.sha256(self.wire).hexdigest()


@dataclass(frozen=True, slots=True)
class RetentionReport:
    _wire: bytes

    def __post_init__(self):
        _require(type(self._wire) is bytes and 0 < len(self._wire) <= MAX_REPORT_BYTES)
        try:
            value = json.loads(self._wire)
            _require(type(value) is dict and value['format'] == FORMAT
                     and all(value[key] is False for key in ('inventory_complete',
                         'schema_and_owner_authority_verified', 'wire_bytes_are_database_storage',
                         'eligible_for_deletion', 'deletion_authority', 'restoration_authority', 'hosted_authority'))
                     and value['actual_table_toast_index_wal_bytes'] is None
                     and type(value['artifacts']) is list
                     and all(row['eligible_for_deletion'] is False and row['disposition'] == 'retain'
                             for row in value['artifacts'])
                     and _canonical(value) == self._wire)
            _uuid(value['owner_id']); _uuid(value['run_id'])
        except (KeyError, TypeError, ValueError, UnicodeError, RecursionError):
            raise RetentionReportError('Invalid conservative retention report') from None

    @property
    def report_id(self):
        return hashlib.sha256(self._wire).hexdigest()

    @property
    def deletion_authority(self):
        return False

    def to_dict(self):
        return json.loads(self._wire)


def build_retention_report(owner_id, run_id, artifacts):
    """Retain every supplied artifact and report missing inventory evidence.

    A reference is another supplied artifact's exact-byte SHA-256. Missing
    references are reported, not converted into deletion candidates. Native
    schemas/receipts, source truth, authenticated owner scope and completeness
    belong to separate validators; this function grants none of those claims.
    """
    _uuid(owner_id); _uuid(run_id)
    _require(type(artifacts) is tuple and 0 < len(artifacts) <= MAX_ARTIFACTS)
    _require(all(type(item) is RetainedArtifact for item in artifacts))
    _require(sum(len(item.references) for item in artifacts) <= MAX_REFERENCES)
    total = sum(len(item.wire) for item in artifacts)
    _require(total <= MAX_INPUT_BYTES)
    descriptors, blobs, kinds = {}, {}, set()
    referenced = {ref for item in artifacts for ref in item.references}
    for item in artifacts:
        item.__post_init__()
        digest = item.sha256
        key = (item.kind, digest)
        _require(key not in descriptors)
        if digest in blobs:
            _require(blobs[digest] == item.wire)
        blobs[digest] = item.wire
        kinds.add(item.kind)
        reasons = list(GATE_REASONS) + [KINDS[item.kind]]
        if digest in referenced:
            reasons.append('referenced_retained_artifact')
        descriptors[key] = {
            'kind': item.kind, 'sha256': digest, 'wire_bytes': len(item.wire),
            'references': sorted(item.references), 'protected_reasons': sorted(reasons),
            'disposition': 'retain', 'eligible_for_deletion': False,
        }
    missing = sorted(referenced - blobs.keys())
    body = {
        'format': FORMAT, 'owner_id': owner_id, 'run_id': run_id,
        'artifacts': [descriptors[key] for key in sorted(descriptors)],
        'supplied_artifact_count': len(artifacts), 'supplied_wire_bytes': total,
        'unique_blob_count': len(blobs), 'unique_blob_wire_bytes': sum(map(len, blobs.values())),
        'missing_referenced_digests': missing,
        'missing_artifact_classes': sorted(KINDS.keys() - kinds),
        'inventory_complete': False, 'schema_and_owner_authority_verified': False,
        'wire_bytes_are_database_storage': False, 'actual_table_toast_index_wal_bytes': None,
        'eligible_for_deletion': False, 'deletion_authority': False,
        'restoration_authority': False, 'hosted_authority': False,
        'blocking_reasons': list(GATE_REASONS),
    }
    return RetentionReport(_canonical(body))
