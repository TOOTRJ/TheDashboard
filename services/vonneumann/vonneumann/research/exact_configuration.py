"""Strict primitive configuration checks for the two provider GA research models.

This validates evidence before configuration reconstruction. It creates no
runtime state, version conversion, database admission or restoration authority.
"""
from __future__ import annotations

import json


class ConfigurationFormatError(ValueError):
    """Configuration differs from its reviewed field/type/policy contract."""


_VARIABLE_PATHS = frozenset({
    ('initial_cash',), ('seed_capital',), ('search_seed',),
    ('execution', 'config', 'fee_bps'),
    ('execution', 'config', 'half_spread_bps'),
    ('execution', 'config', 'slippage_bps'),
    ('lifecycle_policy', 'account_loss_bps'),
    ('source_policy', 'epoch'),
})


def validate_configuration(value, template_wire: bytes) -> None:
    """Match a trusted immutable template before consuming caller scalar values.

    Only the documented string-valued run settings vary. Their canonical values
    and economic/range relationships are checked by the model constructor next.
    All remaining headers and policies require exact types and values. Recursion
    follows the small trusted template; unknown keys, extra list items, cycles,
    numeric aliases and unsupported Python subclasses cannot expand the walk.
    """
    expected = json.loads(template_wire)

    def fail():
        raise ConfigurationFormatError('Noncanonical provider GA configuration')

    def match(actual, reviewed, path=()):
        kind = type(reviewed)
        if type(actual) is not kind:
            fail()
        if kind is dict:
            # Reject unsupported key objects before dictionary comparison can
            # invoke their equality/hash methods against trusted policy keys.
            if (len(actual) != len(reviewed)
                    or any(type(key) is not str or len(key) > 75 for key in actual)
                    or actual.keys() != reviewed.keys()):
                fail()
            for key, item in reviewed.items():
                match(actual[key], item, path + (key,))
        elif kind is list:
            if len(actual) != len(reviewed):
                fail()
            for index, item in enumerate(reviewed):
                match(actual[index], item, path + (index,))
        elif path in _VARIABLE_PATHS:
            # Every variable is a bounded plain string, never a JSON number.
            if kind is not str or not 1 <= len(actual) <= 75:
                fail()
        elif kind not in (str, int, bool, type(None)) or actual != reviewed:
            fail()

    match(value, expected)
