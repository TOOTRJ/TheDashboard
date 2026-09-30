"""Offline HTTP validation rejects unsafe configuration before any side effect."""

from __future__ import annotations

import importlib
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.security_support import USER_A, OfflineTestMixin, deny_network

with deny_network():
    from fastapi.testclient import TestClient
    from pydantic import ValidationError
    from vonneumann.core.colony_config import PRESET_CONFIGS
    from vonneumann.server.auth import VerifiedUser, require_user
    from vonneumann.server.models import StartRequest, build_colony_config
    app_module = importlib.import_module("vonneumann.server.app")


class ConfigurationValidationTests(OfflineTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(app_module.app)
        self.addCleanup(self.client.close)
        before = dict(app_module.app.dependency_overrides)
        self.addCleanup(lambda: (app_module.app.dependency_overrides.clear(),
                                 app_module.app.dependency_overrides.update(before)))
        app_module.app.dependency_overrides[require_user] = lambda: VerifiedUser(
            USER_A, int(time.time()) + 3600)
        self.repo = self.offline_stack.enter_context(patch.object(app_module, "VonNeumannRepository"))
        self.create = self.offline_stack.enter_context(patch.object(
            app_module.colony_manager, "create_colony", new=AsyncMock()))

    def assert_rejected(self, payload):
        result = self.client.post("/api/v1/colonies/", json=payload)
        self.assertEqual(result.status_code, 422, result.text)
        self.repo.assert_not_called()
        self.create.assert_not_awaited()
        for issue in result.json()["detail"]:
            self.assertEqual(set(issue), {"type", "msg", "loc"})

    def test_modes_strategies_presets_and_unknown_fields_fail_before_mutation(self):
        for payload in ({"mode": "live"}, {"mode": "pretend"}, {"strategy": "bad"},
                        {"preset": "bad"}, {"unknown_secret_field": "secret-value"},
                        {"colony_config": {"unknown": 1}},
                        {"colony_config": {"gene_overrides": {"ema_fast": {"unknown": 1}}}}):
            with self.subTest(payload=payload):
                self.assert_rejected(payload)

    def test_numeric_bounds_types_and_capital_allocation(self):
        for payload in ({"gen0_count": 1}, {"gen0_count": 51}, {"gen0_count": 2.0},
                        {"gen0_count": True}, {"max_probes": 101}, {"max_probes": 2},
                        {"max_capital": 9}, {"max_capital": 1_000_000_001},
                        {"seed_capital": 9}, {"seed_capital": True}, {"max_capital": 999},
                        {"tick_interval_ms": 0}, {"tick_interval_ms": 99},
                        {"tick_interval_ms": 60_001}, {"mutation_rate": -0.01},
                        {"mutation_rate": .51}, {"mutation_rate": "0.2"},
                        {"strategy": "differential_evolution", "gen0_count": 3}):
            with self.subTest(payload=payload):
                self.assert_rejected(payload)

    def test_de_funds_complete_pairs_before_any_side_effect(self):
        for count in (2, 4, 6, 7, 9, 11):
            with self.subTest(count=count):
                self.assert_rejected({"strategy": "differential_evolution", "gen0_count": count})
        for count in (8, 10, 50):
            request = StartRequest(strategy="differential_evolution", gen0_count=count,
                                   max_probes=count, seed_capital=100, max_capital=count * 100)
            self.assertEqual(request.gen0_count, count)
        self.assert_rejected({"strategy": "differential_evolution", "gen0_count": 8,
                              "max_probes": 7})
        self.assert_rejected({"strategy": "differential_evolution", "gen0_count": 8,
                              "seed_capital": 100, "max_capital": 799})

    def test_nonfinite_values_are_safe_json_errors_without_raw_input(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            for field in ("max_capital", "seed_capital", "mutation_rate"):
                response = self.client.post("/api/v1/colonies/", content='{"' + field + '":' + value + '}',
                                            headers={"Content-Type": "application/json"})
                self.assertEqual(response.status_code, 422)
                self.assertNotIn('"input"', response.text)
                self.assertNotIn('"ctx"', response.text)
        self.repo.assert_not_called()
        self.create.assert_not_awaited()

    def test_gene_and_asset_sets_are_known_unique_and_nonempty_where_required(self):
        for config in ({"enabled_genes": ["ema_fast", "ema_fast"]},
                       {"enabled_genes": ["unknown"]}, {"available_assets": []},
                       {"available_assets": ["SOL/USDC", "SOL/USDC"]},
                       {"available_assets": ["UNKNOWN"]},
                       {"gene_overrides": {"unknown": {"fixed": 1}}},
                       {"reproduction_interval": 0}, {"reproduction_interval": 1.0},
                       {"max_lifespan_ticks": -1}):
            with self.subTest(config=config):
                self.assert_rejected({"colony_config": config})

    def test_gene_bounds_integer_values_defaults_and_relationships(self):
        overrides = [
            {"ema_fast": {"min": 21}}, {"ema_fast": {"min": 12, "max": 11}},
            {"ema_fast": {"fixed": 9.5}}, {"ema_fast": {"min": 10, "default": 9}},
            {"ema_fast": {"max": 8, "fixed": 9}},
            {"ema_fast": {"min": 15}, "ema_slow": {"max": 15}},
            {"ema_fast": {"fixed": 15}},
            {"stop_loss_pct": {"fixed": .05}, "take_profit_pct": {"fixed": .04}},
        ]
        for override in overrides:
            with self.subTest(override=override):
                self.assert_rejected({"colony_config": {"gene_overrides": override}})
        self.assert_rejected({"colony_config": {"available_assets": ["SOL/USDC"],
                                               "gene_overrides": {"num_assets": {"fixed": 2}}}})

    def test_validation_does_not_reflect_untrusted_field_names_or_values(self):
        response = self.client.post("/api/v1/colonies/", json={"secret-field": "secret-value"})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("secret-field", response.text)
        self.assertNotIn("secret-value", response.text)

    def test_presets_stay_valid_and_are_copied(self):
        before = {name: value.to_dict() for name, value in PRESET_CONFIGS.items()}
        for name in PRESET_CONFIGS:
            with self.subTest(preset=name):
                config = build_colony_config(StartRequest(preset=name))
                config.gene_overrides.clear()
        self.assertEqual(before, {name: value.to_dict() for name, value in PRESET_CONFIGS.items()})

    def test_zero_and_explicit_null_overrides_preserve_intent(self):
        config = build_colony_config(StartRequest(preset="fast_evolution", mutation_rate=0,
            colony_config={"max_lifespan_ticks": 0, "enabled_genes": []}))
        self.assertEqual(config.mutation_rate, 0)
        self.assertEqual(config.max_lifespan_ticks, 0)
        self.assertEqual(config.enabled_genes, [])
        self.assertEqual(build_colony_config(StartRequest(preset="fast_evolution")).mutation_rate, .35)
        self.assertIsNone(build_colony_config(StartRequest(preset="fast_evolution",
            colony_config={"max_lifespan_ticks": None})).max_lifespan_ticks)

    def test_empty_override_clears_preset_fixed_gene(self):
        config = build_colony_config(StartRequest(preset="rsi_focus",
            colony_config={"gene_overrides": {"ema_fast": {}}}))
        self.assertIsNone(config.gene_overrides["ema_fast"].fixed)

    def test_valid_boundary_request_passes_effective_config_to_manager(self):
        fake = MagicMock()
        fake.execute_async = AsyncMock()
        self.repo.return_value = fake
        response = self.client.post("/api/v1/colonies/", json={
            "gen0_count": 2, "max_probes": 2, "max_capital": 20, "seed_capital": 10,
            "mutation_rate": 0, "tick_interval_ms": 100,
            "colony_config": {"available_assets": ["SOL/USDC"], "enabled_genes": []}})
        self.assertEqual(response.status_code, 200, response.text)
        # Returned effective configuration can be submitted again without hidden extra fields.
        StartRequest.model_validate(response.json()["config"])
        self.assertEqual(self.create.await_args.kwargs["mutation_rate"], 0)
        fake.execute_async.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
