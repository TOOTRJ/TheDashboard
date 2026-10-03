"""Bounded, deterministic evidence for reviewed optimizer/cohort continuation.

This is not a checkpoint decoder or authorization to restore, install, or retry
an engine transition. The caller must exclusively own the source during this
synchronous capture. Object types, fields, aliases, map order, numeric types,
and both private random generators are recorded explicitly. No serialization
hooks, pickle, repr, callbacks, or optimizer ask/tell methods are invoked.

CMA 0.13.1 allocates its termination history with np.empty. Only slots written
by completed tell calls are evidence. Unwritten slots are represented by null
under an explicit mask and are never read or emitted. They cannot affect this
reviewed solver before it has overwritten every slot.
"""

from __future__ import annotations

import json
import math
import random
import re
import sys

import numpy as np

from . import strategy_fork as reviewed
from .colony_config import ColonyConfig, GeneOverride
from .evaluation import EvaluatedCandidate, EvaluationCohort
from .gene_registry import GeneDomain
from .genome import Genome
from .parameter_codec import ParameterCodec
from .search_random import SearchRandomStreams
from .strategies.cma_es import CMAEvolutionStrategy, cmaes_lib
from .strategies.cohort_contract import SelectionCohort
from .strategies.differential_evolution import DifferentialEvolutionStrategy
from .strategies.genetic_algorithm import GeneticAlgorithmStrategy
from .strategies.particle_swarm import ParticleSwarmStrategy


EVIDENCE_VERSION = "optimizer-evidence-v1"
MAX_EVIDENCE_BYTES = 196_608
MAX_NODES = 20_000
MAX_DEPTH = 64
MAX_ITEMS = 4096
MAX_STRING_BYTES = 4096
MAX_ARRAY_BYTES = 65_536
MAX_INTEGER_BITS = 256

_TYPE_NAMES = {
    GeneticAlgorithmStrategy: "GeneticAlgorithmStrategy",
    DifferentialEvolutionStrategy: "DifferentialEvolutionStrategy",
    ParticleSwarmStrategy: "ParticleSwarmStrategy",
    CMAEvolutionStrategy: "CMAEvolutionStrategy",
    SearchRandomStreams: "SearchRandomStreams",
    SelectionCohort: "SelectionCohort",
    ParameterCodec: "ParameterCodec",
    ColonyConfig: "ColonyConfig",
    GeneOverride: "GeneOverride",
    GeneDomain: "GeneDomain",
    Genome: "Genome",
    EvaluatedCandidate: "EvaluatedCandidate",
    EvaluationCohort: "EvaluationCohort",
}


