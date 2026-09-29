import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cfd_studio.execution_workspace import ExecutionWorkspace,read_json
from cfd_studio.form_wizard import generate,profile
from cfd_studio.form_schema import config_from_schema,validate_values
from cfd_studio.solver_requirements import rules,inspect_config
from cfd_studio.solver_catalog import CATALOG
ROOT=Path(__file__).resolve().parents[1]

def filled(solver='icoFoam'):
    answers={k:v[0]['value'] for k,v in profile(solver)['options'].items()}
    result=generate(solver,answers);config=copy.deepcopy(result['config'])
    for rule in rules(solver,result['config'],config):
        values={'number':0,'positive':1,'integer':1,'nonnegative_integer':0,'text':'userValue','boolean':False,'object':{},'choice':rule['unit'],'unit':rule['unit'],'mapping':{'default':'userValue'},'sequence':['userValue'],'filled':{'value':1}}
        if rule['path']==['outputs','fields']:continue
        obj=config
        for k in rule['path'][:-1]:obj=obj.setdefault(k,{})
        obj[rule['path'][-1]]=values[rule['kind']]
    return result,config

class TemplateValuesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.kw=dict(folder=self.base/'registry',output=self.base/'results');self.w=ExecutionWorkspace(ROOT,[],**self.kw)
    def test_blank_definition_keeps_metadata_but_no_physical_defaults(self):
        for item in CATALOG:
            result,_=filled(item['id']);config=result['config']
            self.assertEqual(config['analysis']['solver'],item['id'])
            def visit(fields):
                for f in fields:
                    if f['type']=='object':visit(f['fields'])
                    elif not f.get('readonly'):self.assertIn(f['value'],(None,'',[]),f['key'])
            visit(result['config_schema']['fields'])
            self.assertTrue(item['upstream']);self.assertTrue(all(x['url'].startswith('https://') for x in item['upstream']))
    def test_project_values_and_scoped_preset_survive_restart_without_changing_definition(self):
        result,config=filled();self.assertEqual(inspect_config('icoFoam',config)['missing_count'],0)
        form=self.w.save_form('Custom','solver_definition','icoFoam',result['config'],config_schema=result['config_schema'],input_schema=result['config_schema'])
        baseline=copy.deepcopy(self.w.form(form['id']))
        project=self.w.create_project('A',form_id=form['id'],initial_config=config,preset_name='User inputs')
        self.assertEqual(self.w.preset_form(project['default_preset']),form['id'])
        fresh=ExecutionWorkspace(ROOT,[],**self.kw)
        self.assertEqual(fresh.form(form['id']),baseline)
        self.assertEqual(fresh.snapshot()['projects'][0]['initial_config'],config)
        self.assertEqual(read_json(Path(project['storage_path'])/'project.cfdproj')['initial_config'],config)
        with self.assertRaises(ValueError):fresh.save_case(project['id'],'Run',config)
    def test_missing_input_wrong_metadata_and_cross_template_presets_fail(self):
        result,config=filled();forms=[self.w.save_form(name,'solver_definition','icoFoam',result['config'],config_schema=result['config_schema']) for name in ('A','B')]
        with self.assertRaises(ValueError):self.w.create_project('Empty',form_id=forms[0]['id'],initial_config=result['config'])
        preset=self.w.save_scoped_preset('Inputs',config,forms[0]['id'])
        with self.assertRaises(ValueError):self.w.check_form_preset(forms[1]['id'],preset['id'])
        changed=copy.deepcopy(config);changed['analysis']['solver']='simpleFoam'
        with self.assertRaises(ValueError):self.w.check_project_config(forms[0]['id'],changed)
    def test_connected_project_input_is_independent_of_legacy_preset_and_case(self):
        form=self.w.form('immersion');before=copy.deepcopy(form['config']);value=copy.deepcopy(before);value['heater']['total_W']+=10
        project=self.w.create_project('Cooling',form_id=form['id'],initial_config=value)
        case=self.w.save_case(project['id'],'Run',value)
        self.assertEqual(self.w.template('form:immersion'),before)
        self.assertEqual(self.w.queue_data()['cases'][case['run_key']]['config']['heater']['total_W'],value['heater']['total_W'])
        self.assertIsNone(form['blank_config']['heater']['total_W'])
    def test_failed_project_storage_rolls_back_new_preset(self):
        form=self.w.form('immersion');before=self.w.presets()
        with patch.object(self.w,'prepare_project_folder',side_effect=OSError('disk')):
            with self.assertRaises(OSError):self.w.create_project('Fail',form_id=form['id'],initial_config=form['config'],preset_name='Should not remain')
        self.assertEqual(self.w.presets(),before)

if __name__=='__main__':unittest.main()
