#!/usr/bin/env python3
"""Check the reviewed workflow's capabilities and required independent test gates."""
from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "verification.yml"
ACTION_PINS = {
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1",
    "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1",
}
JOB_MINUTES = {"frontend": 20, "worker": 30, "postgres": 50}
PYTHON = '"$RUNNER_TEMP/dashboard-python/bin/python"'
HASH_INSTALL = f"{PYTHON} -m pip install --require-hashes --only-binary=:all: -r services/vonneumann/requirements-dev.txt"
REQUIRED_COMMANDS = {
    "frontend": {
        ': > "$NPM_CONFIG_USERCONFIG"', ': > "$NPM_CONFIG_GLOBALCONFIG"',
        "npm ci --ignore-scripts --no-audit --no-fund",
        "node --test tests/*.test.mjs tests/probes/*.test.mjs scripts/tests/*.test.mjs",
        "node node_modules/typescript/bin/tsc --noEmit", "npm run lint",
        "node scripts/check-advisories.mjs", "node scripts/check-build.mjs",
    },
    "worker": {
        'python -m venv "$RUNNER_TEMP/dashboard-python"', HASH_INSTALL,
        f"{PYTHON} -m pip check", f"{PYTHON} scripts/check-worker.py offline",
    },
    "postgres": {
        'python -m venv "$RUNNER_TEMP/dashboard-python"', HASH_INSTALL,
        f"{PYTHON} -m pip check", f"{PYTHON} scripts/check-ci-images.py --prepare-images",
        f"{PYTHON} scripts/check-worker.py postgres --allow-isolated-postgres",
    },
}


def validate_workflow(source: str) -> None:
    data = yaml.safe_load(source)
    if not isinstance(data, dict) or not isinstance(data.get("on"), dict):
        raise ValueError("Workflow must use an explicit event mapping")
    events = data["on"]
    if set(events) != {"pull_request", "push", "workflow_dispatch"}:
        raise ValueError("Workflow trigger capabilities changed")
    if any(events[name] not in (None, {}) for name in ("pull_request", "workflow_dispatch")):
        raise ValueError("Required PR and dispatch checks cannot have trigger filters")
    if events["push"] != {"branches": ["main"]}:
        raise ValueError("Main pushes cannot have additional filters or duplicate feature jobs")
    if data.get("permissions") != {"contents": "read"}:
        raise ValueError("Workflow must have only read-only repository permissions")
    if data.get("concurrency", {}).get("cancel-in-progress") is not True:
        raise ValueError("Concurrent verification must be bounded")
    if re.search(r"\$\{\{\s*secrets\.", source):
        raise ValueError("Verification must not reference application credentials")
    jobs = data.get("jobs", {})
    if set(jobs) != {"frontend", "worker", "postgres"}:
        raise ValueError("The three independent verification gates are required")
    for name, job in jobs.items():
        if (job.get("runs-on") != "ubuntu-24.04" or type(job.get("timeout-minutes")) is not int
                or job["timeout-minutes"] != JOB_MINUTES[name]):
            raise ValueError("Verification requires bounded disposable hosted runners")
        if any(key in job for key in ("permissions", "environment", "services", "container", "if")):
            raise ValueError("Verification cannot widen privileges or skip a required job")
        for step in job.get("steps", []):
            if "if" in step or step.get("continue-on-error") or "env" in step:
                raise ValueError("Required checks cannot be bypassed or receive step credentials")
            if "uses" in step and step["uses"] not in ACTION_PINS:
                raise ValueError("Action must be one of the reviewed full commit pins")
            if step.get("uses", "").startswith("actions/checkout@") and step.get("with", {}).get("persist-credentials") is not False:
                raise ValueError("Checkout must not persist its read-only credential")
            if step.get("uses", "").startswith("actions/setup-node@") and step.get("with") != {"node-version": "24.19.0", "package-manager-cache": False}:
                raise ValueError("Node runtime and uncached setup must remain reviewed")
            if step.get("uses", "").startswith("actions/setup-python@") and step.get("with") != {"python-version": "3.12.14", "architecture": "x64", "allow-prereleases": False}:
                raise ValueError("Python runtime and release-only setup must remain reviewed")
            if "run" in step and "${{" in step["run"]:
                raise ValueError("Shell commands cannot interpolate untrusted event expressions")
    for name, required in REQUIRED_COMMANDS.items():
        commands = {line.strip() for step in jobs[name]["steps"]
                    for line in step.get("run", "").splitlines() if line.strip()}
        if not required <= commands:
            raise ValueError("An advertised required check, locked installation or image boundary is missing")


if __name__ == "__main__":
    validate_workflow(WORKFLOW.read_text())
    print("Dashboard workflow capability and required-gate checks passed")
