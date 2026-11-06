"""Pure all-opportunity fee scenarios; no execution, quotes or market inference.

The population is declared by the caller, not authenticated or discovered here.
Its fees use the existing provenance contract. An unresolved row prevents complete
population totals; it is never silently discarded or assigned a zero cost.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from .fee_provenance import FeeLedger, FeeProvenanceError, OUTCOMES, _amount, _text, CURRENCIES

VERSION = 'all-opportunity-cost-scenarios-v1'
STATUSES = frozenset({'missing_quote', 'assembly_refused', 'not_submitted', 'attempted'})
MAX_OPPORTUNITIES = 128
MAX_ATTEMPTS_PER_OPPORTUNITY = 8
MAX_TOTAL_ATTEMPTS = 512
MAX_INPUT_BYTES = 2_097_152
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z', re.ASCII)
_HASH = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)


class OpportunityCostError(ValueError):
    def __init__(self, code='opportunity_invalid'):
        allowed = {'opportunity_invalid', 'opportunity_capacity',
                   'opportunity_duplicate', 'opportunity_sequence', 'opportunity_fee_refused'}
        self.code = code if code in allowed else 'opportunity_invalid'
        super().__init__('All-opportunity fee scenario refused the evidence.')


def _identity(value, pattern):
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise OpportunityCostError()


def _fee(value):
    if type(value) is not FeeLedger:
        raise OpportunityCostError()
    try:
        value.__post_init__()
    except FeeProvenanceError:
        raise OpportunityCostError('opportunity_fee_refused') from None


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


@dataclass(frozen=True, slots=True)
class ScenarioAttempt:
    attempt_id: str
    evidence_sha256: str
    fees: FeeLedger

    def __post_init__(self):
        _identity(self.attempt_id, _ID)
        _identity(self.evidence_sha256, _HASH)
        _fee(self.fees)

    def to_dict(self):
        return dict(attempt_id=self.attempt_id, evidence_sha256=self.evidence_sha256,
                    fees=self.fees.to_dict())


@dataclass(frozen=True, slots=True)
class ScenarioOpportunity:
    opportunity_id: str
    status: str
    evidence_sha256: str
    attempts: tuple[ScenarioAttempt, ...] = ()
    unattempted_fees: FeeLedger | None = None

    def __post_init__(self):
        _identity(self.opportunity_id, _ID)
        _identity(self.evidence_sha256, _HASH)
        if (type(self.status) is not str or self.status not in STATUSES or
                type(self.attempts) is not tuple or len(self.attempts) > MAX_ATTEMPTS_PER_OPPORTUNITY or
                any(type(v) is not ScenarioAttempt for v in self.attempts)):
            raise OpportunityCostError()
        if self.status == 'attempted':
            if not self.attempts or self.unattempted_fees is not None:
                raise OpportunityCostError()
        elif self.attempts:
            raise OpportunityCostError()
        if self.unattempted_fees is not None:
            _fee(self.unattempted_fees)
            if self.unattempted_fees.outcome != 'rejected_before_submission':
                raise OpportunityCostError()
        terminal = False
        for attempt in self.attempts:
            attempt.__post_init__()
            if terminal:
                raise OpportunityCostError('opportunity_sequence')
            # New attempts after uncertainty need an independent reconciliation
            # protocol. This report cannot infer it or replace an original ID.
            terminal = attempt.fees.outcome in {'success', 'uncertain'}

    def to_dict(self):
        return dict(opportunity_id=self.opportunity_id, status=self.status,
                    evidence_sha256=self.evidence_sha256,
                    attempts=[v.to_dict() for v in self.attempts],
                    unattempted_fees=None if self.unattempted_fees is None else self.unattempted_fees.to_dict())


def _add(group, values):
    for currency, text in values.items():
        group[currency] = group.get(currency, 0) + _amount(text, currency)


def _formatted(group):
    values = {currency: _text(units, CURRENCIES[currency]) for currency, units in sorted(group.items())}
    for currency, text in values.items():
        _amount(text, currency)  # Population totals stay inside the currency bound.
    return values


def summarize_opportunities(scenario_id, opportunities, *, scenario_evidence_sha256):
    """Review every declared opportunity and retain exact, separate currencies.

    Cost per completed flow uses costs over the ENTIRE population as numerator,
    including failed opportunities and failed attempts preceding a success. The
    denominator is the count of opportunities ending in success. Ratios remain
    exact numerator/denominator pairs; fractional lamports are not rounded.
    """
    _identity(scenario_id, _ID)
    _identity(scenario_evidence_sha256, _HASH)
    if type(opportunities) is not tuple or not 1 <= len(opportunities) <= MAX_OPPORTUNITIES:
        raise OpportunityCostError('opportunity_capacity')
    if any(type(v) is not ScenarioOpportunity for v in opportunities):
        raise OpportunityCostError()
    for opportunity in opportunities:
        opportunity.__post_init__()
    if sum(len(v.attempts) for v in opportunities) > MAX_TOTAL_ATTEMPTS:
        raise OpportunityCostError('opportunity_capacity')
    ids = [v.opportunity_id for v in opportunities]
    attempt_ids = [a.attempt_id for v in opportunities for a in v.attempts]
    if len(ids) != len(set(ids)) or len(attempt_ids) != len(set(attempt_ids)):
        raise OpportunityCostError('opportunity_duplicate')
    inputs = dict(version=VERSION, scenario_id=scenario_id,
                  scenario_evidence_sha256=scenario_evidence_sha256,
                  opportunities=[v.to_dict() for v in opportunities])
    raw = _wire(inputs)
    if len(raw) > MAX_INPUT_BYTES:
        raise OpportunityCostError('opportunity_capacity')

    groups = {name: {} for name in ('additional_account_debits',
              'included_in_quote_disclosure', 'sponsor_additional_debits')}
    statuses = {name: 0 for name in sorted(STATUSES)}
    outcomes = {name: 0 for name in sorted(OUTCOMES)}
    rows = []
    completed = 0
    unresolved_opportunities = 0
    resolved_ledgers = 0
    total_ledgers = 0
    source_components = set()
    source_kinds = {}

    def review_ledger(ledger):
        nonlocal resolved_ledgers, total_ledgers
        total_ledgers += 1
        for charge in ledger.charges:
            # Explicitly excluded charges are not debited. Potentially charged
            # uncertain records still reserve their provenance identity.
            if ledger.outcome != 'uncertain' and ledger.outcome not in charge.charged_on:
                continue
            key = (charge.source_ref, charge.kind)
            if key in source_components:
                raise OpportunityCostError('opportunity_duplicate')
            source_components.add(key)
            source_kinds.setdefault(charge.source_ref, set()).add(charge.kind)
            if {'network_priority_and_tip', 'tip'} <= source_kinds[charge.source_ref]:
                raise OpportunityCostError('opportunity_duplicate')
        result = ledger.review()
        if result['resolved']:
            resolved_ledgers += 1
            for name in groups:
                _add(groups[name], result[name])
        return result

    try:
        for opportunity in opportunities:
            statuses[opportunity.status] += 1
            reviews = []
            if opportunity.status == 'attempted':
                for attempt in opportunity.attempts:
                    outcomes[attempt.fees.outcome] += 1
                    reviews.append(dict(attempt_id=attempt.attempt_id,
                        evidence_sha256=attempt.evidence_sha256,
                        fee_review=review_ledger(attempt.fees)))
                success = opportunity.attempts[-1].fees.outcome == 'success'
                resolved = all(v['fee_review']['resolved'] for v in reviews)
                missing = None
            else:
                success = False
                missing = 'unattempted_fee_evidence_missing' if opportunity.unattempted_fees is None else None
                reviews = [] if missing else [dict(attempt_id=None,
                    evidence_sha256=opportunity.evidence_sha256,
                    fee_review=review_ledger(opportunity.unattempted_fees))]
                resolved = not missing and all(v['fee_review']['resolved'] for v in reviews)
            completed += int(success)
            unresolved_opportunities += int(not resolved)
            rows.append(dict(opportunity_id=opportunity.opportunity_id, status=opportunity.status,
                evidence_sha256=opportunity.evidence_sha256, completed_successfully=success,
                accounting_resolved=bool(resolved), missing_evidence=missing, fee_reviews=reviews))
        known = {name: _formatted(group) for name, group in groups.items()}
    except FeeProvenanceError:
        raise OpportunityCostError('opportunity_fee_refused') from None
    complete = unresolved_opportunities == 0
    total = known['additional_account_debits'] if complete else None

    def ratio(denominator):
        if total is None or denominator == 0:
            return None
        return {currency: dict(numerator_amount=amount, denominator=denominator)
                for currency, amount in total.items()}

    return dict(version=VERSION, scope='declared_all_opportunity_fee_scenarios_only',
        scenario_id=scenario_id, scenario_evidence_sha256=scenario_evidence_sha256,
        population_sha256=hashlib.sha256(raw).hexdigest(), opportunities=len(opportunities),
        attempts=len(attempt_ids), opportunity_status_counts=statuses, attempt_outcome_counts=outcomes,
        completed_opportunities=completed, unresolved_opportunities=unresolved_opportunities,
        fee_ledgers=total_ledgers, resolved_fee_ledgers=resolved_ledgers,
        known_subtotals_from_fully_resolved_ledgers=known,
        complete_population_totals=known if complete else None,
        cost_per_opportunity=ratio(len(opportunities)), cost_per_completed_flow=ratio(completed),
        ratio_numerator='all_population_additional_account_debits',
        no_completed_flow=completed == 0, currency_conversion='none', opportunity_reviews=rows,
        calibration=False, population_completeness_verified=False,
        provider_authentication=False, quote_completeness_verified=False,
        settlement_authority=False, historical_replay_authority=False, paper_integration=False,
        live_trading_authority=False)
