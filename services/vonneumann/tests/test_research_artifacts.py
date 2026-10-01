"""Local result integrity and publication tests; no trading semantic claims."""

from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import patch

from vonneumann.research import artifacts as codec
from vonneumann.research.artifacts import (
    ResearchArtifactError, canonical_bytes, load_result, plain_data, write_result,
)


def payload():
    return {"schema_version": "ema-research-v1", "config": {"asset": "SOL/USDC", "seed": "0"},
            "definitions": {"prices": [1, 0.00000001], "enabled": True, "note": "\u03b1"},
            "selection": None, "evaluations": []}


class ResearchArtifactTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for target in ("socket.getaddrinfo", "socket.create_connection", "socket.socket.connect"):
            self.stack.enter_context(patch(target, side_effect=AssertionError("No network permitted")))
        temp = self.stack.enter_context(tempfile.TemporaryDirectory(prefix="research-artifact-", dir="/private/tmp"))
        self.root = Path(temp)
        self.index = 0

    def output(self):
        self.index += 1
        return self.root / f"result-{self.index}"

    def reject(self, action, code=None):
        with self.assertRaises(ResearchArtifactError) as caught:
            action()
        self.assertEqual(str(caught.exception), "Offline research artifact validation failed.")
        if code is not None:
            self.assertEqual(caught.exception.code, code)
        return caught.exception

    def replace_payload(self, path, raw):
        (path / "result.json").write_bytes(raw)
        manifest = {"schema_version": "ema-research-artifact-v1", "payload": {
            "file": "result.json", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}}
        (path / "manifest.json").write_bytes(canonical_bytes(manifest))

    def test_roundtrip_exact_bytes_hash_and_recursive_immutability(self):
        original, path = payload(), self.output()
        result = write_result(path, original)
        self.assertEqual(load_result(path), result)
        raw = (path / "result.json").read_bytes()
        self.assertEqual(raw, canonical_bytes(original))
        self.assertTrue(raw.endswith(b"\n"))
        self.assertIn(b"\\u03b1", raw)
        self.assertEqual(result.manifest["payload"]["bytes"], len(raw))
        self.assertEqual(result.manifest["payload"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result.result_id, hashlib.sha256((path / "manifest.json").read_bytes()).hexdigest())
        self.assertNotIn("result_id", result.manifest)
        original["config"]["seed"] = "changed"
        original["definitions"]["prices"].append(20)
        self.assertEqual(result.payload["config"]["seed"], "0")
        self.assertEqual(result.payload["definitions"]["prices"], (1, 0.00000001))
        with self.assertRaises(TypeError):
            result.payload["config"]["seed"] = "mutated"
        with self.assertRaises(TypeError):
            result.manifest["payload"]["bytes"] = 0
        detached = plain_data(result.payload)
        detached["definitions"]["prices"].append(99)
        self.assertEqual(len(result.payload["definitions"]["prices"]), 2)
        clone = write_result(self.output(), result.payload)
        self.assertEqual(clone.result_id, result.result_id)

    def test_content_id_changes_with_payload_but_not_mapping_insertion_order(self):
        original = payload()
        reverse = dict(reversed(list(original.items())))
        a = write_result(self.output(), original)
        b = write_result(self.output(), reverse)
        self.assertEqual(a.result_id, b.result_id)
        reverse["config"]["seed"] = "1"
        c = write_result(self.output(), reverse)
        self.assertNotEqual(a.result_id, c.result_id)

    def test_codec_accepts_arbitrary_finite_json_without_certifying_trading_semantics(self):
        value = {"schema_version": "ema-research-v1", "unknown_strategy": "not verified",
                 "finite_values": (False, None, -1, 1e308, -0.0), "impossible_profit": 999999}
        result = write_result(self.output(), MappingProxyType(value))
        self.assertEqual(plain_data(result.payload), {**value, "finite_values": list(value["finite_values"])})

    def test_invalid_input_is_rejected_before_creating_output(self):
        for bad in (None, [], {}, {"schema_version": "other"},
                    {"schema_version": "ema-research-v1", 1: "bad key"}):
            path = self.output()
            self.reject(lambda: write_result(path, bad), "research_invalid")
            self.assertFalse(path.exists())
        for bad in (float("nan"), float("inf"), -float("inf"), 10**400, object(), b"private"):
            path, value = self.output(), payload()
            value["nested"] = {"bad": bad}
            self.reject(lambda: write_result(path, value), "research_invalid")
            self.assertFalse(path.exists())

    def test_nesting_cycles_and_writer_limits_fail_before_creation(self):
        for cycle in (False, True):
            value, cursor = payload(), []
            value["nested"] = cursor
            if cycle:
                cursor.append(cursor)
            else:
                for _ in range(codec.MAX_DEPTH + 1):
                    child = []
                    cursor.append(child)
                    cursor = child
            path = self.output()
            self.reject(lambda: write_result(path, value), "research_limits")
            self.assertFalse(path.exists())
        for constant in ("MAX_RESULT_BYTES", "MAX_MANIFEST_BYTES"):
            path = self.output()
            with patch.object(codec, constant, 8):
                self.reject(lambda: write_result(path, payload()), "research_limits")
            self.assertFalse(path.exists())

    def test_modified_bytes_wrong_lengths_and_manifest_tampering_fail(self):
        for mutation in ("content", "length", "digest", "unknown_key", "filename", "boolean_length"):
            path = self.output()
            write_result(path, payload())
            manifest = json.loads((path / "manifest.json").read_bytes())
            if mutation == "content":
                raw = (path / "result.json").read_bytes().replace(b"SOL", b"JUP")
                (path / "result.json").write_bytes(raw)
            else:
                if mutation == "length":
                    manifest["payload"]["bytes"] += 1
                elif mutation == "digest":
                    manifest["payload"]["sha256"] = "0" * 64
                elif mutation == "unknown_key":
                    manifest["private"] = "secret"
                elif mutation == "filename":
                    manifest["payload"]["file"] = "../private.json"
                else:
                    manifest["payload"]["bytes"] = True
                (path / "manifest.json").write_bytes(canonical_bytes(manifest))
            self.reject(lambda: load_result(path))

    def test_rehashed_payload_still_requires_valid_canonical_finite_json(self):
        cases = [
            b'{"schema_version":"ema-research-v1","x":1,"x":2}\n',
            b'{"schema_version":"ema-research-v1","x":NaN}\n',
            b'{"schema_version":"ema-research-v1","x":1e999}\n',
            b'{"schema_version":"ema-research-v1","x":' + str(10**400).encode() + b'}\n',
            b'{"schema_version":"ema-research-v1", "x":1}\n',
            b'{"schema_version":"ema-research-v1"}',
            b'{"schema_version":"other"}\n', b'[]\n', b'\xff', b'{',
            b'{"schema_version":"ema-research-v1","x":"\xce\xb1"}\n',
        ]
        for raw in cases:
            path = self.output()
            write_result(path, payload())
            self.replace_payload(path, raw)
            self.reject(lambda: load_result(path))

    def test_manifest_itself_requires_canonical_json_and_no_duplicate_keys(self):
        for mutation in ("whitespace", "duplicate", "nonfinite"):
            path = self.output()
            write_result(path, payload())
            raw = (path / "manifest.json").read_bytes()
            if mutation == "whitespace":
                raw = b" " + raw
            elif mutation == "duplicate":
                raw = raw.replace(b'{', b'{"schema_version":"ema-research-artifact-v1",', 1)
            else:
                raw = raw.replace(b'"bytes":', b'"bad":Infinity,"bytes":', 1)
            (path / "manifest.json").write_bytes(raw)
            self.reject(lambda: load_result(path))

    def test_bounded_reads_reject_oversized_regular_files_and_growth_after_stat(self):
        path = self.output()
        write_result(path, payload())
        for filename, constant in (("result.json", "MAX_RESULT_BYTES"),
                                   ("manifest.json", "MAX_MANIFEST_BYTES")):
            with patch.object(codec, constant, (path / filename).stat().st_size - 1):
                self.reject(lambda: load_result(path), "research_limits")
        # Force the pre-read stat to underreport size; bounded read must still
        # detect limit+1 bytes rather than trusting that potentially stale stat.
        real_stat = codec.os.fstat
        def undersized(descriptor):
            info = real_stat(descriptor)
            class Info:
                st_mode = info.st_mode
                st_size = 0
            return Info()
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with patch.object(codec.os, "fstat", side_effect=undersized):
                self.reject(lambda: codec._read_file(descriptor, "result.json", 10), "research_limits")
        finally:
            os.close(descriptor)

    def test_existing_directories_files_and_symlink_targets_are_never_replaced(self):
        path = self.output()
        first = write_result(path, payload())
        self.reject(lambda: write_result(path, payload()), "research_exists")
        self.assertEqual(load_result(path), first)
        for kind in ("empty_dir", "file", "symlink"):
            target = self.output()
            if kind == "empty_dir":
                target.mkdir()
            elif kind == "file":
                target.write_text("private original")
            else:
                target.symlink_to(path, target_is_directory=True)
            self.reject(lambda: write_result(target, payload()), "research_exists")
            if kind == "file":
                self.assertEqual(target.read_text(), "private original")

    def test_symlink_ancestors_bundle_files_and_path_traversal_are_rejected(self):
        path = self.output()
        write_result(path, payload())
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.reject(lambda: load_result(alias / path.name), "research_path")
        self.reject(lambda: write_result(alias / "new", payload()), "research_path")
        self.assertFalse((self.root / "new").exists())
        for invalid in ("", ".", "/", "../private", str(path / ".." / path.name), "\x00", "\ud800"):
            self.reject(lambda: load_result(invalid), "research_path")
            self.reject(lambda: write_result(invalid, payload()), "research_path")
        original = (path / "result.json").read_bytes()
        other = self.root / "actual.json"
        other.write_bytes(original)
        (path / "result.json").unlink()
        (path / "result.json").symlink_to(other)
        self.reject(lambda: load_result(path), "research_path")
        self.assertEqual(other.read_bytes(), original)

    def test_nonregular_files_incomplete_bundles_and_extra_entries_are_rejected(self):
        for change in ("missing", "extra", "directory", "fifo"):
            path = self.output()
            write_result(path, payload())
            target = path / "result.json"
            if change == "extra":
                (path / "unexpected.json").write_text("private")
            else:
                target.unlink()
                if change == "directory":
                    target.mkdir()
                elif change == "fifo":
                    os.mkfifo(target)
            self.reject(lambda: load_result(path), "research_path")

    def test_publish_order_syncs_payload_manifest_directory_and_parent(self):
        path, events = self.output(), []
        real_open, real_sync = codec.os.open, codec.os.fsync
        def opened(name, flags, *args, **kwargs):
            if flags & os.O_CREAT:
                events.append(("create", name))
            return real_open(name, flags, *args, **kwargs)
        def synced(descriptor):
            events.append(("sync", "directory" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "file"))
            return real_sync(descriptor)
        with patch.object(codec.os, "open", side_effect=opened), patch.object(codec.os, "fsync", side_effect=synced):
            write_result(path, payload())
        self.assertEqual(events, [("create", "result.json"), ("sync", "file"),
                                  ("create", "manifest.json"), ("sync", "file"),
                                  ("sync", "directory"), ("sync", "directory")])

    def test_payload_sync_failure_leaves_owned_incomplete_bundle_without_cleanup(self):
        path = self.output()
        with patch.object(codec.os, "fsync", side_effect=OSError("private path or token")):
            error = self.reject(lambda: write_result(path, payload()), "research_io")
        self.assertTrue(path.is_dir())
        self.assertTrue((path / "result.json").is_file())
        self.assertFalse((path / "manifest.json").exists())
        self.reject(lambda: load_result(path), "research_path")
        self.reject(lambda: write_result(path, payload()), "research_exists")
        self.assertTrue(error.__suppress_context__)

    def test_partial_manifest_failure_is_not_a_loadable_or_repairable_result(self):
        path, real_open = self.output(), codec.os.open
        def partial(name, flags, *args, **kwargs):
            descriptor = real_open(name, flags, *args, **kwargs)
            if name == "manifest.json" and flags & os.O_CREAT:
                os.write(descriptor, b"{")
                os.close(descriptor)
                raise OSError("private-token")
            return descriptor
        with patch.object(codec.os, "open", side_effect=partial):
            self.reject(lambda: write_result(path, payload()), "research_io")
        self.assertEqual((path / "manifest.json").read_bytes(), b"{")
        self.reject(lambda: load_result(path))
        self.reject(lambda: write_result(path, payload()), "research_exists")

    def test_error_codes_are_allowlisted_and_never_echo_untrusted_strings(self):
        for value in ("/private/secret", None, [], {"key": "secret"}):
            error = ResearchArtifactError(value)
            self.assertEqual(error.code, "research_invalid")
            self.assertEqual(str(error), "Offline research artifact validation failed.")


if __name__ == "__main__":
    unittest.main()
