"""Offline checks for project scoping and secret-safe identity verification."""
import importlib.util
from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('dashboard_railway',Path(__file__).parents[1]/'scripts/dashboard-railway.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)

def project_metadata():
 return {'project':{'id':helper.PROJECT,'name':helper.PROJECT_NAME,'workspaceId':helper.WORKSPACE,
  'deletedAt':None,'workspace':{'name':helper.WORKSPACE_NAME}},
  'environment':{'id':helper.ENVIRONMENT,'name':'production','projectId':helper.PROJECT}}

class RailwayIdentityTests(unittest.TestCase):
 def test_scoped_token_is_verified_before_project_metadata(self):
  calls=[]
  def execute(token,document,variables=None):
   calls.append((document,variables));self.assertEqual(token,'synthetic-private-token')
   if len(calls)==1:return {'projectToken':{'projectId':helper.PROJECT,'environmentId':helper.ENVIRONMENT}}
   return project_metadata()
  result=helper.verify('synthetic-private-token',execute)
  self.assertEqual(len(calls),2);self.assertEqual(calls[1][1],{'id':helper.PROJECT,'environment':helper.ENVIRONMENT})
  self.assertNotIn('synthetic-private-token',str(result))
 def test_wrong_token_scope_stops_before_any_project_read(self):
  for field in ('projectId','environmentId'):
   calls=[];value={'projectId':helper.PROJECT,'environmentId':helper.ENVIRONMENT};value[field]='another-project'
   def execute(*args):calls.append(args);return {'projectToken':value}
   with self.assertRaisesRegex(helper.Refused,'token mismatch'):helper.verify('synthetic',execute)
   self.assertEqual(len(calls),1)
 def test_wrong_name_owner_or_deleted_project_is_refused(self):
  for field in ('id','name','workspaceId','deletedAt'):
   project={'id':helper.PROJECT,'name':helper.PROJECT_NAME,'workspaceId':helper.WORKSPACE,'deletedAt':None,'workspace':{'name':helper.WORKSPACE_NAME}}
   project[field]='mismatch'
   def execute(token,document,variables=None):
    return {'projectToken':{'projectId':helper.PROJECT,'environmentId':helper.ENVIRONMENT}} if variables is None else {**project_metadata(),'project':project}
   with self.assertRaisesRegex(helper.Refused,'identity mismatch'):helper.verify('synthetic',execute)
 def test_duplicate_metadata_keys_are_refused(self):
  with self.assertRaises(helper.Refused):helper.unique([('project','allowed'),('project','other')])

 def test_actual_environment_name_and_parent_are_checked(self):
  for field in ('id','name','projectId'):
   result=project_metadata();result['environment'][field]='mismatch'
   def execute(token,document,variables=None):
    return {'projectToken':{'projectId':helper.PROJECT,'environmentId':helper.ENVIRONMENT}} if variables is None else result
   with self.assertRaisesRegex(helper.Refused,'environment identity mismatch'):helper.verify('synthetic',execute)

 def test_application_header_and_bounded_response_without_secret_diagnostics(self):
  class Response:
   status=200
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,limit):
    self.assert_limit=limit
    return b'{"data":{"projectToken":{}}}'
  response=Response();requests=[]
  class Opener:
   def open(self,request,timeout):requests.append((request,timeout));return response
  with patch.object(helper.urllib.request,'build_opener',return_value=Opener()):
   helper.query('synthetic-private-token','query{projectToken{id}}')
  self.assertEqual(response.assert_limit,65537)
  self.assertEqual(requests[0][0].get_header('User-agent'),'TheDashboard-Identity/1.0')
  self.assertEqual(requests[0][1],10)
  class FailingOpener:
   def open(self,*args,**kwargs):raise ValueError('synthetic-private-token')
  with patch.object(helper.urllib.request,'build_opener',return_value=FailingOpener()):
   with self.assertRaises(helper.Refused) as error:helper.query('synthetic-private-token','query{projectToken{id}}')
  self.assertNotIn('synthetic-private-token',str(error.exception))

 def test_service_target_and_required_settings_fail_closed(self):
  good={'service':{'id':helper.SERVICE,'name':helper.SERVICE_NAME,'projectId':helper.PROJECT},
   'serviceInstance':{'serviceId':helper.SERVICE,'environmentId':helper.ENVIRONMENT,
    'serviceName':helper.SERVICE_NAME,'numReplicas':1,'sleepApplication':False,'restartPolicyType':'NEVER',
    'overlapSeconds':0,'drainingSeconds':30,'healthcheckPath':'/health','healthcheckTimeout':60,
    'ipv6EgressEnabled':True,'latestDeployment':None},
   'serviceInstanceLimits':{'containers':{'cpu':0.25,'memoryBytes':500000000}}}
  def execute(token,document,variables=None):
   if variables is None:return {'projectToken':{'projectId':helper.PROJECT,'environmentId':helper.ENVIRONMENT}}
   return good if 'service' in variables else project_metadata()
  self.assertEqual(helper.verify_service('synthetic',execute)['resource_limits']['vcpus'],0.25)
  for section,field in [('service','projectId'),('service','id'),('serviceInstance','environmentId'),
                        ('serviceInstance','numReplicas'),('serviceInstance','ipv6EgressEnabled')]:
   old=good[section][field];good[section][field]='mismatch'
   with self.assertRaises(helper.Refused):helper.verify_service('synthetic',execute)
   good[section][field]=old

