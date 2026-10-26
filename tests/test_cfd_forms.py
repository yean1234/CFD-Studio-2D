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

    def test_input_options_follow_template_adapter_and_preserve_explicit_definition(self):
        form=self.new_form('Any project target')
        schema=copy.deepcopy(self.w.form(form['id'])['input_schema'])
        run=next(f for f in schema['fields'] if f['key']=='run')
        output=next(f for f in run['fields'] if f['key']=='output_fields')
        self.assertIn('flow',output['item_enum'])
        output['item_enum']=['flow','custom_field']
        self.w.save_form('Renamed target',form['model'],form['solver'],form['config'],
                         form_id=form['id'],revision=form['revision'],input_schema=schema)
        fresh=self.w.form(form['id'])
        run=next(f for f in fresh['input_schema']['fields'] if f['key']=='run')
        self.assertEqual(next(f for f in run['fields'] if f['key']=='output_fields')['item_enum'],['flow','custom_field'])

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

    def test_project_initial_config_overrides_preset_template_for_validation(self):
        config = copy.deepcopy(self.w.template('config:immersion_2d'))
        config['section_2d'].update({
            'x_mm': 185,
            'represented_width_mm': 456,
            'thickness_mm': 3.0,
            'coil_UA_W_mK': 235.87,
        })

        project = self.w.create_project(
            'TMC49 2D',
            default_preset='config:immersion_2d',
            storage_path=str(self.base/'tmc49-2d'),
            form_id='immersion',
            initial_config=config,
        )

        self.assertEqual(project['default_preset'], 'config:immersion_2d')
        self.assertEqual(project['initial_config'], config)

    def test_2d_preset_auto_values_and_case_save_validate_submitted_config(self):
        from cfd_studio.execution_workspace import validate_settings
        preset = self.w.template('config:immersion_2d')
        self.assertIsNone(preset['section_2d']['x_mm'])
        self.assertEqual(validate_settings(copy.deepcopy(preset)), 'immersion')
        broken = copy.deepcopy(preset)
        broken['section_2d']['cpu_index'] = None
        with self.assertRaisesRegex(ValueError, 'section_2d.cpu_index'):
            validate_settings(broken)

        project = self.w.create_project('TMC49 2D case', default_preset='config:immersion_2d',
                                        storage_path=str(self.base/'tmc49-2d-case'), form_id='immersion')
        config = copy.deepcopy(preset)
        config['section_2d'].update({'x_mm': 185, 'thickness_mm': 3.0})
        saved = self.w.save_case(project['id'], 'TMC49_2D_baseline', config, preset_id='config:immersion_2d')
        case = self.w.queue_data()['cases'][saved['run_key']]
        self.assertEqual(case['config']['section_2d']['x_mm'], 185)
        self.assertEqual(case['preset_id'], 'config:immersion_2d')

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

class FormMetadataTests(unittest.TestCase):
    setUp = FormTests.setUp
    def test_templates_supply_solver_specific_inputs_without_mutating_forms(self):
        before = copy.deepcopy(self.w.forms())
        templates = self.w.form_templates()
        steady = next(t for t in templates if t['solver'] == 'simpleFoam')
        transient = next(t for t in templates if t['solver'] == 'pimpleFoam')
        self.assertEqual(steady['config']['run']['time_basis'], 'iterations')
        self.assertEqual(transient['config']['run']['time_basis'], 'physical_time')
        self.assertEqual(transient['config']['openfoam_mapping']['pressure_velocity_coupling'], 'PIMPLE')
        transient['config']['run']['output_fields'].clear()
        self.assertEqual(self.w.forms(), before)
        self.assertFalse(any(t['solver'] == 'icoFoam' for t in templates))

    def test_form_names_and_output_capabilities_are_metadata(self):
        form = self.w.form('immersion')
        self.w.save_form('Custom cooling', form['model'], form['solver'], form['config'], form['id'], form['revision'])
        template = next(t for t in self.w.form_templates() if t['model'] == 'immersion')
        self.assertEqual(template['name'], 'Custom cooling')
        self.assertEqual(self.w.form('immersion')['capabilities']['default_output_fields'], ['bubble', 'phase', 'flow', 'therm'])

    def test_unassigned_projects_do_not_silently_become_warehouse_forms(self):
        self.assertIsNone(self.w.project_form({'runs': []}))
        self.assertIsNone(self.w.project_form({'runs': ['x']}, {'x': {'model': 'custom'}}))
        records = {'a': {'model': 'immersion'}, 'b': {'model': 'grain_silo'}}
        self.assertIsNone(self.w.project_form({'runs': ['a', 'b']}, records))
        self.assertEqual(self.w.project_form({'runs': ['a']}, records), 'immersion')
        self.assertEqual(self.w.project_form({'runs': ['w']}, {'w': {'kind': 'warehouse', 'model': 'normalized_gable_verification'}}), 'warehouse')

    def test_unavailable_legacy_paths_do_not_hide_known_form(self):
        project={'runs':['legacy:old-name','legacy:moved','legacy:current']}
        records={'legacy:current':{'kind':'legacy','model':'immersion'}}
        before=copy.deepcopy(project)
        self.assertEqual(self.w.project_form(project,records),'immersion')
        self.assertEqual(project,before)
        self.assertIsNone(self.w.project_form(project,{}))

    def test_archived_tracer_results_do_not_override_warehouse_form(self):
        project={'runs':['w','tracer','missing']}
        records={'w':{'kind':'warehouse','model':'clo2_coupled_scenario'},
                 'tracer':{'kind':'legacy','model':'gas_transport'}}
        self.assertEqual(self.w.project_form(project,records),'warehouse')
        self.assertIsNone(self.w.project_form({'runs':['tracer']},records))
        records['cooling']={'kind':'legacy','model':'immersion'}
        self.assertIsNone(self.w.project_form({'runs':['w','tracer','cooling']},records))
        self.assertEqual(self.w.project_form({'form_id':'explicit','runs':['w']},records),'explicit')

    def test_inferred_legacy_form_is_used_when_saving_new_case(self):
        project=self.w.create_project('Imported',storage_path=str(self.base/'imported'))
        data=read_json(self.w.folder/'projects.json')
        next(p for p in data['projects'] if p['id']==project['id'])['runs']=['missing','legacy:current']
        self.w.persist_catalog(data)
        record={'id':'legacy:current','kind':'legacy','model':'immersion','created':1,'status':'saved'}
        with patch.object(self.w,'discover',return_value={'legacy:current':record}):
            before=read_json(self.w.folder/'projects.json')
            snapshot=self.w.snapshot()
            self.assertEqual(snapshot['projects'][0]['form_id'],'immersion')
            saved=self.w.save_case(project['id'],'New Case',self.w.template('form:immersion'),preset_id='form:immersion')
            case=self.w.queue_data()['cases'][saved['run_key']]
            self.assertEqual(case['form_id'],'immersion')
            self.assertEqual(case['form_snapshot']['id'],'immersion')
            self.assertEqual(case['status'],'draft')
            self.assertEqual(read_json(self.w.folder/'projects.json'),before)
            with self.assertRaises(ValueError):
                self.w.save_case(project['id'],'Wrong model',self.w.template('warehouse'))
