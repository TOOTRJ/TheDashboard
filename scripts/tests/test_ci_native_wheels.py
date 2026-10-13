"""Pure fixture validation and mocked hosted preparation; no downloads or Docker."""
from contextlib import ExitStack
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wheels = load("dashboard_native_wheels_tests", SCRIPTS / "check-ci-native-wheels.py")
images = load("dashboard_native_image_tests", SCRIPTS / "check-ci-images.py")


def wheel_bytes(name="fixture", version="1.0", tag="py3-none-any", internal_tag=None,
                metadata_name=None, metadata_version=None, requires_python=None):
    content = io.BytesIO()
    directory = f"{name}-{version}.dist-info"
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr(directory + "/WHEEL", f"Wheel-Version: 1.0\nTag: {internal_tag or tag}\n")
        archive.writestr(directory + "/METADATA", f"Metadata-Version: 2.3\nName: {metadata_name or name}\nVersion: {metadata_version or version}\n" +
                         (f"Requires-Python: {requires_python}\n" if requires_python else ""))
    return f"{name}-{version}-{tag}.whl", content.getvalue()


class NativeWheelTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        temporary = self.stack.enter_context(tempfile.TemporaryDirectory(prefix="dashboard-native-wheel-test-"))
        self.root = Path(temporary).resolve()
        self.lock = self.root / "requirements-dev.txt"
        self.helper = self.root / "helper.py"; self.helper.write_text("# reviewed fixture helper\n")
        self.stack.enter_context(patch.object(wheels, "ROOT", self.root))
        self.stack.enter_context(patch.object(wheels, "LOCK", self.lock))
        self.stack.enter_context(patch.object(wheels, "HELPER", self.helper))
        self.directory = self.root / wheels.NAME

    def stage(self, entries=None, *, publish=True):
        entries = [wheel_bytes()] if entries is None else entries
        self.directory.mkdir(mode=0o700)
        pins = []
        for filename, content in entries:
            (self.directory / filename).write_bytes(content)
            (self.directory / filename).chmod(0o600)
            name, version, _, _ = wheels.parse_wheel_filename(filename)
            pins.append(f"{name}=={version} --hash=sha256:{hashlib.sha256(content).hexdigest()}")
        self.lock.write_text("--only-binary :all:\n" + "\n".join(pins) + "\n")
        if publish:
            self.publish()

    def publish(self):
        sidecar = wheels.manifest_path(self.directory)
        sidecar.write_text(json.dumps(wheels.bundle_manifest(self.directory, wheels.wheel_records(self.directory))))
        sidecar.chmod(0o600)

    def hosted(self):
        return {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
                "GITHUB_REPOSITORY_ID": "1141090963", "RUNNER_TEMP": str(self.root)}

    def runtime(self):
        self.stack.enter_context(patch.object(wheels.sys, "version_info", (3, 12, 14)))
        self.stack.enter_context(patch.object(wheels.sys, "platform", "linux"))
        self.stack.enter_context(patch.object(wheels.platform, "machine", return_value="x86_64"))

    def test_pure_validation_accepts_complete_bound_bundle_without_hosted_environment(self):
        self.stage([wheel_bytes(), wheel_bytes("nativefixture", "2.0", "cp312-cp312-manylinux_2_36_x86_64")])
        with patch.dict(os.environ, {}, clear=True), patch.object(wheels.subprocess, "run") as execute:
            self.assertEqual(wheels.validate_bundle(self.directory), self.directory)
            execute.assert_not_called()

    def test_renamed_mac_wheel_fails_internal_tag_binding_even_with_approved_archive_hash(self):
        self.stage([wheel_bytes(tag="cp312-cp312-manylinux_2_17_x86_64", internal_tag="cp312-cp312-macosx_11_0_arm64")], publish=False)
        with self.assertRaisesRegex(RuntimeError, "internal tags"):
            wheels.wheel_records(self.directory)

    def test_internal_name_and_version_must_match_the_locked_filename(self):
        for name, version in (("foreign", None), (None, "2.0")):
            with self.subTest(name=name, version=version):
                if self.directory.exists():
                    for path in self.directory.iterdir(): path.unlink()
                    self.directory.rmdir()
                self.stage([wheel_bytes(metadata_name=name, metadata_version=version)], publish=False)
                with self.assertRaisesRegex(RuntimeError, "internal package identity"):
                    wheels.wheel_records(self.directory)

    def test_bookworm_target_rejects_ubuntu_musl_wrong_abi_and_architecture(self):
        for tag in ("cp312-cp312-manylinux_2_39_x86_64", "cp312-cp312-musllinux_1_2_x86_64",
                    "cp313-cp313-manylinux_2_17_x86_64", "cp312-cp312-manylinux_2_17_aarch64",
                    "cp312-cp312-linux_x86_64"):
            with self.subTest(tag=tag):
                if self.directory.exists():
                    for path in self.directory.iterdir(): path.unlink()
                    self.directory.rmdir()
                self.stage([wheel_bytes(tag=tag)], publish=False)
                with self.assertRaisesRegex(RuntimeError, "incompatible"):
                    wheels.wheel_records(self.directory)

    def test_universal_filename_cannot_override_internal_python_requirement(self):
        self.stage([wheel_bytes(requires_python=">=3.13")], publish=False)
        with self.assertRaisesRegex(RuntimeError, "unsupported Python"):
            wheels.wheel_records(self.directory)

    def test_complete_inventory_hash_and_manifest_bindings_are_required(self):
        self.stage()
        sidecar = wheels.manifest_path(self.directory)
        original = sidecar.read_bytes()
        for key, value in (("lock_sha256", "0" * 64), ("helper_sha256", "0" * 64),
                           ("directory", "/foreign/dashboard-native-wheels"), ("target", {}), ("files", [])):
            manifest = json.loads(original); manifest[key] = value; sidecar.write_text(json.dumps(manifest))
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, "stale"):
                wheels.validate_bundle(self.directory)
        sidecar.write_bytes(original)
        file = next(self.directory.iterdir()); content = file.read_bytes()
        file.write_bytes(content + b"alteration")
        with self.assertRaisesRegex(RuntimeError, "lock hash"): wheels.validate_bundle(self.directory)
        file.write_bytes(content)
        file.unlink()
        with self.assertRaisesRegex(RuntimeError, "every locked package"): wheels.validate_bundle(self.directory)

    def test_legacy_bundle_permissions_links_extra_files_and_size_are_refused(self):
        self.stage()
        sidecar = wheels.manifest_path(self.directory); original = sidecar.read_bytes(); sidecar.unlink()
        with self.assertRaisesRegex(RuntimeError, "sibling manifest"): wheels.validate_bundle(self.directory)
        sidecar.write_bytes(original); sidecar.chmod(0o600)
        for path in (sidecar, next(self.directory.iterdir()), self.directory):
            mode = path.stat().st_mode & 0o777; path.chmod(0o777)
            with self.subTest(path=path.name), self.assertRaises(RuntimeError): wheels.validate_bundle(self.directory)
            path.chmod(mode)
        extra = self.directory / "secret.txt"; extra.write_text("synthetic only")
        with self.assertRaises(RuntimeError): wheels.validate_bundle(self.directory)
        extra.unlink()
        link = self.root / "link"; link.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaises(RuntimeError): wheels.validate_bundle(link)
        with patch.object(wheels, "MAX_BYTES", 1), self.assertRaisesRegex(RuntimeError, "150 MiB"):
            wheels.validate_bundle(self.directory)
        existing = next(self.directory.iterdir()); hardlink = self.root / "hardlink.whl"; os.link(existing, hardlink)
        with self.assertRaisesRegex(RuntimeError, "links"): wheels.validate_bundle(self.directory)

    def test_lock_requires_exact_unique_hash_pins_before_any_process(self):
        for text in ("", "--index-url https://foreign.invalid\n", "fixture>=1.0\n", "fixture==1.0\n",
                     "fixture==1.0 --hash=sha256:" + "0" * 64 + "\nfixture==1.0 --hash=sha256:" + "0" * 64 + "\n"):
            self.lock.write_text(text)
            with self.subTest(text=text), self.assertRaises(RuntimeError): wheels.locked_packages()

    def test_current_source_or_lock_change_retires_an_older_manifest(self):
        self.stage()
        self.helper.write_text("# changed reviewed fixture helper\n")
        with self.assertRaisesRegex(RuntimeError, "stale"): wheels.validate_bundle(self.directory)
        self.publish()
        self.lock.write_text(self.lock.read_text() + "# lock source changed\n")
        with self.assertRaisesRegex(RuntimeError, "stale"): wheels.validate_bundle(self.directory)

    def test_public_source_symlink_and_duplicate_manifest_keys_are_refused(self):
        self.stage()
        sidecar = wheels.manifest_path(self.directory)
        sidecar.write_text('{"schema":"dashboard-native-wheels-v1","schema":"dashboard-native-wheels-v1"}')
        with self.assertRaisesRegex(RuntimeError, "duplicate keys"): wheels.validate_bundle(self.directory)
        self.publish()
        original = self.helper.read_bytes(); self.helper.unlink()
        target = self.root / "other.py"; target.write_bytes(original); self.helper.symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, "links or private"): wheels.validate_bundle(self.directory)

    def test_preparation_refuses_nonhosted_wrong_target_runtime_path_and_reuse_before_process(self):
        self.runtime()
        self.lock.write_text("fixture==1.0 --hash=sha256:" + "0" * 64 + "\n")
        with patch.object(wheels.subprocess, "run") as execute:
            for env in ({}, {**self.hosted(), "RUNNER_ENVIRONMENT": "self-hosted"},
                        {**self.hosted(), "GITHUB_REPOSITORY_ID": "wrong"}):
                with self.assertRaises(RuntimeError): wheels.prepare(self.directory, env)
            with self.assertRaises(RuntimeError): wheels.prepare(self.root / "foreign", self.hosted())
            with patch.object(wheels.platform, "machine", return_value="aarch64"), self.assertRaises(RuntimeError):
                wheels.prepare(self.directory, self.hosted())
            self.directory.mkdir(mode=0o700)
            with self.assertRaisesRegex(RuntimeError, "existing"): wheels.prepare(self.directory, self.hosted())
            execute.assert_not_called()

    def test_preparation_uses_explicit_bookworm_tags_and_no_secret_environment_or_cache(self):
        self.runtime()
        filename, content = wheel_bytes()
        self.lock.write_text(f"fixture==1.0 --hash=sha256:{hashlib.sha256(content).hexdigest()}\n")
        def download(command, **kwargs):
            self.assertIn("--require-hashes", command); self.assertIn("--only-binary=:all:", command)
            self.assertIn("--no-cache-dir", command)
            self.assertEqual(command[command.index("--python-version") + 1], "3.12.14")
            self.assertEqual(command[command.index("--implementation") + 1], "cp")
            self.assertIn("manylinux_2_36_x86_64", command); self.assertNotIn("manylinux_2_39_x86_64", command)
            self.assertEqual(kwargs["env"]["PIP_CONFIG_FILE"], os.devnull)
            self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", kwargs["env"])
            self.assertNotIn("HOME", kwargs["env"]); self.assertNotIn("PIP_INDEX_URL", kwargs["env"])
            self.assertEqual(kwargs["timeout"], 240)
            (self.directory / filename).write_bytes(content)
            return subprocess.CompletedProcess(command, 0, "", "")
        with patch.object(wheels.subprocess, "run", side_effect=download), patch("sys.stdout", io.StringIO()):
            self.assertEqual(wheels.prepare(self.directory, {**self.hosted(), "SUPABASE_SERVICE_ROLE_KEY": "never-copy"}), self.directory)
        self.assertTrue(wheels.manifest_path(self.directory).is_file())
        self.assertEqual(wheels.validate_bundle(self.directory), self.directory)

    def test_failed_download_cleans_only_its_created_fixture(self):
        self.runtime(); self.lock.write_text("fixture==1.0 --hash=sha256:" + "0" * 64 + "\n")
        foreign = self.root / "other-fixture"; foreign.mkdir(); (foreign / "keep").write_text("keep")
        with patch.object(wheels.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "")), self.assertRaises(RuntimeError):
            wheels.prepare(self.directory, self.hosted())
        self.assertFalse(self.directory.exists()); self.assertFalse(wheels.manifest_path(self.directory).exists())
        self.assertEqual((foreign / "keep").read_text(), "keep")

    def test_local_existing_record_only_creates_absent_sidecar_after_complete_validation(self):
        self.stage(publish=False)
        content = next(self.directory.iterdir()).read_bytes()
        with patch.dict(os.environ, {}, clear=True), patch.object(wheels.subprocess, "run") as execute, patch("sys.stdout", io.StringIO()):
            self.assertEqual(wheels.record_existing(self.directory), self.directory)
            with self.assertRaisesRegex(RuntimeError, "replace"): wheels.record_existing(self.directory)
            execute.assert_not_called()
        self.assertEqual(next(self.directory.iterdir()).read_bytes(), content)
        self.assertEqual(wheels.validate_bundle(self.directory), self.directory)

    def test_local_existing_record_rejects_bad_bundle_before_creating_metadata(self):
        self.stage(publish=False)
        next(self.directory.iterdir()).write_bytes(b"not a locked wheel")
        with patch.object(wheels.subprocess, "run") as execute, self.assertRaises(RuntimeError):
            wheels.record_existing(self.directory)
        execute.assert_not_called()
        self.assertFalse(wheels.manifest_path(self.directory).exists())

    def test_third_image_requires_only_explicit_official_aliases_and_exact_digest(self):
        pin = images.PINS[2]
        self.assertEqual(pin["tag"], "python:3.12.14-slim-bookworm")
        for repository in pin["digest_repositories"]:
            images.verify_image({"Architecture": "amd64", "Os": "linux", "Id": pin["config"],
                                 "RepoDigests": [repository + "@" + pin["manifest"]]}, pin)
        for repository in ("foreign.invalid/library/python", "attacker/python", "python-foreign"):
            with self.assertRaises(ValueError):
                images.verify_image({"Architecture": "amd64", "Os": "linux", "Id": pin["config"],
                                     "RepoDigests": [repository + "@" + pin["manifest"]]}, pin)


if __name__ == "__main__": unittest.main()