class OptimizerEvidenceError(ValueError):
    """State is outside the reviewed types, initialized values, or size bounds."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OptimizerEvidenceError(message)


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


class _Encoder:
    def __init__(self) -> None:
        self.seen: dict[int, int] = {}
        self.active: set[int] = set()
        self.retained: list[object] = []
        self.histories: list[np.ndarray] = []
        self.arrays: list[np.ndarray] = []
        self.nodes = 0
        self.budget = 0

    def charge(self, amount: int) -> None:
        # Bound working allocation before hex/JSON construction as well as the
        # exact final wire length. Structural overhead is conservatively counted.
        self.budget += amount
        _require(self.budget <= MAX_EVIDENCE_BYTES, "Optimizer evidence exceeds its byte budget")

    def text(self, value: str) -> str:
        _require(type(value) is str and len(value) <= MAX_STRING_BYTES,
                 "Optimizer strings must be bounded plain text")
        try:
            size = len(value.encode("utf-8"))
        except UnicodeEncodeError:
            raise OptimizerEvidenceError("Optimizer strings must be valid UTF-8") from None
        _require(size <= MAX_STRING_BYTES, "Optimizer string exceeds its byte budget")
        self.charge(len(json.dumps(value, ensure_ascii=True)))
        return value

    def value(self, value: object, depth: int = 0):
        self.nodes += 1
        _require(self.nodes <= MAX_NODES and depth <= MAX_DEPTH,
                 "Optimizer evidence exceeds its node or depth bound")
        self.charge(16)
        kind = type(value)
        if value is None or kind is bool:
            return value
        if kind is str:
            return self.text(value)
        if kind is int:
            _require(value.bit_length() <= MAX_INTEGER_BITS, "Optimizer integer exceeds its bound")
            encoded = str(value)
            self.charge(len(encoded) + 24)
            return {"type": "integer", "decimal": encoded}
        if kind in (float, np.float64):
            _require(math.isfinite(value), "Nonfinite optimizer value is not a reviewed sentinel")
            encoded = float(value).hex()
            self.charge(len(encoded) + 32)
            return {"type": "float" if kind is float else "numpy.float64", "hex": encoded}

        identity = id(value)
        _require(identity not in self.active, "Cyclic optimizer evidence is unsupported")
        if identity in self.seen:
            return {"ref": self.seen[identity]}
        index = len(self.seen)
        self.seen[identity] = index
        self.retained.append(value)  # Keep temporary RNG records from reusing ids.
        self.active.add(identity)
        try:
            result = self.compound(value, kind, depth)
            return {"node": index, **result}
        finally:
            self.active.remove(identity)

    def compound(self, value, kind, depth: int) -> dict:
        if kind in (tuple, list):
            _require(len(value) <= MAX_ITEMS, "Optimizer sequence exceeds its item bound")
            return {"type": "tuple" if kind is tuple else "list",
                    "items": [self.value(item, depth + 1) for item in value]}
        if kind is dict:
            _require(len(value) <= MAX_ITEMS and all(type(key) is str for key in value),
                     "Optimizer maps require bounded plain-string keys")
            # Order is explicit: strategy continuation can depend on map order.
            return {"type": "map", "entries": [[self.text(key), self.value(item, depth + 1)]
                                                  for key, item in value.items()]}
        if kind is np.ndarray:
            _require(not any(value is history or np.shares_memory(value, history)
                             for history in self.histories),
                     "CMA history cannot alias another optimizer field")
            self.arrays.append(value)
            return self.array(value)
        if kind is random.Random:
            return self.python_rng(value)
        if kind is np.random.RandomState:
            return self.numpy_rng(value)

        reviewed._check_fields(value)
        is_cma = cmaes_lib is not None and kind is cmaes_lib.CMA
        _require(is_cma or kind in _TYPE_NAMES, "Optimizer object type is not reviewed")
        if is_cma:
            history = vars(value)["_funhist_values"]
            _require(type(history) is np.ndarray and id(history) not in self.seen
                     and not any(np.shares_memory(history, array) for array in self.arrays),
                     "CMA history cannot alias another optimizer field")
            self.histories.append(history)
        fields = reviewed._CMA_FIELDS if is_cma else reviewed._STATE_FIELDS[kind]
        self.charge(40 + sum(len(field) + 4 for field in fields))
        encoded = {}
        for field in sorted(fields):
            member = vars(value)[field]
            encoded[field] = (self.cma_history(value, member) if is_cma and field == "_funhist_values"
                              else self.value(member, depth + 1))
        return {"type": "object", "class": "cmaes.CMA@0.13.1" if is_cma else _TYPE_NAMES[kind],
                "fields": encoded}

    def array_shape(self, value: np.ndarray) -> dict:
        _require(type(value) is np.ndarray, "Optimizer arrays require the exact reviewed type")
        dtype = value.dtype
        _require(type(value) is np.ndarray and not dtype.hasobject and dtype.metadata is None
                 and dtype.fields is None and dtype.subdtype is None
                 and ((dtype.kind in "iu" and dtype.itemsize in (1, 2, 4, 8))
                      or (dtype.kind == "f" and dtype.itemsize in (4, 8))
                      or (dtype.kind == "b" and dtype.itemsize == 1)),
                 "Optimizer array dtype is outside the reviewed numeric types")
        _require(value.ndim <= 4 and value.size <= MAX_ITEMS and value.nbytes <= MAX_ARRAY_BYTES,
                 "Optimizer array exceeds its shape or byte bound")
        _require(all(abs(stride) <= MAX_ARRAY_BYTES for stride in value.strides),
                 "Optimizer array strides exceed the reviewed byte bound")
        return {"dtype": dtype.str, "shape": list(value.shape), "strides": list(value.strides),
                "writeable": bool(value.flags.writeable)}

    def array(self, value: np.ndarray) -> dict:
        shape = self.array_shape(value)
        self.charge(160 + value.nbytes * 2)
        _require(bool(np.isfinite(value).all()), "Optimizer arrays require finite initialized values")
        return {"type": "ndarray", **shape, "order": "C", "hex": value.tobytes(order="C").hex()}

    def python_rng(self, value: random.Random) -> dict:
        version, words, gaussian = reviewed._python_rng_state(value)
        _require(type(version) is int and version == 3 and type(words) is tuple and len(words) == 625
                 and all(type(word) is int and 0 <= word < 2**32 for word in words[:-1])
                 and type(words[-1]) is int and 0 <= words[-1] <= 624,
                 "Python RNG state is outside the reviewed MT19937 schema")
        result = {"type": "python.Random", "algorithm": "MT19937", "state_version": version,
                  "words": list(words[:-1]), "index": words[-1],
                  "gaussian_hex": None if gaussian is None else gaussian.hex()}
        self.charge(len(_json_bytes(result)))
        return result

    def numpy_rng(self, value: np.random.RandomState) -> dict:
        algorithm, words, index, has_gauss, gaussian = value.get_state()
        _require(algorithm == "MT19937" and type(words) is np.ndarray
                 and words.dtype == np.dtype("uint32") and words.shape == (624,)
                 and type(index) is int and 0 <= index <= 624
                 and type(has_gauss) is int and has_gauss in (0, 1)
                 and type(gaussian) is float and math.isfinite(gaussian),
                 "NumPy RNG state is outside the reviewed MT19937 schema")
        result = {"type": "numpy.RandomState", "algorithm": algorithm,
                  "key_dtype": words.dtype.str, "keys_hex": words.tobytes().hex(),
                  "index": index, "has_gaussian": has_gauss, "gaussian_hex": gaussian.hex()}
        self.charge(len(_json_bytes(result)))
        return result

    def cma_history(self, optimizer, values) -> dict:
        """Never inspect the np.empty slots that tell() has not initialized."""
        generation, term = optimizer._g, optimizer._funhist_term
        dimensions, population = optimizer._n_dim, optimizer._popsize
        _require(type(generation) is int and 0 <= generation < 2**63
                 and type(term) is int and 1 <= term <= MAX_ITEMS // 2
                 and type(dimensions) is int and 1 <= dimensions <= 100
                 and type(population) is int and 2 <= population <= 100
                 and term == 10 + (30 * dimensions + population - 1) // population,
                 "CMA fitness-history bounds do not match the reviewed solver")
        shape = self.array_shape(values)
        _require(values.dtype == np.dtype("float64") and values.shape == (term * 2,),
                 "CMA fitness-history storage does not match the reviewed solver")
        self.charge(200 + values.size * 64)
        written = [generation >= term or 1 <= slot <= generation for slot in range(term)]
        slots = []
        for slot, initialized in enumerate(written):
            if not initialized:
                slots.append(None)
                continue
            best, worst = float(values[slot * 2]), float(values[slot * 2 + 1])
            _require(math.isfinite(best) and math.isfinite(worst),
                     "Initialized CMA history must contain finite fitness")
            slots.append([best.hex(), worst.hex()])
        return {"type": "cmaes-fitness-history-v1", **shape, "generation": generation,
                "written_pairs": written, "slots_hex": slots}


def encode_optimizer_evidence(strategy, cohort: EvaluationCohort | None = None) -> dict:
    """Capture reviewed continuation evidence without mutating its source.

    Integers outside known MT words are decimal strings under a type tag;
    floating-point state uses hex/byte tags, never JSON floats or lossy money
    conversion. Map insertion order and shared reference topology are retained.
    Unknown fields, callbacks, cycles, nonfinite initialized values, and large
    inputs fail closed. The returned JSON tree is fully detached.
    """
    _require(type(strategy) in reviewed._STRATEGY_FIELDS,
             "Only the four reviewed strategies have an evidence schema")
    _require(cohort is None or type(cohort) is EvaluationCohort,
             "Only a reviewed EvaluationCohort has an evidence schema")
    encoder = _Encoder()
    try:
        # Traverse with strict bounds before allocating the reviewed deep copy.
        result = {"version": EVIDENCE_VERSION,
                  "software": {"python": ".".join(map(str, sys.version_info[:3])),
                               "numpy": np.__version__, "cmaes": reviewed.CMA_FORK_VERSION},
                  "strategy": encoder.value(strategy), "cohort": encoder.value(cohort)}
        _require(len(_json_bytes(result)) <= MAX_EVIDENCE_BYTES,
                 "Optimizer evidence exceeds its serialized byte budget")
        # The existing independently tested copier additionally validates RNG
        # ownership, package version, and unsupported overlapping array views.
        memo: dict[int, object] = {}
        reviewed.fork_strategy(strategy, memo=memo)
        if cohort is not None:
            reviewed.fork_evaluation(cohort, memo=memo)
        validate_optimizer_evidence(result)
    except reviewed.StrategyForkError as error:
        raise OptimizerEvidenceError(str(error)) from None
    return result


def _fields(value, keys) -> None:
    _require(type(value) is dict and all(type(key) is str for key in value)
             and value.keys() == set(keys), "Optimizer evidence has unexpected fields")


def _integer(value, minimum=0, maximum=2**63 - 1) -> int:
    _require(type(value) is int and minimum <= value <= maximum,
             "Optimizer evidence integer is outside its schema")
    return value


def _finite_hex(value) -> str:
    _require(type(value) is str and 1 <= len(value) <= 32,
             "Optimizer float evidence requires bounded canonical hex")
    try:
        parsed = float.fromhex(value)
    except (ValueError, OverflowError):
        raise OptimizerEvidenceError("Optimizer float evidence is invalid") from None
    _require(math.isfinite(parsed) and parsed.hex() == value,
             "Optimizer float evidence must be finite and canonical")
    return value


class _WireValidator:
    def __init__(self):
        self.nodes: dict[int, dict] = {}
        self.active: set[int] = set()
        self.visits = 0

    def value(self, value, depth=0):
        self.visits += 1
        _require(self.visits <= MAX_NODES and depth <= MAX_DEPTH,
                 "Optimizer evidence exceeds its graph bound")
        if value is None or type(value) is bool:
            return
        if type(value) is str:
            _require(len(value) <= MAX_STRING_BYTES and len(value.encode("utf-8")) <= MAX_STRING_BYTES,
                     "Optimizer value string exceeds its bound")
            return
        _require(type(value) is dict, "Optimizer evidence values require explicit numeric/container tags")
        if value.keys() == {"ref"}:
            target = _integer(value["ref"])
            _require(target in self.nodes and target not in self.active,
                     "Optimizer reference is forward, missing, or cyclic")
            return
        tag = value.get("type")
        _require(type(tag) is str, "Optimizer evidence type is missing")
        if tag == "integer":
            _fields(value, {"type", "decimal"})
            decimal = value["decimal"]
            _require(type(decimal) is str and len(decimal) <= 79
                     and re.fullmatch(r"0|-?[1-9][0-9]*", decimal, re.ASCII) is not None
                     and int(decimal).bit_length() <= MAX_INTEGER_BITS,
                     "Optimizer integer evidence must be bounded and canonical")
            return
        if tag in {"float", "numpy.float64"}:
            _fields(value, {"type", "hex"})
            _finite_hex(value["hex"])
            return
        node = _integer(value.get("node"))
        _require(node == len(self.nodes), "Optimizer node identities must follow traversal order")
        self.nodes[node] = value
        self.active.add(node)
        try:
            self.compound(value, tag, depth)
        finally:
            self.active.remove(node)

    def compound(self, value, tag, depth):
        if tag in {"list", "tuple"}:
            _fields(value, {"node", "type", "items"})
            _require(type(value["items"]) is list and len(value["items"]) <= MAX_ITEMS,
                     "Optimizer sequence is outside its item bound")
            for item in value["items"]:
                self.value(item, depth + 1)
        elif tag == "map":
            _fields(value, {"node", "type", "entries"})
            entries = value["entries"]
            _require(type(entries) is list and len(entries) <= MAX_ITEMS,
                     "Optimizer map is outside its item bound")
            keys = set()
            for pair in entries:
                _require(type(pair) is list and len(pair) == 2 and type(pair[0]) is str
                         and pair[0] not in keys, "Optimizer map entries must have unique string keys")
                self.value(pair[0], depth + 1)
                keys.add(pair[0])
                self.value(pair[1], depth + 1)
        elif tag == "object":
            self.object(value, depth)
        elif tag == "ndarray":
            _fields(value, {"node", "type", "dtype", "shape", "strides", "writeable", "order", "hex"})
            dtype, size = self.array_shape(value)
            _require(value["order"] == "C", "Optimizer array payload order must be C")
            self.hex_bytes(value["hex"], size * dtype.itemsize)
            # This bounded numeric check is not an object/optimizer decoder.
            numbers = np.frombuffer(bytes.fromhex(value["hex"]), dtype=dtype)
            _require(bool(np.isfinite(numbers).all()), "Optimizer array evidence contains nonfinite values")
        elif tag == "python.Random":
            _fields(value, {"node", "type", "algorithm", "state_version", "words", "index", "gaussian_hex"})
            _require(value["algorithm"] == "MT19937" and type(value["state_version"]) is int
                     and value["state_version"] == 3 and type(value["words"]) is list
                     and len(value["words"]) == 624, "Unsupported Python RNG schema")
            for word in value["words"]:
                _integer(word, maximum=2**32 - 1)
            _integer(value["index"], maximum=624)
            if value["gaussian_hex"] is not None:
                _finite_hex(value["gaussian_hex"])
        elif tag == "numpy.RandomState":
            _fields(value, {"node", "type", "algorithm", "key_dtype", "keys_hex", "index",
                            "has_gaussian", "gaussian_hex"})
            _require(value["algorithm"] == "MT19937" and type(value["key_dtype"]) is str
                     and value["key_dtype"] in {"<u4", ">u4"},
                     "Unsupported NumPy RNG schema")
            self.hex_bytes(value["keys_hex"], 624 * 4)
            _integer(value["index"], maximum=624)
            _integer(value["has_gaussian"], maximum=1)
            _finite_hex(value["gaussian_hex"])
        else:
            raise OptimizerEvidenceError("Unknown optimizer evidence type")

    def object(self, value, depth):
        _fields(value, {"node", "type", "class", "fields"})
        name = value["class"]
        names = {name: kind for kind, name in _TYPE_NAMES.items()}
        _require(type(name) is str and (name in names or name == "cmaes.CMA@0.13.1"),
                 "Unknown optimizer evidence object class")
        fields = value["fields"]
        required = reviewed._CMA_FIELDS if name == "cmaes.CMA@0.13.1" else reviewed._STATE_FIELDS[names[name]]
        _fields(fields, required)
        for key in sorted(required):
            if name == "cmaes.CMA@0.13.1" and key == "_funhist_values":
                self.history(fields[key], fields)
            else:
                self.value(fields[key], depth + 1)
        strategy_names = {_TYPE_NAMES[kind] for kind in reviewed._STRATEGY_FIELDS}
        if name in strategy_names:
            self.role(fields["_rng"], "python.Random")
            self.role(fields["_search_streams"], "object", "SearchRandomStreams")
            if "_cohort" in fields:
                self.role(fields["_cohort"], "object", "SelectionCohort")
        if name == "cmaes.CMA@0.13.1":
            self.role(fields["_rng"], "numpy.RandomState")
        if name == "CMAEvolutionStrategy" and fields["_optimizer"] is not None:
            self.role(fields["_optimizer"], "object", "cmaes.CMA@0.13.1")
        if name in {"ParticleSwarmStrategy", "CMAEvolutionStrategy"} and fields["_codec"] is not None:
            self.role(fields["_codec"], "object", "ParameterCodec")

    def role(self, value, tag, class_name=None):
        """Required continuation resources cannot be replaced by null/other tags."""
        _require(type(value) is dict, "Missing required optimizer continuation resource")
        record = self.nodes[value["ref"]] if value.keys() == {"ref"} else value
        _require(record.get("type") == tag and
                 (class_name is None or record.get("class") == class_name),
                 "Optimizer continuation resource has the wrong typed role")

    @staticmethod
    def hex_bytes(value, size):
        _require(type(value) is str and len(value) == size * 2
                 and re.fullmatch(r"[0-9a-f]*", value, re.ASCII) is not None,
                 "Optimizer bytes must match their bounded lowercase hexadecimal shape")

    @staticmethod
    def array_shape(value):
        dtype = value["dtype"]
        allowed = {"|b1", "|i1", "|u1"} | {
            endian + kind + str(size) for endian in ("<", ">")
            for kind, sizes in (("i", (2, 4, 8)), ("u", (2, 4, 8)), ("f", (4, 8))) for size in sizes}
        _require(type(dtype) is str and dtype in allowed, "Unsupported numeric evidence dtype")
        shape, strides = value["shape"], value["strides"]
        _require(type(shape) is list and len(shape) <= 4 and type(strides) is list
                 and len(strides) == len(shape) and type(value["writeable"]) is bool,
                 "Optimizer array shape metadata is invalid")
        size = 1
        for dimension in shape:
            size *= _integer(dimension, maximum=MAX_ITEMS)
        for stride in strides:
            _integer(stride, minimum=-MAX_ARRAY_BYTES, maximum=MAX_ARRAY_BYTES)
        parsed = np.dtype(dtype)
        _require(size <= MAX_ITEMS and size * parsed.itemsize <= MAX_ARRAY_BYTES,
                 "Optimizer array shape exceeds its byte bound")
        return parsed, size

    def history(self, value, fields):
        _fields(value, {"type", "dtype", "shape", "strides", "writeable", "generation",
                        "written_pairs", "slots_hex"})
        _require(value["type"] == "cmaes-fitness-history-v1", "Unknown CMA history encoding")
        dtype, size = self.array_shape(value)
        generation = _integer(value["generation"])
        term = size // 2
        _require(dtype.kind == "f" and dtype.itemsize == 8 and value["shape"] == [term * 2]
                 and size > 0 and size % 2 == 0, "CMA history shape is invalid")
        expected = [generation >= term or 1 <= slot <= generation for slot in range(term)]
        mask, slots = value["written_pairs"], value["slots_hex"]
        _require(type(mask) is list and all(type(item) is bool for item in mask) and mask == expected
                 and type(slots) is list and len(slots) == term, "CMA written-slot mask is invalid")
        for initialized, pair in zip(mask, slots):
            if not initialized:
                _require(pair is None, "CMA unwritten memory cannot appear in evidence")
            else:
                _require(type(pair) is list and len(pair) == 2, "CMA written history requires a finite pair")
                _finite_hex(pair[0]); _finite_hex(pair[1])
        numbers = {}
        for key in ("_g", "_funhist_term", "_n_dim", "_popsize"):
            scalar = fields[key]
            _fields(scalar, {"type", "decimal"})
            _require(scalar["type"] == "integer", "CMA history counters require integer evidence")
            self.value(scalar)
            numbers[key] = int(scalar["decimal"])
        _require(generation == numbers["_g"] and term == numbers["_funhist_term"]
                 and 1 <= numbers["_n_dim"] <= 100 and 2 <= numbers["_popsize"] <= 100
                 and term == 10 + (30 * numbers["_n_dim"] + numbers["_popsize"] - 1) // numbers["_popsize"],
                 "CMA history does not match its optimizer generation/dimensions")


def validate_optimizer_evidence(value: object) -> None:
    """Validate bounded tagged evidence without restoring or running a solver.

    This validates the complete reviewed wire grammar, including references and
    initialized-state boundaries and mandatory RNG/search/cohort roles. It does
    not prove every field's semantic restoration compatibility, optimizer math,
    phenotype correspondence, or agreement with an authoritative prior checkpoint.
    """
    visits = 0
    active = set()
    budget = 0

    def raw(item, depth=0):
        nonlocal visits, budget
        visits += 1
        _require(visits <= MAX_NODES * 8 and depth <= MAX_DEPTH * 3,
                 "Optimizer JSON exceeds its structural bound")
        kind = type(item)
        budget += 8
        if item is None or kind is bool:
            pass
        elif kind is int:
            _require(item.bit_length() <= 64, "Untagged optimizer integer exceeds its schema")
            budget += 20
        elif kind is str:
            _require(len(item) <= MAX_EVIDENCE_BYTES, "Optimizer JSON string exceeds its bound")
            try:
                budget += len(item.encode("utf-8"))
            except UnicodeEncodeError:
                raise OptimizerEvidenceError("Optimizer JSON requires valid UTF-8") from None
        elif kind in (dict, list):
            _require(len(item) <= MAX_ITEMS and id(item) not in active,
                     "Optimizer JSON contains a cycle or oversized container")
            active.add(id(item))
            try:
                if kind is dict:
                    _require(all(type(key) is str for key in item), "Optimizer JSON requires plain string keys")
                    for key, child in item.items():
                        raw(key, depth + 1); raw(child, depth + 1)
                else:
                    for child in item:
                        raw(child, depth + 1)
            finally:
                active.remove(id(item))
        else:
            raise OptimizerEvidenceError("Optimizer evidence must contain only exact JSON types")
        _require(budget <= MAX_EVIDENCE_BYTES * 3, "Optimizer JSON exceeds its allocation bound")

    raw(value)
    _require(len(_json_bytes(value)) <= MAX_EVIDENCE_BYTES, "Optimizer evidence exceeds its wire byte bound")
    _fields(value, {"version", "software", "strategy", "cohort"})
    _require(value["version"] == EVIDENCE_VERSION, "Unknown optimizer evidence version")
    _fields(value["software"], {"python", "numpy", "cmaes"})
    for version in value["software"].values():
        _require(type(version) is str and len(version) <= 32
                 and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version, re.ASCII) is not None,
                 "Optimizer software versions must be explicit stable versions")
    _require(value["software"]["cmaes"] == reviewed.CMA_FORK_VERSION,
             "Optimizer evidence requires the reviewed CMA schema version")
    validator = _WireValidator()
    validator.value(value["strategy"])
    strategy = value["strategy"]
    _require(type(strategy) is dict and strategy.get("type") == "object"
             and strategy.get("class") in {_TYPE_NAMES[kind] for kind in reviewed._STRATEGY_FIELDS},
             "Optimizer evidence requires one reviewed root strategy")
    validator.value(value["cohort"])
    if value["cohort"] is not None:
        cohort = value["cohort"]
        _require(type(cohort) is dict, "Optimizer evidence requires a reviewed evaluation cohort")
        if "ref" in cohort:
            cohort = validator.nodes[cohort["ref"]]
        _require(cohort.get("type") == "object" and cohort.get("class") == "EvaluationCohort",
                 "Optimizer evidence requires a reviewed evaluation cohort")
