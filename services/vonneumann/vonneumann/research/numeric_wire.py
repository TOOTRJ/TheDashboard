"""Canonical research JSON numbers, safe through JavaScript JSON round trips.

Decoding returns bounded primitive evidence only, never a runtime or authority.
Every integer/finite binary64 value is tagged; untagged JSON numbers are refused.
"""
import json
import math
import re

from ..db.command_protocol import CommandValidationError, canonical_json

MAX_BYTES = 262144
MAX_NODES = 20000
MAX_DEPTH = 64
TAGS = {'$integer', '$float64'}


def _fail(message):
    raise CommandValidationError(message)


def _walk(value, *, decode):
    visits, budget, active = [0], [0], set()

    def visit(item, depth=0):
        visits[0] += 1
        budget[0] += 4
        if visits[0] > MAX_NODES or depth > MAX_DEPTH or budget[0] > MAX_BYTES:
            _fail('Numeric evidence exceeds structural capacity')
        kind = type(item)
        if kind is str:
            if len(item) > 16384 or len(item.encode('utf-8')) > 16384 or '\x00' in item:
                _fail('Numeric evidence string exceeds capacity')
            budget[0] += len(item.encode('utf-8'))
            if budget[0] > MAX_BYTES:
                _fail('Numeric evidence exceeds byte traversal capacity')
            return item
        if item is None or kind is bool:
            return item
        if kind is int:
            if decode or item.bit_length() > 256:
                _fail('Untagged or oversized integer')
            return {'$integer': str(item)}
        if kind is float:
            if decode or not math.isfinite(item):
                _fail('Untagged or nonfinite float')
            return {'$float64': item.hex()}
        if kind not in (dict, list) or len(item) > 4096 or id(item) in active:
            _fail('Numeric evidence requires bounded acyclic exact JSON')
        active.add(id(item))
        try:
            if kind is list:
                return [visit(child, depth + 1) for child in item]
            if any(type(key) is not str for key in item):
                _fail('Numeric evidence keys must be strings')
            if TAGS.intersection(item):
                if not decode or len(item) != 1:
                    _fail('Reserved numeric tag collision')
                key, text = next(iter(item.items()))
                if type(text) is not str or len(text) > 100:
                    _fail('Invalid numeric tag')
                if key == '$integer':
                    if not re.fullmatch(r'0|-?[1-9][0-9]*', text):
                        _fail('Noncanonical integer tag')
                    number = int(text)
                    if number.bit_length() > 256:
                        _fail('Integer tag exceeds capacity')
                    return number
                try:
                    number = float.fromhex(text)
                except ValueError:
                    _fail('Invalid binary64 tag')
                if not math.isfinite(number) or number.hex() != text:
                    _fail('Noncanonical binary64 tag')
                return number
            result = {}
            for key, child in item.items():
                visit(key, depth + 1)
                result[key] = visit(child, depth + 1)
            return result
        finally:
            active.remove(id(item))

    try:
        return visit(value)
    except (UnicodeError, RecursionError, OverflowError):
        _fail('Invalid numeric evidence')


def encode(value, *, maximum=MAX_BYTES):
    wire = canonical_json(_walk(value, decode=False))
    if len(wire) > maximum:
        _fail('Numeric wire exceeds capacity')
    return wire


def decode(wire, *, maximum=MAX_BYTES):
    if type(wire) is not bytes or len(wire) > maximum:
        _fail('Numeric wire exceeds capacity')

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail('Duplicate numeric evidence key')
            result[key] = value
        return result

    try:
        tagged = json.loads(wire, object_pairs_hook=pairs)
        if canonical_json(tagged) != wire:
            _fail('Noncanonical numeric wire')
        result = _walk(tagged, decode=True)
        if encode(result, maximum=maximum) != wire:
            _fail('Numeric evidence round trip differs')
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        _fail('Invalid numeric wire')
