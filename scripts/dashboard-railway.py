#!/usr/bin/env python3
"""Read-only Railway identity checks and a secret-free local worker export.

No shared CLI configuration, account token, credential output or mutation API.
References: https://docs.railway.com/integrations/api and Railway CLI queries.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import hashlib
import re
import stat
import subprocess
import sys
import urllib.request

ROOT = Path('/Users/redjester/Projects/Next/TheDashboard')
TOKEN_FILE = ROOT / 'ssl/railway-project-token.txt'
ENDPOINT = 'https://backboard.railway.com/graphql/v2'
PROJECT = '38facb49-4de9-4d66-85aa-2861e0306dcf'
ENVIRONMENT = '9bbe52c6-2305-467a-bf39-8d5e1a98e4e4'
WORKSPACE = 'f3fcd4b2-e424-4c6b-ac33-91196ccc96e1'
PROJECT_NAME = 'The Dashboard Worker'
WORKSPACE_NAME = "Red Jester's Projects"
SERVICE = '8e78ad4b-1d8f-43e7-898a-3882ac5053d7'
SERVICE_NAME = 'dashboard-paper-worker'

class Refused(RuntimeError): pass

def token():
    # Open without following links; inspect the opened descriptor, not an earlier
    # path stat. Parent directory links are also refused.
    if ROOT.resolve() != ROOT or TOKEN_FILE.parent.is_symlink():
        raise Refused('Dashboard token path is not isolated')
    try:
        fd = os.open(TOKEN_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as source:
            info = os.fstat(source.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 4096):
                raise Refused('Dashboard project token must be an owned mode-0600 regular file')
            raw = source.read(4097)
    except OSError:
        raise Refused('Dashboard project token unavailable at the documented private path') from None
    try: value = raw.decode('ascii').strip()
    except UnicodeError: raise Refused('Invalid Dashboard project token format') from None
    if not 16 <= len(value) <= 2048 or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in value):
        raise Refused('Invalid Dashboard project token format')
    return value

def unique(items):
    result = {}
    for key, value in items:
        if key in result: raise Refused('Invalid Railway metadata response')
        result[key] = value
    return result

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None

def query(project_token, document, variables=None):
    request = urllib.request.Request(ENDPOINT, data=json.dumps({
        'query': document, 'variables': variables or {}}).encode('utf-8'),
        headers={'Project-Access-Token': project_token, 'Content-Type': 'application/json',
                 'User-Agent': 'TheDashboard-Identity/1.0'}, method='POST')
    # Do not inherit another project's proxy configuration or follow a redirect
    # with the project credential. Never include provider error text in output.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=10) as response:
            if response.status != 200: raise ValueError()
            raw = response.read(65537)
        if len(raw) > 65536: raise ValueError()
        data = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
        if not isinstance(data, dict) or data.get('errors') or not isinstance(data.get('data'), dict):
            raise ValueError()
        return data['data']
    except Exception:
        raise Refused('Railway metadata request failed; raw response suppressed') from None

def verify(project_token, execute=query):
    scoped = execute(project_token, 'query { projectToken { projectId environmentId } }').get('projectToken')
    if not isinstance(scoped, dict) or (scoped.get('projectId'), scoped.get('environmentId')) != (PROJECT, ENVIRONMENT):
        raise Refused('Railway project/environment token mismatch')
    # Resolve only the authorized project, never enumerate other project contents.
    result = execute(project_token,
        'query DashboardProject($id:String!,$environment:String!) { project(id:$id) { id name workspaceId deletedAt workspace { name } } environment(id:$environment,projectId:$id) { id name projectId } }',
        {'id': PROJECT, 'environment': ENVIRONMENT})
    if not isinstance(result, dict):
        raise Refused('Railway Dashboard metadata response mismatch')
    environment = result.get('environment')
    result = result.get('project')
    if not isinstance(result, dict) or not isinstance(result.get('workspace'), dict) or (
        result.get('id'), result.get('name'), result.get('workspaceId'), result.get('deletedAt'), result['workspace'].get('name')) != (
            PROJECT, PROJECT_NAME, WORKSPACE, None, WORKSPACE_NAME):
        raise Refused('Railway Dashboard project/workspace identity mismatch')
    if environment != {'id': ENVIRONMENT, 'name': 'production', 'projectId': PROJECT}:
        raise Refused('Railway production environment identity mismatch')
    return {'project': {'id': PROJECT, 'name': PROJECT_NAME},
        'environment': {'id': ENVIRONMENT, 'name': 'production'},
        'workspace': {'id': WORKSPACE, 'name': WORKSPACE_NAME},
        'verified': 'project/environment token and exact project/workspace metadata',
        'operations': 'read-only; no service, variables, deployment or billing changes'}

def verify_service(project_token, execute=query):
    result = verify(project_token, execute)
    value = execute(project_token,
        'query DashboardService($service:String!,$environment:String!) { service(id:$service) { id name projectId } serviceInstance(serviceId:$service,environmentId:$environment) { serviceId environmentId serviceName numReplicas sleepApplication restartPolicyType overlapSeconds drainingSeconds healthcheckPath healthcheckTimeout ipv6EgressEnabled latestDeployment { id status } } serviceInstanceLimits(serviceId:$service,environmentId:$environment) }',
        {'service': SERVICE, 'environment': ENVIRONMENT})
    if not isinstance(value, dict):
        raise Refused('Railway Dashboard service metadata mismatch')
    expected = {'serviceId': SERVICE, 'environmentId': ENVIRONMENT,
        'serviceName': SERVICE_NAME, 'numReplicas': 1, 'sleepApplication': False,
        'restartPolicyType': 'NEVER', 'overlapSeconds': 0, 'drainingSeconds': 30,
        'healthcheckPath': '/health', 'healthcheckTimeout': 60, 'ipv6EgressEnabled': True}
    if value.get('service') != {'id': SERVICE, 'name': SERVICE_NAME, 'projectId': PROJECT}:
        raise Refused('Railway Dashboard service identity mismatch')
    instance = value.get('serviceInstance')
    if not isinstance(instance, dict) or any(
        type(instance.get(k)) is not type(v) or instance.get(k) != v for k, v in expected.items()):
        raise Refused('Railway Dashboard service settings mismatch')
    resource = value.get('serviceInstanceLimits')
    limits = resource.get('containers') if isinstance(resource, dict) else None
    if not isinstance(limits, dict) or limits.get('cpu') != 0.25 or limits.get('memoryBytes') != 500000000:
        raise Refused('Railway Dashboard resource limits mismatch')
    result['service'] = instance
    result['resource_limits'] = {'vcpus': 0.25, 'memory_bytes': 500000000}
    result['acceptance'] = 'settings only; deployed region/image, mode, TLS/auth and pilot need separate evidence'
    return result

def git_read(arguments):
    try:
        result = subprocess.run(['git', *arguments], cwd=ROOT, capture_output=True,
                                timeout=15, check=False)
        if result.returncode: raise ValueError()
        return result.stdout
    except Exception:
        raise Refused('Dashboard immutable worker source unavailable') from None

def export_worker(commit, destination, read=git_read):
    """Only immutable allowlisted source; normalize modes for non-root Docker COPY.

    This does not upload, prove review approval, or include operator credentials.
    The caller must verify the remote target and chosen source before deployment.
    """
    if not isinstance(commit, str) or re.fullmatch(r'[a-f0-9]{40}', commit) is None:
        raise Refused('Use an explicit full Dashboard source commit')
    destination = Path(destination)
    if (destination.parent != Path('/private/tmp') or destination.parent.resolve() != destination.parent
        or re.fullmatch(r'dashboard-railway-worker-[a-z0-9-]+', destination.name) is None
        or destination.exists() or destination.is_symlink()):
        raise Refused('Use a new isolated Dashboard worker directory under /private/tmp')
    if read(['rev-parse', commit + '^{commit}']).decode('ascii').strip() != commit:
        raise Refused('Dashboard source commit mismatch')
    paths = read(['ls-tree', '-r', '--name-only', commit, '--', 'services/vonneumann']).decode('utf-8').splitlines()
    prefix = 'services/vonneumann/'
    required = {'Dockerfile', '.dockerignore', 'requirements.txt', 'start-worker.sh',
                'railway.json', 'tools/native_tls_preflight.py', 'tools/native_session_canary.py',
                'tools/provider_read_canary.py', 'tools/paper_controller_canary.py'}
    selected = []
    for path in paths:
        if not path.startswith(prefix): raise Refused('Unexpected worker source path')
        relative = path[len(prefix):]
        if relative in required or (relative.startswith('vonneumann/') and relative.endswith('.py')):
            parts = Path(relative).parts
            if any(part in ('..', '.', '__pycache__', '.env', 'ssl') for part in parts):
                raise Refused('Unsafe worker source path')
            selected.append((path, relative))
    if not required.issubset({relative for _, relative in selected}):
        raise Refused('Incomplete worker source export')
    # Read all blobs before creating anything. Even tracked symlinks are exported
    # as ordinary byte files, never followed into environment/credential files.
    blobs = [(relative, read(['show', commit + ':' + path])) for path, relative in selected]
    destination.mkdir(mode=0o700)
    os.chmod(destination, 0o700)
    manifest = []
    for relative, data in blobs:
        target = destination / relative
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        # pathlib's intermediate parents honor umask; explicitly normalize all
        # exported child directories without opening the private staging root.
        parent = target.parent
        while parent != destination:
            os.chmod(parent, 0o755)
            parent = parent.parent
        target.write_bytes(data)
        mode = 0o555 if relative == 'start-worker.sh' else 0o644
        os.chmod(target, mode)
        manifest.append({'path': relative, 'sha256': hashlib.sha256(data).hexdigest(),
                         'bytes': len(data), 'mode': oct(mode)})
    encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
    return {'source_sha': commit, 'directory': str(destination), 'files': len(manifest),
        'bytes': sum(item['bytes'] for item in manifest),
        'manifest_sha256': hashlib.sha256(encoded).hexdigest(),
        'credentials_included': False, 'remote_operations': False}

def main():
    arguments = sys.argv[1:]
    if Path.cwd() != ROOT: raise Refused('Use the exact Dashboard repository')
    if arguments == ['verify']: result = verify(token())
    elif arguments == ['service']: result = verify_service(token())
    elif len(arguments) == 3 and arguments[0] == 'export-worker':
        result = export_worker(arguments[1], arguments[2])
    else: raise Refused('Use verify, service, or export-worker COMMIT NEW_DIRECTORY')
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    try: main()
    except Refused as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
