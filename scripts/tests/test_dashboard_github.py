"""Offline checks for the dedicated Dashboard authentication boundary."""

import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "dashboard_github", Path(__file__).resolve().parents[1] / "dashboard-github.py",
)
dashboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard)
TOKEN = "github_pat_OFFLINE_SENTINEL_DO_NOT_PRINT"


class DashboardGitHubTests(unittest.TestCase):
    def setUp(self):
        # Any accidentally unmocked process, including network access, fails.
        self.process_guard = patch.object(
            dashboard.subprocess, "run", side_effect=AssertionError("Unexpected real subprocess"),
        )
        self.process_guard.start()
        self.addCleanup(self.process_guard.stop)
        self.client = dashboard.DashboardGitHub.__new__(dashboard.DashboardGitHub)
        self.client.git = "/usr/bin/git"
        self.client.gh = "/opt/homebrew/bin/gh"
        self.client.env = dashboard.isolated_environment({"HOME": "/unchanged/home"})
        self.calls = []
        self.branch = "codex/identity-isolation"
        self.urls = [dashboard.ORIGIN]
        self.push_urls = [dashboard.ORIGIN]
        self.user = {"login": dashboard.LOGIN, "id": dashboard.USER_ID}
        self.repo = {"full_name": dashboard.REPO, "id": dashboard.REPO_ID,
                     "permissions": {"push": True}}
        self.client.run = self.fake_run

    def fake_run(self, command, *, env=None, failure):
        self.calls.append((command, env))
        if command[1:3] == ["remote", "get-url"]:
            urls = self.push_urls if "--push" in command else self.urls
            return "\n".join(urls) + "\n"
        if command[1] == "symbolic-ref":
            return self.branch + "\n"
        if command[0] == "/usr/bin/security":
            return TOKEN + "\n"
        if command[0] == self.client.gh and command[1] == "api":
            return json.dumps(self.user if command[-1] == "user" else self.repo)
        return "completed\n"

    def test_environment_removes_shared_auth_identity_and_trace_overrides(self):
        original = {
            "HOME": "/unchanged/home", "PATH": "/unchanged/path",
            "GH_TOKEN": TOKEN, "GITHUB_TOKEN": TOKEN,
            "GH_CONFIG_DIR": "/shared", "GH_REPO": "other/repository",
            "GH_DEBUG": "api", "GIT_TRACE_CURL": "1", "GIT_CONFIG_PARAMETERS": "bad",
            "GIT_AUTHOR_EMAIL": "other@example.invalid", "GIT_COMMITTER_NAME": "Other",
            "GIT_ASKPASS": "/other/helper", "GCM_CREDENTIAL_STORE": "keychain",
            "EDITOR": "/other/editor", "SSH_ASKPASS": "/other/helper",
        }
        result = dashboard.isolated_environment(original)
        self.assertEqual(result["HOME"], original["HOME"])
        self.assertEqual(result["PATH"], original["PATH"])
        self.assertEqual(result["GIT_TERMINAL_PROMPT"], "0")
        self.assertNotIn(TOKEN, result.values())
        self.assertNotIn("GIT_AUTHOR_EMAIL", result)
        self.assertNotIn("GIT_CONFIG_PARAMETERS", result)
        self.assertNotIn("GH_CONFIG_DIR", result)
        self.assertNotIn("EDITOR", result)
        self.assertEqual(original["GH_TOKEN"], TOKEN)

    def test_verify_outputs_only_identity_metadata(self):
        result = self.client.execute(["verify"])
        self.assertNotIn(TOKEN, result)
        self.assertEqual(json.loads(result)["repository_id"], dashboard.REPO_ID)
        api_calls = [(command, env) for command, env in self.calls if command[1] == "api"]
        self.assertEqual(len(api_calls), 2)
        for command, env in api_calls:
            self.assertEqual(env["GH_TOKEN"], TOKEN)
            self.assertTrue(Path(env["GH_CONFIG_DIR"]).name.startswith("dashboard-gh-"))
            self.assertFalse(Path(env["GH_CONFIG_DIR"]).exists())  # cleaned up
            self.assertNotIn(TOKEN, " ".join(command))
        self.assertNotIn("GH_TOKEN", self.client.env)

    def test_wrong_or_multiple_origins_fail_before_keychain_read(self):
        for urls in (["https://github.com/other/repo.git"],
                     [dashboard.ORIGIN, dashboard.ORIGIN], []):
            with self.subTest(urls=urls):
                self.calls.clear()
                self.urls = urls
                with self.assertRaises(dashboard.DashboardError):
                    self.client.execute(["verify"])
                self.assertFalse(any(command[0] == "/usr/bin/security" for command, _ in self.calls))

    def test_separate_push_url_cannot_redirect_write(self):
        self.push_urls = ["https://github.com/other/repo.git"]
        with self.assertRaises(dashboard.DashboardError):
            self.client.execute(["push"])
        self.assertFalse(any(command[0] == "/usr/bin/security" for command, _ in self.calls))

    def test_wrong_account_fails_before_requested_operation(self):
        for user in ({"login": "RedJester14", "id": dashboard.USER_ID},
                     {"login": dashboard.LOGIN, "id": 1}, {"login": None}):
            with self.subTest(user=user):
                self.calls.clear()
                self.user = user
                with self.assertRaises(dashboard.DashboardError):
                    self.client.execute(["pr", "create", "--title", "Example"])
                self.assertFalse(any(command[1] == "pr" for command, _ in self.calls))

    def test_wrong_repository_or_missing_write_access_fails_closed(self):
        for changes in ({"id": 1}, {"full_name": "other/repo"},
                        {"permissions": {"push": False}}, {"permissions": None}):
            with self.subTest(changes=changes):
                self.repo = {"full_name": dashboard.REPO, "id": dashboard.REPO_ID,
                             "permissions": {"push": True}, **changes}
                with self.assertRaises(dashboard.DashboardError):
                    self.client.execute(["fetch"])

    def test_invalid_branch_fails_before_token_is_read(self):
        for branch in ("main", "feature/other", "codex/../../main", "codex/a.lock/b",
                       "codex/a//b", "codex/.hidden", "", "HEAD"):
            with self.subTest(branch=branch):
                self.calls.clear()
                self.branch = branch
                with self.assertRaises(dashboard.DashboardError):
                    self.client.execute(["push"])
                self.assertFalse(any(command[0] == "/usr/bin/security" for command, _ in self.calls))

    def test_push_uses_exact_ref_and_isolated_helper_without_hooks(self):
        self.client.execute(["push"])
        command, env = self.calls[-1]
        self.assertEqual(command[-1], "refs/heads/codex/identity-isolation:refs/heads/codex/identity-isolation")
        self.assertIn("credential.helper=", command)
        self.assertIn(f"credential.{dashboard.ORIGIN}.helper=!{self.client.gh} auth git-credential", command)
        self.assertIn("credential.useHttpPath=true", command)
        self.assertIn("core.hooksPath=/dev/null", command)
        self.assertIn("--recurse-submodules=no", command)
        self.assertNotIn("--force", command)
        self.assertNotIn(TOKEN, " ".join(command))
        self.assertEqual(env["GH_TOKEN"], TOKEN)

    def test_fetch_is_fixed_to_origin_main_and_disables_ref_hooks(self):
        self.client.execute(["fetch"])
        command, _ = self.calls[-1]
        self.assertEqual(command[-4:], ["fetch", "--recurse-submodules=no", "origin", "main"])
        self.assertIn("core.hooksPath=/dev/null", command)

    def test_missing_credential_never_falls_back_to_shared_gh(self):
        with patch.object(self.client, "keychain_token", side_effect=dashboard.DashboardError("Credential unavailable")):
            with self.assertRaisesRegex(dashboard.DashboardError, "Credential unavailable"):
                self.client.execute(["verify"])
        self.assertFalse(any(command[0] == self.client.gh for command, _ in self.calls))

    def test_invalid_or_classic_keychain_value_is_rejected(self):
        for token in ("", "ghp_CLASSIC_SENTINEL", TOKEN + "\nsecond-line"):
            with patch.object(self.client, "run", return_value=token):
                with self.assertRaises(dashboard.DashboardError) as error:
                    self.client.keychain_token()
                self.assertNotIn("SENTINEL", str(error.exception))

    def test_pr_repository_is_pinned_and_output_is_preserved(self):
        result = self.client.execute(["pr", "view", "12", "--json", "url,headRefOid"])
        self.assertEqual(result, "completed\n")
        self.assertEqual(self.calls[-1][0], [self.client.gh, "pr", "view", "--repo", dashboard.REPO,
                                           "12", "--json", "url,headRefOid"])

    def test_pr_overrides_and_foreign_selectors_are_rejected(self):
        cases = (["view", "--repo", "other/repo"], ["view", "-Rother/repo"],
                 ["view", "--hostname=evil.invalid"],
                 ["view", "https://github.com/other/repo/pull/1"],
                 ["create", "--head", "other:codex/test"], ["create", "--editor"],
                 ["merge", "1", "--delete-branch"], ["merge", "1", "--admin"],
                 ["checkout", "1"], ["view", "--web"])
        for args in cases:
            with self.subTest(args=args), self.assertRaises(dashboard.DashboardError):
                dashboard.validate_pr_args(args)

    def test_api_rejects_foreign_encoded_traversal_and_token_endpoints(self):
        for path in ("/user/emails", "https://evil.invalid/user", "//evil.invalid/user",
                     "repos/TOOTRJ/Other", "repos/TOOTRJ/TheDashboard/../Other",
                     "repos/TOOTRJ/TheDashboard/%2e%2e/Other", "repos/TOOTRJ/TheDashboard//commits",
                     "repos/TOOTRJ/TheDashboard\\Other", "user#fragment", "user\n"):
            with self.subTest(path=path), self.assertRaises(dashboard.DashboardError):
                dashboard.validate_api_path(path)
        self.assertEqual(dashboard.validate_api_path("/repos/TOOTRJ/TheDashboard/commits?per_page=5"),
                         "repos/TOOTRJ/TheDashboard/commits?per_page=5")

    def test_api_is_always_get_and_rejects_extra_method_arguments(self):
        self.client.execute(["api", "/repos/TOOTRJ/TheDashboard/commits"])
        command, _ = self.calls[-1]
        self.assertEqual(command[command.index("--method") + 1], "GET")
        with self.assertRaises(dashboard.DashboardError):
            self.client.execute(["api", "/user", "--method", "POST"])

    def test_subprocess_errors_do_not_expose_output_or_tokens(self):
        for response in (
            subprocess.CompletedProcess([], 1, stdout=TOKEN, stderr=TOKEN),
            subprocess.TimeoutExpired([TOKEN], 60, output=TOKEN, stderr=TOKEN),
        ):
            kwargs = {"side_effect": response} if isinstance(response, Exception) else {"return_value": response}
            with patch.object(dashboard.subprocess, "run", **kwargs):
                with self.assertRaises(dashboard.DashboardError) as error:
                    dashboard.DashboardGitHub.run(self.client, ["fake"], failure="Safe failure.")
                self.assertEqual(str(error.exception), "Safe failure.")


if __name__ == "__main__":
    unittest.main()
