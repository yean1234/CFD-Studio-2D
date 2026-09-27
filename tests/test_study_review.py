"""임시 데이터와 가짜 실행기로 복구·HTTP·내보내기 경계를 검사한다."""
import base64
import copy
import errno
import hashlib
import io
import json
from pathlib import Path
import shlex
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

from study_platform import http, packages, runner
from study_platform.contracts import candidates, canonical
from study_platform.research_design import variable_schema
from study_platform.service import Conflict, Service, owner_lock, uid


DESIGN = {'variable': 'K_porous_m2_s', 'method': 'manual', 'values': [.001, .004], 'seed': 42}


def research_fixture():
    variables = variable_schema()['variables']
    values = {
        'layout': {'spacing_axis': 0, 'blocks': [
            {'id': 'a', 'min': [1, 1, 0], 'max': [3, 3, 2], 'mass_kg': 10},
            {'id': 'b', 'min': [4, 1, 0], 'max': [6, 3, 2], 'mass_kg': 10}]},
        'spacing_m': 1, 'supply_positions': [[8, 2, 1]],
        'total_supply': {'value': 1, 'unit': 'normalized_test_unit', 'evidence': 'unit_test_only'},
    }
    for key, value in values.items():
        variables[key]['value'] = value
    return {'profile': 'warehouse_joint_v1', 'variables': variables,
            'baseline': {key: copy.deepcopy(entry['value']) for key, entry in variables.items()},
            'sampling': {'method': 'cartesian_choices', 'seed': 42},
            'common': {'geometry': {'length_m': 10, 'width_m': 8, 'eaves_m': 4},
                       'stored_mass_kg': 20, 'mass_tolerance_kg': 0, 'source_count': 1,
                       'supply_duration_s': 10, 'wall_clearance_m': 1, 'maximum_stack_height_m': 3,
                       'aisles': [{'min': [0, 4, 0], 'max': [10, 6, 4], 'width_axis': 1, 'minimum_width_m': 2}],
                       'allowed_source_regions': [{'min': [7, 1, 0], 'max': [9, 3, 3]}]}}


class StudyReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Service(Path(self.temp.name)/'study', adapter=Mock(return_value={'pass': True}))
        self.store.wake = Mock()
        self.study = self.store.create('review')
        self.revision = self.store.commit(self.study, DESIGN, candidates(DESIGN)['preview_hash'], None)

    def attempt(self, state='failed', case_index=0, result=None):
        key = self.store.enqueue([self.revision['cases'][case_index]], uid())['attempts'][0]
        with self.store.db() as db:
            db.execute('UPDATE attempts SET state=?,owner=?,result=? WHERE id=?',
                       (state, 'previous-worker', canonical(result) if result is not None else None, key))
        return key

    def post(self, body, attempt=None, study=None, suffix=None):
        path = '/api/studies/'+(study or self.study)
        path += '/attempts/'+attempt if attempt else '/'+(suffix or 'enqueue')
        handler = Mock(path=path)
        self.assertTrue(http.post(handler, self.store, body))
        args = handler._json.call_args.args
        return (args[1] if len(args) > 1 else 200), args[0]

    def test_detail_discovers_orphan_without_changing_state(self):
        orphan = self.attempt('running')
        other = self.store.create('other study')
        data = self.store.detail(self.study)
        self.assertTrue(data['attempts'][0]['recovery_available'])
        self.assertEqual(data['attempts'][0]['state'], 'running')
        self.assertEqual(self.store.detail(other)['recovery_blocker'], {
            'study_id': self.study, 'study_name': 'review', 'attempt_id': orphan,
            'state': 'running', 'recovery_available': True})
        with owner_lock(self.store.root/'worker.lock') as locked:
            self.assertTrue(locked)
            data = self.store.detail(self.study)
            self.assertFalse(data['attempts'][0]['recovery_available'])
            self.assertIsNone(data['recovery_blocker'])
        self.store.adapter.assert_not_called()

    def test_recovery_requires_confirmation_preserves_data_and_pauses(self):
        original = {'error': 'original diagnostic', 'checks': {'pass': False}}
        orphan = self.attempt('recovery_required', result=original)
        raw = self.store.root/'attempts'/orphan/'raw'
        raw.mkdir(parents=True)
        (raw/'checkpoint').write_bytes(b'preserved')
        for confirmed, note in [(False, 'stopped'), ('true', 'stopped'), (1, 'stopped'), (True, ''), (True, ' '*3), (True, 'x'*2001)]:
            with self.subTest(confirmed=confirmed, note_length=len(note)):
                status, _ = self.post({'action': 'resolve_recovery', 'confirmed_stopped': confirmed,
                                       'operator_note': note}, orphan)
                self.assertEqual(status, 400)
        body = {'action': 'resolve_recovery', 'confirmed_stopped': True, 'operator_note': 'Solver stopped manually'}
        status, response = self.post(body, orphan)
        self.assertEqual(status, 200)
        self.assertEqual(self.post(body, orphan)[1], response)
        data = self.store.detail(self.study)
        row = data['attempts'][0]
        self.assertEqual(row['state'], 'failed')
        self.assertEqual(row['result']['checks'], original['checks'])
        self.assertEqual(row['result']['error'], original['error'])
        self.assertEqual(row['result']['failure_category'], 'interrupted')
        self.assertEqual(row['result']['recovery_audit']['previous_owner'], 'previous-worker')
        self.assertTrue(data['paused'])
        self.assertIsNone(data['recovery_blocker'])
        self.assertEqual((raw/'checkpoint').read_bytes(), b'preserved')
        self.store.wake.assert_not_called()
        self.store.adapter.assert_not_called()

    def test_active_owner_cannot_be_resolved_even_with_confirmation(self):
        orphan = self.attempt('running')
        with owner_lock(self.store.root/'worker.lock') as locked:
            self.assertTrue(locked)
            status, _ = self.post({'action': 'resolve_recovery', 'confirmed_stopped': True,
                                   'operator_note': 'stopped'}, orphan)
        self.assertEqual(status, 409)
        self.assertEqual(self.store.detail(self.study)['attempts'][0]['state'], 'running')

    def test_all_recoveries_must_be_resolved_before_explicit_continue(self):
        first = self.attempt('running', 0)
        second = self.attempt('recovery_required', 1)
        queued = self.attempt('queued', 2)
        body = {'action': 'resolve_recovery', 'confirmed_stopped': True, 'operator_note': 'stopped'}
        self.assertEqual(self.post(body, first)[0], 200)
        self.store.pause(False)
        self.store.drain()
        self.store.adapter.assert_not_called()
        self.assertEqual(self.store.detail(self.study)['recovery_blocker']['attempt_id'], second)
        self.assertEqual(self.post(body, second)[0], 200)
        self.store.drain()
        self.store.adapter.assert_not_called()
        self.store.pause(False)
        self.store.drain()
        states = {a['id']: a['state'] for a in self.store.detail(self.study)['attempts']}
        self.assertEqual(states, {first: 'failed', second: 'failed', queued: 'finished'})
        self.store.adapter.assert_called_once()

    def test_every_action_checks_study_membership(self):
        attempt = self.attempt('recovery_required')
        other = self.store.create('other')
        for action in ('resolve_recovery', 'cancel', 'retry', 'resume'):
            with self.subTest(action=action):
                status, _ = self.post({'action': action, 'confirmed_stopped': True,
                                       'operator_note': 'stopped', 'request_id': uid()}, attempt, other)
                self.assertEqual(status, 400)
        self.assertEqual(self.store.detail(self.study)['attempts'][0]['state'], 'recovery_required')
        self.store.wake.assert_not_called()

    def test_cancel_is_idempotent_and_never_cancels_running_work(self):
        queued = self.attempt('queued')
        self.assertEqual(self.post({'action': 'cancel'}, queued)[0], 200)
        self.assertEqual(self.post({'action': 'cancel'}, queued)[0], 200)
        active = self.attempt('running', 1)
        self.assertEqual(self.post({'action': 'cancel'}, active)[0], 409)
        self.store.wake.assert_not_called()

    def test_retry_and_resume_create_one_new_attempt_per_request(self):
        for index, action in enumerate(('retry', 'resume')):
            with self.subTest(action=action):
                source = self.attempt('failed', index, {'error': 'preserve'})
                body = {'action': action, 'request_id': uid()}
                self.assertEqual(self.post({'action': action}, source)[0], 400)
                status, response = self.post(body, source)
                self.assertEqual(status, 200)
                self.assertEqual(self.post(body, source)[1], response)
                rows = {a['id']: a for a in self.store.detail(self.study)['attempts']}
                target = rows[response['result']['attempts'][0]]
                self.assertNotEqual(target['id'], source)
                self.assertEqual(target['resume_from'], source if action == 'resume' else None)
                self.assertEqual(rows[source]['result'], {'error': 'preserve'})
                self.assertEqual(self.post({**body, 'action': 'resume' if action == 'retry' else 'retry'}, source)[0], 409)
                self.assertEqual(self.post({**body, 'request_id': uid()}, source)[0], 409)
        self.assertEqual(len(self.store.detail(self.study)['attempts']), 4)

    def test_unresolved_attempts_cannot_retry_or_resume(self):
        for index, state in enumerate(('running', 'recovery_required', 'queued')):
            source = self.attempt(state, index)
            for action in ('retry', 'resume'):
                self.assertEqual(self.post({'action': action, 'request_id': uid()}, source)[0], 409)

    def test_enqueue_forwards_resume_and_validates_source(self):
        source = self.attempt('failed')
        body = {'cases': [self.revision['cases'][0]], 'request_id': uid(), 'resume_from': source}
        status, response = self.post(body)
        self.assertEqual(status, 200)
        self.assertEqual(self.post(body)[1], response)
        rows = self.store.detail(self.study)['attempts']
        self.assertEqual(rows[-1]['resume_from'], source)
        for bad in ([], {}, False, '../escape', ''):
            self.assertEqual(self.post({**body, 'request_id': uid(), 'resume_from': bad})[0], 400)
        self.assertEqual(self.post({'cases': [self.revision['cases'][1]], 'request_id': uid(), 'resume_from': source})[0], 400)

    def test_malformed_case_lists_return_validation_errors(self):
        for value in (None, 'case', {}, [None], [{}], [], ['unknown']):
            with self.subTest(value=value):
                self.assertEqual(self.post({'cases': value, 'request_id': uid()})[0], 400)

    def fake_wslpath(self, argv, **kwargs):
        self.assertEqual(argv[-3:-1], ['wslpath', '-u'])
        # 가짜 실행기는 호스트에서 파일을 쓰므로 WSL 변환 대신 원래 임시 경로를 유지한다.
        return argv[-1]+'\n'

    def run_reported_failure(self, category):
        self.store.adapter = self.store._real_adapter
        self.store.enqueue(self.revision['cases'][:2], uid())
        calls = []
        def fake_run(argv, **kwargs):
            words = shlex.split(argv[-1])
            folder = Path(words[words.index('study_platform.runner')+1])
            calls.append(folder)
            if len(calls) == 1:
                (folder/'failure.json').write_text(canonical({'category': category, 'error': 'controlled failure'}))
                return SimpleNamespace(returncode=1)
            (folder/'raw').mkdir()
            (folder/'raw/checks.json').write_text(canonical({'pass': True}))
            return SimpleNamespace(returncode=0)
        with patch('study_platform.service.subprocess.check_output', side_effect=self.fake_wslpath), \
                patch('study_platform.service.subprocess.run', side_effect=fake_run):
            self.store.drain()
        return self.store.detail(self.study), calls

    def test_case_failure_does_not_pause_following_candidates(self):
        data, calls = self.run_reported_failure('case')
        self.assertEqual([a['state'] for a in data['attempts']], ['failed', 'finished'])
        self.assertEqual(data['attempts'][0]['result']['failure_category'], 'case')
        self.assertFalse(data['paused'])
        self.assertEqual(len(calls), 2)

    def test_environment_failure_pauses_following_candidates(self):
        data, calls = self.run_reported_failure('environment')
        self.assertEqual([a['state'] for a in data['attempts']], ['failed', 'queued'])
        self.assertTrue(data['paused'])
        self.assertEqual(len(calls), 1)

    def test_runner_reports_failure_categories_without_solver(self):
        failures = [(ValueError('case rejected'), 'case'), (RuntimeError('solver failed'), 'case'),
                    (FileNotFoundError(errno.ENOENT, 'checkpoint missing'), 'case'),
                    (OSError(errno.ENOSPC, 'disk full'), 'environment'),
                    (ImportError('numpy missing'), 'environment'),
                    (runner.EnvironmentFailure('solver missing'), 'environment')]
        for exc, category in failures:
            with self.subTest(category=category, error=type(exc).__name__):
                folder = Path(self.temp.name)/uid(); folder.mkdir()
                with patch.object(runner, '_run', side_effect=exc), self.assertRaises(type(exc)):
                    runner.run(folder)
                report = json.loads((folder/'failure.json').read_text(encoding='utf-8'))
                self.assertEqual(report['category'], category)
                self.assertEqual(report['error'], str(exc))

    def test_runner_missing_executable_reports_environment(self):
        folder = Path(self.temp.name)/'runner'; folder.mkdir()
        (folder/'input.json').write_text('{}')
        # 실행 파일 검사만 검증하며 NumPy 설치 여부와 실제 수송 모듈에 의존하지 않는다.
        dependencies = {'numpy': ModuleType('numpy')}
        operations = []
        for name, attribute in [('tracer_transport.run', 'execute'),
                                ('tracer_transport.restart', 'restart'),
                                ('tracer_transport.export_studio', 'export_case')]:
            module = ModuleType(name)
            operation = Mock(side_effect=AssertionError('실제 수송 실행은 허용하지 않습니다'))
            setattr(module, attribute, operation)
            dependencies[name] = module
            operations.append(operation)
        with patch.dict(sys.modules, dependencies), patch.object(runner.shutil, 'which', return_value=None) as which:
            with self.assertRaises(runner.EnvironmentFailure):
                runner.run(folder)
        which.assert_called_once_with('blockMesh')
        for operation in operations:
            operation.assert_not_called()
        self.assertEqual(json.loads((folder/'failure.json').read_text(encoding='utf-8'))['category'], 'environment')

    def test_auto_environment_supports_opt_and_usr(self):
        folder = Path(self.temp.name)/'adapter'; (folder/'raw').mkdir(parents=True)
        (folder/'raw/checks.json').write_text('{"pass":true}')
        with patch('study_platform.service.subprocess.check_output', side_effect=self.fake_wslpath), \
                patch('study_platform.service.subprocess.run', return_value=SimpleNamespace(returncode=0)) as launch:
            self.store._real_adapter(folder, {}, Path(self.temp.name)/'code', None)
        command = launch.call_args.args[0][-1]
        self.assertIn('/opt/openfoam*/etc/bashrc', command)
        self.assertIn('/usr/lib/openfoam/openfoam*/etc/bashrc', command)

    def test_export_uses_one_detail_snapshot_across_revision_change(self):
        def fake(folder, *args):
            (folder/'metrics.json').write_text(canonical({'evaluation_window_s': [0, 1],
                'physical_end_s': 1, 'times': [0, 1], 'mean_C': [1, 1]}))
            return {'pass': True}
        self.store.adapter = fake
        original = self.store.enqueue([self.revision['cases'][0]], uid())['attempts'][0]
        self.store.drain()
        read = self.store.detail
        def read_then_commit(study):
            detail = read(study)
            self.store.commit(study, DESIGN, candidates(DESIGN)['preview_hash'], detail['current_revision'])
            return detail
        with patch.object(self.store, 'detail', side_effect=read_then_commit) as reads:
            exported = packages.export(self.store, self.study)
        reads.assert_called_once_with(self.study)
        path = self.store.root/'packages'/exported['filename']
        packages.inspect(path)
        with zipfile.ZipFile(path) as archive:
            detail = json.loads(archive.read('inputs/study.json'))
            comparison = json.loads(archive.read('figures/comparison.json'))
        self.assertEqual(detail['current_revision'], self.revision['revision'])
        self.assertEqual(comparison['rows'][0]['attempt'], original)
        self.assertNotEqual(read(self.study)['current_revision'], self.revision['revision'])
        packages.import_package(path, Path(self.temp.name)/'imported')

    def test_malformed_research_shapes_return_400(self):
        mutations = [lambda d: d.update(common=None), lambda d: d.update(sampling=[]),
                     lambda d: d.update(baseline=None), lambda d: d['common'].update(geometry=[]),
                     lambda d: d['common'].update(allowed_source_regions=None),
                     lambda d: d['baseline'].update(layout=[]),
                     lambda d: d['baseline']['layout']['blocks'].__setitem__(0, None),
                     lambda d: d['variables']['total_supply']['value'].update(unit={}),
                     lambda d: d['variables'].update(spacing_m={'mode': 'search', 'bounds': [1], 'count': 2}),
                     lambda d: d['variables'].update(spacing_m={'mode': 'derived', 'rule': 'minimum_horizontal_clearance'})]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                design = research_fixture(); mutate(design)
                if index == len(mutations)-1:
                    design['baseline']['layout']['blocks'] = [None]
                self.assertEqual(self.post({'design': design}, suffix='preview')[0], 400)

    def test_explicit_research_values_validate_without_filling_null(self):
        design = research_fixture()
        before = copy.deepcopy(design)
        result = candidates(design)
        self.assertTrue(result['candidates'][0]['valid'])
        self.assertIsNone(result['candidates'][0]['input']['variables']['temperature_K'])
        self.assertEqual(design, before)
        invalid = {'temperature_K': [0, -10], 'porosity': [0, 2], 'dt_s': [0, -1],
                   'mesh_m': ['nonsense', 0], 'evaluation_s': [0], 'write_interval_s': [-1],
                   'leakage': [-1], 'bag_resistance': [-1], 'diffusion': [-1],
                   'reaction': [-1], 'convergence': [0]}
        for key, values in invalid.items():
            for value in values+[True, float('nan'), float('inf'), {}, []]:
                with self.subTest(key=key, value=value):
                    design = research_fixture()
                    design['variables'][key]['value'] = value
                    design['baseline'][key] = value
                    self.assertEqual(self.post({'design': design}, suffix='preview')[0], 400)
        design = research_fixture()
        for key, value in [('temperature_K', 1e20), ('mesh_m', 1e-20), ('leakage', 0), ('diffusion', 0)]:
            design['variables'][key]['value'] = design['baseline'][key] = value
        self.assertTrue(candidates(design)['candidates'][0]['valid'])

    def test_malformed_package_manifests_return_400_and_leave_no_upload(self):
        metadata = {'size': 4, 'sha256': hashlib.sha256(b'data').hexdigest()}
        manifests = [None, [], 1, {'schema_version': True, 'level': 'A', 'files': {}},
                     {'schema_version': 1, 'level': 'A', 'files': []}]
        for bad in (None, [], {}, {**metadata, 'size': True}, {**metadata, 'sha256': []}):
            manifests.append({'schema_version': 1, 'level': 'A', 'files': {'data.txt': bad}})
        for manifest in manifests:
            with self.subTest(manifest=manifest):
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, 'w') as archive:
                    archive.writestr('data.txt', b'data')
                    archive.writestr('manifest.json', json.dumps(manifest))
                handler = Mock(path='/api/study-packages/import')
                http.post(handler, self.store, {'base64': base64.b64encode(buffer.getvalue()).decode('ascii')})
                self.assertEqual(handler._json.call_args.args[1], 400)
                self.assertEqual(list((self.store.root/'imports').iterdir()), [])

    def test_static_study_script_remains_whitelisted(self):
        handler = Mock(path='/studies/study.js')
        with patch.object(Path, 'read_bytes', return_value=b'// static'):
            self.assertTrue(http.get(handler, self.store))
        self.assertEqual(handler._send.call_args.args[0], 200)


if __name__ == '__main__':
    unittest.main()
