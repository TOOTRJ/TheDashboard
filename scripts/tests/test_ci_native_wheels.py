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


class PullClock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def docker_args(command):
    return command[command.index("--host") + 2:]


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
                "GITHUB_REPOSITORY_ID": "1141090963", "RUNNER_TEMP": str(self.root),
                "DASHBOARD_TEST_SHARD": "1"}

    def runtime(self):
        self.stack.enter_context(patch.object(wheels.sys, "version_info", (3, 12, 14)))
        self.stack.enter_context(patch.object(wheels.sys, "platform", "linux"))
        self.stack.enter_context(patch.object(wheels.platform, "machine", return_value="x86_64"))

    def prepare_image(self, pin, execute, clock, output, *, jitter=0):
        with patch.object(images, "PINS", (pin,)), patch.object(images.subprocess, "run", side_effect=execute), \
             patch.object(images.time, "sleep", side_effect=clock.sleep), \
             patch.object(images.time, "monotonic", side_effect=clock.monotonic), \
             patch.object(images, "jitter_seconds", return_value=jitter), patch("sys.stdout", output):
            images.prepare(self.hosted())

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

    def test_docker_failure_classes_do_not_include_captured_private_text(self):
        samples = (("toomanyrequests: You have reached your unauthenticated pull rate limit", "rate-limited"),
                   ("unexpected status from HEAD request: 503 Service Unavailable", "registry-unavailable"),
                   ("net/http: TLS handshake timeout", "network-timeout"),
                   ("read tcp: connection reset by peer", "transport-reset"),
                   ("manifest unknown", "manifest-unavailable"), ("unauthorized: authentication required", "authorization-denied"),
                   ("Cannot connect to the Docker daemon at unix:///var/run/docker.sock", "daemon-unavailable"),
                   ("unexpected failure for synthetic-private-token", "unclassified"))
        for message, category in samples:
            with self.subTest(category=category):
                self.assertEqual(images.error_class(message + " synthetic-private-token"), category)

    def test_rate_limit_changes_once_to_the_verified_mirror_and_tags_the_actual_source(self):
        for pin in images.PINS[:2]:
            mirror = images.MIRRORS[pin["repository"]]
            reference = mirror["repository"] + "@" + pin["manifest"]
            metadata = {"Architecture": "amd64", "Os": "linux", "Id": pin["config"],
                        "RepoDigests": [mirror["digest_repositories"][-1] + "@" + pin["manifest"]]}
            events, output, clock = [], io.StringIO(), PullClock()
            def execute(command, **kwargs):
                args = docker_args(command); events.append((args, kwargs))
                self.assertNotIn("HOME", kwargs["env"])
                self.assertNotIn("DOCKER_AUTH_CONFIG", kwargs["env"])
                if args[0] == "pull":
                    if sum(event[0][0] == "pull" for event in events) == 1:
                        clock.now += 2
                        return subprocess.CompletedProcess(command, 1, "", "429 synthetic-private-token")
                    clock.now += 3
                return subprocess.CompletedProcess(command, 0, json.dumps([metadata]) if args[:2] == ["image", "inspect"] else "", "")
            with self.subTest(pin=pin["repository"]):
                self.prepare_image(pin, execute, clock, output, jitter=3)
            pulls = [(args, kwargs) for args, kwargs in events if args[0] == "pull"]
            self.assertEqual([args[-1] for args, _ in pulls], [pin["repository"] + "@" + pin["manifest"], reference])
            self.assertEqual([kwargs["timeout"] for _, kwargs in pulls], [237, 222])
            self.assertEqual(clock.sleeps, [3, 13])
            self.assertEqual([args for args, _ in events if args[:2] == ["image", "tag"]],
                             [["image", "tag", reference, pin["tag"]]])
            self.assertEqual([args[-1] for args, _ in events if args[:2] == ["image", "inspect"]],
                             [reference, pin["tag"]])
            reports = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(len([r for r in reports if r.get("state") == "mirror-selected"]), 1)
            self.assertEqual([r["source_repository"] for r in reports if r.get("operation") == "pull" and r.get("state") == "starting"],
                             [pin["repository"], mirror["repository"]])
            self.assertTrue(all(r["source_repository"] == mirror["repository"] for r in reports
                                if r.get("operation") in {"inspect-pulled", "tag-fixture", "inspect-fixture"}))
            self.assertNotIn("synthetic-private-token", output.getvalue())
            self.assertFalse(list(self.root.glob("dashboard-ci-docker-*")))

    def test_mirror_transition_keeps_five_total_attempts_and_never_bounces_to_ecr(self):
        pin = images.PINS[0]; mirror = images.MIRRORS[pin["repository"]]["repository"]
        events, output, clock = [], io.StringIO(), PullClock()
        errors = ["503 unavailable", "429 rate limit", "503 unavailable", "429 rate limit", "503 unavailable"]
        def execute(command, **kwargs):
            args = docker_args(command); events.append((args, kwargs)); clock.now += 1
            self.assertEqual(args[0], "pull")
            return subprocess.CompletedProcess(command, 1, "", errors[len(events) - 1])
        with self.assertRaisesRegex(RuntimeError, "registry-unavailable"):
            self.prepare_image(pin, execute, clock, output)
        self.assertEqual(len(events), 5)
        self.assertEqual([args[-1] for args, _ in events],
                         [repo + "@" + pin["manifest"] for repo in [pin["repository"], pin["repository"], mirror, mirror, mirror]])
        self.assertEqual([kwargs["timeout"] for _, kwargs in events], [240, 229, 208, 167, 106])
        self.assertEqual(clock.sleeps, [0, 10, 20, 40, 60])
        self.assertEqual(output.getvalue().count('"state": "mirror-selected"'), 1)
        self.assertFalse(list(self.root.glob("dashboard-ci-docker-*")))

    def test_permanent_or_unknown_ecr_failure_never_selects_a_mirror_even_with_429_wording(self):
        for error in ("unauthorized", "403 rate limit", "unauthorized 429", "manifest unknown 429",
                      "Cannot connect to the docker daemon 429", "unknown synthetic-private-token"):
            pin = images.PINS[0]; events, output, clock = [], io.StringIO(), PullClock()
            def execute(command, **kwargs):
                events.append(docker_args(command))
                return subprocess.CompletedProcess(command, 1, "", error)
            with self.subTest(error=error), self.assertRaises(RuntimeError):
                self.prepare_image(pin, execute, clock, output)
            self.assertEqual(events, [["pull", "--platform", "linux/amd64", pin["repository"] + "@" + pin["manifest"]]])
            self.assertEqual(clock.sleeps, [0])
            self.assertNotIn("mirror-selected", output.getvalue())
            self.assertNotIn("synthetic-private-token", output.getvalue())

    def test_permanent_mirror_failure_stops_without_canonical_retry(self):
        for error in ("unauthorized", "manifest unknown", "unknown synthetic-private-token"):
            pin = images.PINS[0]; events, output, clock = [], io.StringIO(), PullClock()
            def execute(command, **kwargs):
                events.append(docker_args(command))
                return subprocess.CompletedProcess(command, 1, "", "429" if len(events) == 1 else error)
            with self.subTest(error=error), self.assertRaises(RuntimeError):
                self.prepare_image(pin, execute, clock, output)
            self.assertEqual([args[-1] for args in events], [pin["repository"] + "@" + pin["manifest"],
                             images.MIRRORS[pin["repository"]]["repository"] + "@" + pin["manifest"]])
            self.assertEqual(clock.sleeps, [0, 10])
            self.assertFalse(list(self.root.glob("dashboard-ci-docker-*")))

    def test_identity_failure_never_triggers_another_pull_or_an_unverified_tag(self):
        for use_mirror in (False, True):
            pin = images.PINS[0]; events, output, clock = [], io.StringIO(), PullClock()
            selected = images.MIRRORS[pin["repository"]]["repository"] if use_mirror else pin["repository"]
            other = pin["repository"] if use_mirror else images.MIRRORS[pin["repository"]]["repository"]
            metadata = {"Architecture": "amd64", "Os": "linux", "Id": pin["config"],
                        "RepoDigests": [other + "@" + pin["manifest"]]}
            def execute(command, **kwargs):
                args = docker_args(command); events.append(args)
                if use_mirror and len(events) == 1:
                    return subprocess.CompletedProcess(command, 1, "", "429")
                return subprocess.CompletedProcess(command, 0, json.dumps([metadata]) if args[:2] == ["image", "inspect"] else "", "")
            with self.subTest(mirror=use_mirror), self.assertRaises(ValueError):
                self.prepare_image(pin, execute, clock, output)
            self.assertEqual(sum(args[0] == "pull" for args in events), 2 if use_mirror else 1)
            self.assertEqual(events[-1], ["image", "inspect", selected + "@" + pin["manifest"]])
            self.assertFalse(any(args[:2] == ["image", "tag"] for args in events))

    def test_final_fixture_inspection_requires_the_actual_mirror_digest_without_invented_ecr_digest(self):
        pin = images.PINS[0]; mirror = images.MIRRORS[pin["repository"]]["repository"]
        events, output, clock = [], io.StringIO(), PullClock()
        def execute(command, **kwargs):
            args = docker_args(command); events.append(args)
            if len(events) == 1:
                return subprocess.CompletedProcess(command, 1, "", "429")
            repository = pin["repository"] if args[-1] == pin["tag"] else mirror
            metadata = {"Architecture": "amd64", "Os": "linux", "Id": pin["config"],
                        "RepoDigests": [repository + "@" + pin["manifest"]]}
            return subprocess.CompletedProcess(command, 0, json.dumps([metadata]) if args[:2] == ["image", "inspect"] else "", "")
        with self.assertRaises(ValueError):
            self.prepare_image(pin, execute, clock, output)
        self.assertEqual(sum(args[0] == "pull" for args in events), 2)
        self.assertEqual(events[-2:], [["image", "tag", mirror + "@" + pin["manifest"], pin["tag"]],
                                      ["image", "inspect", pin["tag"]]])

    def test_mirror_late_success_or_timeout_cannot_restart_the_original_deadline(self):
        for outcome in ("late-success", "timeout"):
            pin = images.PINS[0]; events, output, clock = [], io.StringIO(), PullClock()
            def execute(command, **kwargs):
                args = docker_args(command); events.append((args, kwargs["timeout"]))
                if len(events) == 1:
                    clock.now += 1
                    return subprocess.CompletedProcess(command, 1, "", "429")
                clock.now += kwargs["timeout"] + (0.1 if outcome == "late-success" else 0)
                if outcome == "timeout":
                    raise subprocess.TimeoutExpired(command, kwargs["timeout"])
                return subprocess.CompletedProcess(command, 0, "", "")
            with self.subTest(outcome=outcome), self.assertRaisesRegex(RuntimeError, "network-timeout"):
                self.prepare_image(pin, execute, clock, output)
            self.assertEqual([timeout for _, timeout in events], [240, 229])
            self.assertEqual([args[-1] for args, _ in events], [pin["repository"] + "@" + pin["manifest"],
                             images.MIRRORS[pin["repository"]]["repository"] + "@" + pin["manifest"]])
            self.assertTrue(all(args[0] == "pull" for args, _ in events))
            self.assertEqual(clock.sleeps, [0, 10])
            self.assertFalse(list(self.root.glob("dashboard-ci-docker-*")))

    def test_transient_pull_retries_same_exact_pin_within_original_budget_without_stderr_output(self):
        pin = images.PINS[0]
        metadata = {"Architecture": "amd64", "Os": "linux", "Id": pin["config"],
                    "RepoDigests": [pin["repository"] + "@" + pin["manifest"]]}
        events, output = [], io.StringIO()
        clock = PullClock()
        def execute(command, **kwargs):
            events.append((command, kwargs))
            if docker_args(command)[0] == "pull" and sum(docker_args(event[0])[0] == "pull" for event in events) == 1:
                clock.now += 2
                return subprocess.CompletedProcess(command, 1, "", "503 service unavailable synthetic-private-token")
            return subprocess.CompletedProcess(command, 0, json.dumps([metadata]) if docker_args(command)[:2] == ["image", "inspect"] else "", "")
        with patch.object(images, "PINS", (pin,)), patch.object(images.subprocess, "run", side_effect=execute), \
             patch.object(images.time, "sleep", side_effect=clock.sleep), patch.object(images.time, "monotonic", side_effect=clock.monotonic), \
             patch.object(images, "jitter_seconds", return_value=3), \
             patch("sys.stdout", output):
            images.prepare(self.hosted())
        pulls = [event for event in events if docker_args(event[0])[0] == "pull"]
        self.assertEqual(len(pulls), 2); self.assertEqual(pulls[0][0], pulls[1][0])
        self.assertEqual([event[1]["timeout"] for event in pulls], [237, 222])
        self.assertEqual(clock.sleeps, [3, 13])
        self.assertIn(pin["manifest"], output.getvalue()); self.assertIn("registry-unavailable", output.getvalue())
        reports = [json.loads(line) for line in output.getvalue().splitlines()]
        failure = next(item for item in reports if item.get('state') == 'failed')
        self.assertEqual(failure['elapsed_seconds'], 2)
        self.assertEqual(failure['pin_elapsed_seconds'], 5)
        self.assertNotIn("synthetic-private-token", output.getvalue())

    def test_permanent_pull_failure_and_exhausted_retry_are_bounded_and_never_fallback(self):
        pin = images.PINS[2]
        for error, count in (("unauthorized synthetic-private-token", 1), ("manifest unknown synthetic-private-token", 1),
                             ("unknown synthetic-private-token", 1), ("toomanyrequests synthetic-private-token", 5)):
            output = io.StringIO()
            clock = PullClock()
            with self.subTest(error=error), patch.object(images, "PINS", (pin,)), \
                 patch.object(images.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", error)) as execute, \
                 patch.object(images.time, "sleep", side_effect=clock.sleep), patch.object(images.time, "monotonic", side_effect=clock.monotonic), \
                 patch.object(images, "jitter_seconds", return_value=3), \
                 patch("sys.stdout", output), self.assertRaises(RuntimeError) as caught:
                images.prepare(self.hosted())
            self.assertEqual(execute.call_count, count)
            self.assertLessEqual(sum(clock.sleeps), 145)
            self.assertEqual(clock.sleeps, [3, 13, 23, 43, 63] if count == 5 else [3])
            self.assertTrue(all(call.args[0][-1] == pin["repository"] + "@" + pin["manifest"] for call in execute.call_args_list))
            self.assertTrue(all(0 < call.kwargs['timeout'] <= 240 for call in execute.call_args_list))
            self.assertNotIn("synthetic-private-token", output.getvalue() + str(caught.exception))

    def test_pull_deadline_exhaustion_prevents_a_second_240_second_attempt(self):
        output = io.StringIO()
        clock = PullClock()
        def expired(*args, **kwargs):
            clock.now += kwargs['timeout']
            raise subprocess.TimeoutExpired([], kwargs['timeout'])
        with patch.object(images, "PINS", (images.PINS[0],)), patch.object(images.subprocess, "run", side_effect=expired) as execute, \
             patch.object(images.time, "sleep", side_effect=clock.sleep), patch.object(images.time, "monotonic", side_effect=clock.monotonic), \
             patch.object(images, "jitter_seconds", return_value=0), \
             patch("sys.stdout", output), self.assertRaisesRegex(RuntimeError, "network-timeout"):
            images.prepare(self.hosted())
        self.assertEqual(execute.call_count, 1); self.assertEqual(clock.sleeps, [0])

    def test_initial_shard_stagger_is_part_of_each_pin_budget_and_never_an_image_selector(self):
        pins = images.PINS[:2]
        for shard in range(1, 5):
            clock, events = PullClock(), []
            def execute(command, **kwargs):
                args = docker_args(command); events.append((args, kwargs['timeout']))
                pin = next(pin for pin in pins if args[-1] in (pin['tag'], pin['repository'] + '@' + pin['manifest']))
                metadata = {'Architecture': 'amd64', 'Os': 'linux', 'Id': pin['config'],
                            'RepoDigests': [pin['repository'] + '@' + pin['manifest']]}
                return subprocess.CompletedProcess(command, 0, json.dumps([metadata]) if args[:2] == ['image', 'inspect'] else '', '')
            with self.subTest(shard=shard), patch.object(images, 'PINS', pins), \
                 patch.object(images.subprocess, 'run', side_effect=execute), \
                 patch.object(images.time, 'monotonic', side_effect=clock.monotonic), \
                 patch.object(images.time, 'sleep', side_effect=clock.sleep), \
                 patch.object(images, 'jitter_seconds', return_value=3), patch('sys.stdout', io.StringIO()):
                images.prepare({**self.hosted(), 'DASHBOARD_TEST_SHARD': str(shard)})
            delay = (shard - 1) * 4 + 3
            self.assertEqual(clock.sleeps, [delay, delay])
            pulls = [(args, timeout) for args, timeout in events if args[0] == 'pull']
            self.assertEqual([args[-1] for args, _ in pulls], [pin['repository'] + '@' + pin['manifest'] for pin in pins])
            self.assertEqual([timeout for _, timeout in pulls], [240 - delay, 240 - delay])

    def test_noncanonical_or_absent_shard_refuses_before_filesystem_or_process_work(self):
        for value in (None, '', '0', '5', '01', '1 ', ' 1', '1\n', '1.0', True, 1, 'secret'):
            environment = self.hosted(); environment['DASHBOARD_TEST_SHARD'] = value
            with self.subTest(value=value), patch.object(images, 'runner_directory') as directory, \
                 patch.object(images.os, 'mkdir') as mkdir, patch.object(images.subprocess, 'run') as execute, \
                 self.assertRaisesRegex(RuntimeError, 'canonical SQL shard'):
                images.prepare(environment)
            directory.assert_not_called(); mkdir.assert_not_called(); execute.assert_not_called()

    def test_runner_directory_requires_canonical_owned_nonwritable_directory_before_process(self):
        regular = self.root / 'regular'; regular.write_text('preserve')
        target = self.root / 'target'; target.mkdir(mode=0o700)
        link = self.root / 'linked'; link.symlink_to(target, target_is_directory=True)
        writable = self.root / 'writable'; writable.mkdir(mode=0o777); writable.chmod(0o777)
        for value in ('relative', '', None, str(regular), str(link), str(target / '..' / 'target'),
                      str(self.root / 'absent'), str(writable)):
            with self.subTest(value=value), patch.object(images.os, 'mkdir') as mkdir, \
                 patch.object(images.subprocess, 'run') as execute, self.assertRaisesRegex(RuntimeError, 'owned runner temporary'):
                images.prepare({**self.hosted(), 'RUNNER_TEMP': value})
            mkdir.assert_not_called(); execute.assert_not_called()
        metadata = target.lstat()
        with patch.object(images.Path, 'lstat', return_value=type('ForeignOwner', (), {
                'st_mode': metadata.st_mode, 'st_uid': os.geteuid() + 1})()), \
             patch.object(images.subprocess, 'run') as execute, self.assertRaises(RuntimeError):
            images.runner_directory(str(target))
        execute.assert_not_called(); self.assertEqual(regular.read_text(), 'preserve')

    def test_every_docker_child_uses_same_empty_private_config_and_sanitized_environment_then_removes_only_it(self):
        pin = images.PINS[0]; configs = []
        foreign = self.root / 'shared-docker'; foreign.mkdir(); (foreign / 'config.json').write_text('preserve private credentials')
        metadata = {'Architecture': 'amd64', 'Os': 'linux', 'Id': pin['config'],
                    'RepoDigests': [pin['repository'] + '@' + pin['manifest']]}
        inherited = {**self.hosted(), 'PATH': '/test/bin', 'DOCKER_CONFIG': str(foreign),
                     'HOME': str(foreign), 'DOCKER_AUTH_CONFIG': 'synthetic-private-token',
                     'DOCKER_CONTEXT': 'private-context', 'SUPABASE_SERVICE_ROLE_KEY': 'synthetic-private-token',
                     'HTTPS_PROXY': 'private-proxy', 'TMPDIR': '/foreign/temp'}
        def execute(command, **kwargs):
            config = Path(command[command.index('--config') + 1]); configs.append(config)
            self.assertEqual(config.parent, self.root); self.assertEqual(config.stat().st_mode & 0o777, 0o700)
            self.assertEqual(list(config.iterdir()), [])
            self.assertEqual(kwargs['env'], {'PATH': '/test/bin', 'DOCKER_HOST': 'unix:///var/run/docker.sock',
                                            'DOCKER_CONFIG': str(config), 'TMPDIR': str(self.root)})
            args = docker_args(command)
            return subprocess.CompletedProcess(command, 0, json.dumps([metadata]) if args[:2] == ['image', 'inspect'] else '', '')
        with patch.object(images, 'PINS', (pin,)), patch.object(images.subprocess, 'run', side_effect=execute), \
             patch.object(images.time, 'sleep'), patch.object(images, 'jitter_seconds', return_value=0), patch('sys.stdout', io.StringIO()):
            images.prepare(inherited)
        self.assertEqual(len(configs), 4); self.assertEqual(len(set(configs)), 1)
        self.assertFalse(configs[0].exists()); self.assertEqual((foreign / 'config.json').read_text(), 'preserve private credentials')

    def test_success_after_deadline_and_scheduler_sleep_overshoot_fail_without_inspect_or_retry(self):
        for phase in ('pull-success', 'initial-sleep', 'retry-sleep'):
            clock, events = PullClock(), []
            def sleep(seconds):
                clock.sleep(seconds)
                if phase == 'initial-sleep' or (phase == 'retry-sleep' and len(clock.sleeps) == 2):
                    clock.now += 241
            def execute(command, **kwargs):
                events.append((command, kwargs))
                if phase == 'pull-success':
                    clock.now += 241
                    return subprocess.CompletedProcess(command, 0, '', '')
                return subprocess.CompletedProcess(command, 1, '', '429 synthetic-private-token')
            output = io.StringIO()
            with self.subTest(phase=phase), patch.object(images, 'PINS', (images.PINS[0],)), \
                 patch.object(images.subprocess, 'run', side_effect=execute), \
                 patch.object(images.time, 'monotonic', side_effect=clock.monotonic), patch.object(images.time, 'sleep', side_effect=sleep), \
                 patch.object(images, 'jitter_seconds', return_value=0), patch('sys.stdout', output), self.assertRaises(RuntimeError):
                images.prepare(self.hosted())
            self.assertEqual(len(events), 0 if phase == 'initial-sleep' else 1)
            self.assertTrue(all(docker_args(command)[0] == 'pull' for command, _ in events))
            self.assertFalse(list(self.root.glob('dashboard-ci-docker-*')))
            self.assertNotIn('synthetic-private-token', output.getvalue())

    def test_keyboard_cancellation_during_stagger_or_pull_unwinds_only_owned_config(self):
        foreign = self.root / 'untouched'; foreign.mkdir(); (foreign / 'keep').write_text('keep')
        for phase in ('stagger', 'pull'):
            output = io.StringIO()
            with self.subTest(phase=phase), patch.object(images, 'PINS', (images.PINS[0],)), \
                 patch.object(images, 'jitter_seconds', return_value=0), \
                 patch.object(images.time, 'sleep', side_effect=KeyboardInterrupt if phase == 'stagger' else None), \
                 patch.object(images.subprocess, 'run', side_effect=KeyboardInterrupt) as execute, \
                 patch('sys.stdout', output), self.assertRaises(KeyboardInterrupt):
                images.prepare(self.hosted())
            self.assertEqual(execute.call_count, 0 if phase == 'stagger' else 1)
            self.assertFalse(list(self.root.glob('dashboard-ci-docker-*')))
            self.assertEqual((foreign / 'keep').read_text(), 'keep')
            if phase == 'pull': self.assertIn('"state": "cancelled"', output.getvalue())

    def test_changed_config_name_is_refused_and_replacement_is_never_removed(self):
        preserved = []
        def replace(command, **kwargs):
            config = Path(command[command.index('--config') + 1])
            moved = config.with_name(config.name + '-original'); config.rename(moved)
            config.mkdir(mode=0o700); (config / 'keep').write_text('replacement')
            preserved.extend((config, moved))
            return subprocess.CompletedProcess(command, 0, '', '')
        try:
            with patch.object(images, 'PINS', (images.PINS[0],)), patch.object(images.subprocess, 'run', side_effect=replace) as execute, \
                 patch.object(images.time, 'sleep'), patch.object(images, 'jitter_seconds', return_value=0), \
                 patch('sys.stdout', io.StringIO()), self.assertRaisesRegex(RuntimeError, 'cleanup refused'):
                images.prepare(self.hosted())
            self.assertEqual(execute.call_count, 1)
            self.assertEqual((preserved[0] / 'keep').read_text(), 'replacement'); self.assertTrue(preserved[1].is_dir())
        finally:
            if preserved:
                (preserved[0] / 'keep').unlink(); preserved[0].rmdir(); preserved[1].rmdir()

    def test_new_config_contents_refuse_before_next_command_and_are_not_recursively_deleted(self):
        configs = []
        def write(command, **kwargs):
            config = Path(command[command.index('--config') + 1]); configs.append(config)
            (config / 'config.json').write_text('synthetic only')
            return subprocess.CompletedProcess(command, 0, '', '')
        try:
            with patch.object(images, 'PINS', (images.PINS[0],)), patch.object(images.subprocess, 'run', side_effect=write) as execute, \
                 patch.object(images.time, 'sleep'), patch.object(images, 'jitter_seconds', return_value=0), \
                 patch('sys.stdout', io.StringIO()), self.assertRaisesRegex(RuntimeError, 'cleanup refused'):
                images.prepare(self.hosted())
            self.assertEqual(execute.call_count, 1); self.assertEqual((configs[0] / 'config.json').read_text(), 'synthetic only')
        finally:
            if configs: (configs[0] / 'config.json').unlink(); configs[0].rmdir()

    def test_parent_replacement_refuses_and_descriptor_cleanup_touches_only_original_created_directory(self):
        parent = self.root / 'runner-temp'; parent.mkdir(mode=0o700)
        moved = self.root / 'original-runner-temp'
        configs = []
        def replace(command, **kwargs):
            configs.append(Path(command[command.index('--config') + 1]).name)
            parent.rename(moved); parent.mkdir(mode=0o700); (parent / 'keep').write_text('replacement')
            return subprocess.CompletedProcess(command, 0, '', '')
        with patch.object(images, 'PINS', (images.PINS[0],)), patch.object(images.subprocess, 'run', side_effect=replace) as execute, \
             patch.object(images.time, 'sleep'), patch.object(images, 'jitter_seconds', return_value=0), \
             patch('sys.stdout', io.StringIO()), self.assertRaisesRegex(RuntimeError, 'binding changed'):
            images.prepare({**self.hosted(), 'RUNNER_TEMP': str(parent)})
        self.assertEqual(execute.call_count, 1)
        self.assertFalse((moved / configs[0]).exists()); self.assertEqual((parent / 'keep').read_text(), 'replacement')

    def test_final_config_mode_change_is_refused_before_successful_return_and_owned_empty_directory_is_removed(self):
        pin, configs = images.PINS[0], []
        metadata = {'Architecture': 'amd64', 'Os': 'linux', 'Id': pin['config'],
                    'RepoDigests': [pin['repository'] + '@' + pin['manifest']]}
        calls = 0
        def execute(command, **kwargs):
            nonlocal calls
            calls += 1; config = Path(command[command.index('--config') + 1]); configs.append(config)
            if calls == 4: config.chmod(0o777)
            return subprocess.CompletedProcess(command, 0, json.dumps([metadata]) if docker_args(command)[:2] == ['image', 'inspect'] else '', '')
        with patch.object(images, 'PINS', (pin,)), patch.object(images.subprocess, 'run', side_effect=execute), \
             patch.object(images.time, 'sleep'), patch.object(images, 'jitter_seconds', return_value=0), \
             patch('sys.stdout', io.StringIO()), self.assertRaisesRegex(RuntimeError, 'binding changed'):
            images.prepare(self.hosted())
        self.assertEqual(calls, 4); self.assertFalse(configs[0].exists())


if __name__ == "__main__": unittest.main()
