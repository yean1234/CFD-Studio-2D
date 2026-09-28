import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from cfd_studio.execution_workspace import ExecutionWorkspace, read_json, atomic_json, post_route

ROOT = Path(__file__).resolve().parents[1]


class ExecutionWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.projects = self.base/'Project'
        for i in range(3):
            p = self.projects/f'old-{i}';p.mkdir(parents=True)
            atomic_json(p/'meta.json', {'run_id':str(i+1),'name':f'old-{i}','completed':True})
            atomic_json(p/'case_config.json', {'run':{'end_time_s':i+1}})
            (p/'flow_1.bin').write_bytes(bytes([i,2,3]))
        self.workspace = ExecutionWorkspace(ROOT,[self.projects],folder=self.base/'workspace',output=self.base/'output')
        self.config = self.workspace.template()

    def hashes(self):
        return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.projects.rglob('*') if p.is_file()}

    def test_consolidation_preserves_all_original_bytes_and_has_no_project_config(self):
        before=self.hashes();snap=self.workspace.snapshot()
        self.assertEqual(len(snap['projects']),1)
        self.assertEqual(len(snap['projects'][0]['runs']),3)
        self.assertNotIn('config',snap['projects'][0])
        self.assertEqual(before,self.hashes())
        self.assertEqual(self.workspace.snapshot(),snap)

    def test_project_switch_keeps_its_own_membership_without_settings(self):
        initial=self.workspace.snapshot()['projects'][0]
        second=self.workspace.create_project('second')
        snap=self.workspace.snapshot()
        self.assertEqual(len(snap['projects'][0]['runs']),3)
        self.assertEqual(snap['projects'][1]['runs'],[])
        self.workspace.rename_project(initial['id'],'renamed')
        self.assertEqual(self.workspace.snapshot()['projects'][0]['name'],'renamed')
        self.assertNotIn('config',second)

    def test_unknown_run_and_path_traversal_cannot_read_arbitrary_files(self):
        for key in ('../../secret','legacy:../../secret','warehouse:../x'):
            with self.assertRaises(ValueError):self.workspace.detail(key)
        d=self.workspace.detail('legacy:2')
        self.assertEqual(d['config']['run']['end_time_s'],2)
        self.assertIsNone(d['log_source'])

    def test_new_execution_freezes_input_and_reserves_one_slot(self):
        project=self.workspace.snapshot()['projects'][0]['id']
        with patch.object(self.workspace,'_command',return_value=['fake']), patch('cfd_studio.execution_workspace.subprocess.Popen') as popen, patch('cfd_studio.execution_workspace.threading.Thread'):
            popen.return_value=Mock()
            job=self.workspace.start(project,'first',self.config)
            self.config['numerics']['end_s']=600
            saved=read_json(self.workspace.folder/'runs'/job['id']/'input.json')
            self.assertEqual(saved['numerics']['end_s'],300)
            with self.assertRaisesRegex(ValueError,'진행 중'):self.workspace.start(project,'second',self.config)
            self.assertEqual(popen.call_count,1)
            self.assertEqual(len(self.workspace.snapshot()['projects'][0]['runs']),4)

    def test_invalid_settings_and_external_busy_create_no_run(self):
        project=self.workspace.snapshot()['projects'][0]['id']
        for value in (0,-1,True,'',float('nan')):
            spec=copy.deepcopy(self.config);spec['numerics']['dt_s']=value
            with self.assertRaises((ValueError,TypeError)):self.workspace.start(project,'bad',spec)
        self.workspace.busy=lambda:True
        with self.assertRaises(ValueError):self.workspace.start(project,'busy',self.config)
        self.assertFalse((self.workspace.folder/'runs').exists())

    def test_failed_launch_is_retained_without_changing_old_results(self):
        before=self.hashes();project=self.workspace.snapshot()['projects'][0]['id']
        with patch.object(self.workspace,'_command',side_effect=OSError('no environment')):
            with self.assertRaises(OSError):self.workspace.start(project,'failed',self.config)
        runs=self.workspace.snapshot()['projects'][0]['runs']
        failed=next(r for r in runs if r['name']=='failed')
        self.assertEqual(failed['status'],'failed')
        self.assertEqual(before,self.hashes())

    def test_windows_launcher_uses_exec_and_utf8_for_korean_paths(self):
        job_path=self.base/'한글 경로'/'job.json'
        with patch('cfd_studio.execution_workspace.os.name','nt'), patch('cfd_studio.execution_workspace.subprocess.check_output',return_value='/mnt/c/한글 경로\n') as convert:
            command=self.workspace._command(job_path)
        self.assertEqual(command[:3],['wsl.exe','--exec','bash'])
        for call in convert.call_args_list:
            self.assertIn('--exec',call.args[0])
            self.assertEqual(call.kwargs['encoding'],'utf-8')

    def test_invalid_http_body_returns_validation_error(self):
        handler=Mock();handler.path='/api/executions/start'
        self.assertTrue(post_route(handler,self.workspace,[]))
        self.assertEqual(handler._json.call_args.args[1],400)
        self.assertFalse((self.workspace.folder/'runs').exists())

    def test_concurrent_project_creation_does_not_drop_existing_membership(self):
        self.workspace.snapshot()
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(lambda i:self.workspace.create_project(f'p{i}'),range(8)))
        self.assertEqual(len(self.workspace.snapshot()['projects']),9)
        self.assertEqual(len(self.workspace.snapshot()['projects'][0]['runs']),3)


if __name__=='__main__':unittest.main()
