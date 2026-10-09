"""Pure reference capture and capacity research; no runtime/network authority."""
from copy import deepcopy
import json
import unittest

from tests.security_support import OfflineTestMixin
from tests.test_provider_contract import (
    OWNER, RUN, WALL, EPOCH, MONO, WORKER, life, kernel, seed_bundle,
    source_inputs, raw_capture, source,
)
from vonneumann.core import exact_rehearsal as base
from vonneumann.db.command_protocol import CommandValidationError, PreparedCommand, canonical_json
from vonneumann.research.checkpoint_reference import (
    CheckpointReference, ReferencedTransition, encode_owned_candidate,
    expand_for_validation, jsonb_text_bytes, MAX_EXPANDED_BYTES,
)


def research_reference(candidate):
    before = candidate.transition['before']
    return CheckpointReference(OWNER, RUN, 1 if before is None else before['revision'], 'a' * 64)


def pair():
    config = life.ProviderLifecycleConfig(kernel.ExactLifecycleConfig(
        'genetic_algorithm', OWNER, RUN, asset='SOL/USD'), EPOCH)
    boot = life.bootstrap(config, seed_bundle(last_close='80'), source_inputs(WALL))
    frame = source.make_frame(raw_capture(), prior_source=boot.state.to_dict()['source'],
        epoch=EPOCH, wall_now=WALL + 1, monotonic_now=MONO + 1)
    protected = life.prepare_protective(boot.state, frame,
        source_inputs(WALL + 1, mono=MONO + 1, serial=1))
    return boot, protected


class CheckpointReferenceTests(OfflineTestMixin, unittest.TestCase):
    def test_owned_bootstrap_and_protective_expand_to_every_original_byte(self):
        for candidate in pair():
            with self.subTest(revision=candidate.state.revision):
                ref = research_reference(candidate)
                encoded = encode_owned_candidate(candidate, ref)
                expanded = expand_for_validation(encoded.to_dict(), ref, candidate.transition['before'])
                self.assertEqual(canonical_json(expanded), candidate._wire)
                self.assertEqual(encoded.expanded_bytes, candidate.payload_bytes)
                self.assertNotIn('before', encoded.to_dict()['transition'])
                self.assertEqual(encoded.wire, encode_owned_candidate(candidate, ref).wire)
        self.assertLess(encoded.payload_bytes, candidate.payload_bytes)

    def test_detached_output_and_frozen_reference_preserve_original_intent(self):
        _, candidate = pair()
        original = candidate.state.to_dict()
        ref = research_reference(candidate)
        encoded = encode_owned_candidate(candidate, ref)
        first_wire = encoded.wire
        copy = encoded.to_dict()
        copy['transition']['after']['reserve'] = '0'
        descriptor = ref.to_dict(); descriptor['sha256'] = 'b' * 64
        self.assertEqual(encoded.wire, first_wire)
        self.assertEqual(candidate.state.to_dict(), original)
        with self.assertRaises(AttributeError):
            encoded._ReferencedTransition__wire = b'changed'
        with self.assertRaises(AttributeError):
            ref.revision = 1
        with self.assertRaises(CommandValidationError):
            ReferencedTransition()

    def test_reference_rejects_wrong_owner_run_revision_and_noncanonical_descriptor(self):
        _, candidate = pair()
        ref = research_reference(candidate)
        for change in ({'owner_id': WORKER}, {'run_id': WORKER}, {'revision': 1},
                       {'revision': True}, {'sha256': 'A' * 64}, {'sha256': None},
                       {'version': True}, {'hash_policy': 'client-json'}, {'extra': 1}):
            with self.subTest(change=change), self.assertRaises(CommandValidationError):
                changed = CheckpointReference.from_dict({**ref.to_dict(), **change})
                encode_owned_candidate(candidate, changed)

    def test_raw_wire_changes_and_embedded_before_are_rejected(self):
        _, candidate = pair()
        ref = research_reference(candidate)
        encoded = encode_owned_candidate(candidate, ref)
        for change in ('version', 'before', 'hash', 'revision', 'economic', 'source'):
            altered = encoded.to_dict()
            if change == 'version': altered['model_version'] = 6
            if change == 'before': altered['transition']['before'] = candidate.transition['before']
            if change == 'hash': altered['before_reference']['sha256'] = 'b' * 64
            if change == 'revision': altered['transition']['after']['revision'] += 1
            if change == 'economic': altered['transition']['after']['reserve'] = '0'
            if change == 'source': altered['transition']['after']['source']['quote_sequence'] += 1
            with self.subTest(change=change), self.assertRaises(CommandValidationError):
                expand_for_validation(altered, ref, candidate.transition['before'])

    def test_smaller_wire_cannot_bypass_expanded_model_capacity(self):
        _, candidate = pair()
        ref = research_reference(candidate)
        encoded = encode_owned_candidate(candidate, ref)
        checkpoint = deepcopy(candidate.transition['before'])
        checkpoint['oversized_research_padding'] = 'x' * MAX_EXPANDED_BYTES
        self.assertLess(encoded.payload_bytes, MAX_EXPANDED_BYTES)
        with self.assertRaisesRegex(CommandValidationError, 'Expanded model exceeds capacity'):
            expand_for_validation(encoded.to_dict(), ref, checkpoint)
        oversized = encoded.to_dict()
        oversized['transition']['after']['oversized_research_padding'] = 'x' * MAX_EXPANDED_BYTES
        with self.assertRaisesRegex(CommandValidationError, 'Reference wire exceeds capacity'):
            expand_for_validation(oversized, ref, candidate.transition['before'])

    def test_prototype_cannot_enter_existing_runtime_command_versions(self):
        _, candidate = pair()
        encoded = encode_owned_candidate(candidate, research_reference(candidate))
        for version in (5, 6):
            with self.subTest(version=version), self.assertRaises(CommandValidationError):
                PreparedCommand.batch(OWNER, RUN, WORKER, 1, candidate.state.revision - 1,
                    candidate.operations, version=version, transition=encoded.to_dict()['transition'])
        self.assertIsInstance(json.loads(encoded.wire), dict)
        self.assertEqual(jsonb_text_bytes(json.loads(encoded.wire)), encoded.payload_bytes)
