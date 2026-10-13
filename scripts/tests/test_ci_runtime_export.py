"""Synthetic only: no image bytes, Docker, network, workflow or hosted authentication."""
from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dashboard_runtime_export_tests", SCRIPTS / "check-ci-runtime-export.py")
export = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = export
spec.loader.exec_module(export)


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def layer_file(name, raw=b"synthetic-file"):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        entry = tarfile.TarInfo(name)
        entry.size = len(raw); entry.mode = 0o600
        tar.addfile(entry, io.BytesIO(raw))
        link = tarfile.TarInfo("synthetic-link")
        link.type = tarfile.SYMTYPE; link.linkname = name
        tar.addfile(link)
        whiteout = tarfile.TarInfo(".wh.synthetic-obsolete")
        tar.addfile(whiteout, io.BytesIO())
    return output.getvalue()


def outer_archive(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, raw in entries:
            entry = tarfile.TarInfo(name)
            entry.size = len(raw); entry.mode = 0o600
            tar.addfile(entry, io.BytesIO(raw))
    return output.getvalue()


class CountedReader(io.BytesIO):
    def __init__(self, raw):
        super().__init__(raw); self.calls = 0; self.requested = []

    def read(self, size):
        self.calls += 1; self.requested.append(size)
        return super().read(size)


class BundleFixture:
    """Independent synthetic original config/manifests; private test pin substitution only."""
    def __init__(self):
        self.layers = [layer_file("synthetic-A"), layer_file("synthetic-B"), layer_file("synthetic-C")]
        self.images = []
        self.metadata = []
        self.pins = []
        memberships = ((0, 1), (1, 2), (0, 2))
        for index, membership in enumerate(memberships):
            repository, tag, _, _ = export.APPROVED_PINS[index]
            ordered = [self.layers[n] for n in membership]
            config = {"os": "linux", "architecture": "amd64", "config": {"Env": ["SYNTHETIC=only"]},
                      "rootfs": {"type": "layers", "diff_ids": [digest(raw) for raw in ordered]}, "unused_fraction": 0.25}
            config_raw = json.dumps(config, indent=2).encode() + b"\n"
            manifest = {"schemaVersion": 2, "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
                        "config": {"mediaType": "application/vnd.docker.container.image.v1+json", "size": len(config_raw), "digest": digest(config_raw)},
                        "layers": [{"mediaType": "application/vnd.docker.image.rootfs.diff.tar.gzip", "size": len(gzip.compress(raw, mtime=0)),
                                    "digest": digest(gzip.compress(raw, mtime=0))} for raw in ordered]}
            manifest_raw = json.dumps(manifest, indent=2).encode() + b"\n"
            self.metadata.append([manifest_raw, config_raw])
            self.pins.append((repository, tag, digest(manifest_raw), digest(config_raw)))
            self.images.append({"repository": repository, "tag": tag, "platform": "linux/amd64",
                                "platform_manifest_sha256": digest(manifest_raw), "config_sha256": digest(config_raw),
                                "manifest_member": f"images/{index}/platform-manifest.json", "config_member": f"images/{index}/config.json",
                                "layers": [{"member": f"layers/{digest(raw)[7:]}.tar", "diff_id": digest(raw), "bytes": str(len(raw))} for raw in ordered]})
        context = {"repository_id": "1141090963", "workflow_path": ".github/workflows/verification.yml",
                   "workflow_sha256": hashlib.sha256((export.ROOT / ".github/workflows/verification.yml").read_bytes()).hexdigest(),
                   "checkout_commit": "8" * 40, "head_commit": "9" * 40, "ref": "refs/pull/999/merge",
                   "run_id": "123", "run_attempt": "1", "producer_job": "fixture_images",
                   "artifact_name": f"dashboard-runtime-content-123-1-{export.POLICY_SHA256}"}
        source = {"producer_source_sha256": "1" * 64,
                  "verifier_source_sha256": hashlib.sha256((SCRIPTS / "check-ci-runtime-export.py").read_bytes()).hexdigest(),
                  "pin_source_sha256": hashlib.sha256(export.PIN_FILE.read_bytes()).hexdigest(),
                  "export_profile_sha256": "2" * 64, "normalized_mapping_format": "dashboard-ci-uncompressed-layer-map-v1"}
        self.transport = {"format": "dashboard-ci-runtime-content-archive-v1", "policy_sha256": export.POLICY_SHA256,
                          "producer_context": context, "source_declaration": source, "images": self.images, "authority": copy.deepcopy(export.FLAGS)}
        self.expected_base = {"format": "dashboard-ci-runtime-content-expected-v1", "policy_sha256": export.POLICY_SHA256,
                              "producer_context": copy.deepcopy(context), "source_declaration": copy.deepcopy(source), "artifact_id": "456"}

    def entries(self):
        entries = [("manifest.json", canonical(self.transport))]
        for index, (manifest, config) in enumerate(self.metadata):
            entries += [(f"images/{index}/platform-manifest.json", manifest), (f"images/{index}/config.json", config)]
        unique = {digest(raw): raw for raw in self.layers}
        entries += [(f"layers/{key[7:]}.tar", raw) for key, raw in sorted(unique.items())]
        return entries

    def wires(self, entries=None, archive=None):
        entries = entries if entries is not None else self.entries()
        raw = archive if archive is not None else outer_archive(entries)
        expected = {**copy.deepcopy(self.expected_base), "archive_sha256": hashlib.sha256(raw).hexdigest(),
                    "archive_bytes": str(len(raw)), "transport_manifest_sha256": hashlib.sha256(entries[0][1]).hexdigest()}
        return raw, canonical(expected)

    def replace_original(self, index, *, manifest=None, config=None):
        original = json.loads(self.metadata[index][0])
        if config is not None:
            self.metadata[index][1] = config
            original["config"]["digest"] = digest(config)
            original["config"]["size"] = len(config)
        self.metadata[index][0] = manifest if manifest is not None else canonical(original)
        repository, tag, _, _ = self.pins[index]
        self.pins[index] = (repository, tag, digest(self.metadata[index][0]), digest(self.metadata[index][1]))
        self.images[index]["platform_manifest_sha256"] = self.pins[index][2]
        self.images[index]["config_sha256"] = self.pins[index][3]


class RuntimeExportTests(unittest.TestCase):
    def setUp(self):
        anchor = {"darwin": "/private/tmp", "linux": "/tmp"}.get(sys.platform)
        if anchor is None:
            raise RuntimeError("Runtime export fixtures require a reviewed Darwin or Linux temporary anchor")
        self.parent = Path(tempfile.mkdtemp(prefix="dashboard-runtime-export-test-", dir=anchor))
        self.addCleanup(shutil.rmtree, self.parent)
        self.fixture = BundleFixture()

    def verify(self, archive=None, expected=None, entries=None, private_pins=True, reader=None):
        raw, wire = self.fixture.wires(entries, archive)
        wire = expected if expected is not None else wire
        source = reader if reader is not None else CountedReader(raw)
        if private_pins:
            with patch.object(export, "_reviewed_pins", return_value=tuple(self.fixture.pins)):
                report = export.verify_capture(source, wire, self.parent)
        else:
            report = export.verify_capture(source, wire, self.parent)
        self.assertEqual(list(self.parent.iterdir()), [])
        return json.loads(report), source

    def refused(self, **kwargs):
        with self.assertRaises(export.Refusal) as caught:
            self.verify(**kwargs)
        self.assertNotIn("SYNTHETIC", str(caught.exception))
        self.assertNotIn(str(self.parent), str(caught.exception))
        return caught.exception.code

    def test_three_images_complete_original_bytes_order_and_shared_layers(self):
        report, reader = self.verify()
        self.assertEqual(len(report["images"]), 3)
        self.assertTrue(all(value is False for value in report["authority"].values()))
        self.assertEqual([row["layer_count"] for row in report["images"]], ["2", "2", "2"])
        for image, row in zip(self.fixture.images, report["images"]):
            self.assertEqual(row["ordered_diff_ids_sha256"], hashlib.sha256(canonical([x["diff_id"] for x in image["layers"]])).hexdigest())
        self.assertGreater(reader.calls, 0)
        self.assertTrue(all(0 < size <= export.BUFFER for size in reader.requested))

    def test_actual_fixed_production_pins_reject_synthetic_not_caller_substitutable(self):
        self.assertEqual(self.refused(private_pins=False), "transport_schema")
        raw, wire = self.fixture.wires()
        value = json.loads(wire); value["pins"] = self.fixture.pins
        reader = CountedReader(raw)
        with patch.object(export, "OwnedInputs") as created:
            self.assertEqual(self.refused(expected=canonical(value), reader=reader), "expected_schema")
        created.assert_not_called(); self.assertEqual(reader.calls, 0)

    def test_wrong_independent_expectation_refuses_before_source_or_file_creation(self):
        raw, wire = self.fixture.wires()
        mutations = [("artifact_id", "0"), ("archive_bytes", "4294967297"), ("policy_sha256", "0" * 64),
                     ("archive_sha256", True), ("transport_manifest_sha256", "A" * 64)]
        for key, replacement in mutations:
            with self.subTest(key=key):
                value = json.loads(wire); value[key] = replacement
                reader = CountedReader(raw)
                with patch.object(export, "OwnedInputs") as created:
                    self.refused(expected=canonical(value), reader=reader)
                created.assert_not_called(); self.assertEqual(reader.calls, 0)

    def test_expected_context_source_pin_and_canonicalness_are_independent(self):
        raw, wire = self.fixture.wires()
        variants = []
        for key in ("workflow_sha256", "checkout_commit", "head_commit", "run_id", "run_attempt", "producer_job", "artifact_name", "repository_id"):
            value = json.loads(wire); value["producer_context"][key] = "wrong-private-value"
            variants.append(canonical(value))
        for key in self.fixture.expected_base["source_declaration"]:
            value = json.loads(wire); value["source_declaration"][key] = "wrong-private-value"
            variants.append(canonical(value))
        variants += [b" " + wire, wire + b"\n", b"\xef\xbb\xbf" + wire, b"{" + b" " * 65536 + b"}"]
        for variant in variants:
            with self.subTest(variant_sha=hashlib.sha256(variant).hexdigest()):
                reader = CountedReader(raw)
                with patch.object(export, "OwnedInputs") as created:
                    self.refused(expected=variant, reader=reader)
                created.assert_not_called(); self.assertEqual(reader.calls, 0)

    def test_stale_actual_verifier_workflow_and_pin_file_hashes_refuse_early(self):
        raw, wire = self.fixture.wires()
        for container, field in (("source_declaration", "verifier_source_sha256"), ("source_declaration", "pin_source_sha256"), ("producer_context", "workflow_sha256")):
            value = json.loads(wire); value[container][field] = "0" * 64
            reader = CountedReader(raw)
            with patch.object(export, "OwnedInputs") as created:
                self.assertEqual(self.refused(expected=canonical(value), reader=reader), "source_binding")
            created.assert_not_called(); self.assertEqual(reader.calls, 0)

    def test_source_parent_replacement_during_read_cannot_rebind_original_opened_leaf(self):
        directory = self.parent / "source-dir"; directory.mkdir(mode=0o700)
        source = directory / "helper.py"; source.write_bytes(b"old-owned-source")
        before = source.lstat()
        original_read = os.read
        replaced = [False]
        def replace_parent_after_read(fd, size):
            raw = original_read(fd, size)
            if raw and not replaced[0]:
                replaced[0] = True
                directory.rename(self.parent / "moved-source-dir")
                directory.mkdir(mode=0o700); source.write_bytes(b"new-owned-source")
            return raw
        with patch.object(export.os, "read", side_effect=replace_parent_after_read), self.assertRaises(export.Refusal) as caught:
            export._source_bytes(source)
        self.assertEqual(caught.exception.code, "source_binding")
        original = (self.parent / "moved-source-dir/helper.py").lstat()
        self.assertEqual((original.st_dev, original.st_ino, original.st_size, original.st_mtime_ns, original.st_ctime_ns),
                         (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns))
        self.assertEqual(source.read_bytes(), b"new-owned-source")

    def test_transport_context_does_not_replace_original_expected_run(self):
        self.fixture.transport["producer_context"]["run_attempt"] = "2"
        self.fixture.transport["producer_context"]["artifact_name"] = f"dashboard-runtime-content-123-2-{export.POLICY_SHA256}"
        self.assertEqual(self.refused(), "transport_schema")

    def test_wrong_source_profile_and_all_false_authority_cannot_be_promoted(self):
        for key in export.FLAGS:
            with self.subTest(key=key):
                original = self.fixture.transport["authority"][key]
                self.fixture.transport["authority"][key] = True
                self.assertEqual(self.refused(), "transport_schema")
                self.fixture.transport["authority"][key] = original
        self.fixture.transport["authority"]["sql_executed"] = 0
        self.assertEqual(self.refused(), "transport_schema")

    def test_byte_corruption_is_refused_even_before_typed_parse(self):
        raw, wire = self.fixture.wires()
        corrupted = bytearray(raw); corrupted[600] ^= 1
        self.assertEqual(self.refused(archive=bytes(corrupted), expected=wire), "content_pin")

    def test_rehashed_archive_cannot_substitute_original_config_or_manifest(self):
        for index in (1, 2):
            with self.subTest(entry=index):
                entries = self.fixture.entries(); name, raw = entries[index]
                replacement = raw + b" " if index == 1 else raw.replace(b"0.25", b"0.26", 1)
                self.assertNotEqual(replacement, raw)
                if index == 2: self.assertEqual(len(replacement), len(raw))
                entries[index] = name, replacement
                self.assertEqual(self.refused(entries=entries), "content_pin")

    def test_every_real_layer_hash_is_checked_not_just_metadata(self):
        entries = self.fixture.entries(); name, raw = entries[-1]
        changed = bytearray(raw); changed[800] ^= 1
        entries[-1] = name, bytes(changed)
        self.assertEqual(self.refused(entries=entries), "content_pin")

    def test_ordered_config_diffids_cannot_be_reordered_by_mapping(self):
        self.fixture.images[0]["layers"].reverse()
        self.assertEqual(self.refused(), "original_schema")

    def test_foreign_platform_repository_tag_and_member_paths_refuse(self):
        for key, wrong in (("platform", "linux/arm64"), ("repository", "foreign.invalid/image"), ("tag", "python:latest"),
                           ("manifest_member", "../manifest.json"), ("config_member", "images/1/config.json")):
            value = self.fixture.images[0][key]; self.fixture.images[0][key] = wrong
            self.refused(); self.fixture.images[0][key] = value

    def test_missing_extra_reordered_and_duplicate_outer_members_refuse(self):
        entries = self.fixture.entries()
        for mutated in (entries[:-1], entries + [("foreign.txt", b"fake")], entries[:1] + entries[2:3] + entries[1:2] + entries[3:],
                        entries + [entries[-1]]):
            with self.subTest(names=[name for name, _ in mutated]):
                self.refused(entries=mutated)

    def test_layer_size_counter_and_shared_size_disagreement_refuse(self):
        for wrong in ("0", "01", "-1", "1.0", 1, True, "8589934593"):
            value = self.fixture.images[0]["layers"][0]["bytes"]
            self.fixture.images[0]["layers"][0]["bytes"] = wrong
            self.refused(); self.fixture.images[0]["layers"][0]["bytes"] = value
        self.fixture.images[1]["layers"][0]["bytes"] = "1"
        self.assertEqual(self.refused(), "transport_schema")

    def test_layer_count_limits_include_complete_extra_references(self):
        value = self.fixture.images[0]["layers"]
        for wrong in ([], value * 33):
            self.fixture.images[0]["layers"] = wrong
            self.assertEqual(self.refused(), "transport_schema")
        self.fixture.images[0]["layers"] = value

    def test_logical_bytes_charge_all_shared_references(self):
        # This bounded private cap demonstrates logical charging without allocating GiBs.
        physical = sum(len(raw) for raw in self.fixture.layers)
        with patch.object(export, "LAYER_MAX", physical):
            self.assertEqual(self.refused(), "archive_budget")

    def test_original_bool_float_schema_slots_and_foreign_urls_refuse(self):
        original = copy.deepcopy(self.fixture)
        for change in ({"schemaVersion": True}, {"schemaVersion": 2.0}, {"schemaVersion": 3},
                       {"mediaType": "unknown"}):
            self.fixture = copy.deepcopy(original)
            manifest = json.loads(self.fixture.metadata[0][0]); manifest.update(change)
            self.fixture.replace_original(0, manifest=canonical(manifest)); self.assertEqual(self.refused(), "original_schema")
        self.fixture = copy.deepcopy(original)
        manifest = json.loads(self.fixture.metadata[0][0]); manifest["layers"][0]["urls"] = ["https://foreign.invalid"]
        self.fixture.replace_original(0, manifest=canonical(manifest)); self.assertEqual(self.refused(), "original_schema")

    def test_unused_original_fields_receive_complete_strict_json_validation(self):
        original = copy.deepcopy(self.fixture)
        cases = [b'{"unused":NaN}', b'{"unused":Infinity}', b'{"unused":"\\ud800"}', b'{"\\u0000":1}',
                 b'{"os":"linux","o\\u0073":"linux"}', b'{"unused":' + b'1' * 129 + b'}']
        for raw in cases:
            with self.subTest(raw_sha=hashlib.sha256(raw).hexdigest()):
                self.fixture = copy.deepcopy(original); self.fixture.replace_original(0, config=raw)
                self.refused()

    def test_valid_original_supplementary_unicode_escaped_and_literal_is_byte_preserved(self):
        config = json.loads(self.fixture.metadata[0][1]); config["unused_unicode"] = "supplementary \U0001f680"
        for ascii_only in (True, False):
            raw = json.dumps(config, ensure_ascii=ascii_only, indent=2).encode("utf-8") + b"\n"
            self.fixture.replace_original(0, config=raw)
            report, _ = self.verify(); self.assertEqual(report["images"][0]["config_sha256"], digest(raw))

    def test_json_depth_nodes_number_and_byte_caps_before_full_typed_use(self):
        for raw in (b'[' * 33 + b'0' + b']' * 33,
                    b'[' + b'0,' * 100000 + b'0]', b'1' * 129, b' ' * (export.JSON_MAX + 1)):
            with self.subTest(length=len(raw)), self.assertRaises(export.Refusal):
                export._json(raw)
        value = export._json(b'[' * 32 + b'0' + b']' * 32)
        for _ in range(32):
            self.assertIs(type(value), list); self.assertEqual(len(value), 1); value = value[0]
        self.assertEqual(value, 0)

    def test_compressed_outer_input_and_noncanonical_transport_refuse(self):
        raw, wire = self.fixture.wires()
        with self.assertRaises(export.Refusal):
            self.verify(archive=gzip.compress(raw), expected=wire)
        entries = self.fixture.entries(); entries[0] = "manifest.json", entries[0][1] + b"\n"
        self.assertEqual(self.refused(entries=entries), "json_canonical")

    def test_outer_header_links_devices_extensions_and_names_refuse(self):
        raw, _ = self.fixture.wires()
        for offset, replacement in ((156, b"2"), (156, b"1"), (156, b"3"), (156, b"5"), (156, b"x"),
                                    (156, b"S"), (0, b"../"), (257, b"GNU"), (345, b"x"), (108, b"9")):
            changed = bytearray(raw); changed[offset:offset + len(replacement)] = replacement
            changed[148:156] = b"        "
            changed[148:156] = f"{sum(changed[:512]):06o}\0 ".encode()
            self.assertEqual(self.refused(archive=bytes(changed)), "archive_header")

    def test_header_checksum_padding_and_terminal_exact_eof(self):
        raw, _ = self.fixture.wires()
        changed = bytearray(raw); changed[148] ^= 1
        self.assertEqual(self.refused(archive=bytes(changed)), "archive_header")
        entries = self.fixture.entries(); body_end = 512 + len(entries[0][1])
        changed = bytearray(raw); changed[body_end] = 1
        self.assertEqual(self.refused(archive=bytes(changed)), "archive_padding")
        changed = bytearray(raw); changed[-1] = 1
        self.assertEqual(self.refused(archive=bytes(changed)), "archive_terminal")
        self.assertEqual(self.refused(archive=raw + bytes(10240)), "archive_terminal")

    def test_truncated_and_oversized_capture_is_bounded_without_loading(self):
        raw, wire = self.fixture.wires()
        reader = CountedReader(raw[:-1]); self.assertEqual(self.refused(expected=wire, reader=reader), "content_pin")
        class Oversized:
            def read(self, size):
                return b"x" * (export.BUFFER + 1)
        self.assertEqual(self.refused(expected=wire, reader=Oversized()), "capture_budget")
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_source_exception_is_fixed_safe_and_own_cleanup_completes(self):
        class Unavailable:
            def read(self, size):
                raise RuntimeError("fake-private-source-message")
        _, wire = self.fixture.wires()
        self.assertEqual(self.refused(expected=wire, reader=Unavailable()), "capture")
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_late_capture_success_refuses_and_does_not_restart_deadline(self):
        now = [0.0]
        class Late(CountedReader):
            def read(self, size):
                result = super().read(size); now[0] = 241.0
                return result
        raw, wire = self.fixture.wires()
        with patch.object(export.time, "monotonic", side_effect=lambda: now[0]):
            self.assertEqual(self.refused(expected=wire, reader=Late(raw)), "deadline")
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_late_cleanup_completion_cannot_return_success(self):
        now = [0.0]
        original = export.OwnedInputs.close
        def close_after_deadline(owned):
            original(owned); now[0] = 241.0
        with patch.object(export.time, "monotonic", side_effect=lambda: now[0]), \
                patch.object(export.OwnedInputs, "close", close_after_deadline):
            self.assertEqual(self.refused(), "deadline")
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_cleanup_rechecks_each_remaining_leaf_after_first_own_unlink(self):
        owned = export.OwnedInputs(self.parent)
        owned.create("expected.json"); owned.write("expected.json", b"{}")
        owned.create("bundle.tar"); owned.write("bundle.tar", b"original")
        directory = self.parent / owned.name
        original_unlink = os.unlink
        def replace_after_first(name, **kwargs):
            original_unlink(name, **kwargs)
            if name == "expected.json":
                (directory / "bundle.tar").rename(directory / "old-bundle.tar")
                (directory / "bundle.tar").write_text("replacement-private-test-only")
        with patch.object(export.os, "unlink", side_effect=replace_after_first), self.assertRaises(export.Refusal):
            owned.close()
        self.assertEqual((directory / "bundle.tar").read_text(), "replacement-private-test-only")
        self.assertEqual((directory / "old-bundle.tar").read_bytes(), b"original")

    def test_private_directory_inventory_stops_at_first_unknown_entry(self):
        owned = export.OwnedInputs(self.parent)
        owned.create("expected.json"); owned.write("expected.json", b"{}")
        class Entries:
            visits = 0
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self): return self
            def __next__(self):
                self.visits += 1
                if self.visits > 1: raise AssertionError("Unknown inventory must not be materialized")
                return type("Entry", (), {"name": "foreign-private-test-only"})()
        entries = Entries()
        with patch.object(export.os, "scandir", return_value=entries), self.assertRaises(export.Refusal):
            owned.check()
        self.assertEqual(entries.visits, 1)
        owned.close(); self.assertEqual(list(self.parent.iterdir()), [])

    def test_parent_symlink_foreign_mode_and_preexisting_directory_are_not_adopted(self):
        link = self.parent / "link"; link.symlink_to(self.parent, target_is_directory=True)
        with self.assertRaises(export.Refusal): export.OwnedInputs(link)
        self.parent.chmod(0o777)
        with self.assertRaises(export.Refusal): export.OwnedInputs(self.parent)
        self.parent.chmod(0o700)
        name = "dashboard-runtime-export-" + "1" * 32
        foreign = self.parent / name; foreign.mkdir(); (foreign / "sentinel").write_text("private-test-only")
        fake = type("Token", (), {"hex": "1" * 32})()
        with patch.object(export.uuid, "uuid4", return_value=fake), self.assertRaises(export.Refusal):
            export.OwnedInputs(self.parent)
        self.assertEqual((foreign / "sentinel").read_text(), "private-test-only")

    def test_controller_rejects_file_replacement_and_preserves_foreign_inode(self):
        owned = export.OwnedInputs(self.parent)
        owned.create("expected.json"); owned.write("expected.json", b"{}")
        directory = self.parent / owned.name
        original = directory / "original-expected.json"
        (directory / "expected.json").rename(original)
        (directory / "expected.json").write_text("replacement-private-test-only")
        with self.assertRaises(export.Refusal): owned.check()
        with self.assertRaises(export.Refusal): owned.close()
        self.assertEqual((directory / "expected.json").read_text(), "replacement-private-test-only")
        self.assertEqual(original.read_bytes(), b"{}")

    def test_controller_refuses_hardlink_mode_and_content_changes(self):
        for action in ("hardlink", "mode", "content"):
            with self.subTest(action=action):
                owned = export.OwnedInputs(self.parent)
                owned.create("expected.json"); owned.write("expected.json", b"{}")
                file = self.parent / owned.name / "expected.json"
                if action == "hardlink": os.link(file, self.parent / owned.name / "extra")
                elif action == "mode": file.chmod(0o644)
                else: file.write_bytes(b"xx")
                with self.assertRaises(export.Refusal): owned.check()
                with self.assertRaises(export.Refusal): owned.close()
                self.assertTrue(file.exists())

    def test_changed_parent_path_preserves_replacement_and_never_foreign_cleanup(self):
        parent = self.parent / "private-parent"; parent.mkdir(mode=0o700)
        owned = export.OwnedInputs(parent); owned.create("expected.json"); owned.write("expected.json", b"{}")
        original = self.parent / "moved-parent"; parent.rename(original)
        parent.mkdir(mode=0o700); (parent / "sentinel").write_text("replacement")
        with self.assertRaises(export.Refusal): owned.check()
        with self.assertRaises(export.Refusal): owned.close()
        self.assertEqual((parent / "sentinel").read_text(), "replacement")
        self.assertEqual((original / owned.name / "expected.json").read_bytes(), b"{}")


if __name__ == "__main__":
    unittest.main()
