import json
import unittest
from tests.postgres import forward_fixture as fixture

class ForwardPackageTests(unittest.TestCase):
 def test_artifacts_reproduce_with_all_component_digests(self):
  sql,manifest=fixture.package()
  self.assertEqual(fixture.builder.sha(sql),manifest['package_sha256'])
  self.assertEqual(len(manifest['functions']),97);self.assertEqual(len(manifest['tables']),26)
  self.assertEqual(manifest['installed_admission'],'closed')
  self.assertFalse(manifest['production_application_available'])
 def test_economic_guard_inventory_excludes_readback_relay_and_interruption(self):
  _,manifest=fixture.package()
  self.assertEqual(manifest['release_guarded_functions'],[
   'vn_durability.commit_command','vn_durability.create_run','vn_durability.heartbeat'])
  self.assertEqual(len(manifest['dependencies_sha256']),20)
