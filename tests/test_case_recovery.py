"""Recovery policy tests. No solver process is launched."""
import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from cfd_studio.execution_workspace import ExecutionWorkspace
from cfd_studio.execution_adapters import install

ROOT = Path(__file__).resolve().parents[1]

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.w = ExecutionWorkspace(ROOT, [], folder=Path(self.temp.name)/'registry', output=Path(self.temp.name)/'output')
        self.p = self.w.create_project('Recovery')
        self.config = self.w.template()
        self.key = self.w.save_case(self.p['id'], 'Failed', self.config)['run_key']
        q = self.w.queue_data(); q['cases'][self.key].update(status='failed', error='실행기가 완료 기록 없이 종료되었습니다'); self.w.save_queue(q)

    def test_unknown_failure_allows_retry_without_claiming_config_error(self):
        recovery = self.w.detail(self.key)['recovery']
        self.assertTrue(recovery['retry']); self.assertEqual(recovery['category'], 'runtime')
        before = copy.deepcopy(self.w.queue_data()['cases'][self.key]['config'])
        self.w.recover_case(self.key, 'retry')
        q = self.w.queue_data(); self.assertEqual(q['order'], [self.key]); self.assertTrue(q['paused'])
        self.assertEqual(q['cases'][self.key]['config'], before)
        with self.assertRaises(ValueError): self.w.recover_case(self.key, 'retry')

    def test_invalid_config_and_completed_case_cannot_retry(self):
        q = self.w.queue_data(); q['cases'][self.key]['config']['numerics']['dt_s'] = -1; self.w.save_queue(q)
        self.assertEqual(self.w.detail(self.key)['recovery']['category'], 'config')
        with self.assertRaises(ValueError): self.w.queue_action('retry', case_id=self.key)
        q = self.w.queue_data(); q['cases'][self.key].update(status='complete'); self.w.save_queue(q)
        self.assertIsNone(self.w.detail(self.key)['recovery'])
        with self.assertRaises(ValueError): self.w.recover_case(self.key, 'retry')

    def test_unsupported_resume_does_not_restart_from_zero(self):
        q = self.w.queue_data(); q['cases'][self.key]['status'] = 'stopped'; self.w.save_queue(q)
        recovery = self.w.detail(self.key)['recovery']
        self.assertFalse(recovery['resume']); self.assertIn('재개', recovery['resume_reason'])
        with self.assertRaises(ValueError): self.w.recover_case(self.key, 'continue_case')
        self.assertEqual(self.w.queue_data()['cases'][self.key]['status'], 'stopped')

    def test_retry_does_not_clear_another_case_failure(self):
        q = self.w.queue_data(); q['failure'] = 'unrelated'; self.w.save_queue(q)
        self.w.recover_case(self.key, 'retry')
        self.assertEqual(self.w.queue_data()['failure'], 'unrelated')

    def test_remove_retry_restores_failed_state_and_can_retry_again(self):
        self.w.recover_case(self.key, 'retry')
        self.w.queue_action('remove', case_id=self.key)
        self.assertEqual(self.w.queue_data()['cases'][self.key]['status'], 'failed')
        self.w.recover_case(self.key, 'retry')
        self.assertEqual(self.w.queue_data()['order'], [self.key])

    def test_imported_failed_result_retries_in_new_case_without_changing_original(self):
        from cfd_studio.execution_workspace import atomic_json
        folder = self.w.output/'warehouse_transport_failed'; folder.mkdir(parents=True)
        atomic_json(folder/'model_contract.json', {'kind':'clo2_coupled_scenario'})
        atomic_json(folder/'state.json', {'status':'failed','error':'runtime'})
        atomic_json(folder/'transport_input.json', self.config)
        original = {p.name:p.read_bytes() for p in folder.iterdir()}
        self.w.snapshot()
        result = self.w.recover_case('warehouse:warehouse_transport_failed', 'retry')
        self.assertTrue(result['id'].startswith('case:'))
        self.assertEqual({p.name:p.read_bytes() for p in folder.iterdir()}, original)
        self.assertEqual(self.w.queue_data()['order'], [result['id']])

    def test_log_evidence_is_plain_text_and_not_an_invented_cause(self):
        result = self.w.recovery({'status':'failed'}, self.config, 'FOAM FATAL ERROR\nCannot find patch test\n<script>')
        self.assertIn('Cannot find patch test', result['evidence'])
        self.assertEqual(result['category'], 'runtime')

    def test_recorded_result_failure_shows_failed_measurement(self):
        result = self.w.recovery({'status':'failed'}, self.config, 'trapFpe: Floating point exception trapping enabled',
                                 {'execution_checks_pass':False, 'max_divergence_s_inv':.00118})
        self.assertEqual(result['category'], 'result_check')
        self.assertIn('0.00118', result['reason']); self.assertIn('1e-05', result['reason'])
        self.assertEqual(result['evidence'], '')
        self.assertTrue(result['retry'])

    def test_resume_preserves_source_and_dispatches_native_resume_not_fresh(self):
        folder = Path(self.temp.name)/'attempt'; folder.mkdir()
        case = {'id':'case:x', 'name':'Resume', 'project_id':'p', 'result_key':'legacy:12',
                'end_s':20, 'config':{'run':{}},
                'attempts':[{'mode':'resume','source_result_key':'legacy:12','job_path':str(folder/'job.json')}]}
        calls = []
        class Handler:
            def _run_legacy(self, body):
                calls.append(body); self._json({'ok':True,'rid':'12'})
        w = SimpleNamespace(queue_data=lambda:{'cases':{'case:x':case}})
        commands = []
        def wsl(command, **kwargs):
            commands.append(command)
            return True, 'STUDIO_ANCHOR=5'
        g = {'_resume_mode_error':lambda rid:None, 'WSL_CASE':'/case', '_active_rid':lambda:'12', '_shq':lambda s:repr(s),
             '_resume_anchor_shell':lambda *a:'CHECK; ', 'wsl':wsl, 'win2wsl':lambda s:s, 'H':Handler, 'project_config':lambda rid:case['config']}
        install(w,g);w.legacy_start(case)
        self.assertEqual(calls[0]['mode'], 'resume_archived')
        self.assertEqual(calls[0]['selected_rid'], '12')
        self.assertIn('cp -a', commands[1]); self.assertIn('Recovery_Source', commands[1])
        calls.clear()
        def failed_copy(command, **kwargs):
            return (True,'STUDIO_ANCHOR=5') if 'STUDIO_ANCHOR' in command else (False,'disk full')
        g['wsl'] = failed_copy
        with self.assertRaisesRegex(ValueError,'보존 실패'): w.legacy_start(case)
        self.assertEqual(calls, [])

    def test_resume_requires_positive_complete_checkpoint_before_target(self):
        w = SimpleNamespace(); output = ['STUDIO_ANCHOR=0']
        g = {'_resume_mode_error':lambda rid:None, 'WSL_CASE':'/case', '_active_rid':lambda:'12', '_shq':lambda s:repr(s),
             '_resume_anchor_shell':lambda *a:'CHECK; ', 'wsl':lambda *a,**kw:(True,output[0])}
        install(w,g)
        c = {'result_key':'legacy:12','end_s':20}
        for value in ('0', '20', ''):
            output[0] = 'STUDIO_ANCHOR='+value
            self.assertFalse(w.legacy_recovery(c)['resume'])
        output[0] = 'STUDIO_ANCHOR=5'
        self.assertEqual(w.legacy_recovery(c)['anchor'], 5)
        g['wsl'] = lambda *a,**kw:(False, 'missing fields')
        self.assertFalse(w.legacy_recovery(c)['resume'])

if __name__ == '__main__': unittest.main()
