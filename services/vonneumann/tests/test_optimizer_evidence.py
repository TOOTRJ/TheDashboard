"""Independent bounded evidence checks across real optimizer progressions."""

from copy import deepcopy
import json
import math
import unittest
from unittest.mock import patch

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    import numpy as np
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.evaluation import EvaluationCohort
    from vonneumann.core.optimizer_evidence import (
        MAX_EVIDENCE_BYTES, OptimizerEvidenceError, encode_optimizer_evidence,
        validate_optimizer_evidence,
    )
    from vonneumann.core.search_random import SearchRandomStreams
    from vonneumann.core.strategy_fork import fork_evaluation, fork_strategy
    from vonneumann.core.strategies.cma_es import CMAEvolutionStrategy, cmaes_lib
    from vonneumann.core.strategies.particle_swarm import ParticleSwarmStrategy
    from tests.test_strategy_fork import KINDS, probe, result_state, state


def setup(kind, *, fixed=False):
    config = ColonyConfig(enabled_genes=[] if fixed else ["rsi_oversold", "volume_threshold"],
                          available_assets=["SOL/USDC"], mutation_rate=.3)
    members = [probe(i + 1, float(i)) for i in range(8)]
    for member in members:
        member.genome.validate(config)
    strategy = kind()
    strategy.configure_search(SearchRandomStreams("18446744073709551615", strategy.name), epoch=3)
    strategy.initialize(members, config)
    if kind is not CMAEvolutionStrategy:
        strategy.bind_candidates(members)
    return strategy, config, members


def encoded(strategy, cohort=None):
    evidence = encode_optimizer_evidence(strategy, cohort)
    validate_optimizer_evidence(evidence)
    return json.dumps(evidence, sort_keys=True,
                      ensure_ascii=True, allow_nan=False, separators=(",", ":"))


def objects(value, tag):
    if type(value) is dict:
        if value.get("type") == tag:
            yield value
        for item in value.values():
            yield from objects(item, tag)
    elif type(value) is list:
        for item in value:
            yield from objects(item, tag)


