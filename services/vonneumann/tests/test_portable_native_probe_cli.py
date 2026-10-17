"""Local CLI file rights only; no timed/native/provider fixture is executed."""
import ast
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import shutil
import tempfile
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'research/run_portable_native_bar_probe.py'
SPEC=importlib.util.spec_from_file_location('owned_native_probe_cli',SOURCE)
driver=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)
OPT_INS={driver.OPT_IN:'1','DASHBOARD_PORTABLE_NATIVE_REAL_BAR_PROBE':'1'}


class PortableNativeProbeCliTests(unittest.TestCase):
    def setUp(self):
        self.anchor=driver._temporary_anchor()
        self.temp=tempfile.TemporaryDirectory(prefix='dashboard-probe-cli-',dir=self.anchor)
        self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name);self.output=self.directory/'result.json'
        self.running=self.directory/'result.running.json'

    def main(self,*,output=None,flags=OPT_INS,maximum='30',action=None):
        result={'accepted':True,'elapsed_seconds':0}
        with patch.dict(os.environ,flags,clear=True),patch('sys.argv',['probe','--output',
            str(self.output) if output is None else output,'--maximum-seconds',maximum]),\
            patch.object(driver,'run',side_effect=action,return_value=result) as run,redirect_stdout(io.StringIO()):
            driver.main()
        return run

    def test_missing_either_opt_in_performs_no_path_io_and_preserves_existing_sibling(self):
        self.running.write_bytes(b'other task original PID record')
        for flags in ({},{driver.OPT_IN:'1'},{'DASHBOARD_PORTABLE_NATIVE_REAL_BAR_PROBE':'1'}):
            with self.subTest(flags=flags),patch.object(driver.os,'open',side_effect=AssertionError('No file operation')):
                with self.assertRaisesRegex(RuntimeError,'opt-ins'):self.main(flags=flags)
            self.assertEqual(self.running.read_bytes(),b'other task original PID record')
            self.assertFalse(self.output.exists())

    def test_invalid_deadline_performs_no_file_operation(self):
        for maximum in ('29','971'):
            with self.subTest(maximum=maximum),patch.object(driver.os,'open',side_effect=AssertionError('No file operation')):
                with self.assertRaises(ValueError):self.main(maximum=maximum)
            self.assertFalse(self.output.exists());self.assertFalse(self.running.exists())

    def test_existing_output_or_pid_is_preserved_and_only_new_reservations_are_removed(self):
        for prior in (self.output,self.running):
            prior.write_bytes(b'other task immutable file')
            with self.assertRaises(driver.ProbeOutputError):self.main()
            self.assertEqual(prior.read_bytes(),b'other task immutable file')
            self.assertFalse((self.running if prior==self.output else self.output).exists())
            prior.unlink()

    def test_symlink_leaves_and_ancestors_are_refused_without_touching_targets(self):
        target=self.directory/'original';target.write_bytes(b'other task original')
        for leaf in (self.output,self.running):
            leaf.symlink_to(target)
            with self.assertRaises(driver.ProbeOutputError):self.main()
            self.assertTrue(leaf.is_symlink());self.assertEqual(target.read_bytes(),b'other task original')
            leaf.unlink()
        alias=self.directory/'alias';alias.symlink_to(self.directory,target_is_directory=True)
        with self.assertRaises(driver.ProbeOutputError):self.main(output=str(alias/'result.json'))
        self.assertFalse(self.output.exists());self.assertFalse(self.running.exists())

    def test_noncanonical_outside_or_shared_nested_parents_are_refused(self):
        outside='/tmp/result.json' if self.anchor==Path('/private/tmp') else '/private/tmp/result.json'
        for output in (str(self.directory/'..'/'result.json'),str(self.directory)+'/./result.json',
            str(self.directory)+'//result.json',outside,'relative.json',str(self.directory/'result.txt')):
            with self.subTest(output=output),self.assertRaises(driver.ProbeOutputError):self.main(output=output)
        self.directory.chmod(0o755)
        try:
            with self.assertRaises(driver.ProbeOutputError):self.main()
            self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode),0o755,'No existing parent is chmodded')
        finally:self.directory.chmod(0o700)

    def test_fixed_platform_selection_ignores_environment_and_tempfile_defaults(self):
        with patch.dict(os.environ,{'TMPDIR':'/untrusted','TMP':'/untrusted','TEMP':'/untrusted'},clear=True),\
            patch.object(tempfile,'gettempdir',side_effect=AssertionError('No default temporary directory')):
            for platform,expected in [('darwin',Path('/private/tmp')),('linux',Path('/tmp'))]:
                with self.subTest(platform=platform),patch.object(driver.sys,'platform',platform):
                    self.assertEqual(driver._temporary_anchor(),expected)

    def test_unknown_platform_refuses_before_any_file_operation(self):
        for platform in ('win32','freebsd14','linux2',''):
            with self.subTest(platform=platform),patch.object(driver.sys,'platform',platform),\
                patch.object(driver.os,'open',side_effect=AssertionError('No file operation')):
                with self.assertRaises(driver.ProbeOutputError):driver._temporary_anchor()
                with self.assertRaises(driver.ProbeOutputError):driver._OwnedProbeOutput(str(self.output))

    def test_success_reserves_exact_private_files_and_removes_only_its_pid(self):
        def action(**kwargs):
            self.assertEqual(kwargs,{'maximum_seconds':30})
            for file in (self.output,self.running):
                value=file.lstat();self.assertTrue(stat.S_ISREG(value.st_mode))
                self.assertEqual(stat.S_IMODE(value.st_mode),0o600);self.assertEqual(value.st_uid,os.geteuid())
            self.assertEqual(json.loads(self.running.read_text())['pid'],os.getpid())
            return {'accepted':True,'elapsed_seconds':0}
        run=self.main(action=action);self.assertEqual(run.call_count,1)
        self.assertTrue(json.loads(self.output.read_text())['accepted']);self.assertFalse(self.running.exists())
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode),0o600)

    def test_run_failure_cleans_only_files_this_invocation_created(self):
        failure=RuntimeError('synthetic run refusal')
        with self.assertRaisesRegex(RuntimeError,'synthetic run refusal'):self.main(action=failure)
        self.assertFalse(self.output.exists());self.assertFalse(self.running.exists())

    def test_replaced_output_or_pid_inode_is_never_deleted(self):
        for leaf in (self.output,self.running):
            def action(**_):
                replacement=self.directory/'replacement';replacement.write_bytes(b'other task replacement')
                os.replace(replacement,leaf)
                raise RuntimeError('synthetic refusal after replacement')
            with self.subTest(leaf=leaf.name),self.assertRaises(driver.ProbeOutputError):self.main(action=action)
            self.assertEqual(leaf.read_bytes(),b'other task replacement')
            self.assertFalse((self.running if leaf==self.output else self.output).exists())
            leaf.unlink()

    def test_parent_replacement_cannot_publish_or_cleanup_the_new_directory(self):
        retired=self.directory.with_name(self.directory.name+'-original')
        self.addCleanup(lambda: shutil.rmtree(retired,ignore_errors=True))
        def action(**_):
            self.directory.rename(retired);self.directory.mkdir(mode=0o700)
            self.output.write_bytes(b'other task output');self.running.write_bytes(b'other task PID')
            return {'accepted':True,'elapsed_seconds':0}
        with self.assertRaises(driver.ProbeOutputError):self.main(action=action)
        self.assertEqual(self.output.read_bytes(),b'other task output');self.assertEqual(self.running.read_bytes(),b'other task PID')
        self.assertFalse((retired/'result.json').exists());self.assertFalse((retired/'result.running.json').exists())

    def test_post_publish_output_or_pid_replacement_refuses_success_and_preserves_replacement(self):
        original=driver._OwnedProbeOutput.publish
        for leaf in (self.output,self.running):
            def publish(owned,result):
                original(owned,result)
                replacement=self.directory/'replacement';replacement.write_bytes(b'other task published-edge replacement')
                os.replace(replacement,leaf)
            with patch.object(driver._OwnedProbeOutput,'publish',publish),self.subTest(leaf=leaf.name),self.assertRaises(driver.ProbeOutputError):
                self.main()
            self.assertEqual(leaf.read_bytes(),b'other task published-edge replacement')
            for file in (self.output,self.running):file.unlink(missing_ok=True)

    def test_post_publish_parent_replacement_refuses_success_without_touching_new_parent(self):
        retired=self.directory.with_name(self.directory.name+'-published')
        self.addCleanup(lambda: shutil.rmtree(retired,ignore_errors=True))
        original=driver._OwnedProbeOutput.publish
        def publish(owned,result):
            original(owned,result);self.directory.rename(retired);self.directory.mkdir(mode=0o700)
            self.output.write_bytes(b'other task output');self.running.write_bytes(b'other task PID')
        with patch.object(driver._OwnedProbeOutput,'publish',publish),self.assertRaises(driver.ProbeOutputError):self.main()
        self.assertEqual(self.output.read_bytes(),b'other task output');self.assertEqual(self.running.read_bytes(),b'other task PID')
        self.assertTrue(json.loads((retired/'result.json').read_text())['accepted'])
        self.assertFalse((retired/'result.running.json').exists())

    def test_changed_mode_refuses_publication_without_chmodding_an_existing_object(self):
        def action(**_):
            self.output.chmod(0o644)
            return {'accepted':True,'elapsed_seconds':0}
        with self.assertRaises(driver.ProbeOutputError):self.main(action=action)
        self.assertFalse(self.output.exists());self.assertFalse(self.running.exists())

    def test_timed_run_kernel_remains_the_original_accepted_source(self):
        source=SOURCE.read_text();node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='run')
        # Exact function bytes from the accepted frozen52a4929 source. CLI
        # ownership changes do not create a new timed/SQL acceptance claim.
        self.assertEqual(hashlib.sha256(ast.get_source_segment(source,node).encode()).hexdigest(),
            '25153c91f462114c6caf73518cf8adf6db925fb03c6ab387b8a575ae752e557e')


if __name__=='__main__':unittest.main()
