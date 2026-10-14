import copy
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from cfd_studio.execution_adapters import install
from cfd_studio.run_management import termination
from cfd_studio.execution_workspace import read_json

ROOT=Path(__file__).resolve().parents[1]

class AdapterTests(unittest.TestCase):
    def test_result_poll_is_nonblocking_and_isolated_by_attempt(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        def status():
            entered.set()
            release.wait(2)
            return {'running': False, 'completed': False}
        w = SimpleNamespace()
        install(w, {'_active_rid': lambda: 'first', 'get_status': status})
        case = {'result_key': 'legacy:first', 'attempts': [{'id': 'a', 'started': 0}]}
        def call():
            w.legacy_poll(case)
            finished.set()
        threading.Thread(target=call, daemon=True).start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertTrue(finished.wait(.2), 'Result polling blocked the queue/UI caller')
            other = {'result_key': 'legacy:second', 'attempts': [{'id': 'b', 'started': 0}]}
            self.assertEqual(w.legacy_poll(other)['status'], 'running')
        finally:
            release.set()

    def test_transient_file_lock_during_poll_does_not_fail_running_case(self):
        calls = []
        def status():
            calls.append(1)
            if len(calls) == 1:
                raise PermissionError(13, 'Permission denied', 'meta.json')
            return {'running': True}
        w = SimpleNamespace()
        install(w, {'_active_rid': lambda: 'first', 'get_status': status})
        case = {'result_key': 'legacy:first', 'attempts': [{'id': 'lock', 'started': 0}]}
        for _ in range(100):
            w.legacy_poll(case)
            if len(calls) >= 2:
                break
            threading.Event().wait(.01)
        self.assertGreaterEqual(len(calls), 2, 'A locked meta.json stopped later polling')
        self.assertEqual(w.legacy_poll(case)['status'], 'running')

    def test_immersion_frame_policy_uses_visual_output_interval_not_restart_interval(self):
        c=read_json(ROOT/'cfd_studio/configs/immersion.json')
        c['_studio']={'termination':{'mode':'frames','frames':101,'include_initial':True}}
        result,policy,end=termination(c)
        self.assertEqual(end,1)
        self.assertEqual(result['run']['write_interval_s'],.5)
        self.assertEqual(result['run']['viz_interval_s'],.01)
        self.assertEqual(c['run']['end_time_s'],60)

    def test_missing_middle_or_truncated_selected_field_requests_update(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)
            cfg={'run':{'output_fields':['flow','therm'],'viz_interval_s':1},'_studio':{'termination':{'mode':'frames','frames':3,'include_initial':True}}}
            for field in ['flow','therm']:
                for t in range(3):(path/f'{field}_{t}.bin').write_bytes(b'valid'*12)
            w=SimpleNamespace()
            g={'project_inventory':lambda p:{'flow':3,'therm':3,'tmax':2},'project_config':lambda rid:cfg,
               '_read_json_file':lambda p:{'last_time':2},'_extract_state':lambda rid:{},'_extract_public':lambda rid:{},
               '_valid_viz_output':lambda p,kind:Path(p).read_bytes()==b'valid'*12}
            install(w,g)
            record={'kind':'legacy','rid':'example','path':td}
            self.assertEqual(w.result_info(record)['result_status'],'ready')
            (path/'therm_1.bin').unlink()
            self.assertEqual(w.result_info(record)['result_status'],'update')
            (path/'therm_1.bin').write_bytes(b'bad')
            self.assertEqual(w.result_info(record)['result_status'],'update')
            (path/'therm_1.bin').write_bytes(b'valid'*12)
            self.assertEqual(w.result_info(record)['result_status'],'ready')
            g['_extract_state']=lambda rid:{'busy':True}
            self.assertEqual(w.result_info(record)['result_status'],'preparing')
            self.assertFalse(w.result_info(record)['can_generate'])

    def test_project_storage_waits_while_allrun_post_processing_runs(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)
            cfg={'run':{'output_fields':['flow'],'viz_interval_s':1},'_studio':{'termination':{'mode':'time','time_s':2}}}
            for t in range(3):(path/f'flow_{t}.bin').write_bytes(b'valid'*12)
            busy=[True];calls=[]
            def wsl(script,timeout=None):
                calls.append(script)
                if 'ALLRUN_BUSY' in script:
                    return True,'ALLRUN_BUSY' if busy[0] else ''
                return True,'PROJECT_SAVED'
            g={'project_inventory':lambda p:{'flow':3,'tmax':2},'project_config':lambda rid:cfg,
               '_read_json_file':lambda p:{'last_time':2},'_extract_state':lambda rid:{},'_extract_public':lambda rid:{},
               '_valid_viz_output':lambda p,kind:True,'_active_rid':lambda:'r','get_status':lambda:{'running':False,'completed':True},
               'proj_dir':lambda rid:td,'wsl':wsl,'_wsl_case_token':lambda:'~/case','win2wsl':lambda p:p,'_shq':lambda p:"'"+p+"'"}
            w=SimpleNamespace();install(w,g)
            case={'result_key':'legacy:r','config':cfg,'attempts':[{'id':'store','started':0,'job_path':str(path/'job.json')}]}
            def settle():
                for _ in range(200):
                    result=w.legacy_poll(case)
                    if result['status']!='running' or calls:break
                    threading.Event().wait(.01)
                threading.Event().wait(.05)
                return w.legacy_poll(case)
            self.assertEqual(settle()['status'],'running')
            self.assertFalse(any('rsync' in c for c in calls),'Copy started while Allrun was still writing')
            busy[0]=False;calls.clear()
            for _ in range(200):
                if w.legacy_poll(case)['status']=='complete':break
                threading.Event().wait(.01)
            self.assertEqual(w.legacy_poll(case)['status'],'complete')
            self.assertTrue((path/'storage_complete.json').is_file())

    def test_initial_frame_cell_centres_use_options_valid_for_postprocess(self):
        # OpenFOAM v2312 postProcess rejects -withZero; only reconstructPar accepts it.
        source=(ROOT/'cfd_studio/app.py').read_text(encoding='utf-8')
        lines=[line for line in source.splitlines() if 'postProcess' in line and 'writeCellCentres' in line]
        self.assertTrue(lines)
        self.assertFalse([line for line in lines if 'withZero' in line or 'ZERO_OPT' in line])
        self.assertIn('-withZero',' '.join(l for l in source.splitlines() if 'with_zero =' in l))

if __name__=='__main__':unittest.main()
