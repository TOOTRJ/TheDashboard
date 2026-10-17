"""Pure fee-annotation/accounting contract; no quote ingestion or settlement.

All inputs are declared evidence. Validation cannot authenticate a provider,
prove that a quote includes every fee, or infer an uncertain transaction result.
Amounts retain separate denominations and are never converted implicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

VERSION = 'fee-provenance-scenarios-v1'
OUTCOMES = frozenset({'success', 'failed_processed', 'expired_unprocessed',
                      'rejected_before_submission', 'uncertain'})
KINDS = frozenset({'platform', 'network_signature', 'network_priority_and_tip',
                   'tip', 'rent', 'transfer', 'explicit_other'})
PROVENANCE = frozenset({'declared_scenario', 'quoted_estimate', 'observed_wallet', 'observed_network'})
CURRENCIES = {'USD_reference': 36, 'SOL_lamports': 0, 'USDC_atomic': 0}
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z', re.ASCII)
_DECIMAL = re.compile(r'(0|[1-9][0-9]*)(?:\.([0-9]+))?\Z', re.ASCII)


class FeeProvenanceError(ValueError):
    def __init__(self, code='fee_invalid'):
        self.code = code if code in {'fee_invalid', 'fee_double_count', 'fee_unresolved'} else 'fee_invalid'
        super().__init__('Fee provenance contract refused the evidence.')


def _amount(value, currency):
    if type(value) is not str or len(value) > 75:
        raise FeeProvenanceError()
    match = _DECIMAL.fullmatch(value)
    scale = CURRENCIES[currency]
    if match is None or len(match[2] or '') > scale:
        raise FeeProvenanceError()
    units = int(match[1]) * 10**scale + int((match[2] or '').ljust(scale, '0') or '0')
    maximum = 10**72 if currency == 'USD_reference' else 2**64 - 1
    if units > maximum or _text(units, scale) != value:
        raise FeeProvenanceError()
    return units


def _text(units, scale):
    whole, fraction = divmod(units, 10**scale)
    tail = str(fraction).rjust(scale, '0').rstrip('0') if scale else ''
    return str(whole) + ('.' + tail if tail else '')


@dataclass(frozen=True, slots=True)
class FeeCharge:
    component_id: str
    source_ref: str
    kind: str
    currency: str
    payer: str  # account, sponsor, or unknown
    amount: str | None  # None is unknown, never an implicit zero
    disposition: str  # included_in_quote or additional_debit
    provenance: str
    charged_on: tuple[str, ...]
    refundable: bool = False
    refund_amount: str | None = '0'  # None explicitly leaves refund accounting unresolved

    def __post_init__(self):
        if (any(type(v) is not str or _ID.fullmatch(v) is None
                for v in (self.component_id, self.source_ref)) or
                type(self.kind) is not str or self.kind not in KINDS or
                type(self.currency) is not str or self.currency not in CURRENCIES or
                type(self.payer) is not str or self.payer not in {'account', 'sponsor', 'unknown'} or
                type(self.disposition) is not str or self.disposition not in {'included_in_quote', 'additional_debit'} or
                type(self.provenance) is not str or self.provenance not in PROVENANCE or
                type(self.charged_on) is not tuple or not self.charged_on or
                len(self.charged_on) > 4 or any(type(v) is not str or v not in OUTCOMES - {'uncertain'} for v in self.charged_on) or
                len(set(self.charged_on)) != len(self.charged_on) or
                type(self.refundable) is not bool):
            raise FeeProvenanceError()
        if self.kind in {'network_signature', 'network_priority_and_tip', 'tip'} and not set(self.charged_on) <= {'success', 'failed_processed'}:
            raise FeeProvenanceError()
        amount = _amount(self.amount, self.currency) if self.amount is not None else None
        refund = _amount(self.refund_amount, self.currency) if self.refund_amount is not None else None
        if ((not self.refundable and self.refund_amount != '0') or
                (refund is not None and refund > 0 and (amount is None or refund > amount))):
            raise FeeProvenanceError()

    def to_dict(self):
        return {key: getattr(self, key) for key in ('component_id', 'source_ref', 'kind', 'currency',
                'payer', 'amount', 'disposition', 'provenance', 'refundable', 'refund_amount')} | {
                    'charged_on': list(self.charged_on)}

    @classmethod
    def from_dict(cls, value):
        fields = {'component_id', 'source_ref', 'kind', 'currency', 'payer', 'amount',
                  'disposition', 'provenance', 'charged_on', 'refundable', 'refund_amount'}
        if type(value) is not dict or set(value) != fields or type(value['charged_on']) is not list:
            raise FeeProvenanceError()
        return cls(**(value | {'charged_on': tuple(value['charged_on'])}))


@dataclass(frozen=True, slots=True)
class FeeLedger:
    outcome: str
    charges: tuple[FeeCharge, ...]

    def __post_init__(self):
        if (type(self.outcome) is not str or self.outcome not in OUTCOMES or
                type(self.charges) is not tuple or len(self.charges) > 32 or
                any(type(charge) is not FeeCharge for charge in self.charges)):
            raise FeeProvenanceError()
        ids, components, by_source = set(), set(), {}
        for charge in self.charges:
            charge.__post_init__()
            component = (charge.source_ref, charge.kind)
            if charge.component_id in ids or component in components:
                raise FeeProvenanceError('fee_double_count')
            ids.add(charge.component_id); components.add(component)
            by_source.setdefault(charge.source_ref, set()).add(charge.kind)
        if any({'network_priority_and_tip', 'tip'} <= kinds for kinds in by_source.values()):
            raise FeeProvenanceError('fee_double_count')

    def review(self):
        """Refuse settlement totals when outcome, charged amount/payer or refund is unknown.

        Known included charges are disclosed separately, never debited again.
        Explicit outcome exclusions are not guessed zero-valued amounts.
        """
        self.__post_init__()
        unresolved = ['transaction_outcome'] if self.outcome == 'uncertain' else []
        additional, included, sponsor, excluded = {}, {}, {}, []
        for charge in self.charges:
            if self.outcome != 'uncertain' and self.outcome not in charge.charged_on:
                excluded.append(charge.component_id)
                continue
            if charge.amount is None or charge.payer == 'unknown' or charge.refund_amount is None:
                unresolved.append(charge.component_id)
                continue
            units = _amount(charge.amount, charge.currency) - _amount(charge.refund_amount, charge.currency)
            group = included if charge.disposition == 'included_in_quote' else (additional if charge.payer == 'account' else sponsor)
            group[charge.currency] = group.get(charge.currency, 0) + units
        def formatted(group):
            result = {currency: _text(units, CURRENCIES[currency]) for currency, units in sorted(group.items())}
            for currency, amount in result.items():
                _amount(amount, currency)  # Aggregate also stays inside the declared currency budget.
            return result
        resolved = not unresolved
        return {'version': VERSION, 'scope': 'declared_fee_annotations_only', 'outcome': self.outcome,
                'resolved': resolved, 'unresolved': unresolved, 'excluded_by_explicit_outcome': excluded,
                'additional_account_debits': formatted(additional) if resolved else None,
                'included_in_quote_disclosure': formatted(included) if resolved else None,
                'sponsor_additional_debits': formatted(sponsor) if resolved else None,
                'settlement_authority': False, 'provider_authentication': False,
                'currency_conversion': 'none', 'quote_completeness_verified': False}

    def require_resolved(self):
        result = self.review()
        if not result['resolved']:
            raise FeeProvenanceError('fee_unresolved')
        return result

    def to_dict(self):
        return {'version': VERSION, 'outcome': self.outcome, 'charges': [charge.to_dict() for charge in self.charges]}

    @classmethod
    def from_dict(cls, value):
        if (type(value) is not dict or set(value) != {'version', 'outcome', 'charges'} or
                value['version'] != VERSION or type(value['charges']) is not list or len(value['charges']) > 32):
            raise FeeProvenanceError()
        return cls(value['outcome'], tuple(FeeCharge.from_dict(charge) for charge in value['charges']))
