#!/usr/bin/env python3
"""Prepare exact fixture images only on a disposable GitHub-hosted CI runner."""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess

PINS = (
    {"tag": "public.ecr.aws/supabase/postgres:17.6.1.095",
     "repository": "public.ecr.aws/supabase/postgres",
     "manifest": "sha256:4c087262afbfbb47da86e2863a52d7e424eb21ab589f732d77eeaab51be8e521",
     "config": "sha256:972aabc75779f6e535f87e1669f36edbab02cdf8bf3f47d13579963c119adefb"},
    {"tag": "public.ecr.aws/supabase/postgrest:v14.5",
     "repository": "public.ecr.aws/supabase/postgrest",
     "manifest": "sha256:bb289d00570b569525e1e22fb77c49cd17c17ca3f41da9ee2b4351a35027551b",
     "config": "sha256:af0a6dad76305650c215449d905a124ae5ad3bcd0f04c01845a0cea17d4e0960"},
)


def verify_image(metadata: dict, pin: dict) -> None:
    expected = f"{pin['repository']}@{pin['manifest']}"
    if (metadata.get("Architecture") != "amd64" or metadata.get("Os") != "linux"
            or expected not in metadata.get("RepoDigests", [])
            or metadata.get("Id") not in {pin["manifest"], pin["config"]}):
        raise ValueError("Fixture image platform, digest or immutable identity does not match")


def prepare(inherited: dict[str, str]) -> None:
    if (inherited.get("GITHUB_ACTIONS") != "true"
            or inherited.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or inherited.get("GITHUB_REPOSITORY_ID") != "1141090963"):
        raise RuntimeError("Image preparation is restricted to the Dashboard GitHub-hosted CI job")
    host = inherited.get("DOCKER_HOST", "unix:///var/run/docker.sock")
    if not host.startswith("unix:///"):
        raise RuntimeError("Refusing a nonlocal CI Docker daemon")
    env = {key: inherited[key] for key in ("PATH", "TMPDIR", "LANG", "LC_ALL") if key in inherited}
    env["DOCKER_HOST"] = host

    def command(args: list[str], timeout: int = 30) -> str:
        result = subprocess.run(["docker", "--host", host, *args], env=env, text=True,
                                capture_output=True, check=False, timeout=timeout)
        if result.returncode:
            raise RuntimeError("Required fixture image preparation failed")
        return result.stdout

    for pin in PINS:
        reference = f"{pin['repository']}@{pin['manifest']}"
        command(["pull", "--platform", "linux/amd64", reference], timeout=240)
        verify_image(json.loads(command(["image", "inspect", reference]))[0], pin)
        # The existing harness resolves these exact tags then runs the immutable ID.
        # Only this new disposable runner daemon is retagged, never a local daemon.
        command(["image", "tag", reference, pin["tag"]])
        verify_image(json.loads(command(["image", "inspect", pin["tag"]]))[0], pin)
    print(json.dumps({"scope": "github-hosted-owned-fixtures", "architecture": "amd64",
                      "verified_manifests": [pin["manifest"] for pin in PINS]}, sort_keys=True))


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
