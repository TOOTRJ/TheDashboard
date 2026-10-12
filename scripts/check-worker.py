#!/usr/bin/env python3
"""Run offline or explicitly required owned PostgreSQL suites with audited skips."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "services" / "vonneumann"
OPT_IN = "DASHBOARD_ISOLATED_POSTGRES_TESTS"
SUPPORTED_PYTHON = (3, 12, 14)
CHILD_DEADLINES = {"offline": 1500, "postgres": 2400}
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
    return env


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
    accepted = result.wasSuccessful() and executed > 0 and not unexpected
    return {
        "scope": mode, "tests_reported": result.testsRun,
        "tests_executed": executed, "skips": skips,
        "unexpected_skips": len(unexpected), "accepted": accepted,
        "hosted_or_live_acceptance": False,
    }, accepted


def run_suites(mode: str) -> int:
    require_supported_python()
    # Reexecution's internal flag is not a way to bypass environment isolation.
    validate_child_environment(mode, dict(os.environ))
    sys.path.insert(0, str(WORKER))
    loader = unittest.TestLoader()
    suite = loader.discover(str(WORKER / "tests" / "postgres" if mode == "postgres" else WORKER / "tests"),
                            pattern="test_*.py", top_level_dir=str(WORKER))
    if mode == "offline":
        # Helpers live outside the worker's tests package; discover each as top level.
        for directory, pattern in ((ROOT / "scripts" / "tests", "test_*.py"), (ROOT / "tests", "*_test.py")):
            suite.addTests(unittest.TestLoader().discover(str(directory), pattern=pattern,
                                                         top_level_dir=str(directory)))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report, accepted = audit_result(result, mode)
    print(json.dumps(report, sort_keys=True))
    return 0 if accepted else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("offline", "postgres"))
    parser.add_argument("--allow-isolated-postgres", action="store_true")
    parser.add_argument("--sanitized-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    require_supported_python()
    if args.mode == "postgres" and not args.allow_isolated_postgres:
        parser.error("Required integration needs --allow-isolated-postgres")
    if args.sanitized_child:
        if os.environ.get("PYTHON_DOTENV_DISABLED") != "1":
            raise RuntimeError("Dotenv loading must remain disabled")
        if args.mode == "postgres" and os.environ.get(OPT_IN) != "1":
            raise RuntimeError("Required integration opt-in is missing")
        return run_suites(args.mode)
    env = worker_environment(args.mode, dict(os.environ))
    command = [sys.executable, str(Path(__file__).resolve()), args.mode, "--sanitized-child"]
    if args.allow_isolated_postgres:
        command.append("--allow-isolated-postgres")
    return subprocess.run(command, cwd=ROOT, env=env, timeout=CHILD_DEADLINES[args.mode], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
