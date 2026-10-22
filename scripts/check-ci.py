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
WORKFLOW_ENV = {
    "NEXT_TELEMETRY_DISABLED": "1", "PYTHON_DOTENV_DISABLED": "1",
    "PYTHONDONTWRITEBYTECODE": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    "PIP_NO_INPUT": "1", "PIP_CONFIG_FILE": "/dev/null",
}
NPM_STEP_ENV = {
    "NPM_CONFIG_USERCONFIG": "${{ runner.temp }}/dashboard-frontend-user.npmrc",
    "NPM_CONFIG_GLOBALCONFIG": "${{ runner.temp }}/dashboard-frontend-global.npmrc",
    "NPM_CONFIG_CACHE": "${{ runner.temp }}/dashboard-frontend-npm-cache",
}
NPM_STEPS = {
    "Clean locked dependencies without lifecycle scripts": '\n'.join((
        ': > "$NPM_CONFIG_USERCONFIG"', ': > "$NPM_CONFIG_GLOBALCONFIG"',
        'npm ci --ignore-scripts --no-audit --no-fund',
    )),
    "ESLint": "npm run lint",
}
PYTHON = '"$RUNNER_TEMP/dashboard-python/bin/python"'
HASH_INSTALL = f"{PYTHON} -m pip install --require-hashes --only-binary=:all: -r services/vonneumann/requirements-dev.txt"
WORKER_SHARD_STEP = "Ordinary discovery with explicit skip audit and sanitized environment"
WORKER_SHARD_ENV = {"DASHBOARD_TEST_SHARD": "${{ matrix.shard }}"}
WORKER_SHARD_COMMAND = f'{PYTHON} scripts/check-worker.py offline --shard "$DASHBOARD_TEST_SHARD"'
WORKER_STRATEGY = {"fail-fast": False, "max-parallel": 3, "matrix": {"shard": [1, 2, 3]}}
POSTGRES_SHARD_STEP = "Required integration (missing Docker, failed setup or opt-in skips fail)"
POSTGRES_SHARD_ENV = {**WORKER_SHARD_ENV, "DASHBOARD_NATIVE_SQL_WHEELS": "${{ runner.temp }}/dashboard-native-wheels"}
POSTGRES_SHARD_COMMAND = f'{PYTHON} scripts/check-worker.py postgres --allow-isolated-postgres --shard "$DASHBOARD_TEST_SHARD"'
POSTGRES_STRATEGY = {"fail-fast": False, "max-parallel": 4, "matrix": {"shard": [1, 2, 3, 4]}}
IMAGE_PREP_STEP = "Pull and verify reviewed immutable amd64 fixture manifests"
IMAGE_PREP_COMMAND = f'{PYTHON} scripts/check-ci-images.py --prepare-images'
NATIVE_WHEELS_PREP_STEP = "Prepare owned hash-locked native SQL wheels"
NATIVE_WHEELS_PREP_COMMAND = f'{PYTHON} scripts/check-ci-native-wheels.py --destination "$RUNNER_TEMP/dashboard-native-wheels"'
SHARD_JOBS = {
    "worker": (WORKER_STRATEGY, WORKER_SHARD_STEP, WORKER_SHARD_COMMAND),
    "postgres": (POSTGRES_STRATEGY, POSTGRES_SHARD_STEP, POSTGRES_SHARD_COMMAND),
}
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
        f"{PYTHON} -m pip check", WORKER_SHARD_COMMAND,
    },
    "postgres": {
        'python -m venv "$RUNNER_TEMP/dashboard-python"', HASH_INSTALL,
        f"{PYTHON} -m pip check", f"{PYTHON} scripts/check-ci-images.py --prepare-images",
        NATIVE_WHEELS_PREP_COMMAND, POSTGRES_SHARD_COMMAND,
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
    if data.get("env") != WORKFLOW_ENV:
        raise ValueError("Workflow environment must contain only reviewed inert verification settings")
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
        if any(key in job for key in ("permissions", "environment", "services", "container", "if", "continue-on-error")):
            raise ValueError("Verification cannot widen privileges or skip a required job")
        if name in SHARD_JOBS:
            strategy = job.get("strategy")
            if (strategy != SHARD_JOBS[name][0] or type(strategy.get("fail-fast")) is not bool
                    or type(strategy.get("max-parallel")) is not int
                    or any(type(value) is not int for value in strategy["matrix"]["shard"])):
                raise ValueError("Verification must execute every reviewed bounded shard for its scope")
        elif "strategy" in job:
            raise ValueError("Frontend verification has no reviewed shard matrix")
        if name == "postgres":
            if job.get("env") != {"DOCKER_HOST": "unix:///var/run/docker.sock"}:
                raise ValueError("PostgreSQL job requires only its reviewed local Docker socket")
        elif "env" in job:
            raise ValueError("Frontend and worker settings cannot use job environment or runner context")
        npm_steps = []
        shard_steps = 0
        native_preparation = 0
        image_preparation = 0
        for step in job.get("steps", []):
            if "if" in step or step.get("continue-on-error"):
                raise ValueError("Required checks cannot be bypassed")
            if name == "frontend" and step.get("name") in NPM_STEPS:
                if step.get("env") != NPM_STEP_ENV or step.get("run", "").strip() != NPM_STEPS[step["name"]]:
                    raise ValueError("Reviewed npm steps require exact isolated temporary configurations and commands")
                npm_steps.append(step["name"])
            elif name in SHARD_JOBS and step.get("name") == SHARD_JOBS[name][1]:
                expected_env = WORKER_SHARD_ENV if name == "worker" else POSTGRES_SHARD_ENV
                if step.get("env") != expected_env or step.get("run") != SHARD_JOBS[name][2]:
                    raise ValueError("Shard step must pass only the reviewed static matrix selection and scope command")
                if name == "postgres" and native_preparation != 1:
                    raise ValueError("Owned native SQL wheels must be prepared before required integration")
                if name == "postgres" and image_preparation != 1:
                    raise ValueError("Reviewed fixture images must be prepared before required integration")
                shard_steps += 1
            elif name == "postgres" and step.get("name") == IMAGE_PREP_STEP:
                if step.get("env") != WORKER_SHARD_ENV or step.get("run") != IMAGE_PREP_COMMAND:
                    raise ValueError("Image preparation requires only the reviewed static SQL matrix shard")
                image_preparation += 1
            elif "env" in step:
                raise ValueError("Other steps cannot receive environment settings or credentials")
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
            if name == "postgres" and step.get("name") == NATIVE_WHEELS_PREP_STEP:
                if step.get("run") != NATIVE_WHEELS_PREP_COMMAND:
                    raise ValueError("Native SQL preparation must use the reviewed fresh runner destination")
                native_preparation += 1
        if name == "frontend" and sorted(npm_steps) != sorted(NPM_STEPS):
            raise ValueError("Exactly the reviewed install and lint steps must own npm isolation")
        if name in SHARD_JOBS and shard_steps != 1:
            raise ValueError("Exactly one required step must execute the reviewed scope matrix selection")
        if name == "postgres" and native_preparation != 1:
            raise ValueError("Exactly one owned native SQL wheel preparation step is required")
        if name == "postgres" and image_preparation != 1:
            raise ValueError("Exactly one reviewed fixture image preparation step is required")
    for name, required in REQUIRED_COMMANDS.items():
        commands = {line.strip() for step in jobs[name]["steps"]
                    for line in step.get("run", "").splitlines() if line.strip()}
        if not required <= commands:
            raise ValueError("An advertised required check, locked installation or image boundary is missing")


if __name__ == "__main__":
    validate_workflow(WORKFLOW.read_text())
    print("Dashboard workflow capability and required-gate checks passed")
