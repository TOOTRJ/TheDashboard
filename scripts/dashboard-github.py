#!/usr/bin/env python3
"""Run narrowly scoped Dashboard GitHub operations without shared auth changes.

The fine-grained PAT stays in macOS Keychain and child-process memory. This
helper never logs in to gh, writes Git configuration, or changes commit identity.
Authenticated Git commands disable hooks for that command so hooks cannot
inherit the credential; no persistent Git configuration is changed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


ROOT = Path("/Users/redjester/Projects/Next/TheDashboard")
REPO = "TOOTRJ/TheDashboard"
REPO_ID = 1141090963
ORIGIN = f"https://github.com/{REPO}.git"
LOGIN = "biggrizzly11"
USER_ID = 16749816
KEYCHAIN_SERVICE = "codex-dashboard-github-biggrizzly11"


class DashboardError(Exception):
    """An actionable failure containing no subprocess output or credentials."""


def isolated_environment(source: dict[str, str]) -> dict[str, str]:
    """Drop inherited identity, credential, command, and tracing overrides."""
    excluded = {"EDITOR", "VISUAL", "BROWSER", "PAGER", "LESS",
                "SSH_ASKPASS", "SSH_ASKPASS_REQUIRE"}
    env = {
        key: value for key, value in source.items()
        if not key.startswith(("GH_", "GITHUB_", "GIT_", "GCM_"))
        and key not in excluded
    }
    env.update({"GH_PROMPT_DISABLED": "1", "GIT_TERMINAL_PROMPT": "0",
                "PAGER": "cat", "GIT_PAGER": "cat"})
    return env


def valid_branch(branch: str) -> bool:
    return bool(
        re.fullmatch(r"codex/[A-Za-z0-9_][A-Za-z0-9_./-]*", branch)
        and ".." not in branch and "//" not in branch
        and not branch.endswith(("/", ".", ".lock"))
        and all(not part.startswith(".") and not part.endswith(".lock")
                for part in branch.split("/"))
    )


def validate_api_path(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        raise DashboardError("Invalid Dashboard API path.") from None
    path = parsed.path.removeprefix("/")
    if (parsed.scheme or parsed.netloc or parsed.fragment
            or "%" in parsed.path or "\\" in value
            or any(part in (".", "..", "") for part in path.split("/"))
            or any(ord(char) < 32 for char in value)
            or not (path == "user" or path == f"repos/{REPO}"
                    or path.startswith(f"repos/{REPO}/"))):
        raise DashboardError("API access is limited to the authenticated user and Dashboard repository GET endpoints.")
    return path + (f"?{parsed.query}" if parsed.query else "")


# Keep the command surface explicit: no browser/editor launch, arbitrary auth
# commands, repository overrides, local branch deletion, or admin bypass.
PR_OPTIONS = {
    "create": ({"--base", "--head", "--title", "--body", "--body-file"},
               {"--draft", "--fill", "--fill-first", "--fill-verbose"}),
    "view": ({"--json", "--jq"}, {"--comments"}),
    "list": ({"--state", "--base", "--head", "--limit", "--json", "--jq",
              "--search", "--author", "--label"}, {"--draft"}),
    "checks": ({"--json", "--jq"}, {"--required"}),
    "merge": ({"--match-head-commit", "--subject", "--body", "--body-file"},
              {"--merge", "--squash", "--rebase", "--auto", "--disable-auto"}),
    "edit": ({"--title", "--body", "--body-file", "--base"}, set()),
}


def validate_pr_args(args: list[str]) -> list[str]:
    if not args or args[0] not in PR_OPTIONS:
        raise DashboardError("Supported PR commands: create, view, list, checks, merge, edit.")
    values, switches = PR_OPTIONS[args[0]]
    selectors: list[str] = []
    index = 1
    while index < len(args):
        argument = args[index]
        flag, separator, inline = argument.partition("=")
        if flag in values:
            if separator:
                value = inline
            else:
                index += 1
                if index >= len(args):
                    raise DashboardError("A PR option is missing its value.")
                value = args[index]
            if flag == "--head" and not valid_branch(value):
                raise DashboardError("PR heads must be Dashboard codex/ branches.")
        elif flag in switches and not separator:
            pass
        elif argument.startswith("-"):
            raise DashboardError("Unsupported PR option; repository, auth, editor, and browser overrides are not allowed.")
        else:
            selectors.append(argument)
        index += 1
    if len(selectors) > (0 if args[0] in ("create", "list") else 1):
        raise DashboardError("Unexpected PR selector.")
    for selector in selectors:
        if not (re.fullmatch(r"[1-9][0-9]*", selector) or valid_branch(selector)
                or re.fullmatch(r"https://github\.com/TOOTRJ/TheDashboard/pull/[1-9][0-9]*", selector)):
            raise DashboardError("PR selectors must identify a Dashboard PR or codex/ branch.")
    return ["pr", args[0], "--repo", REPO, *args[1:]]


class DashboardGitHub:
    def __init__(self) -> None:
        self.env = isolated_environment(dict(os.environ))
        self.git = shutil.which("git")
        self.gh = shutil.which("gh")
        if not self.git or not self.gh:
            raise DashboardError("This helper requires the existing Git and GitHub CLI installations.")
        self.git = str(Path(self.git).resolve())
        self.gh = str(Path(self.gh).resolve())

    def run(self, command: list[str], *, env: dict[str, str] | None = None,
            failure: str) -> str:
        try:
            result = subprocess.run(
                command, cwd=ROOT, env=self.env if env is None else env,
                capture_output=True, text=True, timeout=60, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise DashboardError(failure) from None
        if result.returncode:
            raise DashboardError(failure)
        return result.stdout

    def verify_urls(self) -> None:
        for extra in ([], ["--push"]):
            output = self.run(
                [self.git, "remote", "get-url", *extra, "--all", "origin"],
                failure="Cannot resolve Dashboard origin URLs.",
            )
            if output.splitlines() != [ORIGIN]:
                raise DashboardError("Dashboard origin or push URL does not match the approved repository.")

    def keychain_token(self) -> str:
        token = self.run(
            ["/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
             "-a", LOGIN, "-w"], failure="Dashboard Keychain credential is unavailable.",
        ).strip()
        if not token.startswith("github_pat_") or any(char.isspace() for char in token):
            raise DashboardError("Dashboard Keychain does not contain the expected fine-grained credential.")
        return token

    def json_api(self, path: str, env: dict[str, str]) -> dict:
        output = self.run(
            [self.gh, "api", "--hostname", "github.com", "--method", "GET", path],
            env=env, failure="Dashboard GitHub identity verification failed.",
        )
        try:
            data = json.loads(output)
        except (ValueError, TypeError):
            raise DashboardError("Dashboard GitHub returned an invalid verification response.") from None
        if not isinstance(data, dict):
            raise DashboardError("Dashboard GitHub returned an invalid verification response.")
        return data

    def verify_identity(self, env: dict[str, str]) -> dict:
        user = self.json_api("user", env)
        if (not isinstance(user.get("login"), str)
                or user["login"].lower() != LOGIN or user.get("id") != USER_ID):
            raise DashboardError("Dashboard GitHub credential belongs to an unexpected account.")
        repo = self.json_api(f"repos/{REPO}", env)
        if (repo.get("id") != REPO_ID or repo.get("full_name") != REPO
                or not isinstance(repo.get("permissions"), dict)
                or repo["permissions"].get("push") is not True):
            raise DashboardError("Dashboard repository identity or push access could not be verified.")
        return {"login": LOGIN, "user_id": USER_ID, "repository": REPO,
                "repository_id": REPO_ID, "push_access": True}

    def git_network_command(self, args: list[str], *, push: bool = False) -> list[str]:
        # GH_TOKEN is an environment value, never a command-line argument.
        command = [
            self.git, "-c", "credential.helper=", "-c", "credential.useHttpPath=true",
            "-c", f"credential.{ORIGIN}.helper=!{shlex.quote(self.gh)} auth git-credential",
            "-c", "http.extraHeader=", "-c", f"http.{ORIGIN}.extraHeader=",
            "-c", "core.askPass=/usr/bin/false",
            "-c", "core.hooksPath=/dev/null", "-c", "maintenance.auto=false", "-c", "gc.auto=0",
        ]
        if push:
            command += ["-c", "push.followTags=false",
                        "-c", "push.gpgSign=false"]
        return [*command, *args]

    def execute(self, args: list[str]) -> str:
        if not args:
            raise DashboardError("Usage: dashboard-github.py verify | fetch | push | pr <command> ... | api <path>")
        action = args[0]
        command: list[str] | None = None
        if action in ("verify", "fetch", "push") and len(args) == 1:
            pass
        elif action == "pr":
            command = [self.gh, *validate_pr_args(args[1:])]
        elif action == "api" and len(args) == 2:
            command = [self.gh, "api", "--hostname", "github.com", "--method", "GET",
                       validate_api_path(args[1])]
        else:
            raise DashboardError("Unsupported Dashboard GitHub command.")

        self.verify_urls()
        branch = None
        if action == "push":
            branch = self.run([self.git, "symbolic-ref", "--quiet", "--short", "HEAD"],
                              failure="Push requires a checked-out Dashboard codex/ branch.").strip()
            if not valid_branch(branch):
                raise DashboardError("Push requires a checked-out Dashboard codex/ branch.")

        with tempfile.TemporaryDirectory(prefix="dashboard-gh-") as config_dir:
            env = {**self.env, "GH_CONFIG_DIR": config_dir, "GH_TOKEN": self.keychain_token()}
            identity = self.verify_identity(env)
            if action == "verify":
                return json.dumps(identity, indent=2) + "\n"
            if action == "fetch":
                command = self.git_network_command(["fetch", "--recurse-submodules=no", "origin", "main"])
            elif action == "push":
                # Recheck immediately before the consequential operation.
                self.verify_urls()
                command = self.git_network_command(
                    ["push", "--set-upstream", "--recurse-submodules=no", "origin",
                     f"refs/heads/{branch}:refs/heads/{branch}"], push=True,
                )
            assert command is not None
            return self.run(command, env=env, failure="Dashboard GitHub operation failed; no shared credentials were changed.")


def main() -> int:
    try:
        if Path(__file__).resolve().parents[1] != ROOT:
            raise DashboardError("Run this helper from the approved Dashboard checkout.")
        output = DashboardGitHub().execute(sys.argv[1:])
        sys.stdout.write(output)
        return 0
    except DashboardError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
