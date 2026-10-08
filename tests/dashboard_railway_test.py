"""Offline checks for project scoping and secret-safe identity verification."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('dashboard_railway',Path(__file__).parents[1]/'scripts/dashboard-railway.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)

class RailwayIdentityTests(unittest.TestCase):
 def test_scoped_token_is_verified_before_project_metadata(self):
  calls=[]
  def execute(token,document,variables=None):
   calls.append((document,variables));self.assertEqual(token,'synthetic-private-token')
   if len(calls)==1:return {'projectToken':{'projectId':helper.PROJECT,'environmentId':helper.ENVIRONMENT}}
   return {'project':{'id':helper.PROJECT,'name':helper.PROJECT_NAME,'workspaceId':helper.WORKSPACE,
    'deletedAt':None,'workspace':{'name':helper.WORKSPACE_NAME}}}
  result=helper.verify('synthetic-private-token',execute)
  self.assertEqual(len(calls),2);self.assertEqual(calls[1][1],{'id':helper.PROJECT})
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
    return {'projectToken':{'projectId':helper.PROJECT,'environmentId':helper.ENVIRONMENT}} if variables is None else {'project':project}
   with self.assertRaisesRegex(helper.Refused,'identity mismatch'):helper.verify('synthetic',execute)
 def test_duplicate_metadata_keys_are_refused(self):
  with self.assertRaises(helper.Refused):helper.unique([('project','allowed'),('project','other')])

if __name__=='__main__':unittest.main()
