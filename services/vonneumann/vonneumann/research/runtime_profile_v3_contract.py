"""Inert forward real-provider profile proposal, never a model or runtime.

Only standard-library canonical config validation. No v2 relabeling, provider
client, data acquisition, DB capability, state reconstruction, lease or activation.
The reserved names below are proposals, not implemented native wire formats.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from uuid import UUID
from types import MappingProxyType

FORMAT = 'paper-provider-runtime-profile-proposal-v3'
MAX_PROFILE_BYTES = 32768
MINT = 'So11111111111111111111111111111111111111112'
GENESIS = '5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d'
PROPOSED_VERSIONS = MappingProxyType({
    'configuration': 'ga-provider-paper-config-v3',
    'model': 'ga-provider-paper-model-v3',
    'transition': 'ga-provider-paper-transition-v3',
    'assessment': 'ga-provider-paper-assessment-v3',
    'source': 'ga-provider-paper-source-v3',
    'record': 'ga-provider-acquisition-record-v3',
    'observation': 'ga-provider-accepted-observation-v3',
    'history_manifest': 'ga-provider-paper-history-manifest-v3',
    'checkpoint': 'ga-provider-paper-checkpoint-v3',
    'component': 'ga-provider-paper-component-v3',
    'command': 'ga-provider-paper-compact-command-v3',
    'receipt': 'ga-provider-paper-native-receipt-v3',
    'projection': 'ga-provider-paper-projection-v3',
    'readback': 'ga-provider-paper-readback-v3',
    'original_lookup': 'ga-provider-paper-original-command-readback-v3',
    'epoch_rollover': 'ga-provider-paper-epoch-rollover-v3',
})


class ProfileProposalError(ValueError):
    def __init__(self): super().__init__('Forward paper profile proposal is invalid or unsupported')


def _require(condition):
    if not condition: raise ProfileProposalError()


def _uuid(value):
    _require(type(value) is str and len(value) == 36)
    try: _require(str(UUID(value)) == value)
    except ValueError: raise ProfileProposalError() from None
    return value


def _decimal(value, maximum, minimum=0):
    _require(type(value) is str and re.fullmatch(r'0|[1-9][0-9]{0,19}', value, re.ASCII) is not None)
    _require(minimum <= int(value) <= maximum)
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def _template(owner, run, market_epoch, acquisition_epoch, search_seed, account_loss_bps):
    for identity in (owner, run, market_epoch, acquisition_epoch): _uuid(identity)
    _require(market_epoch != acquisition_epoch)
    _decimal(search_seed, 2**64 - 1); _decimal(account_loss_bps, 10000, 1)
    return {
        'format': FORMAT, 'status': 'review_only_not_implemented',
        'scope': {'owner_id': owner, 'run_id': run},
        'versions': dict(PROPOSED_VERSIONS),
        'market': {'chain': 'solana', 'genesis_hash': GENESIS, 'mint': MINT, 'asset': 'SOL/USD',
            'account_currency': 'USD', 'valuation': 'reference_mark', 'source': 'recorded_provider_observations_proposed_v3',
            'execution': 'paper_usd_reference_uncalibrated', 'cash_scale': '36', 'price_scale': '18', 'quantity_scale': '18'},
        'search': {'algorithm': 'genetic_algorithm', 'genes': ['ema_fast', 'ema_slow'],
            'fast_domain': ['3', '12'], 'slow_domain': ['15', '60'], 'population': '8',
            'horizon_seconds': '3600', 'candle_seconds': '900', 'seed': search_seed,
            'mutation_policy': 'ema-period-triangular-integer-v1',
            'fitness_policy': 'equity-roi-historical-dd-v1', 'fitness_status': 'provisional_heuristic',
            'account_loss_bps': account_loss_bps, 'economic_changes': 'none_without_separate_review'},
        'epochs': {'market_epoch': market_epoch, 'acquisition_epoch': acquisition_epoch,
            'monotonic_scope': 'one_acquisition_process_epoch_only', 'restart': 'explicit_head_bound_epoch_rollover',
            'old_receipts': 'immutable_historical_only_no_freshness_rebase', 'sequence': 'preserve_run_counter',
            'evaluation_gap': 'explicit_withheld_abort_before_selection_then_authorized_restart'},
        'price': {'provider': 'jupiter-price-v3', 'method': 'GET', 'endpoint': 'https://api.jup.ag/price/v3',
            'parameters': {'ids': MINT}, 'auth': 'private_x_api_key_external_to_profile',
            'max_body_bytes': '131072', 'missing_mint': 'refuse', 'created_at': 'not_price_freshness',
            'block_id': 'required_source_reference_not_finality'},
        'rpc': {'methods': ['getGenesisHash', 'getBlockTime'], 'endpoint': 'private_operator_binding_only',
            'max_body_bytes': '65536', 'archive_request_response': True,
            'source_time': 'estimated_block_production_not_provider_publication',
            'missing_time': 'refuse', 'cache': 'retain_original_observation_identity_and_age'},
        'history': {'provider': 'birdeye-ohlcv-v3', 'method': 'GET',
            'endpoint': 'https://public-api.birdeye.so/defi/v3/ohlcv',
            'parameters': {'address': MINT, 'type': '1m', 'mode': 'range', 'currency': 'usd',
                'chart_type': 'price', 'ui_amount_mode': 'raw', 'padding': 'false', 'outlier': 'false'},
            'range_fields': ['time_from', 'time_to'], 'auth': 'private_x_api_key_external_to_profile',
            'max_body_bytes': '4194304', 'max_response_rows': '5000', 'warmup_minutes': '915',
            'warmup_bars': '61', 'retained_bars': '64', 'completion_margin_us': '5000000',
            'window': 'complete_minutes_in_half_open_requested_range',
            'excluded_rows': 'validate_every_row_then_exclude_older_or_forming',
            'gaps': 'refuse_no_padding', 'revisions': 'refuse_conflicting_consumed_overlap',
            'scaled_tokens': 'refuse_except_unscaled_null_or_one_multiplier',
            'outlier_interpretation': 'false_filters_outliers_documented_not_provider_measured'},
        'provenance': {'recording': 'authenticated_scoped_observer_required_not_implemented',
            'raw_bytes': 'immutable_owner_run_bound_pins_required',
            'canonical_request': 'no_secret_headers_or_private_rpc_url',
            'receipts': 'actual_utc_and_monotonic_acquisition_clocks',
            'derivation': 'independently_reparse_original_bytes_and_bind_observation_ids',
            'authenticity': 'hashes_do_not_authenticate_provider_origin_or_historical_availability'},
        'freshness': {'max_receipt_age_us': '5000000', 'max_source_age_us': '30000000',
            'future_tolerance_us': '2000000', 'acquisition_deadline_us': '5000000',
            'status': 'proposed_existing_bounds_require_new_final_boundary_acceptance',
            'repeated_mark': 'no_new_sequence_or_receipt_clock_fabrication',
            'request_retry': 'none_until_separate_bounded_quota_review'},
        'retention': {'jupiter': 'user_approved_for_backtesting', 'birdeye_rights': 'unverified',
            'birdeye_coverage': 'unverified_for_target_windows', 'policy': 'pin_before_archive_no_pruning_from_profile'},
        'admission': {'mode': 'closed', 'continuous_quota': 'unverified', 'cadence': None,
            'run_command_budget': None, 'hot_byte_budget': None, 'raw_observation_budget': None,
            'archive_budget': None, 'stop_budget': 'independent_reserved_slot_and_bytes_required',
            'uncertain_command': 'lookup_original_id_hash_wire_before_any_next_command'},
        'implementation_bindings': {'worker_package_sha256': None, 'parser_sha256': None,
            'model_kernel_sha256': None, 'requirements_lock_sha256': None, 'semantic_validator_sha256': None,
            'native_catalog_sha256': None, 'projection_catalog_sha256': None},
        'authority': {'provider_request': False, 'native_admission': False, 'model_restoration': False,
            'lease_acquisition': False, 'hosted_activation': False, 'live_trading': False},
    }


def _validate(value):
    _require(type(value) is dict and type(value.get('scope')) is dict
        and type(value.get('search')) is dict and type(value.get('epochs')) is dict)
    try:
        expected = _template(value['scope']['owner_id'], value['scope']['run_id'],
            value['epochs']['market_epoch'], value['epochs']['acquisition_epoch'],
            value['search']['seed'], value['search']['account_loss_bps'])
        # Canonical bytes compare avoids bool/int alias equality and catches
        # every unknown/missing/nested key or unapproved value recursively.
        _require(_canonical(value) == _canonical(expected))
    except ProfileProposalError: raise
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError, UnicodeError):
        raise ProfileProposalError() from None


@dataclass(frozen=True, slots=True, init=False)
class ProfileProposal:
    _wire: bytes

    def __init__(self, *args, **kwargs): raise ProfileProposalError()

    def to_dict(self): return json.loads(self._wire)

    @property
    def wire(self): return self._wire

    @property
    def sha256(self): return hashlib.sha256(self._wire).hexdigest()

    @property
    def native_admission(self): return False

    @property
    def hosted_activation(self): return False

    @property
    def lease_acquisition(self): return False


def proposal(owner_id, run_id, market_epoch, acquisition_epoch, *, search_seed='0', account_loss_bps='3000'):
    """Construct only a closed review proposal from explicit caller identifiers."""
    value = _template(owner_id, run_id, market_epoch, acquisition_epoch, search_seed, account_loss_bps)
    return decode_profile(_canonical(value))


def decode_profile(raw):
    """Bounded duplicate/number/unknown-refusing proposal decoder, no I/O."""
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_PROFILE_BYTES)
    def number(_): raise ProfileProposalError()
    def pairs(items):
        _require(len(items) <= 128); result = {}
        for key, value in items:
            _require(key not in result); result[key] = value
        return result
    try:
        value = json.loads(raw.decode('utf-8', errors='strict'), object_pairs_hook=pairs,
            parse_int=number, parse_float=number, parse_constant=number)
        _require(_canonical(value) == raw)
        _validate(value)
    except ProfileProposalError: raise
    except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError): raise ProfileProposalError() from None
    result = object.__new__(ProfileProposal); object.__setattr__(result, '_wire', raw); return result


def refuse_runtime_use(profile):
    """Even a valid proposal is never an implemented startup/native capability."""
    _require(type(profile) is ProfileProposal)
    decode_profile(profile.wire)
    raise ProfileProposalError()
