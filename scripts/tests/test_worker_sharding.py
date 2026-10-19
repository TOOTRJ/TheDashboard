"""Exhaustive bounded selection, source guards and original fixture semantics."""
from collections import Counter
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dashboard_worker_sharding', SCRIPTS / 'check-worker.py')
worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)


def cases(module, names=('test_one', 'test_two')):
    cls = type('SyntheticCase', (unittest.TestCase,), {
        '__module__': module, **{name: lambda self: None for name in names},
    })
    return [cls(name) for name in names]


class WorkerShardingTests(unittest.TestCase):
    def source_fixture(self):
        return patch.object(worker, 'test_source', side_effect=lambda test:
                            ('reviewed/' + test.__class__.__module__ + '.py', '0' * 64))

    def test_deterministic_exhaustive_partition_preserves_alias_occurrences_and_order(self):
        one = cases('tests.test_provider_ga_components')
        two = cases('tests.test_portable_ga_model')
        new = cases('tests.test_future_added_module')
        third = cases('tests.test_source_admission_v3')
        original = one + two + [one[0]] + new + third
        with self.source_fixture():
            tests, shards, coverage = worker.partition_offline(unittest.TestSuite(original))
            again = worker.partition_offline(unittest.TestSuite(original))
        self.assertEqual(tests, tuple(original))
        self.assertEqual((shards, coverage), again[1:])
        self.assertEqual(coverage['baseline_repeated_ids'], 1)
        self.assertEqual(sum(len(indices) for indices in shards.values()), len(original))
        selected = Counter(tests[index].id() for indices in shards.values() for index in indices)
        self.assertEqual(selected, Counter(test.id() for test in original))
        self.assertTrue(all(index in shards[worker.module_shard('tests.test_future_added_module')]
                            for index in range(5, 7)))
        self.assertEqual(coverage['runtime'], 'CPython 3.12.14')
        self.assertEqual(coverage['declared_shards'], [1, 2, 3])
        self.assertEqual(set(shards), {1, 2, 3})
        self.assertEqual(shards[3], (7, 8))
        self.assertEqual(len(coverage['selection_source_sha256']), 64)

    def test_only_model_and_source_move_to_third_shard_with_original_alias_fixture_segments(self):
        model_name = 'tests.test_prospective_ga_v3_model'
        source_name = 'tests.test_source_admission_v3'
        provider_name = 'tests.test_provider_ga_components'
        portable_name = 'tests.test_portable_ga_model'
        self.assertEqual(worker.module_shard(model_name), 3)
        self.assertEqual(worker.module_shard(source_name), 3)
        events = []
        modules = [ModuleType(name) for name in (model_name, source_name, provider_name, portable_name)]
        by_module = []
        for module in modules:
            label = module.__name__
            module.setUpModule = lambda label=label: events.append((label, 'module setup'))
            module.tearDownModule = lambda label=label: events.append((label, 'module teardown'))
            cls = type('ProspectiveFixtureCase', (unittest.TestCase,), {
                '__module__': label,
                'setUpClass': classmethod(lambda cls, label=label: events.append((label, 'class setup'))),
                'tearDownClass': classmethod(lambda cls, label=label: events.append((label, 'class teardown'))),
                'test_first': lambda self, label=label: events.append((label, 'first')),
                'test_last': lambda self, label=label: events.append((label, 'last')),
            })
            by_module.append((cls('test_first'), cls('test_last')))
        model, source, provider, portable = by_module
        original = (model[0], source[0], provider[0], model[1], model[0], portable[0], source[1], source[0])
        with self.source_fixture():
            tests, shards, coverage = worker.partition_offline(unittest.TestSuite(original))
        self.assertEqual(shards, {1: (2,), 2: (5,), 3: (0, 1, 3, 4, 6, 7)})
        self.assertEqual(coverage['baseline_repeated_ids'], 2)
        self.assertEqual(Counter(tests[i].id() for indices in shards.values() for i in indices),
                         Counter(case.id() for case in original))
        self.assertEqual(coverage['declared_shards'], [1, 2, 3])
        with patch.dict(sys.modules, {module.__name__: module for module in modules}):
            baseline = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.TestSuite(original))
            self.assertTrue(baseline.wasSuccessful())
            original_events = tuple(events)
            for shard, selected_modules in ((1, {provider_name}), (2, {portable_name}),
                                            (3, {model_name, source_name})):
                events.clear()
                result = unittest.TextTestRunner(stream=io.StringIO()).run(worker.selected_suite(tests, shards[shard]))
                self.assertTrue(result.wasSuccessful())
                self.assertEqual(tuple(events), tuple(event for event in original_events if event[0] in selected_modules))
                for module in selected_modules:
                    self.assertEqual(sum(event == (module, 'class setup') for event in events),
                                     2 if shard == 3 else 1)

    def test_every_unanchored_source_module_retains_the_original_two_way_fallback(self):
        self.assertEqual(worker.OFFLINE_SHARDS, (1, 2, 3))
        self.assertEqual(worker.OFFLINE_FALLBACK_SHARD_COUNT, 2)
        expected_hints = {
            'tests.test_prospective_ga_v3_model': 3,
            'tests.test_source_admission_v3': 3,
            'tests.test_provider_ga_components': 1,
            'tests.test_portable_ga_model': 2,
            'tests.test_ga_active_model': 2,
            'tests.test_partitioned_checkpoint': 2,
        }
        self.assertEqual(worker.HEAVY_MODULE_SHARDS, expected_hints)
        modules = {f'tests.test_future_unanchored_{index}' for index in range(500)}
        modules.update('tests.' + '.'.join(path.relative_to(worker.WORKER / 'tests').with_suffix('').parts)
                       for path in (worker.WORKER / 'tests').rglob('test_*.py'))
        modules.update(path.stem for directory, pattern in
                       ((worker.ROOT / 'scripts/tests', 'test_*.py'), (worker.ROOT / 'tests', '*_test.py'))
                       for path in directory.glob(pattern))
        for module in sorted(modules - expected_hints.keys()):
            expected = 1 + int.from_bytes(hashlib.sha256(module.encode()).digest(), 'big') % 2
            with self.subTest(module=module):
                self.assertEqual(worker.module_shard(module), expected)
                self.assertIn(worker.module_shard(module), (1, 2))

    def test_partition_rejects_omissions_duplicates_invented_members_split_modules_and_reordering(self):
        tests = (cases('tests.test_provider_ga_components') + cases('tests.test_portable_ga_model')
                 + cases('tests.test_prospective_ga_v3_model'))
        valid = {1: (0, 1), 2: (2, 3), 3: (4, 5)}
        worker.validate_partition(tests, valid)
        invalid = ({**valid, 1: (0,)}, {**valid, 1: (0, 1, 1)},
                   {**valid, 2: (2, 3, 6)}, {**valid, 1: (0, 2), 2: (1, 3)},
                   {**valid, 1: (1, 0)}, {**valid, 2: ()}, {**valid, 3: ()},
                   {**valid, 1: (False, 1)}, {1: (0, 1), 2: (2, 3)},
                   {**valid, 4: ()}, {**valid, '3': valid[3]})
        for shards in invalid:
            with self.subTest(shards=shards), self.assertRaises(RuntimeError):
                worker.validate_partition(tests, shards)

    def test_source_or_case_change_changes_coverage_fingerprint(self):
        original = (cases('tests.test_provider_ga_components') + cases('tests.test_portable_ga_model')
                    + cases('tests.test_source_admission_v3'))
        with self.source_fixture():
            first = worker.partition_offline(unittest.TestSuite(original))[2]
            changed = worker.partition_offline(unittest.TestSuite(original + [original[0]]))[2]
        with patch.object(worker, 'test_source', return_value=('reviewed/new.py', '1' * 64)):
            source = worker.partition_offline(unittest.TestSuite(original))[2]
        self.assertNotEqual(first['discovery_source_sha256'], changed['discovery_source_sha256'])
        self.assertNotEqual(first['discovery_source_sha256'], source['discovery_source_sha256'])

    def test_discovery_errors_fail_before_any_selection_or_test_execution(self):
        loader = unittest.TestLoader(); loader.errors = ['synthetic import failure']
        with patch.object(worker.sys, 'path', list(sys.path)), patch.object(worker.unittest, 'TestLoader', return_value=loader):
            with patch.object(loader, 'discover', return_value=unittest.TestSuite()):
                with self.assertRaisesRegex(RuntimeError, 'discovery failed before selection'):
                    worker.discover_suite('offline')
        with self.assertRaises(RuntimeError): tuple(worker.flatten_tests(object()))

    def test_sources_must_be_regular_files_under_only_the_reviewed_test_roots(self):
        with tempfile.TemporaryDirectory(prefix='dashboard-shard-sources-') as directory:
            root = Path(directory).resolve(); worker_root = root / 'services/vonneumann'
            public = worker_root / 'tests/test_synthetic.py'; public.parent.mkdir(parents=True)
            public.write_text('# public source fixture\n')
            private = root / 'ssl/never-read.py'; private.parent.mkdir(); private.write_text('# synthetic private input\n')
            undiscovered = public.with_name('source_support.py'); undiscovered.write_text('# public unselected fixture\n')
            nested_private = public.parent / 'ssl/test_private.py'; nested_private.parent.mkdir(); nested_private.write_text('# synthetic private input\n')
            symlink = public.with_name('test_link.py'); symlink.symlink_to(public)
            module = ModuleType('tests.test_synthetic_source'); case = cases(module.__name__)[0]
            with patch.object(worker, 'ROOT', root), patch.object(worker, 'WORKER', worker_root), patch.dict(sys.modules, {module.__name__: module}):
                module.__file__ = str(public)
                path, digest = worker.test_source(case)
                self.assertEqual(path, 'services/vonneumann/tests/test_synthetic.py')
                self.assertEqual(len(digest), 64)
                for source in (private, nested_private, undiscovered, symlink, root / 'missing.py'):
                    module.__file__ = str(source)
                    with self.subTest(source=source), self.assertRaises(RuntimeError): worker.test_source(case)
                del module.__file__
                with self.assertRaises(RuntimeError): worker.test_source(case)

    def test_module_and_class_fixtures_keep_original_alias_segment_boundaries(self):
        def run(sharded):
            events = []
            modules = [ModuleType(name) for name in ('tests.test_provider_ga_components', 'tests.test_portable_ga_model')]
            all_cases = []
            for module in modules:
                label = module.__name__
                module.setUpModule = lambda label=label: events.append((label, 'module setup'))
                module.tearDownModule = lambda label=label: events.append((label, 'module teardown'))
                cls = type('FixtureCase', (unittest.TestCase,), {
                    '__module__': label,
                    'setUpClass': classmethod(lambda cls, label=label: events.append((label, 'class setup'))),
                    'tearDownClass': classmethod(lambda cls, label=label: events.append((label, 'class teardown'))),
                    'test_one': lambda self, label=label: events.append((label, 'test')),
                })
                all_cases.append(cls('test_one'))
            tests = (all_cases[0], all_cases[1], all_cases[0])
            suite = worker.selected_suite(tests, (0, 2)) if sharded else unittest.TestSuite(tests)
            with patch.dict(sys.modules, {module.__name__: module for module in modules}):
                result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
            self.assertTrue(result.wasSuccessful())
            return [event for event in events if event[0] == modules[0].__name__]
        self.assertEqual(run(False), run(True))
        self.assertEqual(sum(event[1] == 'class setup' for event in run(True)), 2)

    def test_cli_shard_is_explicit_retains_deadline_and_is_not_inherited_as_credentials(self):
        with patch.object(worker.sys, 'argv', ['check-worker.py', 'offline', '--shard', '3']), patch.dict(os.environ, {
            'PATH': '/test/bin', 'DASHBOARD_TEST_SHARD': '1', 'SUPABASE_SERVICE_ROLE_KEY': 'must-not-copy',
        }, clear=True), patch.object(worker, 'native_wheels_directory', return_value=Path('/test/native-wheels')), patch.object(worker.subprocess, 'run') as execute:
            execute.return_value.returncode = 0
            self.assertEqual(worker.main(), 0)
            self.assertEqual(execute.call_args.args[0][-2:], ['--shard', '3'])
            self.assertEqual(execute.call_args.kwargs['timeout'], 1500)
            self.assertNotIn('DASHBOARD_TEST_SHARD', execute.call_args.kwargs['env'])
            self.assertNotIn('SUPABASE_SERVICE_ROLE_KEY', execute.call_args.kwargs['env'])
        for args in (['offline', '--shard', '4'], ['postgres', '--allow-isolated-postgres', '--shard', '5'],
                     ['postgres', '--shard', '1']):
            with patch.object(worker.sys, 'argv', ['check-worker.py', *args]), self.assertRaises(SystemExit), patch('sys.stderr', io.StringIO()):
                worker.main()

    def test_required_postgres_cli_keeps_opt_in_sanitization_and_2400_second_deadline(self):
        with patch.object(worker.sys, 'argv', ['check-worker.py', 'postgres', '--allow-isolated-postgres', '--shard', '4']), patch.dict(os.environ, {
            'PATH': '/test/bin', 'DASHBOARD_TEST_SHARD': '1', 'SUPABASE_SERVICE_ROLE_KEY': 'must-not-copy',
            worker.NATIVE_WHEELS_ENV: '/test/native-wheels',
        }, clear=True), patch.object(worker, 'native_wheels_directory', return_value=Path('/test/native-wheels')), patch.object(worker.subprocess, 'run') as execute:
            execute.return_value.returncode = 0
            self.assertEqual(worker.main(), 0)
            command = execute.call_args.args[0]
            self.assertIn('--allow-isolated-postgres', command)
            self.assertEqual(command[-2:], ['--shard', '4'])
            self.assertEqual(execute.call_args.kwargs['timeout'], 2400)
            env = execute.call_args.kwargs['env']
            self.assertEqual(env[worker.OPT_IN], '1')
            self.assertEqual(env['DOCKER_HOST'], 'unix:///var/run/docker.sock')
            self.assertEqual(env[worker.NATIVE_WHEELS_ENV], '/test/native-wheels')
            self.assertNotIn('DASHBOARD_TEST_SHARD', env)
            self.assertNotIn('SUPABASE_SERVICE_ROLE_KEY', env)

    def test_sql_bundle_is_revalidated_in_child_and_missing_or_changed_bundle_cannot_bypass_guards(self):
        inherited = {'PATH': '/test/bin', worker.NATIVE_WHEELS_ENV: '/test/native-wheels'}
        with patch.object(worker, 'native_wheels_directory', return_value=Path('/test/native-wheels')) as validate:
            env = worker.worker_environment('postgres', inherited)
            worker.validate_child_environment('postgres', env)
            self.assertEqual(validate.call_count, 2)
        with patch.object(worker, 'native_wheels_directory', side_effect=RuntimeError('changed owned wheel bundle')):
            with self.assertRaisesRegex(RuntimeError, 'changed owned wheel bundle'):
                worker.validate_child_environment('postgres', env)
        for inherited in ({}, {worker.NATIVE_WHEELS_ENV: 'relative/wheels'}):
            with self.assertRaisesRegex(RuntimeError, 'explicit prepared native SQL wheel bundle'):
                worker.native_wheels_directory(inherited)

    def test_four_required_shards_cover_every_original_postgres_occurrence(self):
        modules = ('tests.postgres.test_assessment_transition', 'tests.postgres.test_causal_risk',
                   'tests.postgres.test_optimizer_transition', 'tests.postgres.test_portable_period_mutation')
        original = [test for module in modules for test in cases(module)]
        original.extend((original[0], original[2]))
        with self.source_fixture():
            tests, shards, coverage = worker.partition_suite(unittest.TestSuite(original), 'postgres')
        self.assertEqual(set(shards), {1, 2, 3, 4})
        self.assertEqual(coverage['declared_shards'], [1, 2, 3, 4])
        self.assertEqual(coverage['scope'], 'postgres')
        self.assertEqual(coverage['baseline_repeated_ids'], 2)
        self.assertEqual(Counter(index for indices in shards.values() for index in indices), Counter(range(len(original))))
        self.assertEqual({worker.module_shard(module, 'postgres') for module in modules}, {1, 2, 3, 4})
        for invalid in ({key: value for key, value in shards.items() if key != 4}, {**shards, 4: ()}):
            with self.assertRaises(RuntimeError): worker.validate_partition(tests, invalid, 'postgres')
        for mode in ('unknown', ''):
            with self.assertRaises(RuntimeError): worker.partition_suite(unittest.TestSuite(original), mode)


if __name__ == '__main__': unittest.main()
