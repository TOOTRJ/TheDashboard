"""Immutable source recipes reconstructed through public original-byte parsers.

Recipe digests and original database rows are inputs to an authenticated reader,
not substitutes for that authentication.  No state object is reconstructed by
casting a database dictionary into one of the kernel's sealed source classes.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass

from ..market import provider_acquisition_v3 as acquisition
from ..market import provider_derivation_v3 as derivation
from ..market import prospective_source_v3 as source
from .prospective_runtime import RuntimeRefused, _encoded, _decoded

FORMAT = 'dashboard-prospective-source-recipe-v1'
MAX_RECIPE_BYTES = 8 * 1024 * 1024


def _require(condition):
    if not condition:
        raise RuntimeRefused('invalid_original_source_recipe')


@dataclass(frozen=True, slots=True)
class SourceRecipe:
    wire: bytes

    def __post_init__(self):
        value = self.to_dict()
        _require(type(value) is dict and set(value) == {'format', 'kind', 'sha256', 'inputs'}
            and value['format'] == FORMAT and value['kind'] in {'mark', 'history', 'series'})
        acquisition.digest(value['sha256'])

    def to_dict(self):
        return acquisition.read_json(self.wire, MAX_RECIPE_BYTES, exact=True)

    @property
    def kind(self):
        return self.to_dict()['kind']

    @property
    def sha256(self):
        return self.to_dict()['sha256']


def _recipe(kind, artifact, inputs):
    return SourceRecipe(acquisition.canonical({'format': FORMAT, 'kind': kind,
        'sha256': artifact.sha256, 'inputs': inputs}))


def mark_recipe(price, genesis, block_time, binding, clock, reference):
    """Preserve all three original capsule wires, including original raw bodies."""
    observed = derivation.derive_observation(price, genesis, block_time, binding, clock,
        observation_id=reference.observation_id)
    mark = source.capture_mark(observed, reference)
    data = asdict(binding)
    # JSON primitives alone cannot retain tuple structure; the decoder restores
    # these explicitly before IssuerBinding performs its public validation.
    data['endpoint_bindings'] = [list(pair) for pair in binding.endpoint_bindings]
    inputs = {'binding': data, 'clock': _encoded(asdict(clock)),
        'reference': _encoded(asdict(reference)),
        'capsules': [item.wire.decode('utf-8') for item in (price, genesis, block_time)]}
    return mark, _recipe('mark', mark, inputs)


def history_recipe(marks, reference, *, previous=None):
    """Retain the exact complete inventory plus its original completion clock."""
    marks = tuple(marks)
    frozen = source.freeze_records(marks, reference)
    history = source.derive_sampled_history(frozen, previous=previous,
        expected_previous_sha256=None if previous is None else previous.sha256)
    return history, _recipe('history', history, {
        'marks': [item.sha256 for item in marks], 'reference': _encoded(asdict(reference)),
        'previous_history_sha256': None if previous is None else previous.sha256})


def series_recipe(history):
    series = source.derive_close_series(history, expected_history_sha256=history.sha256)
    return series, _recipe('series', series, {'history_sha256': history.sha256})


class SourceRecipeReader:
    """Scope-pinned recipe reader with a caller-managed cache.

    ``read_original(kind, digest)`` returns immutable SourceRecipe bytes from the
    already verified owner/run storage context.  Cache entries can be discarded
    between restart scans; every miss reconstructs by parsing original bytes.
    """
    def __init__(self, owner_id, run_id, read_original):
        acquisition.uuid(owner_id); acquisition.uuid(run_id)
        self.owner_id, self.run_id = owner_id, run_id
        self._read_original = read_original
        self._cache, self._active = {}, set()

    def clear_cache(self):
        _require(not self._active)
        self._cache.clear()

    def retain(self, dependencies):
        """Release derived objects while keeping all original recipes durable."""
        _require(not self._active and type(dependencies) is set)
        self._cache = {key: value for key, value in self._cache.items() if key in dependencies}

    @property
    def cached_count(self):
        return len(self._cache)

    def __call__(self, kind, sha256):
        _require(kind in {'mark', 'history', 'series'})
        acquisition.digest(sha256)
        key = kind, sha256
        if key in self._cache:
            return self._cache[key]
        _require(key not in self._active)
        self._active.add(key)
        try:
            recipe = SourceRecipe(self._read_original(kind, sha256))
            _require((recipe.kind, recipe.sha256) == key)
            inputs = recipe.to_dict()['inputs']
            _require(type(inputs) is dict)
            if kind == 'mark':
                _require(set(inputs) == {'binding', 'clock', 'reference', 'capsules'})
                binding_data = dict(inputs['binding'])
                binding_data['endpoint_bindings'] = tuple(tuple(pair) for pair in binding_data['endpoint_bindings'])
                binding = acquisition.IssuerBinding(**binding_data)
                _require((binding.owner_id, binding.run_id) == (self.owner_id, self.run_id)
                    and type(inputs['capsules']) is list and len(inputs['capsules']) == 3)
                capsules = [acquisition.decode_capsule(raw.encode('utf-8'), binding)
                    for raw in inputs['capsules']]
                artifact, replay = mark_recipe(*capsules, binding,
                    acquisition.ClockBound(**_decoded(inputs['clock'])),
                    source.RecordReference(**_decoded(inputs['reference'])))
            elif kind == 'history':
                _require(set(inputs) == {'marks', 'reference', 'previous_history_sha256'}
                    and type(inputs['marks']) is list and len(inputs['marks']) <= 5000)
                previous = inputs['previous_history_sha256']
                previous = None if previous is None else self('history', previous)
                marks = [self('mark', digest) for digest in inputs['marks']]
                reference = source.SealReference(**_decoded(inputs['reference']))
                _require((reference.owner_id, reference.run_id) == (self.owner_id, self.run_id))
                artifact, replay = history_recipe(marks, reference, previous=previous)
            else:
                _require(set(inputs) == {'history_sha256'})
                artifact, replay = series_recipe(self('history', inputs['history_sha256']))
            _require(artifact.sha256 == sha256 and replay.wire == recipe.wire)
            self._cache[key] = artifact
            return artifact
        finally:
            self._active.remove(key)


class SourceRecipeStore:
    """Async durable recipe operations plus the pure model's synchronous reader.

    The SQL journal owns authentication, immutable insert and readback.  This
    facade only caches originals that it has read back and checked byte for byte.
    Inventory pages can be smaller than requested; an empty page ends the scan.
    """
    def __init__(self, journal, owner_id, run_id):
        self._journal = journal
        self._wires, self._order, self._sequence = {}, {}, 0
        self._lock = asyncio.Lock()
        self.reader = SourceRecipeReader(owner_id, run_id,
            lambda kind, sha256: self._wires[(kind, sha256)])

    async def restore(self):
        async with self._lock:
            while True:
                rows = await self._journal.artifact_inventory(after_sequence=self._sequence, limit=100)
                if not rows:
                    break
                for row in rows:
                    # SQL identity allocation is global and nontransactional;
                    # rolled-back inserts or another scoped run may leave gaps.
                    _require(type(row['sequence']) is int and row['sequence'] > self._sequence)
                    recipe = SourceRecipe(row['wire'])
                    key = row['kind'], row['sha256']
                    _require((recipe.kind, recipe.sha256) == key
                        and (key not in self._wires or self._wires[key] == recipe.wire))
                    self._wires[key], self._order[key] = recipe.wire, row['sequence']
                    self._sequence = row['sequence']

    async def put(self, kind, sha256, wire):
        recipe = SourceRecipe(wire)
        _require((recipe.kind, recipe.sha256) == (kind, sha256))
        original = await self._journal.put_artifact(kind, sha256, wire)
        _require(type(original) is bytes and original == wire)
        old = self._wires.get((kind, sha256))
        _require(old is None or old == original)
        self._wires[kind, sha256] = original
        return original

    async def get(self, kind, sha256):
        original = await self._journal.get_artifact(kind, sha256)
        if original is None:
            return None
        recipe = SourceRecipe(original)
        _require((recipe.kind, recipe.sha256) == (kind, sha256))
        old = self._wires.get((kind, sha256))
        _require(old is None or old == original)
        self._wires[kind, sha256] = original
        return original

    async def scan(self, kind):
        _require(kind in {'mark', 'history', 'series'})
        await self.restore()
        keys = sorted((key for key in self._wires if key[0] == kind),
            key=lambda key: self._order.get(key, 2**63))
        return [(digest, self._wires[(role, digest)]) for role, digest in keys]
