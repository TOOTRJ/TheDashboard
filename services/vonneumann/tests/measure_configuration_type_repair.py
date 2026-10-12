"""Reproduce the strict configuration repair without credentials or I/O authority.

Run explicitly to create a new measurement; the historical defect and portable
model artifacts are preserved. This never accepts a simulation command.
"""
import hashlib
import json
from pathlib import Path
import platform

from tests.security_support import deny_network
from tests.test_provider_contract import OWNER, RUN, EPOCH, WALL, seed_bundle, source_inputs
from tests.test_research_configuration_types import rehashed_configuration, leaves
from vonneumann.db.command_protocol import CommandValidationError
from vonneumann.research import provider_ga_model as v1, partitioned_checkpoint as cp1
from vonneumann.research import provider_portable_ga_model as v2, portable_partitioned_checkpoint as cp2

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT / 'research/2026-10-12-config-type-review.json'
OUTPUT = ROOT / 'research/configuration-type-repair-measurements.json'
SOURCES = (
    'vonneumann/research/exact_configuration.py',
    'vonneumann/research/provider_ga_model.py',
    'vonneumann/research/provider_portable_ga_model.py',
    'vonneumann/research/provider_checkpoint.py',
    'vonneumann/research/provider_portable_checkpoint.py',
    'vonneumann/research/partitioned_checkpoint.py',
    'vonneumann/research/portable_partitioned_checkpoint.py',
    'tests/test_research_configuration_types.py',
    'tests/test_portable_ga_model.py',
    'tests/measure_configuration_type_repair.py',
)


def measure():
    rows = []
    with deny_network():
        for model, checkpoint in ((v1, cp1), (v2, cp2)):
            ledger = model.SimulationLedger(OWNER, RUN)
            candidate = model.bootstrap(model.GAConfig('genetic_algorithm', OWNER, RUN,
                asset='SOL/USD', source_epoch=EPOCH), seed_bundle(), source_inputs(WALL), ledger=ledger)
            capture = checkpoint.capture_owned_candidate(candidate)
            original = candidate.state.to_dict()['engine']['config']
            original_value = original['lifecycle_policy']['max_lifespan_seconds']
            assert type(original_value) is int and original_value == 0
            changed = json.loads(json.dumps(original))
            changed['lifecycle_policy']['max_lifespan_seconds'] = False
            manifest, components = rehashed_configuration(checkpoint, capture, changed)
            try:
                checkpoint.resolve_manifest(manifest, components, owner_id=OWNER,
                    run_id=RUN, revision=candidate.state.revision)
            except CommandValidationError as error:
                actual = {'accepted': False, 'error': type(error).__name__}
            else:
                raise AssertionError('Incorrect configuration scalar was accepted')
            try:
                model._configuration({'engine': {'config': changed}})
            except model.ExactRehearsalError as error:
                construction = {'accepted': False, 'error': type(error).__name__}
            else:
                raise AssertionError('Incorrect scalar reached configuration construction')
            assert ledger.history == []
            original_hash = next(block.identity for block in capture.components
                                 if block.to_dict()['kind'] == 'configuration')
            changed_hash = next(block.identity for block in components
                                if block.to_dict()['kind'] == 'configuration')
            rows.append({'model_module': model.__name__, 'checkpoint_module': checkpoint.__name__,
                'profile': model.PROFILE, 'model_format': model.MODEL_FORMAT,
                'checkpoint_format': checkpoint.FORMAT,
                'field': 'engine.config.lifecycle_policy.max_lifespan_seconds',
                'original': {'type': 'int', 'value': 0}, 'substitution': {'type': 'bool', 'value': False},
                'configuration_component_sha256_before': original_hash,
                'configuration_component_sha256_after': changed_hash,
                'expected': 'CommandValidationError: noncanonical policy scalar type',
                'actual': actual, 'configuration_reconstruction': construction,
                'configuration_scalar_leaves': sum(1 for _ in leaves(original)),
                'simulation_ledger_accepted_commands': 0})
    historical = json.loads(HISTORICAL.read_text())
    artifact = {'format': 'dashboard-research-config-type-repair-v1', 'date': '2026-10-12',
        'task': 'PAPER-COMPACT-TYPE1',
        'scope': 'Credential-free owned bootstrap/capture and primitive configuration refusal; no complete SQL or hosted admission',
        'environment': {'python': platform.python_version(), 'platform': platform.system(),
                        'machine': platform.machine(), 'network_denied': True},
        'historical_defect_artifact': HISTORICAL.name,
        'historical_defect_artifact_sha256': hashlib.sha256(HISTORICAL.read_bytes()).hexdigest(),
        'source_before': historical['source_sha256'],
        'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES},
        'compatibility_decision': 'same_versions_canonical_wires_unchanged_stricter_rejection_only',
        'compatibility_scope': 'Original research v1/v2 headers, operator, software, canonical configuration and wire semantics stay unchanged. Incorrectly typed evidence is rejected, never normalized or reinterpreted.',
        'results': rows, 'hosted_reads_or_writes': False, 'database_or_docker_access': False,
        'credentials_used': False, 'native_admission': False, 'restoration_authority': False,
        'activation_authority': False}
    OUTPUT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'artifact': str(OUTPUT), 'versions': len(rows), 'rejected_noncanonical_boolean': True}))


if __name__ == '__main__':
    measure()
