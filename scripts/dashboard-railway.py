#!/usr/bin/env python3
"""Read-only Railway identity check using one private project/environment token.

No shared CLI configuration, account token, credential output or mutation API.
References: https://docs.railway.com/integrations/api and Railway CLI queries.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import stat
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
        headers={'Project-Access-Token': project_token, 'Content-Type': 'application/json'}, method='POST')
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
        'query DashboardProject($id:String!) { project(id:$id) { id name workspaceId deletedAt workspace { name } } }',
        {'id': PROJECT}).get('project')
    if not isinstance(result, dict) or not isinstance(result.get('workspace'), dict) or (
        result.get('id'), result.get('name'), result.get('workspaceId'), result.get('deletedAt'), result['workspace'].get('name')) != (
            PROJECT, PROJECT_NAME, WORKSPACE, None, WORKSPACE_NAME):
        raise Refused('Railway Dashboard project/workspace identity mismatch')
    return {'project': {'id': PROJECT, 'name': PROJECT_NAME},
        'environment': {'id': ENVIRONMENT, 'name': 'production'},
        'workspace': {'id': WORKSPACE, 'name': WORKSPACE_NAME},
        'verified': 'project/environment token and exact project/workspace metadata',
        'operations': 'read-only; no service, variables, deployment or billing changes'}

def main():
    if sys.argv[1:] != ['verify'] or Path.cwd() != ROOT:
        raise Refused('Use verify from the exact Dashboard repository')
    print(json.dumps(verify(token()), ensure_ascii=False))

if __name__ == '__main__':
    try: main()
    except Refused as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
