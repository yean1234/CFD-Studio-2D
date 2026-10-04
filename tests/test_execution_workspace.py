import copy
import ast
import os
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

    def test_saved_presets_do_not_change_sources_or_existing_executions(self):
        before = self.hashes()
        source = (ROOT/'tracer_transport/warehouse_porous_convergence.json').read_bytes()
        result = self.workspace.save_preset('시험 설정', self.config)
        changed = self.workspace.template(result['id'])
        changed['numerics']['end_s'] = 600
        self.assertEqual(self.workspace.template(result['id'])['numerics']['end_s'], 300)
        self.assertEqual(self.hashes(), before)
        self.assertEqual((ROOT/'tracer_transport/warehouse_porous_convergence.json').read_bytes(), source)
        with self.assertRaises(FileExistsError): self.workspace.save_preset('시험 설정', changed)
        with self.assertRaises(ValueError): self.workspace.template('config:../../secret')

    def test_legacy_membership_and_live_settings_survive_running_state(self):
        before = self.hashes()
        self.workspace.snapshot()
        target = self.workspace.create_project('이중액침')
        self.workspace.attach_legacy(target['id'], '2')
        self.workspace.live = lambda: {'rid':'2','running':True,'log':'live solver log'}
        snapshot = self.workspace.snapshot()
        self.assertTrue(snapshot['busy'])
        self.assertEqual([r['id'] for r in snapshot['projects'][1]['runs']], ['legacy:2'])
        detail = self.workspace.detail('legacy:2')
        self.assertEqual(detail['log'], 'live solver log')
        self.assertEqual(detail['config']['run']['end_time_s'], 2)
        self.assertEqual(self.hashes(), before)
        self.assertNotIn('config', snapshot['projects'][1])

    def test_grouped_legacy_run_refuses_busy_solver_before_hardware_or_mutations(self):
        import time
        tree = ast.parse((ROOT/'cfd_studio/app.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'H')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_run_legacy')
        env = {'EXECUTION_WORKSPACE':self.workspace, 'time':time, 'STATE':{},
               'get_status':lambda:{'running':True}, '_active_rid':lambda:'2'}
        import sys
        from cfd_studio import execution_workspace
        with patch.dict(sys.modules, {'execution_workspace':execution_workspace}):
            exec(compile(ast.Module(body=[method],type_ignores=[]), '<legacy-run>', 'exec'), env)
            handler = Mock()
            config = read_json(ROOT/'cfd_studio/configs/immersion.json')
            project = self.workspace.snapshot()['projects'][0]['id']
            before = self.hashes()
            env['_run_legacy'](handler, {'mode':'fresh','config':config,'execution_project_id':project,'execution_name':'new'})
            self.assertEqual(handler._json.call_args.args[1], 409)
            self.assertEqual(self.hashes(), before)

    def test_grouped_legacy_launch_snapshots_settings_and_preserves_pending_draft(self):
        import time, re, sys
        from cfd_studio import execution_workspace
        config = read_json(ROOT/'cfd_studio/configs/immersion.json')
        config['run']['output_fields'] = ['flow', 'therm']
        project = self.workspace.create_project('new group')['id']
        frames = self.base/'frames';frames.mkdir()
        pending = self.base/'pending.json';pending.write_text('{"name":"untouched"}')
        def create(rid, name, meta):
            folder = self.projects/rid;folder.mkdir()
            atomic_json(folder/'meta.json', {**meta, 'run_id':rid})
            return str(folder)
        def active():
            path = frames/'_runid.txt'
            return path.read_text() if path.exists() else '2'
        env = dict(EXECUTION_WORKSPACE=self.workspace, time=time, re=re, os=os, json=json,
            STATE={}, PENDF=str(pending), FRAME_DIR=str(frames), WSL_CASE='/case',
            get_status=lambda:{'running':False}, _active_rid=active,
            _project_key=lambda v:v, project_config=lambda rid:{}, _extract_state=lambda rid:{},
            _solver_mode=lambda:'cpu', _prepare_run_hardware=lambda:(True,''),
            _normalize_output_fields=lambda v:v, _apply_board_floor_revision=lambda c:(c,False),
            _persist_project_progress=Mock(), sync_case_files=lambda:(True,''),
            _write_runtime_config=lambda c:'inline.json', _apply_config_file=lambda p:(True,'APPLIED'),
            _create_run_project=create, get_config=lambda:config, meta_write=atomic_json,
            wsl=lambda cmd:(True,''), _run_mpi_np=lambda m:1, _run_of_bash=lambda m:'source foam',
            gpu_index=lambda:0, _case_kill_script=lambda p:'', _archive_current_progress_script=lambda *a:'',
            _mode_public=lambda m:('cpu','CPU'), cpu_pct=lambda:50, open_console=Mock(return_value=True),
            list_projects=lambda:[])
        tree = ast.parse((ROOT/'cfd_studio/app.py').read_text())
        cls = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='H')
        method = next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_run_legacy')
        handler=Mock();before=self.hashes()
        with patch.dict(sys.modules, {'execution_workspace':execution_workspace}):
            exec(compile(ast.Module(body=[method],type_ignores=[]),'<legacy-run>','exec'),env)
            env['_run_legacy'](handler, {'mode':'fresh','config':config,'config_ref':'inline',
                'execution_project_id':project,'execution_name':'new execution'})
        response=handler._json.call_args.args[0]
        self.assertTrue(response['ok'], response)
        self.assertEqual(env['open_console'].call_count,1)
        self.assertEqual(read_json(self.projects/response['rid']/'case_config.json'),config)
        group=next(p for p in self.workspace.snapshot()['projects'] if p['id']==project)
        self.assertEqual([r['rid'] for r in group['runs']], [response['rid']])
        self.assertEqual(pending.read_text(),'{"name":"untouched"}')
        self.assertTrue(all(self.hashes()[p]==digest for p,digest in before.items()))

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
            saved=read_json(self.workspace.attempt_folder(project,job['id'],job['id'])/'input.json')
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

    def test_restore_external_is_idempotent_and_does_not_import_siblings(self):
        external=self.base/'archive'/'3mm_Test';external.mkdir(parents=True)
        atomic_json(external/'meta.json',{'run_id':'1787048959','name':'3mm_Test','tmax':52.49})
        atomic_json(external/'case_config.json',{'tank':{},'dielectric_fluid':{}})
        (external/'flow_0.bin').write_bytes(b'original')
        sibling=external.parent/'unrelated';sibling.mkdir()
        atomic_json(sibling/'meta.json',{'run_id':'unrelated'})
        before={p.name:p.read_bytes() for p in external.iterdir()}
        result=self.workspace.restore_external('이중액침',external)
        self.assertEqual(result,self.workspace.restore_external('이중액침',external))
        snap=self.workspace.snapshot()
        self.assertEqual(len(snap['projects']),2)
        self.assertEqual(len(snap['projects'][0]['runs']),3)
        restored=snap['projects'][1]
        self.assertEqual(len(restored['runs']),1)
        self.assertEqual(restored['runs'][0]['model'],'immersion')
        self.assertEqual(self.workspace.external_paths(),[external])
        self.assertEqual(before,{p.name:p.read_bytes() for p in external.iterdir()})
        self.assertTrue(self.workspace.detail(result['run_key'])['has_results'])
        restarted=ExecutionWorkspace(ROOT,[self.projects],folder=self.workspace.folder,output=self.workspace.output)
        self.assertEqual(restarted.snapshot(),snap)

    def test_linked_result_viewing_never_upgrades_original_phase_files(self):
        tree=ast.parse((ROOT/'cfd_studio/app.py').read_text())
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_upgrade_phase_project')
        context={'os':os,'EXECUTION_WORKSPACE':Mock(external_paths=lambda:[self.base])}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'<phase upgrade>','exec'),context)
        with patch.object(os,'listdir') as listing:
            self.assertEqual(context['_upgrade_phase_project'](self.base),0)
            listing.assert_not_called()

    def test_restore_rejects_missing_metadata_without_changing_catalog(self):
        before=self.workspace.snapshot()
        with self.assertRaises(ValueError):self.workspace.restore_external('이중액침',self.base/'absent')
        self.assertEqual(self.workspace.snapshot(),before)

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

class GenericResultLogTests(unittest.TestCase):
    def test_configured_solver_log_precedes_other_solver_and_setup_logs(self):
        from cfd_studio.execution_workspace import result_logs
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('log.blockMesh', 'log.simpleFoam', 'log.customSolver', 'execution.log'):
                (root/name).write_text(name)
            candidates = result_logs(root, {'analysis': {'solver': 'customSolver'}})
            actual = [p.name for p in candidates if p.is_file()]
            self.assertEqual(actual[0], 'log.customSolver')
            self.assertEqual(actual[-1], 'log.blockMesh')
            self.assertTrue(all(p.parent == root for p in result_logs(root, {'solver': '../secret'})))

    def test_managed_result_uses_archived_solver_log(self):
        from cfd_studio.execution_workspace import result_logs
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root/'Raw_Data'/'Case_State'
            archive.mkdir(parents=True)
            (archive/'log.simpleFoam').write_text('Time = 90\nEnd\n')
            paths = result_logs(root, {'openfoam_mapping': {'solver': 'simpleFoam'}})
            self.assertEqual(next(p for p in paths if p.is_file()), archive/'log.simpleFoam')
