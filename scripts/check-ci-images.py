#!/usr/bin/env python3
"""Prepare exact fixture images only on a disposable GitHub-hosted CI runner."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import random
import re
import stat
import subprocess
import time
import uuid

PULL_BUDGET_SECONDS = 240
PULL_ATTEMPTS = 5
RETRY_DELAYS_SECONDS = (10, 20, 40, 60)
INITIAL_OFFSETS_SECONDS = (0, 4, 8, 12)
MAX_JITTER_SECONDS = 3
TRANSIENT_ERRORS = {"rate-limited", "registry-unavailable", "network-timeout", "transport-reset"}

PINS = (
    {"tag": "public.ecr.aws/supabase/postgres:17.6.1.095",
     "repository": "public.ecr.aws/supabase/postgres",
     "manifest": "sha256:4c087262afbfbb47da86e2863a52d7e424eb21ab589f732d77eeaab51be8e521",
     "config": "sha256:972aabc75779f6e535f87e1669f36edbab02cdf8bf3f47d13579963c119adefb"},
    {"tag": "public.ecr.aws/supabase/postgrest:v14.5",
     "repository": "public.ecr.aws/supabase/postgrest",
     "manifest": "sha256:bb289d00570b569525e1e22fb77c49cd17c17ca3f41da9ee2b4351a35027551b",
     "config": "sha256:af0a6dad76305650c215449d905a124ae5ad3bcd0f04c01845a0cea17d4e0960"},
    {"tag": "python:3.12.14-slim-bookworm",
     "repository": "docker.io/library/python",
     "digest_repositories": ("docker.io/library/python", "library/python", "python"),
     "manifest": "sha256:1aaa65a85fda306ffb8b910824d4e93bdce61e212c7e87168123ea3073b41a1a",
     "config": "sha256:febd0be41adb897a0ab8f1f1c693d8912669ea60c4940e076e9946b60e210ef0"},
)


def verify_image(metadata: dict, pin: dict) -> None:
    # Docker normalizes Docker Hub's official library names in RepoDigests.
    # These explicit aliases all refer to this same pinned official image.
    expected = {f"{repository}@{pin['manifest']}"
                for repository in pin.get("digest_repositories", (pin["repository"],))}
    if (metadata.get("Architecture") != "amd64" or metadata.get("Os") != "linux"
            or not expected.intersection(metadata.get("RepoDigests", []))
            or metadata.get("Id") not in {pin["manifest"], pin["config"]}):
        raise ValueError("Fixture image platform, digest or immutable identity does not match")


def error_class(stderr: str) -> str:
    """Return only a fixed class; never publish Docker output or credentials."""
    text = stderr[:16384].lower() if isinstance(stderr, str) else ""
    patterns = (
        ("rate-limited", ("toomanyrequests", "too many requests", "rate limit", r"\b429\b")),
        ("registry-unavailable", (r"\b50[0234]\b", "service unavailable", "bad gateway")),
        ("network-timeout", ("tls handshake timeout", "i/o timeout", "context deadline exceeded", "connection timed out")),
        ("transport-reset", ("connection reset", "unexpected eof", "temporary failure in name resolution")),
        ("manifest-unavailable", ("manifest unknown", "manifest not found", "no matching manifest")),
        ("authorization-denied", ("unauthorized", "authentication required", "pull access denied", "access denied", r"\b40[13]\b")),
        ("daemon-unavailable", ("cannot connect to the docker daemon", "is the docker daemon running", "connection refused", "no such file or directory")),
    )
    for category, candidates in patterns:
        if any(re.search(pattern, text) for pattern in candidates):
            return category
    return "unclassified"


def diagnostic(pin: dict, operation: str, state: str, **details) -> None:
    print(json.dumps({"scope": "github-hosted-image-preparation", "image": pin["repository"],
                      "manifest": pin["manifest"], "operation": operation, "state": state,
                      **details}, sort_keys=True), flush=True)


def jitter_seconds() -> float:
    return random.SystemRandom().uniform(0, MAX_JITTER_SECONDS)


def runner_directory(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise RuntimeError("A real owned runner temporary directory is required")
    path = Path(value)
    if not path.is_absolute() or str(path) != value:
        raise RuntimeError("A real owned runner temporary directory is required")
    try:
        metadata = path.lstat()
        if (path.resolve(strict=True) != path
                or not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid()
                or metadata.st_mode & 0o022):
            raise RuntimeError("A real owned runner temporary directory is required")
    except (OSError, ValueError):
        raise RuntimeError("A real owned runner temporary directory is required") from None
    return path


class OwnedDockerConfig:
    """One empty, private directory; descriptor-bound cleanup removes only it."""
    def __init__(self, parent: Path):
        self.parent = parent
        self.parent_fd = None
        self.name = None
        self.identity = None

    def __enter__(self):
        try:
            before = self.parent.lstat()
            self.parent_fd = os.open(self.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.parent_identity = os.fstat(self.parent_fd)
            if ((before.st_dev, before.st_ino) != (self.parent_identity.st_dev, self.parent_identity.st_ino)
                    or self.parent_identity.st_uid != os.geteuid()):
                raise RuntimeError("Runner temporary directory changed")
            name = "dashboard-ci-docker-" + uuid.uuid4().hex
            os.mkdir(name, mode=0o700, dir_fd=self.parent_fd)
            self.name = name
            self.path = self.parent / name
            self.identity = os.stat(name, dir_fd=self.parent_fd, follow_symlinks=False)
            self.check()
            return self
        except (OSError, RuntimeError):
            self.close()
            raise RuntimeError("Owned Docker configuration is unavailable") from None

    def check(self):
        directory_fd = None
        try:
            parent = self.parent.lstat()
            item = os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)
            path = self.path.lstat()
            if ((parent.st_dev, parent.st_ino) != (self.parent_identity.st_dev, self.parent_identity.st_ino)
                    or not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid()
                    or parent.st_mode & 0o022
                    or (item.st_dev, item.st_ino) != (self.identity.st_dev, self.identity.st_ino)
                    or (path.st_dev, path.st_ino) != (item.st_dev, item.st_ino)
                    or not stat.S_ISDIR(item.st_mode) or item.st_uid != os.geteuid()
                    or stat.S_IMODE(item.st_mode) != 0o700):
                raise RuntimeError("Owned Docker configuration binding changed")
            directory_fd = os.open(self.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.parent_fd)
            opened = os.fstat(directory_fd)
            if ((opened.st_dev, opened.st_ino) != (self.identity.st_dev, self.identity.st_ino)
                    or os.listdir(directory_fd)):
                raise RuntimeError("Owned Docker configuration must remain empty")
        except OSError:
            raise RuntimeError("Owned Docker configuration binding changed") from None
        finally:
            if directory_fd is not None:
                os.close(directory_fd)

    def close(self):
        try:
            if self.name is not None and self.identity is not None:
                item = os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)
                if (not stat.S_ISDIR(item.st_mode) or item.st_uid != os.geteuid()
                        or (item.st_dev, item.st_ino) != (self.identity.st_dev, self.identity.st_ino)):
                    raise RuntimeError("Owned Docker configuration cleanup refused")
                # No recursive cleanup, replacement removal or shared configuration changes.
                os.rmdir(self.name, dir_fd=self.parent_fd)
        except OSError:
            raise RuntimeError("Owned Docker configuration cleanup refused") from None
        finally:
            if self.parent_fd is not None:
                os.close(self.parent_fd)
                self.parent_fd = None

    def __exit__(self, *_):
        try:
            self.check()
        finally:
            self.close()


def prepare(inherited: dict[str, str]) -> None:
    if (inherited.get("GITHUB_ACTIONS") != "true"
            or inherited.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or inherited.get("GITHUB_REPOSITORY_ID") != "1141090963"):
        raise RuntimeError("Image preparation is restricted to the Dashboard GitHub-hosted CI job")
    host = inherited.get("DOCKER_HOST", "unix:///var/run/docker.sock")
    if not isinstance(host, str) or not host.startswith("unix:///"):
        raise RuntimeError("Refusing a nonlocal CI Docker daemon")
    shard = inherited.get("DASHBOARD_TEST_SHARD")
    if not isinstance(shard, str) or not re.fullmatch(r"[1-4]", shard):
        raise RuntimeError("Image preparation requires a canonical SQL shard from 1 through 4")
    parent = runner_directory(inherited.get("RUNNER_TEMP"))
    with OwnedDockerConfig(parent) as config:
        _prepare(inherited, host, int(shard), config)
    print(json.dumps({"scope": "github-hosted-owned-fixtures", "architecture": "amd64",
                      "verified_manifests": [pin["manifest"] for pin in PINS]}, sort_keys=True))


def _prepare(inherited: dict[str, str], host: str, shard: int, config: OwnedDockerConfig) -> None:
    env = {key: inherited[key] for key in ("PATH", "LANG", "LC_ALL") if key in inherited}
    env.update({"DOCKER_HOST": host, "DOCKER_CONFIG": str(config.path), "TMPDIR": str(config.parent)})
    pin_started = 0.0

    def elapsed() -> float:
        return round(max(0.0, time.monotonic() - pin_started), 3)

    def command(pin: dict, operation: str, args: list[str], timeout: float = 30, attempt: int = 1) -> tuple[str, str | None]:
        config.check()
        diagnostic(pin, operation, "starting", attempt=attempt, pin_elapsed_seconds=elapsed())
        started = time.monotonic()
        try:
            result = subprocess.run(["docker", "--config", str(config.path), "--host", host, *args], env=env, text=True,
                                    capture_output=True, check=False, timeout=timeout)
        except subprocess.TimeoutExpired:
            category = "network-timeout" if operation == "pull" else "operation-timeout"
        except OSError:
            category = "cli-unavailable"
        except KeyboardInterrupt:
            diagnostic(pin, operation, "cancelled", attempt=attempt, error_class="cancelled",
                       elapsed_seconds=round(max(0.0, time.monotonic() - started), 3), pin_elapsed_seconds=elapsed())
            raise
        else:
            if not result.returncode:
                diagnostic(pin, operation, "completed", attempt=attempt,
                           elapsed_seconds=round(max(0.0, time.monotonic() - started), 3), pin_elapsed_seconds=elapsed())
                return result.stdout, None
            category = error_class(result.stderr)
        diagnostic(pin, operation, "failed", attempt=attempt, error_class=category,
                   elapsed_seconds=round(max(0.0, time.monotonic() - started), 3), pin_elapsed_seconds=elapsed())
        return "", category

    def required(pin: dict, operation: str, args: list[str]) -> str:
        output, category = command(pin, operation, args)
        if category:
            raise RuntimeError(f"Required fixture {operation} failed: {pin['repository']}@{pin['manifest']} ({category})") from None
        return output

    def pull(pin: dict, reference: str) -> None:
        deadline = pin_started + PULL_BUDGET_SECONDS
        initial = INITIAL_OFFSETS_SECONDS[shard - 1] + jitter_seconds()
        diagnostic(pin, "pull", "staggering", shard=shard, delay_seconds=initial, pin_elapsed_seconds=elapsed())
        time.sleep(initial)
        category = "network-timeout"
        for attempt in range(1, PULL_ATTEMPTS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            _, category = command(pin, "pull", ["pull", "--platform", "linux/amd64", reference], remaining, attempt)
            if category is None:
                if time.monotonic() <= deadline:
                    return
                category = "network-timeout"
                diagnostic(pin, "pull", "deadline-exhausted", attempt=attempt,
                           error_class=category, pin_elapsed_seconds=elapsed())
                break
            if category not in TRANSIENT_ERRORS or attempt == PULL_ATTEMPTS:
                break
            delay = RETRY_DELAYS_SECONDS[attempt - 1] + jitter_seconds()
            if deadline - time.monotonic() <= delay:
                break
            diagnostic(pin, "pull", "retrying", attempt=attempt, error_class=category,
                       delay_seconds=delay, pin_elapsed_seconds=elapsed())
            time.sleep(delay)
        raise RuntimeError(f"Required fixture pull failed: {reference} ({category})") from None

    for pin in PINS:
        pin_started = time.monotonic()
        reference = f"{pin['repository']}@{pin['manifest']}"
        pull(pin, reference)
        verify_image(json.loads(required(pin, "inspect-pulled", ["image", "inspect", reference]))[0], pin)
        # The existing harness resolves these exact tags then runs the immutable ID.
        # Only this new disposable runner daemon is retagged, never a local daemon.
        required(pin, "tag-fixture", ["image", "tag", reference, pin["tag"]])
        verify_image(json.loads(required(pin, "inspect-fixture", ["image", "inspect", pin["tag"]]))[0], pin)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-images", action="store_true", required=True)
    parser.parse_args()
    for pin in PINS:
        if any(not re.fullmatch(r"sha256:[a-f0-9]{64}", pin[key]) for key in ("manifest", "config")):
            raise RuntimeError("Malformed reviewed fixture digest")
    prepare(dict(os.environ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
