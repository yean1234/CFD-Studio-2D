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

if __name__=='__main__':unittest.main()
