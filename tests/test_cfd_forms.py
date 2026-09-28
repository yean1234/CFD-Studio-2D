import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from cfd_studio.execution_workspace import ExecutionWorkspace, post_route, read_json

ROOT = Path(__file__).resolve().parents[1]


class FormTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.w = ExecutionWorkspace(ROOT, [], folder=self.base/'registry', output=self.base/'output')

    def new_form(self, name='액침 양식'):
        f = self.w.form('immersion')
        return self.w.save_form(name, f['model'], f['solver'], f['config'], sections={'tank': '수조 치수'})

    def project(self, f):
        return self.w.create_project('프로젝트', default_preset='form:'+f['id'], storage_path=str(self.base/'project'), form_id=f['id'])

    def test_project_route_requires_form_and_rejects_cross_form_preset(self):
        h = Mock(path='/api/executions/project')
        post_route(h, self.w, {'name':'프로젝트'})
        self.assertEqual(h._json.call_args.args[1], 400)
        self.assertFalse((self.base/'registry/projects.json').exists())
        with self.assertRaises(ValueError):
            self.w.create_project('잘못된 프로젝트', default_preset='warehouse', form_id='immersion')

    def test_separate_forms_of_same_engine_have_separate_presets(self):
        f = self.new_form()
        with self.assertRaises(ValueError): self.w.check_form_preset(f['id'], 'config:immersion')
        saved = self.w.save_preset('기본값', f['config'], f['id'])
        self.assertEqual(self.w.preset_form(saved['id']), f['id'])
        self.w.check_form_preset(f['id'], saved['id'])
        with self.assertRaises(ValueError): self.w.check_form_preset('immersion', saved['id'])
        with self.assertRaises(ValueError): self.w.save_preset('오류', self.w.template(), f['id'])

    def test_form_edits_and_restart_preserve_case_input_and_baseline(self):
        f = self.new_form(); p = self.project(f)
        c = copy.deepcopy(f['config']); c['run']['output_fields'] = ['flow', 'therm']
        saved = self.w.save_case(p['id'], 'Case A', c, preset_id='form:'+f['id'])
        before = self.w.queue_data()['cases'][saved['run_key']]
        changed = copy.deepcopy(f['config']); changed['heater']['total_W'] += 50
        self.w.save_form('이름 수정', f['model'], f['solver'], changed, f['id'], f['revision'], sections={'tank':'수조 크기'})
        fresh = ExecutionWorkspace(ROOT, [], folder=self.base/'registry', output=self.base/'output')
        self.assertEqual(fresh.queue_data()['cases'][saved['run_key']], before)
        self.assertEqual(fresh.form(f['id'])['name'], '이름 수정')
        self.assertEqual(fresh.snapshot()['projects'][0]['form_id'], f['id'])
        self.assertEqual(fresh.template('form:'+f['id'])['heater']['total_W'], changed['heater']['total_W'])

    def test_form_revision_and_engine_are_protected(self):
        f = self.new_form()
        with self.assertRaises(ValueError): self.w.save_form('stale', f['model'], f['solver'], f['config'], f['id'], 0)
        silo = self.w.form('grain_silo')
        with self.assertRaises(ValueError): self.w.save_form('교체', silo['model'], silo['solver'], silo['config'], f['id'], 1)
        with self.assertRaises(ValueError): self.w.save_form('미지원', f['model'], 'unknownSolver', f['config'])

    def test_case_rejects_wrong_model_without_changing_queue(self):
        f = self.new_form(); p = self.project(f); before = self.w.queue_data()
        with self.assertRaises(ValueError): self.w.save_case(p['id'], '오류', self.w.template(), preset_id='warehouse')
        self.assertEqual(self.w.queue_data(), before)

    def test_optional_preset_failure_is_atomic_and_form_scoped(self):
        f = self.new_form(); p = self.project(f); c = f['config']
        c['run']['output_fields'] = ['flow']
        saved = self.w.save_case(p['id'], 'Case', c, preset_id='form:'+f['id'])
        before = self.w.queue_data()
        with patch.object(self.w, 'save_queue', side_effect=OSError('disk')):
            with self.assertRaises(OSError): self.w.save_case(p['id'], 'Case 2', c, preset_id='form:'+f['id'], preset_name='new')
        self.assertEqual(self.w.queue_data(), before)
        self.assertFalse(any(x['name']=='new' for x in self.w.presets()))
        self.w.save_case(p['id'], 'Case 3', c, preset_id='form:'+f['id'], preset_name='new')
        self.assertEqual([x['form_id'] for x in self.w.presets() if x['name']=='new'], [f['id']])

    def test_existing_builtin_config_bytes_are_preserved(self):
        paths = [ROOT/'cfd_studio/configs/immersion.json',ROOT/'cfd_studio/configs/grain_silo.json',ROOT/'tracer_transport/warehouse_porous_convergence.json']
        before = [p.read_bytes() for p in paths]
        forms = self.w.forms()
        self.assertEqual([x['name'] for x in forms], ['이중액침냉각','옥수수 사일로','식량 저장고 훈증 시스템'])
        f = forms[0]
        self.w.save_form('변경',f['model'],f['solver'],f['config'],f['id'],f['revision'])
        self.assertEqual([p.read_bytes() for p in paths], before)
