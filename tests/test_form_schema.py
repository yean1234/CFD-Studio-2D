import copy
import json
import tempfile
import unittest
from pathlib import Path
from cfd_studio.execution_workspace import ExecutionWorkspace
from cfd_studio.form_schema import config_from_schema,validate_schema

ROOT=Path(__file__).resolve().parents[1]

def sample():
    return {'version':1,'fields':[{'key':'domain','type':'object','fields':[
        {'key':'length','type':'number','unit':'m','value':12.5},
        {'key':'shape','type':'string','value':'house'}]},
        {'key':'zones','type':'array','value':[{'origin':[0,0,0]}]},
        {'key':'enabled','type':'boolean','value':False}]}

class FormSchemaTests(unittest.TestCase):
    def test_nested_config_units_and_solver_independence_survive_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            w=ExecutionWorkspace(ROOT,[],folder=Path(folder)/'registry',output=Path(folder)/'output')
            schema=sample();config=config_from_schema(schema)
            saved=w.save_form('User domain','solver_definition','simpleFoam',config,config_schema=schema)
            fresh=ExecutionWorkspace(ROOT,[],folder=Path(folder)/'registry',output=Path(folder)/'output')
            form=fresh.form(saved['id']);self.assertEqual(form['config'],config);self.assertEqual(form['config_schema'],schema)
            self.assertTrue(form['definition_only'])
            with self.assertRaisesRegex(ValueError,'초안'):fresh.check_form_config(form['id'],config)
            edited=copy.deepcopy(schema);edited['fields'][0]['fields'][0]['value']=15
            fresh.save_form('User domain','solver_definition','simpleFoam',config_from_schema(edited),saved['id'],1,config_schema=edited)
            self.assertEqual(saved['config']['domain']['length'],12.5)

    def test_common_template_route_returns_editable_json_without_mutating_saved_form(self):
        from cfd_studio.execution_workspace import get_route
        class Handler:
            path='/api/executions/config-template'
            def _json(self,value,*args):self.value=value
        handler=Handler()
        self.assertTrue(get_route(handler,None))
        config=handler.value['config']
        self.assertEqual(config,json.loads((ROOT/'cfd_studio/templates/cfd-config-template.json').read_text()))
        self.assertEqual(len(config),9)
        self.assertIsNone(config['numerics']['time_step'])
        self.assertEqual(config['geometry']['regions'],[])
        # Loading the starter file is read-only and returns independent data.
        config['geometry']['regions'].append({'name':'user_region'})
        second=Handler();get_route(second,None)
        self.assertEqual(second.value['config']['geometry']['regions'],[])

    def test_blank_definition_does_not_inject_geometry(self):
        self.assertEqual(config_from_schema({'version':1,'fields':[]}),{})

    def test_invalid_fields_and_config_mismatch_are_rejected(self):
        for kind,value in [('integer',1.5),('number',True),('number',float('inf')),('array','[]'),('boolean',0)]:
            with self.subTest(kind=kind,value=value),self.assertRaises(ValueError):config_from_schema({'version':1,'fields':[{'key':'x','type':kind,'value':value}]})
        with self.assertRaises(ValueError):validate_schema(sample(),{'wrong':1})
        with self.assertRaises(ValueError):validate_schema({'version':1,'fields':[{'key':'x','type':'boolean','value':False}]},{'x':0})
        for key in ('__proto__','constructor','prototype'):
            with self.assertRaises(ValueError):config_from_schema({'version':1,'fields':[{'key':key,'type':'number','value':1}]})
        s=sample();s['fields'].append(copy.deepcopy(s['fields'][0]))
        with self.assertRaisesRegex(ValueError,'Duplicate'):config_from_schema(s)

    def test_existing_linked_form_schema_is_checked_without_altering_cases(self):
        # Server validation must not accept a Config unrelated to the edited schema.
        with tempfile.TemporaryDirectory() as folder:
            w=ExecutionWorkspace(ROOT,[],folder=Path(folder)/'registry',output=Path(folder)/'output')
            before=w.forms()
            with self.assertRaises(ValueError):w.save_form('Mismatch','solver_definition','icoFoam',{},config_schema=sample())
            self.assertEqual(w.forms(),before)

if __name__=='__main__':unittest.main()
