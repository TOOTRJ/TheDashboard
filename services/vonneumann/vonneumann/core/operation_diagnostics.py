"""Fixed failure labels; never serialize exception text or provider bodies."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict

from ..market.feed import MarketFeedError
from ..market.provider_contract import ProviderSourceError

PROVIDER_CODES = frozenset((
    'unsupported_asset', 'price_invalid', 'price_missing', 'price_rate_limited',
    'price_unavailable', 'price_stale', 'source_slot_regressed',
    'source_time_invalid', 'source_time_unavailable', 'rpc_configuration',
    'rpc_invalid', 'rpc_rate_limited', 'rpc_unavailable', 'rpc_wrong_network',
    'candles_backlog', 'candles_batch_limit', 'candles_clock_invalid',
    'candles_closed', 'candles_configuration', 'candles_cursor_invalid',
    'candles_gap', 'candles_invalid', 'candles_missing', 'candles_rate_limited',
    'candles_revision', 'candles_stale', 'candles_unavailable',
    'candles_window_changed',
))
STAGES = frozenset((
    'provider_capture', 'quote_admission', 'acquisition_deadline',
    'invalid_capture', 'acquisition_start', 'service_operation',
    'bootstrap_history', 'bootstrap_settle', 'bootstrap_publish', 'capture',
    'protect_settle', 'protect_publish', 'decision_select', 'decide_settle',
    'decide_publish', 'pause_submit', 'pause_settle', 'pause_publish',
    'stop_submit', 'stop_settle', 'stop_publish', 'heartbeat', 'done',
))
# Only these literal, locally defined admission errors may cross the status
# boundary. Never serialize arbitrary exception text, even for our error type.
ADMISSION_CODES = {
    'provider acquisition admission is closed': 'acquisition_closed',
    'provider owner admission is closed': 'owner_closed',
    'controller ordinary admission is closed': 'controller_closed',
    'controller_receipt_boundary_invalid': 'receipt_boundary_invalid',
    'controller_price_acquisition_expired': 'price_acquisition_expired',
    'controller_receipt_clock_did_not_advance': 'receipt_clock_not_advanced',
    'controller_original_receipt_not_admitted': 'original_receipt_not_admitted',
    'controller_receipt_wait_budget': 'receipt_wait_budget',
}


@dataclass(frozen=True, slots=True)
class OperationFailure:
    stage: str
    category: str
    provider_code: str | None = None
    admission_code: str | None = None

    def to_dict(self):
        result = asdict(self)
        # Keep the existing wire shape when no specific local cause is known.
        if self.admission_code is None:
            del result['admission_code']
        return result


def failure_labels(stage, error):
    """Classify only owned types and allowlisted codes, including hostile errors."""
    stage = stage if type(stage) is str and stage in STAGES else 'unknown_stage'
    if isinstance(error, MarketFeedError):
        code = error.code
        return OperationFailure(stage, 'market_feed_error',
            code if type(code) is str and code in PROVIDER_CODES else 'unclassified_provider_error')
    if isinstance(error, ProviderSourceError):
        return OperationFailure(stage, 'source_validation_failed')
    if isinstance(error, asyncio.CancelledError):
        return OperationFailure(stage, 'operation_cancelled')
    if isinstance(error, TimeoutError):
        return OperationFailure(stage, 'operation_timeout')
    # Imports here avoid changing the provider/owner import graph.
    from ..db.rehearsal_owner import OperationalAdmissionError
    if isinstance(error, OperationalAdmissionError):
        args = error.args
        message = args[0] if len(args) == 1 and type(args[0]) is str else None
        return OperationFailure(stage, 'operational_admission_failed',
                                admission_code=ADMISSION_CODES.get(message))
    return OperationFailure(stage, 'unexpected_exception')
