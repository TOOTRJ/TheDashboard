#!/usr/bin/env python3
"""Run offline or explicitly required owned PostgreSQL suites with audited skips."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "services" / "vonneumann"
OPT_IN = "DASHBOARD_ISOLATED_POSTGRES_TESTS"
NATIVE_WHEELS_ENV = "DASHBOARD_NATIVE_SQL_WHEELS"
SUPPORTED_PYTHON = (3, 12, 14)
CHILD_DEADLINES = {"offline": 1500, "postgres": 2400}
# The hosted log's large gaps include the NEXT module's class setup. Keep the
# 32-window provider traces opposite portable three-seed/four-window traces.
# New modules use a stable SHA-256 partition, never an exclusion list.
OFFLINE_SHARDS = (1, 2)
POSTGRES_SHARDS = (1, 2, 3, 4)
SHARDS_BY_MODE = {"offline": OFFLINE_SHARDS, "postgres": POSTGRES_SHARDS}
HEAVY_MODULE_SHARDS = {
    # Run 39014680277 hit 1500s with model and source admission on shard 2.
    # Keep both whole modules opposite; cases and deadlines remain unchanged.
    "tests.test_prospective_ga_v3_model": 1,
    "tests.test_provider_ga_components": 1,
    "tests.test_portable_ga_model": 2,
    "tests.test_ga_active_model": 2,
    "tests.test_partitioned_checkpoint": 2,
}
# Defining-module anchors distribute the costly semantic setup chains. These
# balancing hints do not omit cases or relax acceptance; hosted timings remain
# required before claiming that all four bounded jobs complete.
POSTGRES_HEAVY_MODULE_SHARDS = {
    "tests.postgres.test_assessment_transition": 1,
    "tests.postgres.test_locked_checkpoint": 1,
    "tests.postgres.test_numeric_wire": 1,
    "tests.postgres.test_checkpoint_reference": 1,
    "tests.postgres.test_command_adapter": 1,
    "tests.postgres.test_decimal_lineage_contract": 1,
    "tests.postgres.test_exact_transition_contract": 1,
    "tests.postgres.test_harness": 1,
    "tests.postgres.test_causal_risk": 2,
    # c58177a's shard2 exceeds2400s during the complete source trace while
    # shard4 completes its205 cases in15m39s. Move all30 original defining
    # module occurrences together; no alias, fixture segment or limit changes.
    # The new hosted run must establish that this distribution completes.
    "tests.postgres.test_source_transition": 4,
    "tests.postgres.test_fenced_commands": 2,
    "tests.postgres.test_lifecycle_contract": 2,
    "tests.postgres.test_lifecycle_adversarial": 2,
    "tests.postgres.test_lifecycle_delivery": 2,
    "tests.postgres.test_transition_coordinator": 2,
    "tests.postgres.test_read_projections": 2,
    "tests.postgres.test_read_projection_http": 2,
    "tests.postgres.test_optimizer_transition": 3,
    "tests.postgres.test_economic_transition": 3,
    "tests.postgres.test_legacy_evidence": 3,
    "tests.postgres.test_legacy_retirement": 3,
    "tests.postgres.test_installer_boundary": 3,
    "tests.postgres.test_expired_paper_maintenance": 3,
    # PR104's actual shard2 reaches the new full semantic module after37m;
    # shard3 finishes18m40s. Keep this module intact on the shorter shard.
    # The2400s child deadline, every occurrence and fixture segment stay fixed.
    "tests.postgres.test_portable_transition": 3,
    "tests.postgres.test_portable_period_mutation": 4,
    "tests.postgres.test_native_sql": 4,
    "tests.postgres.test_session_auth": 4,
    "tests.postgres.test_native_issuer": 4,
    "tests.postgres.test_native_operator": 4,
    "tests.postgres.test_canonical_v5": 4,
    "tests.postgres.test_forward_cutover": 4,
    "tests.postgres.test_paper_service": 4,
    "tests.postgres.test_provider_contract": 4,
    "tests.postgres.test_provider_controller": 4,
    "tests.postgres.test_command_http_postgrest": 4,
}
OPT_IN_REASONS = {
    "Requires isolated PostgreSQL opt-in", "Explicit isolated PostgreSQL opt-in required",
    "Use tests.postgres.run --allow-isolated-postgres",
}
OPTIONAL_MEASUREMENTS = {
    "tests.postgres.test_assessment_transition.AssessmentTransitionSqlTests.test_z_measure_full_boundary": "Optional full assessment timing",
    "tests.postgres.test_causal_risk.CausalRiskSqlTests.test_z_measure_complete_causal_boundary": "Optional full semantic wrapper timing",
    "tests.postgres.test_economic_transition.EconomicTransitionSqlTests.test_z_measure_resolved_economic_boundary_without_effects": "Optional full-boundary timing requires explicit opt-in",
    "tests.postgres.test_locked_checkpoint.LockedCheckpointSqlTests.test_z_measure_full_locked_resolution_without_committing": "Optional server measurement requires explicit opt-in",
    "tests.postgres.test_optimizer_transition.OptimizerTransitionSqlTests.test_z_measure_full_boundary": "Optional complete optimizer timing",
    "tests.postgres.test_source_transition.SourceTransitionSqlTests.test_z_measure_complete_source_boundary": "Optional complete-wrapper timing",
}


def worker_environment(mode: str, inherited: dict[str, str]) -> dict[str, str]:
    env = {key: inherited[key] for key in ("PATH", "TMPDIR") if key in inherited}
    env.update(PYTHONPATH=str(WORKER), PYTHON_DOTENV_DISABLED="1", PYTHONDONTWRITEBYTECODE="1",
               OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", LANG="C", LC_ALL="C", LC_CTYPE="C",
               PYTHONUTF8="1", PYTHONCOERCECLOCALE="0")
    if sys.platform == "darwin":
        # Python's macOS imports initialize this fixed per-UID text encoding.
        # Set it before launch so initialization adds no unexpected environment.
        env["__CF_USER_TEXT_ENCODING"] = f"0x{os.getuid():X}:0x0:0x0"
    if mode == "postgres":
        host = inherited.get("DOCKER_HOST", "unix:///var/run/docker.sock")
        if not host.startswith("unix:///"):
            raise ValueError("Required integration refuses a nonlocal Docker socket")
        env["DOCKER_HOST"] = host
        env[OPT_IN] = "1"
        env[NATIVE_WHEELS_ENV] = str(native_wheels_directory(inherited))
    return env


def native_wheels_directory(inherited: dict[str, str]) -> Path:
    directory = inherited.get(NATIVE_WHEELS_ENV)
    if not isinstance(directory, str) or not directory or not Path(directory).is_absolute():
        raise RuntimeError("Required PostgreSQL verification needs an explicit prepared native SQL wheel bundle")
    helper = ROOT / "scripts" / "check-ci-native-wheels.py"
    if helper.resolve() != helper or not helper.is_file():
        raise RuntimeError("Native SQL wheel validation requires its reviewed regular helper source")
    spec = importlib.util.spec_from_file_location("dashboard_ci_native_wheels_validation", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Pure lock/source/ownership/content validation is repeated in the sanitized
    # child. A path copied from arbitrary parent configuration grants no access.
    return module.validate_bundle(directory)


def require_supported_python(version=None, implementation=None) -> None:
    version = tuple(sys.version_info[:3]) if version is None else version
    implementation = sys.implementation.name if implementation is None else implementation
    if version != SUPPORTED_PYTHON or implementation != "cpython":
        raise RuntimeError("Use CPython 3.12.14 in the hash-locked worker virtual environment; the default system Python is unsupported")


def validate_child_environment(mode: str, inherited: dict[str, str]) -> None:
    expected = worker_environment(mode, inherited)
    if set(inherited) != set(expected) or any(inherited.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Worker verification must run in its exact sanitized child environment")


def skip_category(identity: str, reason: str, mode: str) -> str | None:
    if "tests.postgres." not in identity:
        return None
    if reason in OPT_IN_REASONS:
        return "postgres-opt-in-not-executed" if mode == "offline" else None
    if OPTIONAL_MEASUREMENTS.get(identity) == reason:
        return "non-gating-measurement-not-executed"
    return None


def audit_result(result: unittest.TestResult, mode: str) -> tuple[dict, bool]:
    skips = []
    for test, reason in result.skipped:
        skips.append({"id": test.id(), "reason": reason,
                      "category": skip_category(test.id(), reason, mode)})
    unexpected = [item for item in skips if item["category"] is None]
    # unittest reports class-setup skips separately, without startTest/testsRun.
    method_skips = sum(not item["id"].startswith(("setUpClass (", "setUpModule (")) for item in skips)
    executed = result.testsRun - method_skips
    accepted = result.wasSuccessful() and executed > 0 and not unexpected and not result.shouldStop
    return {
        "scope": mode, "tests_reported": result.testsRun,
        "tests_executed": executed, "skips": skips,
        "unexpected_skips": len(unexpected), "accepted": accepted,
        "hosted_or_live_acceptance": False,
    }, accepted


def discover_suite(mode: str) -> unittest.TestSuite:
    sys.path.insert(0, str(WORKER))
    locations = [(WORKER / "tests" / "postgres" if mode == "postgres" else WORKER / "tests",
                  "test_*.py", WORKER)]
    if mode == "offline":
        # Helpers live outside the worker's tests package; discover each as top level.
        locations.extend((directory, pattern, directory) for directory, pattern in (
            (ROOT / "scripts" / "tests", "test_*.py"), (ROOT / "tests", "*_test.py")))
    suite = unittest.TestSuite()
    for directory, pattern, top_level in locations:
        loader = unittest.TestLoader()
        discovered = loader.discover(str(directory), pattern=pattern, top_level_dir=str(top_level))
        if loader.errors:
            raise RuntimeError(f"Worker discovery failed before selection: {len(loader.errors)} import errors")
        suite.addTests(discovered)
    return suite


def flatten_tests(suite):
    if isinstance(suite, unittest.TestCase):
        yield suite
    elif isinstance(suite, unittest.TestSuite):
        for child in suite:
            yield from flatten_tests(child)
    else:
        raise RuntimeError("Discovery returned an unreviewed test object")


def module_shard(module: str, mode: str = "offline") -> int:
    if not isinstance(module, str) or not module:
        raise RuntimeError("Discovered test has no defining module")
    if mode not in SHARDS_BY_MODE:
        raise RuntimeError("Unreviewed verification scope")
    hints = HEAVY_MODULE_SHARDS if mode == "offline" else POSTGRES_HEAVY_MODULE_SHARDS
    return hints.get(module, 1 + int.from_bytes(hashlib.sha256(module.encode()).digest(), "big") % len(SHARDS_BY_MODE[mode]))


def validate_partition(tests, shards, mode: str = "offline") -> None:
    declared = SHARDS_BY_MODE.get(mode)
    if declared is None or set(shards) != set(declared) or any(type(key) is not int for key in shards):
        raise RuntimeError("Exactly the reviewed scope's complete shard set is required")
    indices = [index for shard in declared for index in shards[shard]]
    if (any(type(index) is not int for index in indices)
            or Counter(indices) != Counter(range(len(tests)))
            or any(not shards[shard] for shard in declared)):
        raise RuntimeError("Shard coverage omitted, duplicated or invented a discovered occurrence")
    modules = []
    for shard in declared:
        selected = shards[shard]
        if tuple(selected) != tuple(sorted(selected)):
            raise RuntimeError("Shards must preserve the original discovery order")
        modules.append({tests[index].__class__.__module__ for index in selected})
        if any(module_shard(tests[index].__class__.__module__, mode) != shard for index in selected):
            raise RuntimeError("Shard membership changed or split a defining module")
    if any(first & second for index, first in enumerate(modules) for second in modules[index + 1:]):
        raise RuntimeError("A defining test module cannot run in more than one shard")
    # Repeated imported TestCase IDs already in ordinary discovery remain repeated.
    original = Counter(test.id() for test in tests)
    selected = Counter(tests[index].id() for index in indices)
    if original != selected:
        raise RuntimeError("Shard coverage changed baseline test-ID multiplicity")


def test_source(test) -> tuple[str, str]:
    module = sys.modules.get(test.__class__.__module__)
    location = getattr(module, "__file__", None)
    if location is None:
        raise RuntimeError("Discovered test must have a reviewed source file")
    path = Path(location).absolute()
    if path.resolve() != path or not path.is_file() or path.suffix != ".py":
        raise RuntimeError("Discovered test source must be a regular nonsymlink Python file")
    roots = ((WORKER / "tests", "test_*.py"), (ROOT / "scripts" / "tests", "test_*.py"),
             (ROOT / "tests", "*_test.py"))
    admitted = False
    for base, pattern in roots:
        if path.is_relative_to(base):
            relative = path.relative_to(base)
            admitted = path.match(pattern) and not any(
                part in {"ssl", ".vercel", ".aws", ".codex", ".claude"} or part.startswith('.env')
                for part in relative.parts)
            break
    if not admitted:
        raise RuntimeError("Discovered test source is outside the three reviewed test roots")
    return path.relative_to(ROOT).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()


def partition_suite(suite, mode: str):
    if mode not in SHARDS_BY_MODE:
        raise RuntimeError("Unreviewed verification scope")
    tests = tuple(flatten_tests(suite))
    sources = {}
    rows = []
    shards = {shard: [] for shard in SHARDS_BY_MODE[mode]}
    for index, test in enumerate(tests):
        module = test.__class__.__module__
        if module not in sources:
            sources[module] = test_source(test)
        path, digest = sources[module]
        rows.append([index, test.id(), module, path, digest])
        shards[module_shard(module, mode)].append(index)
    shards = {shard: tuple(indices) for shard, indices in shards.items()}
    validate_partition(tests, shards, mode)
    def fingerprint(value):
        return hashlib.sha256(json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    coverage = {
        "algorithm": f"{mode}-module-sha256-v1", "scope": mode,
        "declared_shards": list(SHARDS_BY_MODE[mode]), "discovered_occurrences": len(tests),
        "runtime": "CPython 3.12.14",
        "selection_source_sha256": hashlib.sha256((ROOT / "scripts" / "check-worker.py").read_bytes()).hexdigest(),
        "baseline_repeated_ids": sum(count - 1 for count in Counter(test.id() for test in tests).values()),
        "discovery_source_sha256": fingerprint(rows),
        "shards": {str(shard): {"occurrences": len(indices),
                    "modules": sorted({tests[index].__class__.__module__ for index in indices}),
                    "occurrence_source_sha256": fingerprint([rows[index] for index in indices])}
                   for shard, indices in shards.items()},
        "exhaustive_disjoint_occurrences": True,
    }
    return tests, shards, coverage


def partition_offline(suite):
    return partition_suite(suite, "offline")


class ModuleShardSuite(unittest.TestSuite):
    """Preserve original module fixture boundaries when other modules are removed."""
    def run(self, result, debug=False):
        for segment in self:
            if result.shouldStop:
                break
            # Each standard top-level suite tears down its module/class fixtures.
            # CPython's result retains the previous class sentinel afterward;
            # reset it so an imported alias after a removed module sets up anew.
            # This harness requires the reviewed exact CPython runtime above.
            result._previousTestClass = None
            segment.run(result, debug)
        return result


def selected_suite(tests, indices):
    selected = set(indices)
    segments, segment, previous = [], [], None
    for index, test in enumerate(tests):
        module = test.__class__.__module__
        if previous is not None and module != previous:
            if segment:
                segments.append(unittest.TestSuite(segment))
            segment = []
        if index in selected:
            segment.append(test)
        previous = module
    if segment:
        segments.append(unittest.TestSuite(segment))
    return ModuleShardSuite(segments)


def run_suites(mode: str, shard: int | None = None) -> int:
    require_supported_python()
    # Reexecution's internal flag is not a way to bypass environment isolation.
    validate_child_environment(mode, dict(os.environ))
    if mode not in SHARDS_BY_MODE or (shard is not None and (type(shard) is not int or shard not in SHARDS_BY_MODE[mode])):
        raise RuntimeError("Selection must use one of the reviewed scope's declared shards")
    suite = discover_suite(mode)
    tests, shards, coverage = partition_suite(suite, mode)
    # Print source-bound coverage before execution, including on a timeout.
    print(json.dumps({f"{mode}_coverage": coverage, "selected_shard": shard}, sort_keys=True), flush=True)
    if shard is not None:
        suite = selected_suite(tests, shards[shard])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report, accepted = audit_result(result, mode)
    report.update({f"{mode}_coverage": coverage, "selected_shard": shard})
    print(json.dumps(report, sort_keys=True))
    return 0 if accepted else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("offline", "postgres"))
    parser.add_argument("--allow-isolated-postgres", action="store_true")
    parser.add_argument("--shard", type=int,
                        help="Execute a declared module-cohesive shard: offline 1..2 or postgres 1..4; omit for full discovery")
    parser.add_argument("--sanitized-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    require_supported_python()
    if args.mode == "postgres" and not args.allow_isolated_postgres:
        parser.error("Required integration needs --allow-isolated-postgres")
    if args.shard is not None and args.shard not in SHARDS_BY_MODE[args.mode]:
        parser.error("Selection must use a declared shard for its verification scope")
    if args.sanitized_child:
        if os.environ.get("PYTHON_DOTENV_DISABLED") != "1":
            raise RuntimeError("Dotenv loading must remain disabled")
        if args.mode == "postgres" and os.environ.get(OPT_IN) != "1":
            raise RuntimeError("Required integration opt-in is missing")
        return run_suites(args.mode, args.shard)
    env = worker_environment(args.mode, dict(os.environ))
    command = [sys.executable, str(Path(__file__).resolve()), args.mode, "--sanitized-child"]
    if args.allow_isolated_postgres:
        command.append("--allow-isolated-postgres")
    if args.shard is not None:
        command.extend(("--shard", str(args.shard)))
    return subprocess.run(command, cwd=ROOT, env=env, timeout=CHILD_DEADLINES[args.mode], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
