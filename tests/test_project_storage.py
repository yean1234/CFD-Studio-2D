"""Storage isolation and cross-folder recovery without running any CFD solver."""
import copy
import ast
import os
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cfd_studio.execution_workspace import ExecutionWorkspace, read_json, atomic_json
from cfd_studio.project_storage import project_path

ROOT = Path(__file__).resolve().parents[1]


class ProjectStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.w = ExecutionWorkspace(ROOT, [], folder=self.root/'registry', output=self.root/'old-output')
        self.p = self.w.create_project('저장 시험', storage_path=str(self.root/'선택한 폴더'))
        self.config = self.w.template()

    def new_case(self, project=None):
        return self.w.save_case((project or self.p)['id'], 'Case A', self.config)['run_key']

    def test_exact_folder_and_project_local_settings(self):
        self.assertEqual(project_path(self.p['storage_path']), self.root/'선택한 폴더')
        a = self.new_case()
        second = self.w.create_project('second', storage_path=str(self.root/'other drive folder'))
        b = self.new_case(second)
        first_data = read_json(Path(self.p['storage_path'])/'ProjectSettings/executions.json')
        self.assertEqual(set(first_data['cases']), {a})
        self.assertNotIn('cases', read_json(self.w.folder/'queue.json'))
        self.assertEqual(set(self.w.queue_data()['cases']), {a, b})
        restarted = ExecutionWorkspace(ROOT, [], folder=self.w.folder, output=self.w.output)
        self.assertEqual(restarted.queue_data(), self.w.queue_data())

    def test_attempt_input_and_raw_destination_are_inside_project(self):
        key = self.new_case()
        self.w.queue_action('enqueue', [key]); self.w.queue_action('resume')
        with patch.object(self.w, 'launch_case'):
            self.w.queue_tick()
        case = self.w.queue_data()['cases'][key]
        job = Path(case['attempts'][0]['job_path'])
        self.assertTrue(job.is_relative_to(Path(self.p['storage_path'])/'Cases'))
        self.assertEqual(read_json(job.with_name('input.json')), case['config'])
        self.assertTrue(Path(case['output']).is_relative_to(Path(self.p['storage_path'])))
        self.assertFalse(self.w.output.exists())

    def test_failed_local_save_leaves_preset_draft_and_registry_unchanged(self):
        key = self.new_case()
        before = copy.deepcopy(self.w.queue_data())
        original = (Path(self.p['storage_path'])/'ProjectSettings/executions.json').read_bytes()
        from cfd_studio import project_storage
        original_write = project_storage.write
        def fail_registry(path, value):
            if Path(path) == self.w.folder/'queue.json':
                raise OSError('disk full')
            original_write(path, value)
        with patch('cfd_studio.project_storage.write', side_effect=fail_registry):
            with self.assertRaises(OSError):
                self.w.save_case(self.p['id'], 'changed', self.config, key, 1, preset_name='storage failure')
        self.assertEqual(self.w.queue_data(), before)
        self.assertEqual((Path(self.p['storage_path'])/'ProjectSettings/executions.json').read_bytes(), original)
        self.assertNotIn('preset:storage failure', self.w.preset_paths())

    def test_nonempty_destination_does_not_overwrite_or_register(self):
        path = self.root/'occupied';path.mkdir();(path/'keep').write_text('original')
        before = self.w.snapshot()
        with self.assertRaisesRegex(ValueError, '비어'):
            self.w.create_project('bad', storage_path=str(path))
        self.assertEqual(self.w.snapshot(), before)
        self.assertEqual((path/'keep').read_text(), 'original')
        with self.assertRaises(ValueError): project_path('relative/folder')
        with self.assertRaises(ValueError): project_path('D:relative')

    def test_relocate_preserves_source_and_rebinds_attempt_and_results(self):
        key = self.new_case();self.w.queue_action('enqueue', [key]);self.w.queue_action('resume')
        with patch.object(self.w, 'launch_case'): self.w.queue_tick()
        q = self.w.queue_data();c = q['cases'][key]
        old_input = Path(c['attempts'][0]['job_path']).with_name('input.json')
        input_bytes = old_input.read_bytes()
        q['active'] = None;q['paused'] = True;c['status'] = 'complete';self.w.save_queue(q)
        source = Path(self.p['storage_path'])
        cache = source/'Cache'/'item.bin';cache.write_bytes(b'cache')
        target = self.root/'new volume'/'한글 이름'
        self.w.relocate_project(self.p['id'], str(target))
        changed = self.w.queue_data()['cases'][key]
        self.assertTrue(Path(changed['attempts'][0]['job_path']).is_relative_to(target))
        self.assertEqual(Path(changed['attempts'][0]['job_path']).with_name('input.json').read_bytes(), input_bytes)
        self.assertEqual(old_input.read_bytes(), input_bytes)
        self.assertEqual((target/'Cache/item.bin').read_bytes(), b'cache')
        self.assertEqual(read_json(Path(changed['attempts'][0]['job_path']))['output'], changed['output'])

    def test_failed_copy_does_not_change_project_pointer(self):
        with patch('cfd_studio.project_storage.copy_verified', side_effect=OSError('full')):
            with self.assertRaises(OSError):
                self.w.relocate_project(self.p['id'], str(self.root/'failed'))
        self.assertEqual(self.w.project_folder(self.p['id']), Path(self.p['storage_path']))

    def test_detached_project_opens_with_cases_and_paused_queue(self):
        key = self.new_case();self.w.queue_action('enqueue', [key]);self.w.queue_action('resume')
        self.w.snapshot()
        other = ExecutionWorkspace(ROOT, [], folder=self.root/'fresh-studio', output=self.root/'no-output')
        loaded = other.open_project(self.p['storage_path'])
        self.assertEqual(loaded['id'], self.p['id'])
        self.assertEqual(other.queue_data()['cases'][key]['config'], self.w.queue_data()['cases'][key]['config'])
        self.assertTrue(other.queue_data()['paused'])
        self.assertEqual(other.queue_data()['order'], [key])
        self.assertEqual(other.open_project(self.p['storage_path'])['id'], loaded['id'])

    def test_moved_offline_project_can_reopen_without_losing_queued_cases(self):
        key = self.new_case();self.w.queue_action('enqueue', [key]);self.w.snapshot()
        before = self.w.queue_data()['cases'][key]['config']
        source = Path(self.p['storage_path']);moved = self.root/'manually moved'
        source.rename(moved)
        self.assertIn('드라이브', self.w.queue_data()['service_error'])
        with self.assertRaisesRegex(ValueError, '드라이브'): self.w.queue_action('resume')
        opened = self.w.open_project(str(moved))
        self.assertEqual(opened['id'], self.p['id'])
        self.assertEqual(len(self.w.snapshot()['projects']), 1)
        self.assertEqual(self.w.queue_data()['cases'][key]['config'], before)
        self.assertEqual(self.w.queue_data()['order'], [key])
        self.assertTrue(self.w.queue_data()['paused'])

    def test_incomplete_copy_cannot_open_as_a_finished_project(self):
        path = Path(self.p['storage_path'])
        (path/'.storage-incomplete').touch()
        other = ExecutionWorkspace(ROOT, [], folder=self.root/'other-studio')
        with self.assertRaisesRegex(ValueError, '복사가 완료되지'):
            other.open_project(str(path))
        self.assertEqual(other.stored_projects(), [])

    def test_immersion_result_creation_uses_attempt_folder_and_local_raw(self):
        tree = ast.parse((ROOT/'cfd_studio/app.py').read_text(encoding='utf-8'))
        method = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_create_run_project')
        attempt = self.w.attempt_folder(self.p['id'], 'case:test', 'attempt')
        env = {'os': os, 'EXECUTION_WORKSPACE': self.w,
               'proj_dir': lambda rid: str(self.root/'absent'),
               '_raw_archive_dir': lambda: str(self.root/'obsolete global setting'),
               '_validate_raw_archive_dir': lambda value, **kw: (True, value, ''),
               '_desired_project_raw_path': lambda pd, root: str(Path(pd)/'Raw_Data'),
               'meta_write': atomic_json}
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<project-create>', 'exec'), env)
        folder = Path(env['_create_run_project']('123', 'run', {'execution_project_id': self.p['id'], 'execution_attempt_path': str(attempt)}))
        self.assertEqual(folder, attempt/'Results/123')
        meta = read_json(folder/'meta.json')
        self.assertEqual(meta['raw_archive_root'], str(folder))
        self.assertEqual(meta['raw_archive_run'], str(folder/'Raw_Data'))
        self.assertEqual(self.w.result_path('123', 'legacy'), folder)

    def test_old_registry_migrates_before_queue_service_starts(self):
        folder = self.root/'old registry';folder.mkdir()
        legacy_project = {'id': 'a'*32, 'name': 'old', 'runs': [], 'created': 0}
        atomic_json(folder/'projects.json', {'schema': 1, 'projects': [legacy_project]})
        old = ExecutionWorkspace(ROOT, [], folder=folder, output=self.root/'empty')
        with patch('cfd_studio.run_management.threading.Thread'):
            old.start_queue_service()
        loaded = old.stored_projects()[0]
        self.assertTrue((Path(loaded['storage_path'])/'project.cfdproj').is_file())
        self.assertEqual(read_json(folder/'queue.json')['schema'], 2)
        self.assertTrue(old.queue_data()['paused'])

    def test_nested_project_folders_are_rejected(self):
        with self.assertRaisesRegex(ValueError, '겹치지'):
            self.w.create_project('nested', storage_path=str(Path(self.p['storage_path'])/'Cases'/'nested'))
        other = self.w.create_project('other', storage_path=str(self.root/'other'))
        with self.assertRaisesRegex(ValueError, '겹치지'):
            self.w.relocate_project(self.p['id'], str(Path(other['storage_path'])/'nested'))

    def test_running_project_move_is_blocked(self):
        self.w.busy = lambda: True
        with self.assertRaisesRegex(ValueError, '계산'):
            self.w.relocate_project(self.p['id'], str(self.root/'moved'))
        self.assertFalse((self.root/'moved').exists())

    def test_external_results_are_copied_and_original_bytes_preserved(self):
        old = self.root/'old result';old.mkdir()
        atomic_json(old/'meta.json', {'run_id': 'fixture', 'completed': True})
        atomic_json(old/'case_config.json', {'tank': {}, 'dielectric_fluid': {}})
        (old/'flow_1.bin').write_bytes(b'original frame')
        restored = self.w.restore_external(self.p['name'], old)
        self.w.snapshot()
        target = self.root/'consolidated'
        self.w.relocate_project(restored['project_id'], str(target))
        self.assertEqual(self.w.result_path('fixture', 'legacy'), target/'Results/old result')
        self.assertEqual((old/'flow_1.bin').read_bytes(), b'original frame')
        self.assertEqual((target/'Results/old result/flow_1.bin').read_bytes(), b'original frame')
        self.assertEqual(self.w.detail('legacy:fixture')['path'], str(target/'Results/old result'))


if __name__ == '__main__': unittest.main()