class OptimizerEvidenceTests(OfflineTestMixin, unittest.TestCase):
    def test_all_four_real_solvers_capture_every_phase_and_continue_without_effects(self):
        for kind in KINDS:
            with self.subTest(strategy=kind.__name__):
                strategy, config, members = setup(kind)
                baseline = encoded(strategy)
                self.assertEqual(baseline, encoded(fork_strategy(strategy)))
                for generation in range(3):
                    cohort = EvaluationCohort(f"evidence:{generation}", members, 60)
                    warming = encoded(strategy, cohort)
                    self.assertEqual(warming, encoded(fork_strategy(strategy), fork_evaluation(cohort)))
                    cohort.start(1000. + generation * 60)
                    evaluating = encoded(strategy, cohort)
                    self.assertNotEqual(warming, evaluating)
                    cohort.record_terminal(members[0], "terminal_fixture", 1001. + generation * 60)
                    partial = encoded(strategy, cohort)
                    self.assertNotEqual(evaluating, partial)
                    results = list(cohort.complete(members[1:], 1060. + generation * 60))
                    before = state(strategy), state(cohort)
                    complete = encoded(strategy, cohort)
                    self.assertNotEqual(partial, complete)
                    self.assertEqual((state(strategy), state(cohort)), before)
                    self.assertEqual(complete, encoded(strategy, cohort))
                    self.assertLess(len(complete.encode("ascii")), MAX_EVIDENCE_BYTES)
                    fork = fork_strategy(strategy)
                    proposal = strategy.evolve(results, [], config)
                    duplicate = fork.evolve(list(reversed(results)), [], config)
                    self.assertEqual(result_state(proposal), result_state(duplicate))
                    pending = encoded(strategy, cohort)
                    self.assertEqual(pending, encoded(fork, cohort))
                    self.assertNotEqual(complete, pending)
                    next_members = [probe(100 * (generation + 1) + i, float(7 - i), deepcopy(genome))
                                    for i, genome in enumerate(proposal.offspring)]
                    if kind is ParticleSwarmStrategy:
                        for index, member in enumerate(next_members):
                            strategy.remap_probe_id(proposal.parent_map[str(index)][0], member.probe_id)
                    strategy.bind_candidates(next_members)
                    members = next_members
                self.assertNotEqual(baseline, encoded(strategy))

    def test_fixed_uninitialized_and_aborted_strategies_have_deterministic_evidence(self):
        for kind in KINDS:
            with self.subTest(strategy=kind.__name__):
                self.assertEqual(encoded(kind()), encoded(kind()))
                strategy, config, members = setup(kind, fixed=True)
                cohort = EvaluationCohort("fixed", members, 60)
                cohort.abort("fixture_abort", 1000.)
                aborted = encoded(strategy, cohort)
                self.assertEqual(aborted, encoded(fork_strategy(strategy), fork_evaluation(cohort)))
                strategy.abort_cohort()
                self.assertNotEqual(aborted, encoded(strategy, cohort))

    def test_scalar_rng_and_gaussian_cache_mutations_are_bound(self):
        for kind in KINDS:
            with self.subTest(strategy=kind.__name__):
                strategy, _, _ = setup(kind)
                before = encoded(strategy)
                strategy._search_epoch += 1
                self.assertNotEqual(before, encoded(strategy))
                before = encoded(strategy)
                strategy._rng.random()
                self.assertNotEqual(before, encoded(strategy))
                strategy._rng.gauss(0., 1.)
                rng_record = list(objects(encode_optimizer_evidence(strategy), "python.Random"))[0]
                version, words, cached = strategy._rng.getstate()
                self.assertEqual(rng_record["state_version"], version)
                self.assertEqual(rng_record["words"], list(words[:-1]))
                self.assertEqual(rng_record["index"], words[-1])
                self.assertEqual(rng_record["gaussian_hex"], cached.hex())
                before = encoded(strategy)
                strategy._rng.gauss_next = math.nextafter(cached, math.inf)
                self.assertNotEqual(before, encoded(strategy))
        cma, _, _ = setup(CMAEvolutionStrategy)
        before = encoded(cma)
        cma._optimizer._rng.normal()
        self.assertNotEqual(before, encoded(cma))
        rng_record = list(objects(encode_optimizer_evidence(cma), "numpy.RandomState"))[0]
        name, words, index, has_gauss, cached = cma._optimizer._rng.get_state()
        self.assertEqual((rng_record["algorithm"], rng_record["index"], rng_record["has_gaussian"]),
                         (name, index, has_gauss))
        self.assertEqual(rng_record["keys_hex"], words.tobytes().hex())
        self.assertEqual(rng_record["gaussian_hex"], cached.hex())
        before = encoded(cma)
        cma._optimizer._rng.set_state((name, words, index, has_gauss, math.nextafter(cached, math.inf)))
        self.assertNotEqual(before, encoded(cma))

    def test_cma_unwritten_empty_memory_is_omitted_until_each_slot_is_initialized(self):
        strategy, _, _ = setup(CMAEvolutionStrategy)
        optimizer = strategy._optimizer
        initial = encoded(strategy)
        optimizer._funhist_values.fill(float("nan"))
        self.assertEqual(initial, encoded(strategy))
        history = list(objects(encode_optimizer_evidence(strategy), "cmaes-fitness-history-v1"))[0]
        self.assertEqual(history["written_pairs"], [False] * optimizer._funhist_term)
        self.assertEqual(history["slots_hex"], [None] * optimizer._funhist_term)
        # tell() writes the incremented generation's circular slot; slot zero
        # remains unwritten until the first complete wrap.
        optimizer.tell([(optimizer.ask(), float(index)) for index in range(optimizer.population_size)])
        history = list(objects(encode_optimizer_evidence(strategy), "cmaes-fitness-history-v1"))[0]
        self.assertEqual([i for i, written in enumerate(history["written_pairs"]) if written], [1])
        self.assertEqual(history["slots_hex"][1], [0.0.hex(), 7.0.hex()])
        original = encoded(strategy)
        optimizer._funhist_values[0] = 12345.
        self.assertEqual(original, encoded(strategy))
        optimizer._funhist_values[2] = .5
        self.assertNotEqual(original, encoded(strategy))
        optimizer._funhist_values[2] = float("inf")
        with self.assertRaises(OptimizerEvidenceError):
            encoded(strategy)
        optimizer._funhist_values[2] = .5
        for _ in range(optimizer._funhist_term - 1):
            optimizer.tell([(optimizer.ask(), float(index)) for index in range(optimizer.population_size)])
        history = list(objects(encode_optimizer_evidence(strategy), "cmaes-fitness-history-v1"))[0]
        self.assertTrue(all(history["written_pairs"]))
        self.assertTrue(all(slot is not None for slot in history["slots_hex"]))

    def test_cma_unwritten_history_cannot_alias_other_emitted_storage(self):
        for view in (False, True):
            strategy, _, _ = setup(CMAEvolutionStrategy)
            history = strategy._optimizer._funhist_values
            strategy._optimizer._B = history[:2] if view else history
            with self.assertRaises(OptimizerEvidenceError):
                encoded(strategy)

    def test_arrays_and_float_types_preserve_bits_shape_and_writeability(self):
        strategy, _, _ = setup(CMAEvolutionStrategy)
        original = encoded(strategy)
        array = strategy._optimizer._mean
        array[0] = math.nextafter(float(array[0]), math.inf)
        self.assertNotEqual(original, encoded(strategy))
        arrays = list(objects(encode_optimizer_evidence(strategy), "ndarray"))
        record = next(item for item in arrays if item["hex"] == array.tobytes().hex())
        self.assertEqual(record["dtype"], array.dtype.str)
        self.assertEqual(record["shape"], list(array.shape))
        original = encoded(strategy)
        array.setflags(write=False)
        self.assertNotEqual(original, encoded(strategy))
        ga, _, _ = setup(KINDS[0])
        ga.mutation_strength = 0.
        zero = encoded(ga)
        ga.mutation_strength = -0.
        self.assertNotEqual(zero, encoded(ga))
        negative = encoded(ga)
        ga.mutation_strength = np.float64(-0.)
        self.assertNotEqual(negative, encoded(ga))

    def test_unknown_types_fields_callbacks_and_cycles_fail_without_hooks(self):
        class Unexpected:
            def __repr__(self):
                raise AssertionError("repr must not run")

            def __getstate__(self):
                raise AssertionError("serialization hook must not run")

        for mutation in (lambda s: setattr(s, "future_field", 1),
                         lambda s: setattr(s, "_search_streams", Unexpected()),
                         lambda s: setattr(s, "_rng", lambda: None),
                         lambda s: setattr(s, "_cohort", s)):
            strategy, _, _ = setup(KINDS[0])
            mutation(strategy)
            with self.assertRaises(OptimizerEvidenceError):
                encoded(strategy)
        strategy, _, members = setup(KINDS[0])
        cohort = EvaluationCohort("cycle", members, 60)
        cohort._genomes["cycle"] = cohort._genomes
        with self.assertRaises(OptimizerEvidenceError):
            encoded(strategy, cohort)

    def test_nonfinite_and_unsafe_arrays_fail_closed(self):
        for invalid in (float("nan"), float("inf"), float("-inf")):
            strategy, _, _ = setup(KINDS[0])
            strategy.mutation_rate = invalid
            with self.assertRaises(OptimizerEvidenceError):
                encoded(strategy)
        arrays = (np.array([float("nan")]), np.array([object()], dtype=object),
                  np.array([1.], dtype=np.dtype("float64", metadata={"unreviewed": True})),
                  np.array([1.], dtype=np.float16))
        for invalid in arrays:
            strategy, _, _ = setup(CMAEvolutionStrategy)
            strategy._optimizer._mean = invalid
            with self.assertRaises(OptimizerEvidenceError):
                encoded(strategy)

    def test_oversize_input_is_rejected_before_any_reviewed_copy_is_allocated(self):
        cases = [lambda s: setattr(s._search_streams, "seed", "1" * 4097),
                 lambda s: setattr(s, "_search_epoch", 2**257),
                 lambda s: setattr(s._cohort, "_pending", [None] * 4097),
                 lambda s: setattr(s._cohort, "_pending", ["x" * 4096] * 100)]
        for mutation in cases:
            strategy, _, _ = setup(KINDS[0])
            mutation(strategy)
            with patch("vonneumann.core.optimizer_evidence.reviewed.fork_strategy") as copy:
                with self.assertRaises(OptimizerEvidenceError):
                    encoded(strategy)
                copy.assert_not_called()
        strategy, _, _ = setup(CMAEvolutionStrategy)
        strategy._optimizer._mean = np.zeros(4097)
        with self.assertRaises(OptimizerEvidenceError):
            encoded(strategy)
        strategy, _, _ = setup(KINDS[0])
        deep = []
        for _ in range(65):
            deep = [deep]
        strategy._cohort._pending = deep
        with self.assertRaises(OptimizerEvidenceError):
            encoded(strategy)

    def test_output_detaches_maps_preserves_order_and_does_not_use_pickle_hooks(self):
        strategy, _, members = setup(CMAEvolutionStrategy)
        cohort = EvaluationCohort("detached", members, 60)
        expected = encoded(strategy, cohort)
        with patch.object(cmaes_lib.CMA, "__getstate__", side_effect=AssertionError("pickle hook")), \
             patch.object(cmaes_lib.CMA, "__setstate__", side_effect=AssertionError("pickle hook")):
            first = encode_optimizer_evidence(strategy, cohort)
            second = encode_optimizer_evidence(strategy, cohort)
        first["strategy"]["fields"].clear()
        self.assertEqual(json.dumps(second, sort_keys=True, ensure_ascii=True, allow_nan=False,
                                    separators=(",", ":")), expected)
        self.assertEqual(encoded(strategy, cohort), expected)
        cohort._genomes = dict(reversed(list(cohort._genomes.items())))
        self.assertNotEqual(encoded(strategy, cohort), expected)

    def test_wire_schema_rejects_unknown_fields_tags_scalars_and_references(self):
        strategy, _, members = setup(KINDS[0])
        valid = encode_optimizer_evidence(strategy, EvaluationCohort("wire", members, 60))
        changes = {
            "missing_rng": lambda v: v["strategy"]["fields"].pop("_rng"),
            "unknown_class": lambda v: v["strategy"].update({"class": "FutureStrategy"}),
            "node_gap": lambda v: v["strategy"].update({"node": 3}),
            "cycle": lambda v: v["strategy"]["fields"].update({"_rng": {"ref": 0}}),
            "dangling": lambda v: v["strategy"]["fields"].update({"_rng": {"ref": 999}}),
            "raw_float": lambda v: v["strategy"]["fields"].update({"mutation_rate": .2}),
            "future_version": lambda v: v.update({"version": "optimizer-evidence-v2"}),
            "invalid_cohort": lambda v: v.update({"cohort": True}),
            "extra_field": lambda v: v["strategy"]["fields"].update({"future": None}),
            "float_overflow": lambda v: next(objects(v, "float")).update({"hex": "0x1p+9999"}),
            "float_nan": lambda v: next(objects(v, "float")).update({"hex": "nan"}),
            "float_noncanonical": lambda v: next(objects(v, "float")).update({"hex": "0x1p+0"}),
            "int_leading_zero": lambda v: next(objects(v, "integer")).update({"decimal": "01"}),
            "int_oversize": lambda v: next(objects(v, "integer")).update({"decimal": str(2**257)}),
            "rng_length": lambda v: next(objects(v, "python.Random"))["words"].pop(),
            "rng_word": lambda v: next(objects(v, "python.Random"))["words"].__setitem__(0, True),
            "rng_index": lambda v: next(objects(v, "python.Random")).update({"index": 625}),
            "rng_gaussian": lambda v: next(objects(v, "python.Random")).update({"gaussian_hex": "inf"}),
        }
        for label, mutate in changes.items():
            with self.subTest(mutation=label):
                value = deepcopy(valid)
                mutate(value)
                with self.assertRaises(OptimizerEvidenceError):
                    validate_optimizer_evidence(value)
        # Serialization loses neither the ordered graph nor its references.
        validate_optimizer_evidence(json.loads(json.dumps(valid, sort_keys=True)))

    def test_wire_array_rng_and_cma_initialized_memory_bounds_are_checked(self):
        strategy, _, _ = setup(CMAEvolutionStrategy)
        valid = encode_optimizer_evidence(strategy)
        changes = {
            "unsafe_dtype": lambda v: next(objects(v, "ndarray")).update({"dtype": "|O8"}),
            "array_shape": lambda v: next(objects(v, "ndarray")).update({"shape": [4097]}),
            "array_hex": lambda v: next(objects(v, "ndarray")).update({"hex": "FF"}),
            "array_nonfinite": lambda v: next(objects(v, "ndarray")).update({
                "dtype": "<f8", "shape": [1], "strides": [8], "hex": np.array([np.inf], dtype="<f8").tobytes().hex()}),
            "numpy_dtype": lambda v: next(objects(v, "numpy.RandomState")).update({"key_dtype": []}),
            "numpy_hex": lambda v: next(objects(v, "numpy.RandomState")).update({"keys_hex": "00"}),
            "numpy_gaussian": lambda v: next(objects(v, "numpy.RandomState")).update({"has_gaussian": True}),
            "history_mask": lambda v: next(objects(v, "cmaes-fitness-history-v1"))["written_pairs"].__setitem__(0, True),
            "history_unwritten": lambda v: next(objects(v, "cmaes-fitness-history-v1"))["slots_hex"].__setitem__(0, [0.0.hex(), 0.0.hex()]),
            "history_generation": lambda v: next(objects(v, "cmaes-fitness-history-v1")).update({"generation": 1}),
            "history_ordinal": lambda v: next(item for item in objects(v, "object")
                if item["class"] == "cmaes.CMA@0.13.1")["fields"]["_g"].update({"decimal": "1"}),
        }
        for label, mutate in changes.items():
            with self.subTest(mutation=label):
                value = deepcopy(valid)
                mutate(value)
                with self.assertRaises(OptimizerEvidenceError):
                    validate_optimizer_evidence(value)

    def test_wire_resource_and_recursive_inputs_are_rejected_without_hooks(self):
        class Bomb:
            def __eq__(self, other):
                raise AssertionError("custom equality must not run")

            def __repr__(self):
                raise AssertionError("custom repr must not run")

        strategy, _, _ = setup(KINDS[0])
        valid = encode_optimizer_evidence(strategy)
        for replacement in (Bomb(), [None] * 4097, "x" * (MAX_EVIDENCE_BYTES + 1), "\ud800"):
            with self.assertRaises(OptimizerEvidenceError):
                validate_optimizer_evidence({**valid, "cohort": replacement})
        cyclic = {}
        cyclic["cycle"] = cyclic
        with self.assertRaises(OptimizerEvidenceError):
            validate_optimizer_evidence({**valid, "cohort": cyclic})

    def test_mandatory_rng_search_and_cohort_resources_require_their_typed_roles(self):
        for kind in KINDS:
            strategy, _, _ = setup(kind)
            valid = encode_optimizer_evidence(strategy)
            fields = valid["strategy"]["fields"]
            paths = [["strategy", "fields", field] for field in ("_rng", "_search_streams")]
            if "_cohort" in fields:
                paths.append(["strategy", "fields", "_cohort"])
            if kind is CMAEvolutionStrategy:
                paths.extend([["strategy", "fields", "_optimizer"],
                              ["strategy", "fields", "_optimizer", "fields", "_rng"]])
            for path in paths:
                for wrong in (None, {"type": "float", "hex": 0.0.hex()}):
                    with self.subTest(strategy=kind.__name__, role=path, invalid=wrong):
                        value = deepcopy(valid)
                        parent = value
                        for part in path[:-1]:
                            parent = parent[part]
                        parent[path[-1]] = wrong
                        with self.assertRaises(OptimizerEvidenceError):
                            validate_optimizer_evidence(value)


if __name__ == "__main__":
    unittest.main()
