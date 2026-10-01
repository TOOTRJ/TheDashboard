"""Offline dataset integrity, causality, identity and publication contracts."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.market import dataset as codec
    from vonneumann.market.dataset import (
        DatasetError, MAINNET_GENESIS_HASH, TOKEN_MINTS, canonical_bytes,
        load_dataset, write_dataset,
    )


A, B = "SOL/USDC", "JUP/USDC"


def metadata(assets=(A,), *, frames=3):
    return {
        "source_kind": "synthetic_fixture", "network": "synthetic", "genesis_hash": None,
        "assets": [{"asset": a, "mint": "synthetic:" + a.split("/")[0]} for a in assets],
        "quote_provider": "simulation-gbm-discrete-v1",
        "candle_provider": "simulation-minute-endpoints-v1", "quote_currency": "USD",
        "volume_unit": "synthetic_base_token", "quote_volume_semantics": "synthetic_per_step",
        "source_time_semantics": "modeled_time", "availability_semantics": "modeled",
        "valuation_policy": "usd-reference-only-v1", "rights_basis": "synthetic_generated",
        "warmup_minutes": 0, "evaluation_start_at": 0, "evaluation_end_at": frames * 60,
        "simulation_spec": {
            "model_version": "gbm-discrete-v1", "seed": "0", "start_timestamp": 0,
            "step_seconds": 60, "drift": 0.0001, "volatility": 0.02, "volume_noise": 0.5,
            "candle_model": "minute-endpoints-v1", "volume_unit": "synthetic_base_token",
        },
    }


def frames(assets=(A,), count=3):
    return [{
        "seq": i, "observed_at": (i + 1) * 60,
        "quotes": [{"asset": a, "price": 100 + i, "volume": 2,
                    "volume_unit": "synthetic_base_token", "source_time": (i + 1) * 60,
                    "received_at": (i + 1) * 60, "source_slot": None} for a in assets],
        "candles": [{"asset": a, "start": i * 60, "open": 100 + i, "high": 100 + i,
                     "low": 100 + i, "close": 100 + i, "volume": 2,
                     "source": "simulation-minute-endpoints-v1", "quote_currency": "USD",
                     "volume_unit": "synthetic_base_token", "available_at": (i + 1) * 60}
                    for a in assets],
    } for i in range(count)]


def provider_bundle():
    meta, rows = metadata(), frames()
    meta.update(source_kind="provider_observations", network="solana-mainnet",
                genesis_hash=MAINNET_GENESIS_HASH, quote_provider="jupiter-price-v3",
                candle_provider="birdeye-ohlcv-v3", volume_unit="base_token",
                quote_volume_semantics="unavailable_zero_placeholder",
                source_time_semantics="estimated_block_time", availability_semantics="recorded_receipt",
                rights_basis="provider_archive_permission_reviewed", simulation_spec=None,
                evaluation_start_at=60)
    meta["assets"][0]["mint"] = TOKEN_MINTS[A]
    for row in rows:
        quote = row["quotes"][0]
        quote.update(volume=0, volume_unit="base_token", source_slot=row["seq"] + 10,
                     source_time=row["observed_at"] - 1)
        row["candles"][0].update(source="birdeye-ohlcv-v3", volume_unit="base_token")
    return meta, rows


class DatasetTests(OfflineTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(prefix="dataset-test-", dir="/private/tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.index = 0

    def output(self):
        self.index += 1
        return self.root / f"bundle-{self.index}"

    def reject(self, action, code=None):
        with self.assertRaises(DatasetError) as caught:
            action()
        self.assertEqual(str(caught.exception), "Offline market dataset validation failed.")
        if code is not None:
            self.assertEqual(caught.exception.code, code)
        return caught.exception

    def invalid(self, meta=None, rows=None):
        target = self.output()
        self.reject(lambda: write_dataset(target, metadata() if meta is None else meta,
                                         frames() if rows is None else rows))
        self.assertFalse(target.exists(), "validation must finish before directory creation")

    def rehash(self, target, rows):
        content = b"".join(canonical_bytes(row) for row in rows)
        (target / "frames.jsonl").write_bytes(content)
        manifest = json.loads((target / "manifest.json").read_text())
        manifest["frames"]["sha256"] = hashlib.sha256(content).hexdigest()
        (target / "manifest.json").write_bytes(canonical_bytes(manifest))

    def test_roundtrip_exact_bytes_id_and_nested_immutability(self):
        meta, rows, target = metadata((A, B)), frames((A, B)), self.output()
        written = write_dataset(target, meta, iter(rows))
        loaded = load_dataset(target)
        self.assertEqual(written, loaded)
        self.assertEqual(loaded.dataset_id, hashlib.sha256((target / "manifest.json").read_bytes()).hexdigest())
        self.assertNotIn("dataset_id", loaded.manifest)
        self.assertEqual((target / "frames.jsonl").read_bytes(), b"".join(canonical_bytes(r) for r in rows))
        meta["assets"][0]["mint"] = "private-token"
        rows[0]["quotes"][0]["price"] = 900
        self.assertEqual(loaded.frames[0]["quotes"][0]["price"], 100)
        with self.assertRaises(TypeError):
            loaded.frames[0]["quotes"][0]["price"] = 1
        with self.assertRaises(TypeError):
            loaded.manifest["metadata"]["assets"][0]["mint"] = "other"
        clone = write_dataset(self.output(), loaded.manifest["metadata"], loaded.frames)
        self.assertEqual(clone.dataset_id, loaded.dataset_id)

    def test_provider_archive_identity_rights_and_absent_quote_volume_are_explicit(self):
        meta, rows = provider_bundle()
        loaded = write_dataset(self.output(), meta, rows)
        self.assertEqual(loaded.manifest["metadata"]["source_kind"], "provider_observations")
        for key, bad in (("genesis_hash", "other"), ("rights_basis", "public_internet"),
                         ("valuation_policy", "USDC"), ("availability_semantics", "modeled")):
            changed = copy.deepcopy(meta)
            changed[key] = bad
            self.invalid(changed, rows)
        changed = copy.deepcopy(rows)
        changed[0]["quotes"][0]["volume"] = 1
        self.invalid(meta, changed)

    def test_unknown_keys_missing_keys_urls_and_units_are_rejected(self):
        for mutation in (
            lambda m: m.update(api_key="private-token"),
            lambda m: m.pop("rights_basis"),
            lambda m: m.update(quote_provider="https://user:private-token@example.test"),
            lambda m: m.update(quote_currency="USDC"),
            lambda m: m["assets"][0].update(mint=TOKEN_MINTS[A]),
            lambda m: m["assets"].append(m["assets"][0]),
        ):
            meta = metadata()
            mutation(meta)
            self.invalid(meta)
        for section, key, value in (("quotes", "quote_currency", "USDC"),
                                     ("quotes", "volume_unit", "base_token"),
                                     ("candles", "volume_unit", "base_token")):
            rows = frames()
            rows[0][section][0][key] = value
            self.invalid(rows=rows)

    def test_numerics_reject_bool_strings_nonfinite_negative_and_huge_values(self):
        for key in ("price", "volume", "source_time", "received_at"):
            for value in (True, "10", float("nan"), float("inf"), -1, 10**400):
                rows = frames()
                rows[0]["quotes"][0][key] = value
                self.invalid(rows=rows)
        for key in ("seq", "observed_at"):
            rows = frames()
            rows[0][key] = True
            self.invalid(rows=rows)
        for key in ("drift", "volatility", "volume_noise", "start_timestamp"):
            for value in (True, float("inf"), 10**400):
                meta = metadata()
                meta["simulation_spec"][key] = value
                self.invalid(meta)
        meta = metadata()
        meta["simulation_spec"]["volatility"] = 1e308
        self.invalid(meta)

    def test_utc_timestamp_bounds_and_strict_seed(self):
        for seed in ("-1", "01", "+1", "1.0", "18446744073709551616", 1, True):
            meta = metadata()
            meta["simulation_spec"]["seed"] = seed
            self.invalid(meta)
        meta = metadata()
        meta["simulation_spec"]["seed"] = "18446744073709551615"
        write_dataset(self.output(), meta, frames())
        for field in ("evaluation_start_at", "evaluation_end_at"):
            meta = metadata()
            meta[field] = 253402300800
            self.invalid(meta)
        meta = metadata(frames=1)
        meta["simulation_spec"]["start_timestamp"] = 1e100
        self.invalid(meta, frames(count=1))

    def test_complete_ordered_quote_frames_and_regular_synthetic_clock(self):
        for mutate in (
            lambda rows: rows[0]["quotes"].pop(),
            lambda rows: rows[0]["quotes"].reverse(),
            lambda rows: rows[0]["quotes"].append(rows[0]["quotes"][0]),
            lambda rows: rows[1].update(seq=0),
            lambda rows: rows[1].update(observed_at=60),
            lambda rows: rows[1].update(observed_at=121),
            lambda rows: rows[0]["quotes"][0].update(source_time=59),
            lambda rows: rows[0]["quotes"][0].update(source_slot=1),
        ):
            rows = frames((A, B))
            mutate(rows)
            self.invalid(metadata((A, B)), rows)

    def test_provider_source_and_receipt_watermarks_never_regress(self):
        for field, value in (("source_slot", 9), ("source_slot", True),
                             ("source_time", 58), ("received_at", 58),
                             ("received_at", 121), ("source_time", 121)):
            meta, rows = provider_bundle()
            rows[1]["quotes"][0][field] = value
            self.invalid(meta, rows)
        meta, rows = provider_bundle()
        rows[1]["quotes"][0]["source_slot"] = 10
        self.invalid(meta, rows)  # Same block cannot acquire a new estimated timestamp.

    def test_completed_availability_and_no_historical_revisions_or_padding(self):
        for field, value in (("available_at", 59), ("available_at", 61),
                             ("start", 1), ("close", 999), ("open", 0)):
            rows = frames()
            rows[0]["candles"][0][field] = value
            self.invalid(rows=rows)
        rows = frames()
        rows[1]["candles"] = []
        self.invalid(rows=rows)
        rows = frames()
        rows[1]["candles"].insert(0, copy.deepcopy(rows[0]["candles"][0]))
        write_dataset(self.output(), metadata(), rows)  # Identical overlap accepted.
        rows[1]["candles"][0]["available_at"] = 120
        self.invalid(rows=rows)  # Availability evidence is immutable as well.
        rows[1]["candles"][0] = copy.deepcopy(rows[0]["candles"][0])
        rows[1]["candles"][0]["volume"] = 8
        self.invalid(rows=rows)

    def test_warmup_requires_contiguous_history_available_by_evaluation_boundary(self):
        meta = metadata()
        meta.update(warmup_minutes=2, evaluation_start_at=120)
        write_dataset(self.output(), meta, frames())
        meta["warmup_minutes"] = 3
        self.invalid(meta)
        meta["warmup_minutes"] = 2
        rows = frames()
        late = rows[1]["candles"].pop()
        late["available_at"] = 180
        rows[2]["candles"].insert(0, late)
        self.invalid(meta, rows)

    def test_warmup_rejects_backdated_availability_in_a_late_containing_frame(self):
        meta = metadata()
        meta.update(warmup_minutes=2, evaluation_start_at=120)
        for oldest_availability in (60, 180):
            rows = frames()
            old = rows[0]["candles"].pop()
            old["available_at"] = oldest_availability
            newer = rows[1]["candles"].pop()
            rows[2]["candles"] = [old, newer, *rows[2]["candles"]]
            self.invalid(meta, rows)

    def test_window_is_bounded_by_recorded_timeline_and_origin(self):
        for start, end in ((0, 181), (121, 120), (200, 240)):
            meta = metadata()
            meta.update(evaluation_start_at=start, evaluation_end_at=end)
            self.invalid(meta)
        meta, rows = provider_bundle()
        meta["evaluation_start_at"] = 59
        self.invalid(meta, rows)

    def test_digest_tampering_count_and_time_range_mismatches_fail(self):
        target = self.output()
        write_dataset(target, metadata(), frames())
        data = (target / "frames.jsonl").read_bytes()
        (target / "frames.jsonl").write_bytes(data.replace(b'"price":100', b'"price":999'))
        self.reject(lambda: load_dataset(target), "dataset_integrity")
        (target / "frames.jsonl").write_bytes(data)
        original = (target / "manifest.json").read_bytes()
        for key, value in (("count", 2), ("first_observed_at", 0), ("last_observed_at", 181)):
            manifest = json.loads(original)
            manifest["frames"][key] = value
            (target / "manifest.json").write_bytes(canonical_bytes(manifest))
            self.reject(lambda: load_dataset(target), "dataset_integrity")

    def test_semantic_invalidity_cannot_be_hidden_by_rehashing(self):
        target = self.output()
        write_dataset(target, metadata(), frames())
        changed = frames()
        changed[1]["quotes"][0]["source_time"] = 30
        self.rehash(target, changed)
        self.reject(lambda: load_dataset(target))
        changed = frames()
        changed.reverse()
        self.rehash(target, changed)
        self.reject(lambda: load_dataset(target))

    def test_duplicate_json_keys_unknown_keys_and_noncanonical_bytes_fail(self):
        target = self.output()
        write_dataset(target, metadata(), frames())
        original = (target / "manifest.json").read_bytes()
        for content in (b'{"schema_version":"private-token",' + original[1:],
                        original.replace(b'"warmup_minutes":0', b'"warmup_minutes":NaN'),
                        original.rstrip(b"\n"), b" " + original):
            (target / "manifest.json").write_bytes(content)
            self.reject(lambda: load_dataset(target))
        manifest = json.loads(original)
        manifest["frames"]["file"] = "../../private-token"
        (target / "manifest.json").write_bytes(canonical_bytes(manifest))
        self.reject(lambda: load_dataset(target))

    def test_exclusive_publish_preserves_existing_files_and_rejects_extras(self):
        target = self.output()
        write_dataset(target, metadata(), frames())
        original = {p.name: p.read_bytes() for p in target.iterdir()}
        self.reject(lambda: write_dataset(target, metadata(), frames()), "dataset_exists")
        self.assertEqual(original, {p.name: p.read_bytes() for p in target.iterdir()})
        (target / "secret.env").write_text("private-token")
        self.reject(lambda: load_dataset(target), "dataset_path")

    def test_symlinks_parent_symlinks_traversal_fifo_and_wrong_types_rejected(self):
        target = self.output()
        write_dataset(target, metadata(), frames())
        alias = self.root / "alias"
        alias.symlink_to(target, target_is_directory=True)
        self.reject(lambda: load_dataset(alias), "dataset_path")
        self.reject(lambda: write_dataset(alias / "new", metadata(), frames()), "dataset_path")
        self.reject(lambda: load_dataset(self.root / ".." / self.root.name / target.name), "dataset_path")
        (target / "frames.jsonl").unlink()
        (target / "frames.jsonl").symlink_to(self.root / "private-token")
        self.reject(lambda: load_dataset(target), "dataset_path")
        (target / "frames.jsonl").unlink()
        os.mkfifo(target / "frames.jsonl")
        self.reject(lambda: load_dataset(target), "dataset_path")
        for path in ("", None, b"/private/tmp", "/", "private-token\x00"):
            self.reject(lambda p=path: load_dataset(p), "dataset_path")

    def test_limits_fail_before_output_and_loader_bounds_regular_files(self):
        target = self.output()
        with patch.object(codec, "MAX_FRAMES", 2):
            self.reject(lambda: write_dataset(target, metadata(), frames()), "dataset_limits")
        self.assertFalse(target.exists())
        for name in ("MAX_LINE_BYTES", "MAX_DATA_BYTES", "MAX_MANIFEST_BYTES"):
            with patch.object(codec, name, 10):
                self.reject(lambda: write_dataset(target, metadata(), frames()), "dataset_limits")
            self.assertFalse(target.exists())
        write_dataset(target, metadata(), frames())
        with patch.object(codec, "MAX_DATA_BYTES", 10):
            self.reject(lambda: load_dataset(target), "dataset_limits")

    def test_failed_data_write_never_leaves_a_loadable_partial_archive(self):
        target = self.output()
        with patch.object(codec.os, "fsync", side_effect=OSError("private-token")):
            error = self.reject(lambda: write_dataset(target, metadata(), frames()), "dataset_io")
        self.assertNotIn("private-token", str(error))
        self.assertFalse((target / "manifest.json").exists())
        self.reject(lambda: load_dataset(target))

    def test_unknown_error_code_never_echoes_private_payload(self):
        error = DatasetError("https://private-token@example.test")
        self.assertEqual(error.code, "dataset_invalid")
        self.assertNotIn("private-token", str(error))


if __name__ == "__main__":
    unittest.main()
