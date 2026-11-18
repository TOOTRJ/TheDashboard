"""Production factory target guards and provider admission with synthetic keys."""
import unittest
from unittest.mock import AsyncMock, patch

from tests.security_support import OfflineTestMixin, USER_A, USER_B, A1, A2, MISSING, deny_network
with deny_network():
    from vonneumann.server.prospective_configuration import configured_v6_service, SUPABASE, ORIGIN


def environment():
    return {"VN_SERVICE_MODE": "paper-v6", "PYTHON_DOTENV_DISABLED": "1", "VN_ENVIRONMENT": "production",
        "SUPABASE_URL": SUPABASE, "VN_ALLOWED_ORIGINS": ORIGIN, "VN_JUPITER_SOLE_CONSUMER": "1",
        "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_synthetic_with_no_access", "VN_PAPER_OWNER_ID": USER_A,
        "VN_PAPER_RUN_ID": A1, "VN_PAPER_MARKET_EPOCH_ID": A2, "VN_PAPER_PRINCIPAL_BINDING_ID": MISSING,
        "VN_PAPER_RECORDER_PACKAGE_SHA256": "1" * 64, "VN_PAPER_DB_LOGIN": "vn_paper_" + "a" * 32,
        "VN_PAPER_DB_PASSWORD": "synthetic-native-no-access-" + "b" * 32,
        "VN_DATABASE_CA_PEM": "synthetic-certificate-no-access", "JUPITER_API_KEY": "synthetic-jupiter-no-access",
        "VN_SOLANA_RPC_URL": "https://rpc.invalid", "VN_PAPER_FEE_BPS": "25", "VN_PAPER_HALF_SPREAD_BPS": "10",
        "VN_PAPER_SLIPPAGE_BPS": "20", "VN_PAPER_COST_LABEL": "Explicit synthetic uncalibrated scenario",
        "VN_PAPER_COST_EVIDENCE_ID": MISSING, "VN_PAPER_COST_EVIDENCE_SHA256": "2" * 64,
        "VN_PAPER_INITIAL_CASH": "1000", "VN_PAPER_SEED_CAPITAL": "100", "VN_PAPER_SEARCH_SEED": "123"}


class ProspectiveConfigurationTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    async def test_wrong_project_origin_mode_or_private_key_guard_refuses_before_native_construction(self):
        changes = ({"VN_SERVICE_MODE": "paper-v5"}, {"PYTHON_DOTENV_DISABLED": "0"},
            {"VN_ENVIRONMENT": "preview"}, {"SUPABASE_URL": "https://another-project.supabase.co"},
            {"SUPABASE_URL": SUPABASE + "/"}, {"VN_ALLOWED_ORIGINS": "https://another-project.vercel.app"},
            {"VN_ALLOWED_ORIGINS": ORIGIN + "/"}, {"VN_JUPITER_SOLE_CONSUMER": "0"},
            {"SUPABASE_PUBLISHABLE_KEY": "service-role-value"}, {"SUPABASE_SERVICE_ROLE_KEY": "synthetic-forbidden"},
            {"SUPABASE_SECRET_KEY": "synthetic-forbidden"}, {"RAILWAY_TOKEN": "synthetic-forbidden"},
            {"RAILWAY_API_TOKEN": "synthetic-forbidden"})
        with patch("vonneumann.db.prospective_journal.ProspectiveSQLJournal") as journal:
            for change in changes:
                with self.subTest(change=next(iter(change))), self.assertRaisesRegex(RuntimeError, "^explicit_(private_paper_configuration|paper_v6_selection)_required$"):
                    configured_v6_service({**environment(), **change})
            journal.assert_not_called()

    async def test_explicit_owner_costs_and_scope_construct_only_the_new_paper_service(self):
        env = environment()
        with patch("vonneumann.db.prospective_journal.ProspectiveSQLJournal") as journal:
            journal.return_value.close = AsyncMock()
            service = configured_v6_service(env)
            self.assertEqual(journal.call_args.args, (env["VN_PAPER_DB_LOGIN"], env["VN_PAPER_DB_PASSWORD"],
                env["VN_DATABASE_CA_PEM"].encode("ascii"), USER_A, A1))
            self.assertEqual((service.owner_id, service.run_id), (USER_A, A1))
            self.assertEqual(service._config.initial_cash, "1000")
            self.assertEqual(service._config.paper_fill.fee_bps, "25")
            self.assertEqual(service._config.paper_fill.half_spread_bps, "10")
            self.assertEqual(service._config.paper_fill.slippage_bps, "20")
            self.assertEqual(service._config.colony_config().enabled_genes, ["ema_fast", "ema_slow"])
            self.assertEqual(service._feed.interval_seconds, 30)
            journal.return_value.latest_control.assert_not_called()
            await service.close()

    async def test_each_external_read_requires_the_latest_exact_owner_run_start(self):
        with patch("vonneumann.db.prospective_journal.ProspectiveSQLJournal") as journal, patch(
                "vonneumann.market.provider_recorded_transport_v3.ProviderRecordedTransport") as provider:
            journal.return_value.close = AsyncMock()
            service = configured_v6_service(environment())
            service._feed.transport_factory()
            self.assertEqual(provider.call_args.args, ("synthetic-jupiter-no-access", "https://rpc.invalid"))
            self.assertTrue(provider.call_args.kwargs["read_only_opt_in"])
            authorize = provider.call_args.kwargs["authorize_request"]
            journal.return_value.latest_control = AsyncMock()
            for control in (None, {"action": "stop", "owner_id": USER_A, "run_id": A1},
                    {"action": "start", "owner_id": USER_B, "run_id": A1},
                    {"action": "start", "owner_id": USER_A, "run_id": A2}):
                journal.return_value.latest_control.return_value = control
                with self.assertRaisesRegex(RuntimeError, "^paper_collection_closed$"):
                    await authorize(None, "jupiter-price-v3", None, b"synthetic-request")
            journal.return_value.latest_control.return_value = {"action": "start", "owner_id": USER_A, "run_id": A1}
            await authorize(None, "jupiter-price-v3", None, b"synthetic-request")
            await service.close()

    async def test_missing_or_invalid_required_configuration_never_exposes_values(self):
        with patch("vonneumann.db.prospective_journal.ProspectiveSQLJournal"):
            for field in ("VN_PAPER_DB_PASSWORD", "JUPITER_API_KEY", "VN_PAPER_INITIAL_CASH", "VN_PAPER_COST_LABEL"):
                env = environment(); del env[field]
                with self.subTest(field=field), self.assertRaisesRegex(RuntimeError, "^invalid_private_paper_configuration$"):
                    configured_v6_service(env)
