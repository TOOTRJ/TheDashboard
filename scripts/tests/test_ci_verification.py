from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import os
import subprocess
import sys
import unittest
from unittest.mock import patch
import yaml

SCRIPTS = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


worker = load("dashboard_check_worker", "check-worker.py")
images = load("dashboard_check_images", "check-ci-images.py")
policy = load("dashboard_check_ci", "check-ci.py")


class NamedTest:
    def __init__(self, identity): self.identity = identity
    def id(self): return self.identity


class CiVerificationTests(unittest.TestCase):
    def test_real_child_import_retains_exact_fixed_locale_without_secret_keys(self):
        code = '''import importlib.util,os,sys
spec=importlib.util.spec_from_file_location("dashboard_child_locale",sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.validate_child_environment("offline",dict(os.environ))
print("fixed child environment passed")'''
        env = worker.worker_environment("offline", {"PATH": os.environ.get("PATH", ""),
                                                   "LANG": "untrusted-locale", "PYTHONUTF8": "0"})
        self.assertEqual(env["LANG"], "C")
        self.assertEqual(env["LC_ALL"], "C")
        self.assertEqual(env["LC_CTYPE"], "C")
        self.assertEqual(env["PYTHONUTF8"], "1")
        self.assertEqual(env["PYTHONCOERCECLOCALE"], "0")
        result = subprocess.run([sys.executable, "-c", code, str(SCRIPTS / "check-worker.py")],
                                env=env, text=True, capture_output=True, timeout=10, check=True)
        self.assertEqual(result.stdout.strip(), "fixed child environment passed")

    def test_fixed_runtime_requirement_gives_a_clear_setup_failure(self):
        worker.require_supported_python((3, 12, 14), "cpython")
        for version, implementation in (((3, 11, 9), "cpython"), ((3, 12, 15), "cpython"), ((3, 12, 14), "pypy")):
            with self.subTest(version=version, implementation=implementation), self.assertRaisesRegex(RuntimeError, "hash-locked worker virtual environment"):
                worker.require_supported_python(version, implementation)

    def test_owned_child_deadlines_leave_job_setup_and_cleanup_margins(self):
        workflow = yaml.safe_load(policy.WORKFLOW.read_text())
        for mode, job, margin in (("offline", "worker", 300), ("postgres", "postgres", 600)):
            args = ["check-worker.py", mode]
            if mode == "postgres": args.append("--allow-isolated-postgres")
            with patch.object(worker.sys, "argv", args), patch.dict(os.environ, {"PATH": "/test/bin"}, clear=True), patch.object(worker, "native_wheels_directory", return_value=Path('/test/native-wheels')), patch.object(worker.subprocess, "run") as execute:
                execute.return_value.returncode = 0
                self.assertEqual(worker.main(), 0)
                self.assertEqual(execute.call_args.kwargs["timeout"], worker.CHILD_DEADLINES[mode])
                self.assertLessEqual(execute.call_args.kwargs["timeout"], workflow["jobs"][job]["timeout-minutes"] * 60 - margin)

    def test_internal_child_flag_cannot_bypass_secret_isolation(self):
        env = worker.worker_environment("offline", {"PATH": "/test/bin"})
        env["VERCEL_TOKEN"] = "never-copy"
        with patch.dict(os.environ, env, clear=True), patch.object(worker.unittest, "TestLoader") as loader:
            with self.assertRaises(RuntimeError): worker.run_suites("offline")
            loader.assert_not_called()

    def test_owned_worker_child_drops_credentials_and_inherited_opt_in(self):
        inherited = {"PATH": "/test/bin", "LANG": "C", "HOME": "/shared/home",
                     "SUPABASE_SERVICE_ROLE_KEY": "never-copy", "RAILWAY_TOKEN": "never-copy",
                     "VERCEL_TOKEN": "never-copy", "PYTHONPATH": "/foreign/project",
                     worker.OPT_IN: "1", worker.NATIVE_WHEELS_ENV: "/never-copy/wheels", "DASHBOARD_OPTIMIZER_MEASURE": "1"}
        env = worker.worker_environment("offline", inherited)
        self.assertEqual(env["PATH"], "/test/bin")
        self.assertEqual(env["PYTHON_DOTENV_DISABLED"], "1")
        self.assertEqual(env["PYTHONPATH"], str(worker.WORKER))
        for key in ("HOME", "SUPABASE_SERVICE_ROLE_KEY", "RAILWAY_TOKEN", "VERCEL_TOKEN",
                    worker.OPT_IN, worker.NATIVE_WHEELS_ENV, "DASHBOARD_OPTIMIZER_MEASURE"):
            self.assertNotIn(key, env)
        self.assertNotIn("never-copy", env.values())

    def test_required_sql_child_has_explicit_local_socket_and_opt_in(self):
        with self.assertRaisesRegex(RuntimeError, "explicit prepared native SQL wheel bundle"):
            worker.worker_environment("postgres", {"PATH": "/test/bin"})
        with patch.object(worker, "native_wheels_directory", return_value=Path('/test/native-wheels')):
            env = worker.worker_environment("postgres", {"PATH": "/test/bin"})
        self.assertEqual(env[worker.OPT_IN], "1")
        self.assertEqual(env["DOCKER_HOST"], "unix:///var/run/docker.sock")
        self.assertEqual(env[worker.NATIVE_WHEELS_ENV], "/test/native-wheels")
        with self.assertRaises(ValueError):
            worker.worker_environment("postgres", {"DOCKER_HOST": "tcp://foreign.example:2375"})

    def test_opt_in_skip_is_reported_offline_and_fails_required_integration(self):
        result = unittest.TestResult()
        result.testsRun = 2
        result.addSkip(NamedTest("tests.postgres.test_harness.HarnessTests.test_owned_database"),
                       "Explicit isolated PostgreSQL opt-in required")
        report, accepted = worker.audit_result(result, "offline")
        self.assertTrue(accepted)
        self.assertEqual(report["tests_executed"], 1)
        self.assertEqual(report["skips"][0]["category"], "postgres-opt-in-not-executed")
        report, accepted = worker.audit_result(result, "postgres")
        self.assertFalse(accepted)
        self.assertEqual(report["unexpected_skips"], 1)

    def test_empty_all_skipped_or_unexpected_skip_cannot_pass(self):
        self.assertFalse(worker.audit_result(unittest.TestResult(), "postgres")[1])
        result = unittest.TestResult()
        result.testsRun = 1
        identity, reason = next(iter(worker.OPTIONAL_MEASUREMENTS.items()))
        result.addSkip(NamedTest(identity), reason)
        self.assertFalse(worker.audit_result(result, "postgres")[1])
        result.testsRun = 2
        self.assertTrue(worker.audit_result(result, "postgres")[1])
        result.addSkip(NamedTest("tests.postgres.future.RequiredProof.test_validity"), "Optional validity timing")
        self.assertFalse(worker.audit_result(result, "postgres")[1])
        stopped = unittest.TestResult(); stopped.testsRun = 1; stopped.stop()
        self.assertFalse(worker.audit_result(stopped, "offline")[1])

    def test_class_setup_skips_are_not_counted_as_executed_methods(self):
        result = unittest.TestResult()
        result.testsRun = 1
        result.addSkip(NamedTest("setUpClass (tests.postgres.test_native_sql.NativeSqlTests)"),
                       "Explicit isolated PostgreSQL opt-in required")
        self.assertEqual(worker.audit_result(result, "offline")[0]["tests_executed"], 1)
        self.assertFalse(worker.audit_result(result, "postgres")[1])

    def test_fixture_identity_requires_repository_digest_platform_and_known_id(self):
        pin = images.PINS[0]
        metadata = {"Id": pin["config"], "Architecture": "amd64", "Os": "linux",
                    "RepoDigests": [f"{pin['repository']}@{pin['manifest']}"]}
        images.verify_image(metadata, pin)
        images.verify_image({**metadata, "Id": pin["manifest"]}, pin)
        for change in ({"Architecture": "arm64"}, {"Os": "windows"}, {"RepoDigests": []},
                       {"Id": "sha256:" + "0" * 64},
                       {"RepoDigests": [f"foreign.example/postgres@{pin['manifest']}"]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                images.verify_image({**metadata, **change}, pin)

    def test_exact_mirror_identity_requires_the_selected_verified_repository(self):
        self.assertEqual(images.MIRRORS, {
            "public.ecr.aws/supabase/postgres": {
                "repository": "docker.io/supabase/postgres",
                "digest_repositories": ("docker.io/supabase/postgres", "supabase/postgres"),
            },
            "public.ecr.aws/supabase/postgrest": {
                "repository": "docker.io/postgrest/postgrest",
                "digest_repositories": ("docker.io/postgrest/postgrest", "postgrest/postgrest"),
            },
        })
        for pin in images.PINS[:2]:
            mirror = images.MIRRORS[pin["repository"]]
            for alias in mirror["digest_repositories"]:
                metadata = {"Id": pin["config"], "Architecture": "amd64", "Os": "linux",
                            "RepoDigests": [alias + "@" + pin["manifest"]]}
                images.verify_image(metadata, pin, mirror["repository"])
                images.verify_image({**metadata, "Id": pin["manifest"]}, pin, mirror["repository"])
                with self.assertRaises(ValueError):
                    images.verify_image(metadata, pin)
                for change in ({"Architecture": "arm64"}, {"Os": "windows"}, {"RepoDigests": []},
                               {"Id": "sha256:" + "0" * 64},
                               {"RepoDigests": [alias + "@sha256:" + "0" * 64]},
                               {"RepoDigests": [pin["repository"] + "@" + pin["manifest"]]},
                               {"RepoDigests": ["docker.io/supabase/postgrest@" + pin["manifest"]]},
                               {"RepoDigests": ["foreign.invalid/postgres@" + pin["manifest"]]}):
                    with self.subTest(pin=pin["repository"], alias=alias, change=change), self.assertRaises(ValueError):
                        images.verify_image({**metadata, **change}, pin, mirror["repository"])
                for unreviewed in ("docker.io/supabase/postgrest", "docker.io/attacker/postgres", alias.removeprefix("docker.io/")):
                    with self.subTest(source=unreviewed), self.assertRaises(ValueError):
                        images.verify_image(metadata, pin, unreviewed)

    def test_fixture_pins_match_the_reviewed_platform_registry_evidence(self):
        evidence = json.loads((SCRIPTS / "check-ci-images-evidence.json").read_text())
        self.assertEqual(evidence["checked"], "2026-10-12")
        for pin in images.PINS:
            item = next(item for item in evidence["images"]
                        if item.get("registry", "public.ecr.aws") + "/" + item["repository"] == pin["repository"])
            platform = next(value for value in item["platforms"] if value["platform"] == {"architecture": "amd64", "os": "linux"})
            self.assertEqual(platform["manifest_digest"], pin["manifest"])
            self.assertEqual(platform["config_digest"], pin["config"])

    def test_image_preparation_refuses_local_or_other_repository_before_docker(self):
        with patch.object(images.subprocess, "run") as execute:
            for env in ({}, {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "self-hosted",
                            "GITHUB_REPOSITORY_ID": "1141090963"},
                        {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
                         "GITHUB_REPOSITORY_ID": "different-repository"}):
                with self.assertRaises(RuntimeError): images.prepare(env)
            execute.assert_not_called()

    def test_real_workflow_policy_and_privilege_bypass_mutations(self):
        source = policy.WORKFLOW.read_text()
        policy.validate_workflow(source)
        original = yaml.safe_load(source)
        mutations = []
        value = copy.deepcopy(original); value["permissions"]["contents"] = "write"; mutations.append(value)
        value = copy.deepcopy(original); value["on"]["pull_request_target"] = {}; mutations.append(value)
        value = copy.deepcopy(original); del value["jobs"]["postgres"]; mutations.append(value)
        value = copy.deepcopy(original); value["jobs"]["postgres"]["if"] = "false"; mutations.append(value)
        value = copy.deepcopy(original); value["jobs"]["worker"]["steps"][-1]["continue-on-error"] = True; mutations.append(value)
        value = copy.deepcopy(original); value["jobs"]["frontend"]["steps"][0]["uses"] = "actions/checkout@v7"; mutations.append(value)
        value = copy.deepcopy(original); value["jobs"]["frontend"]["steps"][0]["with"]["persist-credentials"] = True; mutations.append(value)
        value = copy.deepcopy(original); value["jobs"]["frontend"]["steps"][-1]["run"] = "echo ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}"; mutations.append(value)
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                policy.validate_workflow(yaml.safe_dump(mutation))

    def test_advertised_commands_cannot_be_deleted_from_the_real_workflow(self):
        original = yaml.safe_load(policy.WORKFLOW.read_text())
        for job, commands in policy.REQUIRED_COMMANDS.items():
            for command in commands:
                mutation = copy.deepcopy(original)
                for step in mutation["jobs"][job]["steps"]:
                    if "run" in step:
                        step["run"] = "\n".join(line for line in step["run"].splitlines() if line.strip() != command)
                with self.subTest(job=job, command=command), self.assertRaises(ValueError):
                    policy.validate_workflow(yaml.safe_dump(mutation))

    def test_runner_temporary_npm_settings_are_only_in_the_two_valid_step_contexts(self):
        workflow = yaml.safe_load(policy.WORKFLOW.read_text())
        policy.validate_workflow(yaml.safe_dump(workflow))
        self.assertNotIn("env", workflow["jobs"]["frontend"])
        env_steps = [step for step in workflow["jobs"]["frontend"]["steps"] if "env" in step]
        self.assertEqual({step["name"] for step in env_steps}, set(policy.NPM_STEPS))
        for step in env_steps:
            self.assertEqual(step["env"], policy.NPM_STEP_ENV)
            self.assertEqual(step["run"].strip(), policy.NPM_STEPS[step["name"]])

    def test_missing_or_changed_npm_step_isolation_is_rejected(self):
        original = yaml.safe_load(policy.WORKFLOW.read_text())
        for step_name in policy.NPM_STEPS:
            for key in (None, *policy.NPM_STEP_ENV):
                mutation = copy.deepcopy(original)
                step = next(step for step in mutation["jobs"]["frontend"]["steps"] if step.get("name") == step_name)
                if key is None:
                    del step["env"]
                else:
                    del step["env"][key]
                with self.subTest(step=step_name, key=key), self.assertRaises(ValueError):
                    policy.validate_workflow(yaml.safe_dump(mutation))
            mutation = copy.deepcopy(original)
            step = next(step for step in mutation["jobs"]["frontend"]["steps"] if step.get("name") == step_name)
            step["env"]["NPM_CONFIG_USERCONFIG"] = "/home/runner/.npmrc"
            with self.subTest(step=step_name, shared_config=True), self.assertRaises(ValueError):
                policy.validate_workflow(yaml.safe_dump(mutation))

    def test_job_context_cannot_receive_runner_expression_or_other_environment(self):
        original = yaml.safe_load(policy.WORKFLOW.read_text())
        for job in original["jobs"]:
            mutation = copy.deepcopy(original)
            mutation["jobs"][job]["env"] = dict(policy.NPM_STEP_ENV)
            with self.subTest(job=job), self.assertRaises(ValueError):
                policy.validate_workflow(yaml.safe_dump(mutation))
        mutation = copy.deepcopy(original)
        frontend = mutation["jobs"]["frontend"]
        frontend["env"] = dict(policy.NPM_STEP_ENV)
        for step in frontend["steps"]:
            step.pop("env", None)
        with self.assertRaises(ValueError): policy.validate_workflow(yaml.safe_dump(mutation))

    def test_extra_environment_credentials_or_misplaced_npm_settings_are_rejected(self):
        original = yaml.safe_load(policy.WORKFLOW.read_text())
        for step_name in policy.NPM_STEPS:
            mutation = copy.deepcopy(original)
            step = next(step for step in mutation["jobs"]["frontend"]["steps"] if step.get("name") == step_name)
            step["env"]["VERCEL_TOKEN"] = "must-not-be-allowed"
            with self.subTest(step=step_name), self.assertRaises(ValueError):
                policy.validate_workflow(yaml.safe_dump(mutation))
        for job in original["jobs"]:
            mutation = copy.deepcopy(original)
            mutation["jobs"][job]["steps"][0]["env"] = dict(policy.NPM_STEP_ENV)
            with self.subTest(job=job), self.assertRaises(ValueError):
                policy.validate_workflow(yaml.safe_dump(mutation))
        for job in original["jobs"]:
            mutation = copy.deepcopy(original)
            mutation["jobs"][job].setdefault("env", {})["SUPABASE_SERVICE_ROLE_KEY"] = "must-not-be-allowed"
            with self.subTest(job=job, credentials=True), self.assertRaises(ValueError):
                policy.validate_workflow(yaml.safe_dump(mutation))
        mutation = copy.deepcopy(original)
        mutation["env"]["RAILWAY_TOKEN"] = "must-not-be-allowed"
        with self.assertRaises(ValueError): policy.validate_workflow(yaml.safe_dump(mutation))

    def test_required_triggers_cannot_acquire_skip_filters(self):
        original = yaml.safe_load(policy.WORKFLOW.read_text())
        for event, config in (("pull_request", {"paths": ["unrelated/**"]}),
                              ("pull_request", {"branches": ["unused"]}),
                              ("pull_request", {"types": ["opened"]}),
                              ("workflow_dispatch", {"inputs": {"skip": {"type": "boolean"}}}),
                              ("push", {"branches": ["main"], "paths-ignore": ["**"]}),
                              ("push", {"branches": ["main", "codex/**"]})):
            mutation = copy.deepcopy(original); mutation["on"][event] = config
            with self.subTest(event=event, config=config), self.assertRaises(ValueError):
                policy.validate_workflow(yaml.safe_dump(mutation))

    def test_worker_matrix_requires_both_bounded_shards_without_bypasses(self):
        original = yaml.safe_load(policy.WORKFLOW.read_text())
        for strategy in (
            {"fail-fast": False, "max-parallel": 2, "matrix": {"shard": [1]}},
            {"fail-fast": False, "max-parallel": 2, "matrix": {"shard": [1, 2, 3]}},
            {"fail-fast": True, "max-parallel": 2, "matrix": {"shard": [1, 2]}},
            {"fail-fast": False, "max-parallel": 8, "matrix": {"shard": [1, 2]}},
            {"fail-fast": False, "max-parallel": 2, "matrix": {"shard": [1, 2], "exclude": [{"shard": 2}]}},
            {"fail-fast": False, "max-parallel": 2, "matrix": {"shard": [True, 2]}},
            {"fail-fast": 0, "max-parallel": 2, "matrix": {"shard": [1, 2]}},
        ):
            mutation = copy.deepcopy(original); mutation["jobs"]["worker"]["strategy"] = strategy
            with self.subTest(strategy=strategy), self.assertRaises(ValueError):
                policy.validate_workflow(yaml.safe_dump(mutation))
        for changed in ({}, {"DASHBOARD_TEST_SHARD": "1"},
                        {"DASHBOARD_TEST_SHARD": "${{ github.event.inputs.shard }}"},
                        {**policy.WORKER_SHARD_ENV, "RAILWAY_TOKEN": "must-not-copy"}):
            mutation = copy.deepcopy(original)
            mutation["jobs"]["worker"]["steps"][-1]["env"] = changed
            with self.subTest(env=changed), self.assertRaises(ValueError):
                policy.validate_workflow(yaml.safe_dump(mutation))
        mutation = copy.deepcopy(original); mutation["jobs"]["frontend"]["strategy"] = policy.WORKER_STRATEGY
        with self.assertRaises(ValueError): policy.validate_workflow(yaml.safe_dump(mutation))

    def test_postgres_concurrency_is_exactly_four_without_removing_any_required_shard(self):
        original = yaml.safe_load(policy.WORKFLOW.read_text())
        expected = {"fail-fast": False, "max-parallel": 4, "matrix": {"shard": [1, 2, 3, 4]}}
        self.assertEqual(policy.POSTGRES_STRATEGY, expected)
        self.assertEqual(original["jobs"]["postgres"]["strategy"], expected)
        policy.validate_workflow(yaml.safe_dump(original))
        for parallel in (0, 1, 2, 3, 8, False, True, 4.0, "4"):
            mutation = copy.deepcopy(original)
            mutation["jobs"]["postgres"]["strategy"]["max-parallel"] = parallel
            with self.subTest(parallel=parallel), self.assertRaises(ValueError):
                policy.validate_workflow(yaml.safe_dump(mutation))

    def test_required_postgres_matrix_keeps_every_shard_and_explicit_integration_authority(self):
        original = yaml.safe_load(policy.WORKFLOW.read_text())
        for strategy in (
            {"fail-fast": False, "max-parallel": 4, "matrix": {"shard": [1, 2, 3]}},
            {"fail-fast": False, "max-parallel": 4, "matrix": {"shard": [1, 2, 3, 4, 5]}},
            {"fail-fast": True, "max-parallel": 4, "matrix": {"shard": [1, 2, 3, 4]}},
            {"fail-fast": False, "max-parallel": 8, "matrix": {"shard": [1, 2, 3, 4]}},
            {"fail-fast": False, "max-parallel": 4, "matrix": {"shard": [True, 2, 3, 4]}},
            {**policy.POSTGRES_STRATEGY, "matrix": {"shard": [1, 2, 3, 4], "exclude": [{"shard": 4}]}},
        ):
            mutation = copy.deepcopy(original); mutation["jobs"]["postgres"]["strategy"] = strategy
            with self.subTest(strategy=strategy), self.assertRaises(ValueError):
                policy.validate_workflow(yaml.safe_dump(mutation))
        for changed in ({}, {"DASHBOARD_TEST_SHARD": "1"},
                        {"DASHBOARD_TEST_SHARD": "${{ github.event.inputs.shard }}"},
                        {**policy.POSTGRES_SHARD_ENV, "SUPABASE_SERVICE_ROLE_KEY": "must-not-copy"}):
            mutation = copy.deepcopy(original)
            mutation["jobs"]["postgres"]["steps"][-1]["env"] = changed
            with self.subTest(env=changed), self.assertRaises(ValueError):
                policy.validate_workflow(yaml.safe_dump(mutation))

    def test_image_preparation_shard_environment_is_exact_step_scoped_and_cannot_bypass_setup(self):
        original = yaml.safe_load(policy.WORKFLOW.read_text())
        policy.validate_workflow(yaml.safe_dump(original))
        image = next(step for step in original['jobs']['postgres']['steps'] if step.get('name') == policy.IMAGE_PREP_STEP)
        self.assertEqual(image['env'], policy.WORKER_SHARD_ENV)
        self.assertEqual(image['run'], policy.IMAGE_PREP_COMMAND)
        for environment in (None, {}, {'DASHBOARD_TEST_SHARD': '1'},
                            {'DASHBOARD_TEST_SHARD': '${{ github.event.inputs.shard }}'},
                            {**policy.WORKER_SHARD_ENV, 'DOCKER_CONFIG': '/shared/docker'},
                            {**policy.WORKER_SHARD_ENV, 'SUPABASE_SERVICE_ROLE_KEY': 'never-copy'}):
            mutation = copy.deepcopy(original)
            step = next(step for step in mutation['jobs']['postgres']['steps'] if step.get('name') == policy.IMAGE_PREP_STEP)
            if environment is None: step.pop('env')
            else: step['env'] = environment
            with self.subTest(environment=environment), self.assertRaises(ValueError):
                policy.validate_workflow(yaml.safe_dump(mutation))
        for change in ('delete', 'duplicate', 'after-integration', 'renamed'):
            mutation = copy.deepcopy(original); steps = mutation['jobs']['postgres']['steps']
            step = next(step for step in steps if step.get('name') == policy.IMAGE_PREP_STEP)
            if change == 'delete': steps.remove(step)
            elif change == 'duplicate': steps.insert(steps.index(step), copy.deepcopy(step))
            elif change == 'after-integration': steps.remove(step); steps.append(step)
            else: step['name'] = 'Unreviewed preparation'
            with self.subTest(change=change), self.assertRaises(ValueError):
                policy.validate_workflow(yaml.safe_dump(mutation))

    def test_native_wheel_preparation_and_exact_owned_execution_path_cannot_be_removed_or_misplaced(self):
        original = yaml.safe_load(policy.WORKFLOW.read_text())
        mutations = []
        value = copy.deepcopy(original)
        value['jobs']['postgres']['steps'] = [step for step in value['jobs']['postgres']['steps']
                                             if step.get('name') != policy.NATIVE_WHEELS_PREP_STEP]
        mutations.append(value)
        value = copy.deepcopy(original)
        steps = value['jobs']['postgres']['steps']; steps[-2], steps[-1] = steps[-1], steps[-2]
        mutations.append(value)
        value = copy.deepcopy(original); del value['jobs']['postgres']['steps'][-1]['env']['DASHBOARD_NATIVE_SQL_WHEELS']; mutations.append(value)
        value = copy.deepcopy(original); value['jobs']['postgres']['steps'][-1]['env']['DASHBOARD_NATIVE_SQL_WHEELS'] = '/home/runner/shared-wheels'; mutations.append(value)
        value = copy.deepcopy(original); value['jobs']['postgres']['steps'][-2]['run'] = policy.NATIVE_WHEELS_PREP_COMMAND.replace('dashboard-native-wheels', 'shared-wheels'); mutations.append(value)
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                policy.validate_workflow(yaml.safe_dump(mutation))
        for omitted in ("--allow-isolated-postgres", '--shard "$DASHBOARD_TEST_SHARD"'):
            mutation = copy.deepcopy(original)
            step = mutation["jobs"]["postgres"]["steps"][-1]
            step["run"] = step["run"].replace(omitted, '')
            with self.subTest(omitted=omitted), self.assertRaises(ValueError):
                policy.validate_workflow(yaml.safe_dump(mutation))


if __name__ == "__main__": unittest.main()
