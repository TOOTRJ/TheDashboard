"""Offline command contracts for bounded, reproducible synthetic datasets."""

from __future__ import annotations

import asyncio
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.security_support import deny_network

with deny_network():
    from vonneumann.market.dataset import MAX_FRAMES, load_dataset, write_dataset
    from vonneumann.market.dataset_cli import generate_synthetic_dataset, main
    from vonneumann.market.sim_feed import SimulationFeed


SUMMARY_KEYS = {
    "dataset_id", "schema_version", "source_kind", "network", "assets", "frame_count",
    "first_observed_at", "last_observed_at", "quote_currency", "volume_unit",
    "availability_semantics", "candle_coverage",
}
MAX_SEED = "18446744073709551615"
PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class DatasetCliTests(unittest.TestCase):
    def setUp(self):
        self.network = deny_network()
        self.network.__enter__()
        self.addCleanup(self.network.__exit__, None, None, None)
        temporary = tempfile.TemporaryDirectory(prefix="dashboard-dataset-cli-")
        self.addCleanup(temporary.cleanup)
        # macOS /var and /tmp are aliases. Production loading deliberately
        # refuses symlink components, so tests use the real physical directory.
        self.root = Path(temporary.name).resolve()

    def invoke(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = main(arguments)
            except SystemExit as error:
                code = error.code
        return code, stdout.getvalue(), stderr.getvalue()

    def generate(self, name="fixture", **overrides):
        values = {"frames": "3", "assets": ["SOL/USDC", "JUP/USDC"], "seed": MAX_SEED}
        values.update(overrides)
        path = self.root / name
        result = self.invoke([
            "generate-synthetic", "--output", str(path), "--frames", values["frames"],
            "--seed", values["seed"], "--assets", *values["assets"],
        ])
        self.assertEqual(result[0], 0, result[2])
        self.assertEqual(result[2], "")
        return path, json.loads(result[1])

    def test_generate_and_validate_print_the_same_small_metadata_report(self):
        path, generated = self.generate()
        code, output, errors = self.invoke(["validate", str(path)])
        self.assertEqual(code, 0, errors)
        self.assertEqual(errors, "")
        self.assertEqual(json.loads(output), generated)
        self.assertEqual(set(generated), SUMMARY_KEYS)
        self.assertEqual(generated["frame_count"], 3)
        self.assertEqual(generated["assets"], ["JUP/USDC", "SOL/USDC"])
        self.assertEqual(generated["source_kind"], "synthetic_fixture")
        self.assertEqual(generated["network"], "synthetic")
        self.assertEqual(generated["quote_currency"], "USD")
        self.assertEqual(generated["volume_unit"], "synthetic_base_token")
        self.assertEqual(generated["availability_semantics"], "modeled")
        self.assertNotIn(str(path), output)
        self.assertNotIn("price", generated)
        self.assertNotIn("profit", generated)

    def test_coverage_reports_unique_delayed_bars_and_missing_histories_honestly(self):
        path, _ = self.generate()
        metadata = json.loads((path / "manifest.json").read_text())["metadata"]
        original = [json.loads(line) for line in (path / "frames.jsonl").read_text().splitlines()]
        quotes_only = [{**frame, "candles": []} for frame in original]
        write_dataset(self.root / "quotes-only", metadata, quotes_only)
        code, output, errors = self.invoke(["validate", str(self.root / "quotes-only")])
        self.assertEqual(code, 0, errors)
        empty = {"count": 0, "first_start": None, "last_end": None}
        self.assertEqual(json.loads(output)["candle_coverage"], {"JUP/USDC": empty, "SOL/USDC": empty})

        # The first JUP candle arrives one frame late and is repeated once.
        # SOL history is absent; both archives remain structurally valid.
        delayed = [{**frame, "candles": []} for frame in original]
        first = {**original[0]["candles"][0], "available_at": original[1]["observed_at"]}
        delayed[1]["candles"] = [first, original[1]["candles"][0]]
        delayed[2]["candles"] = [first, original[2]["candles"][0]]
        write_dataset(self.root / "delayed", metadata, delayed)
        code, output, errors = self.invoke(["validate", str(self.root / "delayed")])
        self.assertEqual(code, 0, errors)
        self.assertEqual(json.loads(output)["candle_coverage"], {
            "JUP/USDC": {"count": 3, "first_start": original[0]["candles"][0]["start"],
                         "last_end": original[-1]["observed_at"]},
            "SOL/USDC": empty,
        })

    def test_seed_precision_and_asset_permutation_preserve_exact_bundle_bytes(self):
        first, first_summary = self.generate("first")
        second, second_summary = self.generate("second", assets=["JUP/USDC", "SOL/USDC"])
        self.assertEqual(first_summary, second_summary)
        for filename in ("manifest.json", "frames.jsonl"):
            self.assertEqual((first / filename).read_bytes(), (second / filename).read_bytes())
        dataset = load_dataset(first)
        metadata = dataset.manifest["metadata"]
        self.assertEqual(metadata["simulation_spec"]["seed"], MAX_SEED)
        self.assertEqual(metadata["warmup_minutes"], 0)
        self.assertEqual(metadata["evaluation_start_at"], metadata["simulation_spec"]["start_timestamp"])
        self.assertEqual(metadata["evaluation_end_at"], dataset.frames[-1]["observed_at"])
        _, other_seed = self.generate("other", seed="18446744073709551614")
        self.assertNotEqual(other_seed["dataset_id"], first_summary["dataset_id"])

    def test_fixture_quotes_and_candles_exactly_match_existing_simulation(self):
        path, _ = self.generate(frames="5")
        dataset = load_dataset(path)
        assets = [entry["asset"] for entry in dataset.manifest["metadata"]["assets"]]

        async def compare():
            feed = SimulationFeed(seed=int(MAX_SEED))
            for sequence, frame in enumerate(dataset.frames):
                ticks = await feed.get_ticks(assets)
                candles = await feed.get_candles(assets)
                self.assertEqual(frame["seq"], sequence)
                self.assertEqual(frame["observed_at"], feed.current_timestamp)
                for quote, asset in zip(frame["quotes"], assets):
                    self.assertEqual(dict(quote), {
                        "asset": asset, "price": ticks[asset].price, "volume": ticks[asset].volume,
                        "volume_unit": "synthetic_base_token", "source_time": ticks[asset].timestamp,
                        "received_at": feed.current_timestamp, "source_slot": None,
                    })
                for actual, candle in zip(frame["candles"], candles):
                    self.assertEqual(dict(actual), {**asdict(candle), "available_at": feed.current_timestamp})

        asyncio.run(compare())

    def test_async_generator_is_usable_with_an_existing_event_loop(self):
        async def generate():
            return await generate_synthetic_dataset(
                self.root / "async", frames=2, assets=["SOL/USDC"], seed="0")

        dataset = asyncio.run(generate())
        self.assertEqual(len(dataset.frames), 2)
        self.assertEqual(dataset.dataset_id, load_dataset(self.root / "async").dataset_id)

    def test_invalid_cli_seed_frame_and_asset_arguments_do_not_publish(self):
        defaults = ["generate-synthetic", "--output", str(self.root / "rejected")]
        cases = []
        for seed in ("-1", "01", "+1", "1.0", "1e3", " 1", "１２", "18446744073709551616"):
            cases.append(["--seed", seed, "--frames", "1", "--assets", "SOL/USDC"])
        for frames in ("0", "-1", "01", "1.0", "1e3", str(MAX_FRAMES + 1), "9" * 1000):
            cases.append(["--seed", "0", "--frames", frames, "--assets", "SOL/USDC"])
        for assets in (["unknown"], ["SOL/USDC", "SOL/USDC"], ["SOL/USDC,JUP/USDC"]):
            cases.append(["--seed", "0", "--frames", "1", "--assets", *assets])
        with patch("vonneumann.market.dataset_cli.write_dataset") as writer:
            for arguments in cases:
                with self.subTest(arguments=arguments):
                    code, stdout, stderr = self.invoke(defaults + arguments)
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn("error:", stderr)
                    self.assertFalse((self.root / "rejected").exists())
            writer.assert_not_called()

    def test_programmatic_invalid_inputs_are_rejected_before_feed_or_writer(self):
        cases = [
            {"frames": True}, {"frames": 0}, {"frames": MAX_FRAMES + 1}, {"frames": 1.5},
            {"seed": 1}, {"seed": "01"}, {"assets": []}, {"assets": [True]},
            {"assets": ["SOL/USDC", "SOL/USDC"]}, {"assets": ["unknown"]},
        ]
        with patch("vonneumann.market.dataset_cli.SimulationFeed") as feed, \
                patch("vonneumann.market.dataset_cli.write_dataset") as writer:
            for change in cases:
                arguments = {"frames": 1, "assets": ["SOL/USDC"], "seed": "0", **change}
                with self.subTest(change=change), self.assertRaises(ValueError):
                    asyncio.run(generate_synthetic_dataset(self.root / "rejected", **arguments))
            feed.assert_not_called()
            writer.assert_not_called()

    def test_existing_bundle_or_directory_is_never_overwritten(self):
        path, _ = self.generate()
        before = {entry.name: entry.read_bytes() for entry in path.iterdir()}
        code, stdout, stderr = self.invoke([
            "generate-synthetic", "--output", str(path), "--frames", "2", "--assets", "SOL/USDC"])
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr), {"error": "dataset_exists"})
        self.assertEqual({entry.name: entry.read_bytes() for entry in path.iterdir()}, before)

    def test_tampered_missing_and_invalid_bundles_return_safe_failure(self):
        path, _ = self.generate()
        marker = "private-payload-must-not-appear"
        with (path / "frames.jsonl").open("ab") as stream:
            stream.write(marker.encode())
        invalid = self.root / "invalid"
        invalid.mkdir()
        (invalid / "manifest.json").write_text(marker)
        (invalid / "frames.jsonl").write_text(marker)
        for candidate in (path, invalid, self.root / "missing"):
            with self.subTest(candidate=candidate.name):
                code, stdout, stderr = self.invoke(["validate", str(candidate)])
                self.assertEqual(code, 1)
                self.assertEqual(stdout, "")
                self.assertEqual(set(json.loads(stderr)), {"error"})
                self.assertNotIn(marker, stderr)
                self.assertNotIn(str(candidate), stderr)
                self.assertNotIn("Traceback", stderr)

    def test_symlink_input_and_output_fail_without_following_or_modifying_target(self):
        path, _ = self.generate()
        link = self.root / "alias"
        link.symlink_to(path, target_is_directory=True)
        before = {entry.name: entry.read_bytes() for entry in path.iterdir()}
        for arguments in (["validate", str(link)], [
            "generate-synthetic", "--output", str(link / "child"),
            "--frames", "1", "--assets", "SOL/USDC",
        ]):
            code, stdout, stderr = self.invoke(arguments)
            self.assertEqual(code, 1)
            self.assertEqual(stdout, "")
            self.assertEqual(set(json.loads(stderr)), {"error"})
        self.assertEqual({entry.name: entry.read_bytes() for entry in path.iterdir()}, before)

    def test_module_entrypoint_works_without_site_packages_credentials_or_network(self):
        # -S removes installed dependencies; import via runpy exercises the real
        # module entrypoint with an outbound-network trap in the child process.
        bootstrap = """
import runpy, socket, sys
def denied(*args, **kwargs):
    raise AssertionError('Unexpected network call')
socket.getaddrinfo = socket.create_connection = denied
socket.socket.connect = socket.socket.connect_ex = denied
sys.path.insert(0, sys.argv.pop(1))
sys.argv[0] = 'vonneumann.market.dataset_cli'
runpy.run_module('vonneumann.market.dataset_cli', run_name='__main__')
"""
        output_path = self.root / "process"
        result = subprocess.run([
            sys.executable, "-S", "-c", bootstrap, str(PACKAGE_ROOT),
            "generate-synthetic", "--output", str(output_path), "--frames", "1",
            "--assets", "SOL/USDC", "--seed", MAX_SEED,
        ], cwd=self.root, env={"PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(set(json.loads(result.stdout)), SUMMARY_KEYS)
        self.assertEqual(load_dataset(output_path).manifest["metadata"]["simulation_spec"]["seed"], MAX_SEED)


if __name__ == "__main__":
    unittest.main()
