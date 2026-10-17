"""Offline original-v2 model restoration and original-request reconciliation.

The authenticated native reader/catalog/actor check belongs to the operator's
separate boundary. These pure functions validate its expected bindings, restore
research model data, and grant no credentials, fence, lease, retry or activation.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from copy import deepcopy
import hashlib

from . import provider_portable_ga_model as model
from . import portable_partitioned_checkpoint as original_checkpoint
from .portable_restoration_graph import reconstruct_graph
from .portable_restoration_wire import (
    RestorationError, ExpectedHead, DecodedCheckpoint, decode_readback, decode_numeric,
    parse_json, fields, require, uuid, revision, canonical, validate_receipt,
    MAX_MANIFEST_BYTES, MAX_COMPONENT_BYTES, MAX_AGGREGATE_BYTES,
)

IDENTITY_FORMAT = 'ga-portable-native-identity-lookup-lab-v1'
COMMAND_READBACK_FORMAT = 'ga-portable-native-command-readback-lab-v1'


@dataclass(frozen=True, slots=True)
class RestoredResearchState:
    checkpoint: DecodedCheckpoint
    state: model.GAState

    @property
    def restoration_authority(self): return False

    @property
    def hosted_authority(self): return False

    @property
    def lease_restored(self): return False

    @property
    def identity_ledger_restored(self): return False

    @property
    def clock_epoch(self): return self.state.to_dict()['source']['epoch']


def _reconstruct_checkpoint(checkpoint):
    """Rebuild reviewed owned classes from exact wires, without bootstrap/reseed."""
    require(type(checkpoint) is DecodedCheckpoint and checkpoint.is_current,
            'Only a current independently bound checkpoint can prepare continuation')
    expected = checkpoint.expected
    expected.__post_init__()
    require(hashlib.sha256(checkpoint.manifest_wire).hexdigest() == expected.manifest_sha256)
    manifest = decode_numeric(checkpoint.manifest_wire, maximum=MAX_MANIFEST_BYTES)
    fields(manifest, {'format', 'source_model_version', 'owner_id', 'run_id', 'revision',
        'status', 'reserve', 'accounts', 'positions', 'engine', 'source', 'components'})
    require(manifest['format'] == original_checkpoint.FORMAT
            and manifest['source_model_version'] == model.MODEL_FORMAT)
    engine = manifest['engine']
    fields(engine, {'generation', 'last_quote', 'decision_timestamp', 'lifecycle', 'cohort_source', 'members'})
    require(type(engine['generation']) is int and 0 <= engine['generation'] <= 2**31 - 1
            and type(engine['members']) is list and len(engine['members']) == 8)
    ids = [uuid(member['id']) for member in engine['members']]
    require(len(set(ids)) == 8)
    expected_slots = [('configuration', 'configuration', 0), ('optimizer', 'optimizer', engine['generation']),
        ('cohort', 'cohort', engine['generation'])] + [('genome', member, engine['generation']) for member in ids]
    expected_slots += [('source_bars', 'source_bars', 0), ('ema', 'ema', 0)]
    require(type(checkpoint.component_wires) is tuple and len(checkpoint.component_wires) == 13)
    bodies, blocks = {}, []
    for ref, wire, slot in zip(manifest['components'], checkpoint.component_wires, expected_slots):
        require(type(wire) is bytes and hashlib.sha256(wire).hexdigest() == ref['sha256'])
        component = decode_numeric(wire, maximum=MAX_COMPONENT_BYTES)
        require((component['kind'], component['entity_id'], component['generation']) == slot
                and all(type(component[key]) is type(ref[key]) and component[key] == ref[key]
                        for key in ('kind', 'entity_id', 'generation')),
                'Original ordered component slots differ')
        bodies[slot[:2]] = component['body']
        blocks.append(original_checkpoint.TypedComponent(wire))
    # This is an additional primitive source/economic/risk/mirror audit, not a
    # substitute for independently accepted native semantic provenance.
    audited = original_checkpoint.resolve_manifest(manifest, tuple(blocks),
        owner_id=expected.owner_id, run_id=expected.run_id, revision=expected.revision)
    data = {key: deepcopy(value) for key, value in manifest.items()
            if key not in {'format', 'source_model_version', 'components'}}
    data['version'] = model.MODEL_FORMAT
    data['engine']['config'] = deepcopy(bodies['configuration', 'configuration'])
    data['engine']['optimizer'] = deepcopy(bodies['optimizer', 'optimizer'])
    data['engine']['cohort'] = deepcopy(bodies['cohort', 'cohort'])
    data['engine']['ema'] = deepcopy(bodies['ema', 'ema'])
    require(type(data['source']) is dict and 'bars' not in data['source'])
    fields(bodies['source_bars', 'source_bars'], {'bars'})
    data['source']['bars'] = deepcopy(bodies['source_bars', 'source_bars']['bars'])
    for member in data['engine']['members']:
        member['genome'] = deepcopy(bodies['genome', member['id']])
    comparison = deepcopy(audited)
    comparison.pop('format'); comparison.pop('source_model_version'); comparison['version'] = model.MODEL_FORMAT
    require(canonical(data) == canonical(comparison), 'Independent component reconstruction loses original evidence')
    model._configuration(data)
    try:
        strategy, cohort = reconstruct_graph(data['engine']['optimizer'], data)
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError):
        raise RestorationError('Original model continuation reconstruction failed') from None
    # Reviewed fixed layout only. GAState._seal / ExactState._seal would make a
    # fresh RNG copier; reconstruct directly from the already owned decoded graph.
    require(model.GAState.__slots__ == ('__owned',)
            and model.base.ExactState.__slots__ == ('__wire', '__strategy', '__cohort'))
    owned = object.__new__(model.base.ExactState)
    object.__setattr__(owned, '_ExactState__wire', model.base._json(data))
    object.__setattr__(owned, '_ExactState__strategy', strategy)
    object.__setattr__(owned, '_ExactState__cohort', cohort)
    state = object.__new__(model.GAState)
    object.__setattr__(state, '_GAState__owned', owned)
    require(canonical(state.to_dict()) == canonical(data))
    return RestoredResearchState(checkpoint, state)


def reconstruct_checkpoint(checkpoint):
    try:
        return _reconstruct_checkpoint(checkpoint)
    except RestorationError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError):
        raise RestorationError('Original model continuation reconstruction failed') from None


def restore_readback(wire, expected):
    return reconstruct_checkpoint(decode_readback(wire, expected))


def prepare_restored_transport(restored, candidate, *, command_id):
    """Encode the explicit next candidate against the original readback references.

    No producer-only prior-capture object is invented. The original manifest and
    component digest set are retained verbatim; IDs/clocks come from the caller.
    This is preparation, never submission, retry, committed outcome or authority.
    """
    require(type(restored) is RestoredResearchState and type(candidate) is model.GACandidate)
    require(restored.checkpoint.is_current)
    uuid(command_id)
    candidate.__post_init__()
    before = restored.state.to_dict()
    require(canonical(candidate.transition['before']) == canonical(before)
            and candidate.state.revision == before['revision'] + 1)
    following = original_checkpoint.capture_owned_candidate(candidate)
    old_hashes = {hashlib.sha256(wire).hexdigest() for wire in restored.checkpoint.component_wires}
    changes = [component.to_dict() for component in following.components if component.identity not in old_hashes]
    body = {'format': original_checkpoint.TRANSPORT_FORMAT, 'command_id': command_id,
        'owner_id': before['owner_id'], 'run_id': before['run_id'],
        'prior': {'revision': before['revision'], 'sha256': restored.checkpoint.expected.manifest_sha256},
        'checkpoint': following.to_dict(), 'components': changes, 'operations': candidate.operations,
        'history': candidate.history, 'evidence': candidate.transition['evidence'],
        'events': candidate.transition['events']}
    control = body['evidence']['control']
    maximum = MAX_AGGREGATE_BYTES if control is not None and control['action'] == 'stop' else original_checkpoint.ORDINARY_COMMAND_BYTES
    from .numeric_wire import encode
    from .checkpoint_reference import jsonb_text_bytes
    import json
    wire = encode(body, maximum=maximum)
    expanded = len(json.dumps(body, sort_keys=True, ensure_ascii=False, allow_nan=False,
                              separators=(', ', ': ')).encode('utf-8'))
    require(jsonb_text_bytes(json.loads(wire)) <= maximum and expanded <= maximum,
            'Complete restored transport exceeds its original capacity')
    return wire


@dataclass(frozen=True, slots=True)
class IdentitySnapshot:
    expected: ExpectedHead
    requested: tuple[str, ...]
    _wire: bytes

    def used(self, identity):
        uuid(identity)
        require(identity in self.requested, 'An unchecked identity has no unused default')
        return parse_json(self._wire)['identities'][identity]['used']


def decode_identity_lookup(wire, expected, requested):
    require(type(expected) is ExpectedHead and expected.allow_historical is False)
    expected.__post_init__()
    require(type(requested) is tuple and 0 <= len(requested) <= 128
            and len(set(requested)) == len(requested), 'Bounded unique asked identity set required')
    for identifier in requested: uuid(identifier)
    response = parse_json(wire, maximum=65536)
    fields(response, {'format', 'owner_id', 'run_id', 'revision', 'manifest_sha256',
        'native_package_sha256', 'identities', 'restoration_authority', 'hosted_authority'})
    require(response['format'] == IDENTITY_FORMAT
            and response['owner_id'] == expected.owner_id and response['run_id'] == expected.run_id
            and revision(response['revision']) == expected.revision
            and response['manifest_sha256'] == expected.manifest_sha256
            and response['native_package_sha256'] == expected.native_package_sha256
            and response['restoration_authority'] is False and response['hosted_authority'] is False)
    fields(response['identities'], set(requested))
    for identifier in requested:
        row = response['identities'][identifier]
        require(type(row) is dict)
        if row.get('used') is False:
            fields(row, {'used'})
        else:
            fields(row, {'used', 'kind', 'born_revision'})
            require(row['used'] is True and type(row['kind']) is str and row['kind'] in {'account', 'position', 'risk'}
                    and revision(row['born_revision']) <= expected.revision)
    return IdentitySnapshot(expected, requested, canonical(response))


class RestorationLedgerView:
    """Pure current-head/asked-ID view, never a reconstructed history or SQL client."""
    def __init__(self, restored, identities):
        require(type(restored) is RestoredResearchState and type(identities) is IdentitySnapshot)
        require(restored.checkpoint.is_current and restored.checkpoint.expected == identities.expected)
        require(decode_identity_lookup(identities._wire, identities.expected, identities.requested) == identities,
                'Identity oracle snapshot was not validated')
        self._state_wire = model.base._json(restored.state.to_dict())
        self._identities = identities
        self.owner_id, self.run_id = identities.expected.owner_id, identities.expected.run_id

    def check(self, before, owner, run):
        require((owner, run) == (self.owner_id, self.run_id)
                and model.base._json(before) == self._state_wire, 'Restored preparation head/scope differs')

    def used(self, identity):
        return self._identities.used(identity)


def prepare_restored_candidate(restored, inputs, identities, *, phase, frame=None,
                               history=None, action=None, trip_id=None):
    """Stage explicit evidence, then invoke the unchanged original-v2 kernel.

    The original public producer requires its complete in-process SimulationLedger.
    We must not manufacture one from active rows. This separate restoration adapter
    uses the head-bound asked-ID oracle and the original source validators instead;
    economic, lifecycle, cohort, selection and RNG preparation remains unchanged.
    """
    require(type(restored) is RestoredResearchState and type(phase) is str and phase in {'protective', 'decision', 'control'})
    require(type(inputs) is model.DecisionInputs and type(identities) is IdentitySnapshot
            and inputs.ids == identities.requested,
            'Every offered allocation must match the bounded independently checked identity set')
    ledger = RestorationLedgerView(restored, identities)
    state = restored.state
    before = state.to_dict()
    ledger.check(before, before['owner_id'], before['run_id'])
    model.source.validate_source_state(before['source'], epoch=model._configuration(before).source_epoch)
    wall, mono = model.evidence_clocks(inputs)
    after_source = deepcopy(before['source'])
    recovery = phase == 'control' and action == 'recover'
    if phase == 'protective':
        require(action is None and history is None and trip_id is None)
        model.source.validate_frame(frame, prior_source=before['source'], epoch=before['source']['epoch'])
        model.source.check_frame(frame, wall_us=wall, monotonic_us=mono)
        after_source.update(quote_sequence=frame['sequence'], last_quote=deepcopy(frame))
    elif phase == 'decision' or recovery:
        require(phase != 'decision' or (action is None and trip_id is None))
        model.source.check_frame(frame, wall_us=wall, monotonic_us=mono)
        if frame != before['source']['last_quote']:
            raise model.source.ProviderSourceError()
    elif frame is not None or history is not None:
        raise model.source.ProviderSourceError()
    if history is not None:
        if before['engine']['lifecycle']['risk']['active'] and not recovery:
            raise model.source.ProviderSourceError()
        model.source.validate_history(history, prior_bars=before['source']['bars'], seed=False,
                                      wall_us=wall, monotonic_us=mono)
        after_source['bars'] = (after_source['bars'] + model.source.derive_bars(history))[-64:]
    observation = None
    if frame is not None:
        bar = after_source['bars'][-1] if history is not None or recovery else None
        observation = model.ExactObservation(frame['decision_second'], frame['quote']['price'],
            None if bar is None else bar[0], None if bar is None else bar[1])
    evidence = {'phase': phase, 'frame': deepcopy(frame), 'history': deepcopy(history),
                'wall_us': wall, 'monotonic_us': mono}
    staged = model._ProviderLedgerView(ledger, {'evidence': evidence, 'after': after_source})
    if phase == 'protective':
        return model._prepare_protective(state, observation, inputs, ledger=staged)
    if phase == 'decision':
        return model._prepare_decision(state, observation, inputs, ledger=staged)
    return model._prepare_control(state, action, inputs, observation, trip_id, ledger=staged)


@dataclass(frozen=True, slots=True)
class PendingOriginalRequest:
    owner_id: str
    run_id: str
    command_id: str
    command_sha256: str
    revision: int
    manifest_sha256: str
    wire: bytes

    @classmethod
    def capture(cls, wire):
        body = decode_numeric(wire, maximum=MAX_AGGREGATE_BYTES)
        fields(body, {'format', 'command_id', 'owner_id', 'run_id', 'prior', 'checkpoint',
            'components', 'operations', 'history', 'evidence', 'events'})
        require(body['format'] == original_checkpoint.TRANSPORT_FORMAT)
        checkpoint = body['checkpoint']
        require(type(checkpoint) is dict and checkpoint.get('format') == original_checkpoint.FORMAT
                and checkpoint.get('source_model_version') == model.MODEL_FORMAT
                and checkpoint.get('owner_id') == body['owner_id'] and checkpoint.get('run_id') == body['run_id'])
        require(type(checkpoint.get('revision')) is int and 2 <= checkpoint['revision'] <= 2**63 - 1)
        for key in ('owner_id', 'run_id', 'command_id'): uuid(body[key])
        require(type(body['evidence']) is dict, 'Original pending request evidence must be an object')
        control = body['evidence'].get('control')
        stop = type(control) is dict and control.get('action') == 'stop'
        require(len(wire) <= (MAX_AGGREGATE_BYTES if stop else original_checkpoint.ORDINARY_COMMAND_BYTES))
        from .numeric_wire import encode
        manifest = encode(checkpoint, maximum=MAX_MANIFEST_BYTES)
        return cls(body['owner_id'], body['run_id'], body['command_id'], hashlib.sha256(wire).hexdigest(),
                   checkpoint['revision'], hashlib.sha256(manifest).hexdigest(), wire)


@dataclass(frozen=True, slots=True)
class OriginalRequestResolution:
    original: PendingOriginalRequest
    outcome: str

    @property
    def retry_authority(self): return False

    @property
    def restoration_authority(self): return False

    @property
    def hosted_authority(self): return False


def reconcile_original_request(original, wire, package_binding):
    """Interpret only an independently observed getter for the same saved ID/hash.

    An absent observation remains uncertain. It never generates a replacement
    ID, automatically retries a write, assumes rollback, or installs a lease.
    """
    require(type(original) is PendingOriginalRequest and type(package_binding) is ExpectedHead)
    require(PendingOriginalRequest.capture(original.wire) == original)
    package_binding.__post_init__()
    require(original.owner_id == package_binding.owner_id and original.run_id == package_binding.run_id)
    response = parse_json(wire)
    require(type(response) is dict and response.get('format') == COMMAND_READBACK_FORMAT)
    if response.get('found') is False:
        fields(response, {'format', 'found'})
        return OriginalRequestResolution(original, 'not_observed_uncertain')
    fields(response, {'format', 'found', 'receipt', 'original_command_wire'})
    require(response['found'] is True and type(response['original_command_wire']) is str)
    try:
        require(response['original_command_wire'].encode('utf-8') == original.wire,
                'Getter changed the saved original request')
    except UnicodeError:
        raise RestorationError('Invalid getter original wire') from None
    expected = replace(package_binding, command_id=original.command_id, command_sha256=original.command_sha256,
                       revision=original.revision, manifest_sha256=original.manifest_sha256, allow_historical=False)
    validate_receipt(response['receipt'], expected)
    return OriginalRequestResolution(original, 'observed_original_commit')
