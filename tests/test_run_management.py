import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from cfd_studio.execution_workspace import ExecutionWorkspace, read_json, atomic_json
from cfd_studio.run_management import termination

ROOT = Path(__file__).resolve().parents[1]


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.w = ExecutionWorkspace(ROOT, [], folder=self.root/'workspace', output=self.root/'output')
        self.p = self.w.create_project('comparison', 'purpose', 'warehouse')
        self.config = self.w.template()
        self.config['numerics'].update(end_s=2, dt_s=.1, write_interval_s=1)
        self.config['_studio'] = {'termination': {'mode':'time', 'time_s':2}, 'goals':'test'}

    def case(self, name='run', **extra):
        return self.w.save_case(self.p['id'], name, self.config, preset_id='warehouse', **extra)['run_key']

    def dispatch(self):
        process = Mock(); process.poll.return_value = None
        with patch.object(self.w, '_command', return_value=['solver']), patch('cfd_studio.run_management.subprocess.Popen', return_value=process):
            self.w.queue_tick()
        return process

    def finish(self, key, state='complete'):
        c = self.w.queue_data()['cases'][key]
        job_path = c['attempts'][-1]['job_path']; j = read_json(job_path);j.update(status=state, error='test failure' if state=='failed' else '', completion_reason='time');atomic_json(job_path,j)
        self.w.queue_tick()

    def test_default_change_only_affects_future_drafts_and_presets_are_independent(self):
        saved = self.w.save_preset('source', self.config)
        original = self.w.template(saved['id'])
        self.w.edit_project(self.p['id'],'comparison','details',saved['id'])
        key = self.case()
        changed = copy.deepcopy(self.config);changed['_studio']['termination']['time_s']=3
        self.w.save_case(self.p['id'],'changed',changed,key,1)
        self.assertEqual(self.w.template(saved['id']),original)
        self.w.edit_project(self.p['id'],'comparison','new purpose','config:immersion')
        self.assertEqual(self.w.detail(key)['config']['numerics']['end_s'],3)
        self.assertEqual(next(p for p in self.w.snapshot()['projects'] if p['id']==self.p['id'])['default_preset'],'config:immersion')

    def test_duplicate_optional_preset_failure_does_not_change_draft(self):
        key=self.case();self.w.save_preset('taken',self.config)
        before=(self.w.folder/'queue.json').read_bytes()
        with self.assertRaises(FileExistsError):self.w.save_case(self.p['id'],'changed',self.config,key,1,preset_name='taken')
        self.assertEqual((self.w.folder/'queue.json').read_bytes(),before)
        result=self.w.save_case(self.p['id'],'changed',self.config,key,1,preset_name='new')
        self.assertTrue(result['preset']['id'].startswith('scoped:'))
        self.assertEqual(self.w.preset_form(result['preset']['id']), 'warehouse')
        self.assertEqual(self.w.template(result['preset']['id']),self.w.detail(key)['config'])

    def test_three_runs_order_edit_pause_and_immutable_attempt(self):
        ids=[self.case(str(i)) for i in range(3)]
        self.w.queue_action('enqueue',ids=ids)
        self.w.queue_action('reorder',ids=[ids[1],ids[0],ids[2]])
        cfg=copy.deepcopy(self.config);cfg['_studio']['termination']={'mode':'frames','frames':4,'include_initial':True}
        self.w.save_case(self.p['id'],'frames',cfg,ids[1],1)
        self.w.queue_action('resume');self.dispatch()
        q=self.w.queue_data();self.assertEqual(q['active'],ids[1])
        path=Path(q['cases'][ids[1]]['attempts'][-1]['job_path']).with_name('input.json')
        frozen=path.read_bytes()
        self.assertEqual(read_json(path)['numerics']['end_s'],3)
        with self.assertRaises(ValueError):self.w.save_case(self.p['id'],'illegal',self.config,ids[1],2)
        with self.assertRaises(ValueError):self.w.queue_action('remove',case_id=ids[1])
        self.w.queue_action('pause');self.finish(ids[1]);self.dispatch()
        self.assertIsNone(self.w.queue_data()['active']);self.assertEqual(path.read_bytes(),frozen)
        self.w.queue_action('resume');self.dispatch();self.finish(ids[0]);self.dispatch();self.finish(ids[2]);self.dispatch()
        self.assertTrue(all(c['status']=='complete' for c in self.w.queue_data()['cases'].values()))
        with self.assertRaises(ValueError):self.w.queue_action('enqueue',ids=[ids[0]])

    def test_failure_blocks_next_retry_retains_old_attempt_and_skip_requires_resume(self):
        a,b=self.case('a'),self.case('b');self.w.queue_action('enqueue',ids=[a,b]);self.w.queue_action('resume');self.dispatch();self.finish(a,'failed')
        self.assertEqual(self.w.queue_data()['failure'],a)
        with self.assertRaises(ValueError):self.w.queue_action('resume')
        self.w.queue_action('retry',case_id=a);self.w.queue_action('resume');self.dispatch()
        attempts=self.w.queue_data()['cases'][a]['attempts'];self.assertEqual(len(attempts),2);self.assertNotEqual(attempts[0]['job_path'],attempts[1]['job_path'])
        self.finish(a,'failed');self.w.queue_action('skip',case_id=a);self.dispatch();self.assertIsNone(self.w.queue_data()['active'])
        self.w.queue_action('resume');self.dispatch();self.assertEqual(self.w.queue_data()['active'],b)

    def test_restart_keeps_active_and_queue_and_never_replays_attempt(self):
        a,b=self.case('a'),self.case('b');self.w.queue_action('enqueue',ids=[a,b]);self.w.queue_action('resume');self.dispatch()
        restarted=ExecutionWorkspace(ROOT,[],folder=self.w.folder,output=self.w.output)
        restarted.start_queue_service();self.addCleanup(restarted._queue_shutdown.set)
        self.assertTrue(restarted.queue_data()['paused']);self.assertEqual(restarted.queue_data()['order'],[b])
        with patch('cfd_studio.run_management.subprocess.Popen') as launch:restarted.queue_tick();launch.assert_not_called()
        self.finish(a);restarted.queue_tick();self.assertEqual(restarted.queue_data()['cases'][a]['status'],'complete')
        self.assertEqual(len(restarted.queue_data()['cases'][a]['attempts']),1)

    def test_stale_editor_and_invalid_reorder_do_not_overwrite(self):
        a=self.case();self.w.save_case(self.p['id'],'revision2',self.config,a,1)
        with self.assertRaises(ValueError):self.w.save_case(self.p['id'],'stale',self.config,a,1)
        self.w.queue_action('enqueue',ids=[a])
        with self.assertRaises(ValueError):self.w.queue_action('reorder',ids=[])
        self.assertEqual(self.w.queue_data()['order'],[a])

    def test_stop_targets_only_active_attempt_and_preserves_waiting(self):
        a,b=self.case('a'),self.case('b');self.w.queue_action('enqueue',ids=[a,b]);self.w.queue_action('resume');self.dispatch()
        with self.assertRaises(ValueError):self.w.queue_action('stop',case_id=b)
        self.w.queue_action('stop',case_id=a)
        q=self.w.queue_data();self.assertEqual(q['order'],[b]);self.assertTrue(Path(q['cases'][a]['attempts'][-1]['job_path']).with_name('stop.json').exists())
        self.finish(a,'stopped');self.assertEqual(self.w.queue_data()['cases'][b]['status'],'queued')

    def test_termination_count_and_units_and_unsupported_convergence(self):
        before=copy.deepcopy(self.config)
        for initial,expected in [(True,2),(False,3)]:
            c=copy.deepcopy(before);c['_studio']['termination']={'mode':'frames','frames':3,'include_initial':initial}
            actual,policy,end=termination(c);self.assertEqual(end,expected);self.assertEqual(actual['numerics']['end_s'],expected)
        self.assertEqual(self.config,before)
        for policy in [{'mode':'convergence'},{'mode':'frames','frames':True},{'mode':'time','time_s':float('nan')}]:
            c=copy.deepcopy(before);c['_studio']['termination']=policy
            with self.assertRaises(ValueError):termination(c)

    def test_short_frame_target_does_not_repurpose_checkpoint_interval(self):
        config = self.w.template('config:immersion')
        original = copy.deepcopy(config)
        config['_studio'] = {'termination': {'mode':'frames', 'frames':3, 'include_initial':False}}
        saved, policy, end = termination(config)
        self.assertEqual(end, .03)
        self.assertEqual(saved['run']['write_interval_s'], original['run']['write_interval_s'])
        self.assertEqual(saved['run']['viz_interval_s'], .01)
        self.assertEqual(config['run']['end_time_s'], original['run']['end_time_s'])

    def test_preset_rename_updates_project_reference_without_touching_runs(self):
        p=self.w.save_preset('old',self.config);self.w.edit_project(self.p['id'],'comparison','',p['id']);key=self.case()
        before=self.w.detail(key)['config'];new=self.w.rename_preset(p['id'],'new')
        self.assertEqual(next(p for p in self.w.snapshot()['projects'] if p['id']==self.p['id'])['default_preset'],new['id'])
        self.assertEqual(self.w.detail(key)['config'],before)

if __name__=='__main__':unittest.main()
