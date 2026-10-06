"""Explicit local opt-in for real Linux/TLS/SCRAM driver acceptance."""
import os
import sys
import unittest
from tests.postgres import harness, session_auth_fixture
from tests.postgres.native_sql_fixture import NativeDriverContainer


class NativeSQLIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get(harness.OPT_IN)!='1':
            raise unittest.SkipTest('Explicit isolated PostgreSQL opt-in required')
        cls.db=session_auth_fixture.start(cls)
        cls.driver=NativeDriverContainer(cls.db)
        cls.addClassCleanup(cls.driver.close)
        cls.driver.start()

    def test_real_driver_controller_and_fault_acceptance(self):
        result=self.driver.run()
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        self.assertIn('Ran 8 tests',result.stderr)
        sys.stderr.write(result.stderr)