class WorkerExportTests(unittest.TestCase):
 def test_export_excludes_operator_files_and_normalizes_nonroot_modes_under_strict_umask(self):
  commit='a'*40
  paths=['Dockerfile','.dockerignore','requirements.txt','start-worker.sh','railway.json',
   'tools/native_tls_preflight.py','tools/native_session_canary.py','tools/provider_read_canary.py',
   'tools/paper_controller_canary.py',
   'vonneumann/server/paper_app.py','ssl/private.pem','.env',
   'tests/test_app.py','.claude/settings.json','vonneumann/__pycache__/app.pyc']
  def read(args):
   if args[0]=='rev-parse':return (commit+'\n').encode()
   if args[0]=='ls-tree':return ('\n'.join('services/vonneumann/'+p for p in paths)+'\n').encode()
   return b'public source fixture\n'
  with tempfile.TemporaryDirectory(prefix='dashboard-railway-worker-test-') as parent:
   staging=Path(parent).resolve();dest=staging/'dashboard-railway-worker-export';old=os.umask(0o077)
   def fixture_path(value):return staging if value=='/private/tmp' else Path(value)
   try:
    with patch.object(helper,'Path',side_effect=fixture_path):result=helper.export_worker(commit,dest,read)
    self.assertEqual(result['files'],10)
    self.assertEqual(dest.stat().st_mode & 0o777,0o700)
    self.assertEqual((dest/'vonneumann/server').stat().st_mode & 0o777,0o755)
    self.assertEqual((dest/'vonneumann/server/paper_app.py').stat().st_mode & 0o777,0o644)
    self.assertEqual((dest/'start-worker.sh').stat().st_mode & 0o777,0o555)
    self.assertEqual((dest/'tools/paper_controller_canary.py').stat().st_mode & 0o777,0o644)
    self.assertFalse((dest/'.env').exists());self.assertFalse((dest/'ssl').exists())
    with patch.object(helper,'Path',side_effect=fixture_path),self.assertRaises(helper.Refused):helper.export_worker(commit,dest,read)
   finally:
    os.umask(old)

 def test_missing_controller_canary_is_refused_before_blob_reads_or_destination_creation(self):
  commit='a'*40
  paths=['Dockerfile','.dockerignore','requirements.txt','start-worker.sh','railway.json',
   'tools/native_tls_preflight.py','tools/native_session_canary.py','tools/provider_read_canary.py',
   'vonneumann/server/paper_app.py']
  def read(args):
   if args[0]=='rev-parse':return (commit+'\n').encode()
   if args[0]=='ls-tree':return ('\n'.join('services/vonneumann/'+p for p in paths)+'\n').encode()
   self.fail('Incomplete source must be refused before reading any blobs')
  with tempfile.TemporaryDirectory(prefix='dashboard-railway-worker-test-') as parent:
   staging=Path(parent).resolve();dest=staging/'dashboard-railway-worker-export'
   def fixture_path(value):return staging if value=='/private/tmp' else Path(value)
   with patch.object(helper,'Path',side_effect=fixture_path),self.assertRaisesRegex(helper.Refused,'Incomplete worker source export'):
    helper.export_worker(commit,dest,read)
   self.assertFalse(dest.exists())

 def test_export_rejects_unpinned_source_or_shared_destination_before_reads(self):
  def read(args):self.fail('Invalid export must not read source')
  for commit,dest in [('main','/private/tmp/dashboard-railway-worker-test'),
                      ('a'*40,'/Users/redjester/.railway'),('a'*40,'/private/tmp/unrelated')]:
   with self.assertRaises(helper.Refused):helper.export_worker(commit,dest,read)

if __name__=='__main__':unittest.main()
