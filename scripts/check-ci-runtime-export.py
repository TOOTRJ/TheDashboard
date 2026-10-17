#!/usr/bin/env python3
"""Pure prototype: verify an owned normalized runtime-content archive, never load it."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
POLICY_FILE = ROOT / "CI-RUNTIME-EXPORT-POLICY.json"
PIN_FILE = ROOT / "scripts/check-ci-images.py"
POLICY_SHA256 = "613edd678d372ff40890b5075cbee00e822745c1ed5e17aa96f63a8c6675d4c7"
ARCHIVE_MAX = 4 * 1024**3
LAYER_MAX = 8 * 1024**3
JSON_MAX = 1024**2
EXPECTED_MAX = 65536
BUFFER = 1024**2
SECONDS = 240
FLAGS = {
    "compressed_registry_blobs_preserved": False, "docker_export_mapping_proven": False,
    "hosted_producer_authenticated": False, "loaded_runtime_verified": False,
    "original_repo_digests_preserved": False, "production_worker_authority": False,
    "sql_executed": False, "trading_authority": False,
}
HEX = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
COMMIT = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
COUNTER = re.compile(r"[1-9][0-9]{0,19}\Z", re.ASCII)
APPROVED_PINS = (
    ("public.ecr.aws/supabase/postgres", "public.ecr.aws/supabase/postgres:17.6.1.095",
     "sha256:4c087262afbfbb47da86e2863a52d7e424eb21ab589f732d77eeaab51be8e521",
     "sha256:972aabc75779f6e535f87e1669f36edbab02cdf8bf3f47d13579963c119adefb"),
    ("public.ecr.aws/supabase/postgrest", "public.ecr.aws/supabase/postgrest:v14.5",
     "sha256:bb289d00570b569525e1e22fb77c49cd17c17ca3f41da9ee2b4351a35027551b",
     "sha256:af0a6dad76305650c215449d905a124ae5ad3bcd0f04c01845a0cea17d4e0960"),
    ("docker.io/library/python", "python:3.12.14-slim-bookworm",
     "sha256:1aaa65a85fda306ffb8b910824d4e93bdce61e212c7e87168123ea3073b41a1a",
     "sha256:febd0be41adb897a0ab8f1f1c693d8912669ea60c4940e076e9946b60e210ef0"),
)
SCHEMAS = {
    "expected": {"format", "policy_sha256", "producer_context", "source_declaration", "artifact_id",
                 "archive_sha256", "archive_bytes", "transport_manifest_sha256"},
    "context": {"repository_id", "workflow_path", "workflow_sha256", "checkout_commit", "head_commit",
                "ref", "run_id", "run_attempt", "producer_job", "artifact_name"},
    "source": {"producer_source_sha256", "verifier_source_sha256", "pin_source_sha256",
               "export_profile_sha256", "normalized_mapping_format"},
    "transport": {"format", "policy_sha256", "producer_context", "source_declaration", "images", "authority"},
    "image": {"repository", "tag", "platform", "platform_manifest_sha256", "config_sha256",
              "manifest_member", "config_member", "layers"},
    "layer": {"member", "diff_id", "bytes"},
}


class Refusal(ValueError):
    """A fixed safe error, without request bodies, paths, secrets or exception text."""
    def __init__(self, code: str):
        self.code = code
        super().__init__("Dashboard runtime-content verification refused: " + code)


def refuse(code: str):
    raise Refusal(code) from None


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        refuse("json_canonical")


def _exact(value, fields, code="json_schema"):
    if type(value) is not dict or set(value) != set(fields):
        refuse(code)
    return value


def _number(token: str, integer=False):
    if len(token) > 128:
        refuse("json_budget")
    try:
        result = int(token) if integer else Decimal(token)
    except (ValueError, InvalidOperation):
        refuse("json_number")
    if isinstance(result, Decimal) and not result.is_finite():
        refuse("json_number")
    return result


def _json(raw: bytes, maximum=JSON_MAX, canonical=False):
    if type(raw) is not bytes or not 0 < len(raw) <= maximum or raw.startswith(b"\xef\xbb\xbf"):
        refuse("json_budget")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                refuse("json_duplicate")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=pairs,
                           parse_int=lambda t: _number(t, True), parse_float=_number,
                           parse_constant=lambda _: refuse("json_number"))
    except Refusal:
        raise
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        refuse("json_parse")
    visits = 0
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        visits += 1
        if depth > 32 or visits > 100000:
            refuse("json_budget")
        if type(item) is dict:
            pending.extend((child, depth + 1) for pair in item.items() for child in pair)
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            if "\0" in item or any(0xD800 <= ord(c) <= 0xDFFF for c in item):
                refuse("json_string")
        elif isinstance(item, Decimal) and not item.is_finite():
            refuse("json_number")
    if canonical and _canonical(value) != raw:
        refuse("json_canonical")
    return value


def _hex(value):
    if type(value) is not str or not HEX.fullmatch(value):
        refuse("identity")
    return value


def _digest(value):
    if type(value) is not str or not value.startswith("sha256:"):
        refuse("identity")
    _hex(value[7:])
    return value


def _counter(value, maximum=2**64 - 1):
    if type(value) is not str or not COUNTER.fullmatch(value) or int(value) > maximum:
        refuse("identity")
    return int(value)


def _uint(value, maximum):
    if type(value) is not int or not 0 < value <= maximum:
        refuse("original_schema")
    return value


def _check_deadline(deadline):
    if time.monotonic() > deadline:
        refuse("deadline")


def _source_bytes(path: Path):
    fd = None
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > JSON_MAX:
            refuse("source_binding")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
            refuse("source_binding")
        raw = bytearray()
        while len(raw) <= JSON_MAX:
            part = os.read(fd, min(BUFFER, JSON_MAX + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        after = os.fstat(fd)
        if (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns):
            refuse("source_binding")
        named = path.lstat()
        if (not stat.S_ISREG(named.st_mode)
                or (named.st_dev, named.st_ino, named.st_size, named.st_mtime_ns, named.st_ctime_ns)
                != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)):
            refuse("source_binding")
        if len(raw) != opened.st_size or len(raw) > JSON_MAX:
            refuse("source_binding")
        return bytes(raw)
    except OSError:
        refuse("source_binding")
    finally:
        if fd is not None:
            os.close(fd)


def _reviewed_pins(raw: bytes):
    """Only this private test seam may be mocked; callers cannot supply pin tuples."""
    try:
        tree = ast.parse(raw.decode("utf-8"))
        declarations = [node.value for node in tree.body if isinstance(node, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "PINS" for t in node.targets)]
        if len(declarations) != 1:
            refuse("source_binding")
        pins = ast.literal_eval(declarations[0])
        observed = tuple(tuple(pin[key] for key in ("repository", "tag", "manifest", "config")) for pin in pins)
    except (ValueError, KeyError, TypeError, UnicodeError, SyntaxError):
        refuse("source_binding")
    if observed != APPROVED_PINS:
        refuse("source_binding")
    return APPROVED_PINS


def _expected(wire: bytes, deadline):
    value = _exact(_json(wire, EXPECTED_MAX, True), SCHEMAS["expected"], "expected_schema")
    if value["format"] != "dashboard-ci-runtime-content-expected-v1" or value["policy_sha256"] != POLICY_SHA256:
        refuse("expected_schema")
    context = _exact(value["producer_context"], SCHEMAS["context"], "expected_schema")
    source = _exact(value["source_declaration"], SCHEMAS["source"], "expected_schema")
    if (context["repository_id"] != "1141090963" or context["workflow_path"] != ".github/workflows/verification.yml"
            or context["producer_job"] != "fixture_images"):
        refuse("identity")
    for key in ("checkout_commit", "head_commit"):
        if type(context[key]) is not str or not COMMIT.fullmatch(context[key]):
            refuse("identity")
    ref = context["ref"]
    if (type(ref) is not str or not 0 < len(ref.encode("utf-8")) <= 256
            or any(ord(c) < 32 or ord(c) == 127 for c in ref)):
        refuse("identity")
    _counter(context["run_id"]); _counter(context["run_attempt"]); _counter(value["artifact_id"])
    if context["artifact_name"] != f"dashboard-runtime-content-{context['run_id']}-{context['run_attempt']}-{POLICY_SHA256}":
        refuse("identity")
    size = _counter(value["archive_bytes"], ARCHIVE_MAX)
    if size % 10240 or size < 10240:
        refuse("archive_budget")
    for key in ("archive_sha256", "transport_manifest_sha256"):
        _hex(value[key])
    for key in ("producer_source_sha256", "verifier_source_sha256", "pin_source_sha256", "export_profile_sha256"):
        _hex(source[key])
    if source["normalized_mapping_format"] != "dashboard-ci-uncompressed-layer-map-v1":
        refuse("expected_schema")
    _hex(context["workflow_sha256"])
    policy = _source_bytes(POLICY_FILE)
    if _hash(_canonical(_json(policy))) != POLICY_SHA256:
        refuse("source_binding")
    if _hash(_source_bytes(Path(__file__))) != source["verifier_source_sha256"]:
        refuse("source_binding")
    pin_source = _source_bytes(PIN_FILE)
    if _hash(pin_source) != source["pin_source_sha256"]:
        refuse("source_binding")
    if _hash(_source_bytes(ROOT / context["workflow_path"])) != context["workflow_sha256"]:
        refuse("source_binding")
    pins = _reviewed_pins(pin_source)
    _check_deadline(deadline)
    return value, pins


@dataclass(frozen=True)
class FilePin:
    device: int
    inode: int
    size: int
    modified: int
    changed: int

    @classmethod
    def of(cls, value):
        return cls(value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


class OwnedInputs:
    """Own only newly exclusive resources; no constructor for an existing input path."""
    def __init__(self, parent: Path):
        self.parent = parent
        self.parent_fd = self.directory_fd = None
        self.name = None
        self.files = {}
        self.pins = {}
        self.closed = False
        try:
            before = parent.lstat()
            if (not parent.is_absolute() or parent.resolve(strict=True) != parent or not stat.S_ISDIR(before.st_mode)
                    or before.st_uid != os.geteuid() or before.st_mode & 0o022):
                refuse("input_ownership")
            self.parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            self.parent_pin = os.fstat(self.parent_fd)
            if (before.st_dev, before.st_ino) != (self.parent_pin.st_dev, self.parent_pin.st_ino):
                refuse("input_ownership")
            self.name = "dashboard-runtime-export-" + uuid.uuid4().hex
            os.mkdir(self.name, mode=0o700, dir_fd=self.parent_fd)
            self.directory_pin = os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)
            self.directory_fd = os.open(self.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.parent_fd)
            if (os.fstat(self.directory_fd).st_dev, os.fstat(self.directory_fd).st_ino) != (self.directory_pin.st_dev, self.directory_pin.st_ino):
                refuse("input_ownership")
        except (OSError, RuntimeError, Refusal):
            try:
                self.close()
            except Refusal:
                pass
            refuse("input_ownership")

    def _check_directory(self):
        try:
            parent = self.parent.lstat()
            directory = os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)
            if ((parent.st_dev, parent.st_ino) != (self.parent_pin.st_dev, self.parent_pin.st_ino)
                    or not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid() or parent.st_mode & 0o022
                    or (directory.st_dev, directory.st_ino) != (self.directory_pin.st_dev, self.directory_pin.st_ino)
                    or not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.geteuid()
                    or stat.S_IMODE(directory.st_mode) != 0o700):
                refuse("input_ownership")
            wanted, seen = set(self.files), set()
            with os.scandir(self.directory_fd) as entries:
                for entry in entries:
                    if entry.name not in wanted or entry.name in seen:
                        refuse("input_ownership")
                    seen.add(entry.name)
            if seen != wanted:
                refuse("input_ownership")
        except OSError:
            refuse("input_ownership")

    def check(self):
        self._check_directory()
        for name, fd in self.files.items():
            try:
                current = os.fstat(fd)
                named = os.stat(name, dir_fd=self.directory_fd, follow_symlinks=False)
                if (not stat.S_ISREG(current.st_mode) or current.st_uid != os.geteuid() or current.st_nlink != 1
                        or stat.S_IMODE(current.st_mode) != 0o600 or FilePin.of(current) != self.pins[name]
                        or FilePin.of(named) != self.pins[name] or not stat.S_ISREG(named.st_mode)):
                    refuse("input_ownership")
            except OSError:
                refuse("input_ownership")

    def create(self, name):
        if name not in ("expected.json", "bundle.tar") or name in self.files:
            refuse("input_ownership")
        self.check()
        try:
            fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=self.directory_fd)
            self.files[name] = fd
            self.pins[name] = FilePin.of(os.fstat(fd))
            self.check()
            return fd
        except OSError:
            refuse("input_ownership")

    def write(self, name, raw):
        self.check()
        fd = self.files[name]
        view = memoryview(raw)
        try:
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    refuse("capture")
                view = view[written:]
                self.pins[name] = FilePin.of(os.fstat(fd))
        except OSError:
            refuse("capture")
        self.check()

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.directory_fd is not None:
                self.check()
                for name in tuple(self.files):
                    self.check()
                    os.unlink(name, dir_fd=self.directory_fd)
                    os.close(self.files.pop(name))
                    self.pins.pop(name)
                self._check_directory()
                os.rmdir(self.name, dir_fd=self.parent_fd)
            elif self.name is not None and hasattr(self, "directory_pin"):
                current = os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) != (self.directory_pin.st_dev, self.directory_pin.st_ino):
                    refuse("cleanup_ownership")
                os.rmdir(self.name, dir_fd=self.parent_fd)
        except (OSError, Refusal):
            refuse("cleanup_ownership")
        finally:
            for fd in self.files.values():
                os.close(fd)
            if self.directory_fd is not None:
                os.close(self.directory_fd)
            if self.parent_fd is not None:
                os.close(self.parent_fd)


def _header(name: str, size: int):
    if len(name.encode("ascii")) > 100 or not 0 <= size < 8 * 1024**3:
        refuse("archive_header")
    block = bytearray(512)
    encoded = name.encode("ascii")
    block[:len(encoded)] = encoded
    block[100:108] = b"0000600\0"
    block[108:116] = block[116:124] = b"0000000\0"
    block[124:136] = f"{size:011o}\0".encode("ascii")
    block[136:148] = b"00000000000\0"
    block[148:156] = b"        "
    block[156:157] = b"0"
    block[257:265] = b"ustar\0" + b"00"
    block[148:156] = f"{sum(block):06o}\0 ".encode("ascii")
    return bytes(block)


class ArchiveReader:
    def __init__(self, inputs, deadline):
        self.inputs, self.deadline = inputs, deadline
        self.fd = inputs.files["bundle.tar"]
        self.position = 0
        os.lseek(self.fd, 0, os.SEEK_SET)

    def exact(self, size):
        if not 0 <= size <= BUFFER:
            refuse("archive_budget")
        _check_deadline(self.deadline)
        pieces = bytearray()
        while len(pieces) < size:
            part = os.read(self.fd, size - len(pieces))
            _check_deadline(self.deadline)
            if not part:
                refuse("archive_truncated")
            pieces.extend(part)
        self.position += size
        return bytes(pieces)

    def member(self, name, maximum, expected_size=None, expected_hash=None):
        block = self.exact(512)
        size_text = block[124:136]
        if not re.fullmatch(rb"[0-7]{11}\x00", size_text):
            refuse("archive_header")
        size = int(size_text[:-1], 8)
        if size > maximum or (expected_size is not None and size != expected_size):
            refuse("archive_budget")
        if block != _header(name, size):
            refuse("archive_header")
        digest = hashlib.sha256()
        raw = bytearray() if expected_hash is None else None
        remaining = size
        while remaining:
            part = self.exact(min(BUFFER, remaining))
            digest.update(part)
            if raw is not None:
                raw.extend(part)
            remaining -= len(part)
        if self.exact((-size) % 512) != bytes((-size) % 512):
            refuse("archive_padding")
        if expected_hash is not None and digest.hexdigest() != expected_hash:
            refuse("content_pin")
        return bytes(raw) if raw is not None else None

    def finish(self, archive_bytes):
        if self.exact(1024) != bytes(1024):
            refuse("archive_terminal")
        padding = (-self.position) % 10240
        if self.position + padding != archive_bytes or self.exact(padding) != bytes(padding):
            refuse("archive_terminal")
        if os.read(self.fd, 1):
            refuse("archive_terminal")
        _check_deadline(self.deadline)
        self.inputs.check()


def _typed_transport(raw, expected, pins):
    if _hash(raw) != expected["transport_manifest_sha256"]:
        refuse("content_pin")
    value = _exact(_json(raw, canonical=True), SCHEMAS["transport"])
    if (value["format"] != "dashboard-ci-runtime-content-archive-v1" or value["policy_sha256"] != POLICY_SHA256
            or value["producer_context"] != expected["producer_context"]
            or value["source_declaration"] != expected["source_declaration"]
            or type(value["authority"]) is not dict or set(value["authority"]) != set(FLAGS)
            or any(value["authority"][key] is not False for key in FLAGS)
            or type(value["images"]) is not list or len(value["images"]) != 3):
        refuse("transport_schema")
    unique = {}
    logical_bytes = 0
    for index, (image, pin) in enumerate(zip(value["images"], pins)):
        _exact(image, SCHEMAS["image"])
        if (tuple(image[key] for key in ("repository", "tag", "platform_manifest_sha256", "config_sha256")) != pin
                or image["platform"] != "linux/amd64"
                or image["manifest_member"] != f"images/{index}/platform-manifest.json"
                or image["config_member"] != f"images/{index}/config.json"
                or type(image["layers"]) is not list or not 1 <= len(image["layers"]) <= 64):
            refuse("transport_schema")
        for layer in image["layers"]:
            _exact(layer, SCHEMAS["layer"])
            diff_id = _digest(layer["diff_id"])
            size = _counter(layer["bytes"], min(LAYER_MAX, int(expected["archive_bytes"])))
            logical_bytes += size
            if logical_bytes > LAYER_MAX or layer["member"] != f"layers/{diff_id[7:]}.tar":
                refuse("archive_budget")
            if diff_id in unique and unique[diff_id] != size:
                refuse("transport_schema")
            unique[diff_id] = size
    return value, unique


def _original(reader, image):
    manifest_raw = reader.member(image["manifest_member"], JSON_MAX)
    if _hash(manifest_raw) != image["platform_manifest_sha256"][7:]:
        refuse("content_pin")
    manifest = _json(manifest_raw)
    if (type(manifest) is not dict or type(manifest.get("schemaVersion")) is not int or manifest["schemaVersion"] != 2
            or manifest.get("mediaType") not in ("application/vnd.docker.distribution.manifest.v2+json", "application/vnd.oci.image.manifest.v1+json")
            or type(manifest.get("config")) is not dict or type(manifest.get("layers")) is not list
            or len(manifest["layers"]) != len(image["layers"])):
        refuse("original_schema")
    config_descriptor = manifest["config"]
    if (config_descriptor.get("digest") != image["config_sha256"]
            or config_descriptor.get("mediaType") not in ("application/vnd.docker.container.image.v1+json", "application/vnd.oci.image.config.v1+json")
            or "urls" in config_descriptor):
        refuse("original_schema")
    config_size = _uint(config_descriptor.get("size"), JSON_MAX)
    for descriptor in manifest["layers"]:
        if (type(descriptor) is not dict or "urls" in descriptor or descriptor.get("mediaType") not in (
                "application/vnd.docker.image.rootfs.diff.tar.gzip", "application/vnd.oci.image.layer.v1.tar",
                "application/vnd.oci.image.layer.v1.tar+gzip")):
            refuse("original_schema")
        _digest(descriptor.get("digest")); _uint(descriptor.get("size"), ARCHIVE_MAX)
    config_raw = reader.member(image["config_member"], JSON_MAX, config_size)
    if _hash(config_raw) != image["config_sha256"][7:]:
        refuse("content_pin")
    config = _json(config_raw)
    if (type(config) is not dict or config.get("os") != "linux" or config.get("architecture") != "amd64"
            or type(config.get("rootfs")) is not dict or config["rootfs"].get("type") != "layers"
            or type(config["rootfs"].get("diff_ids")) is not list
            or config["rootfs"]["diff_ids"] != [layer["diff_id"] for layer in image["layers"]]):
        refuse("original_schema")
    return {"repository": image["repository"], "tag": image["tag"],
            "platform_manifest_sha256": image["platform_manifest_sha256"], "config_sha256": image["config_sha256"],
            "layer_count": str(len(image["layers"])), "layer_bytes": str(sum(int(row["bytes"]) for row in image["layers"])),
            "ordered_diff_ids_sha256": _hash(_canonical(config["rootfs"]["diff_ids"]))}


def verify_capture(source, expected_wire: bytes, parent: Path) -> bytes:
    """Validate independent expectations first; exclusively capture, audit, then clean only own files.

    No public pin/clock override, existing-input-path constructor, network, Docker,
    extraction, load, CLI subprocess or authenticated-runtime capability exists.
    """
    deadline = time.monotonic() + SECONDS
    expected, pins = _expected(expected_wire, deadline)
    inputs = OwnedInputs(parent)
    try:
        inputs.create("expected.json"); inputs.write("expected.json", expected_wire)
        inputs.create("bundle.tar")
        digest = hashlib.sha256()
        captured = 0
        wanted = int(expected["archive_bytes"])
        while True:
            _check_deadline(deadline)
            try:
                part = source.read(min(BUFFER, wanted - captured + 1))
            except Exception:
                refuse("capture")
            _check_deadline(deadline)
            if type(part) is not bytes or len(part) > BUFFER or captured + len(part) > wanted:
                refuse("capture_budget")
            if not part:
                break
            inputs.write("bundle.tar", part)
            digest.update(part); captured += len(part)
        if captured != wanted or digest.hexdigest() != expected["archive_sha256"]:
            refuse("content_pin")
        inputs.check()
        reader = ArchiveReader(inputs, deadline)
        manifest_raw = reader.member("manifest.json", JSON_MAX)
        transport, unique = _typed_transport(manifest_raw, expected, pins)
        images = [_original(reader, image) for image in transport["images"]]
        for diff_id, size in sorted(unique.items()):
            reader.member(f"layers/{diff_id[7:]}.tar", ARCHIVE_MAX, size, diff_id[7:])
        reader.finish(captured)
        report = _canonical({"format": "dashboard-ci-runtime-content-verification-research-v1",
                             "policy_sha256": POLICY_SHA256, "archive_sha256": expected["archive_sha256"],
                             "archive_bytes": str(captured), "transport_manifest_sha256": expected["transport_manifest_sha256"],
                             "artifact_id": expected["artifact_id"], "images": images, "authority": FLAGS})
        if len(report) > 8192:
            refuse("output_budget")
        _check_deadline(deadline)
    except Refusal:
        raise
    except (OSError, ValueError, TypeError, OverflowError):
        refuse("capture")
    finally:
        inputs.close()
    _check_deadline(deadline)
    return report
