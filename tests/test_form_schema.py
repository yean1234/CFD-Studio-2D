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
    def test_shared_region_values_are_not_inherited_as_geometry(self):
        from cfd_studio.form_schema import blank_schema
        config={'loading':{'blocks':[{'id':'A','min_m':[0,0,0],'max_m':[1,1,1]}], 'porosity':.4, 'tortuosity':2}}
        original=copy.deepcopy(config)
        result=config_from_schema(blank_schema(config))
        self.assertEqual(result['loading']['blocks'],config['loading']['blocks'])
        self.assertIsNone(result['loading']['porosity'])
        self.assertIsNone(result['loading']['tortuosity'])
        self.assertEqual(config,original)

    def test_nested_config_units_and_solver_independence_survive_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            w=ExecutionWorkspace(ROOT,[],folder=Path(folder)/'registry',output=Path(folder)/'output')
            schema=sample();config=config_from_schema(schema)
            saved=w.save_form('User domain','solver_definition','simpleFoam',config,config_schema=schema)
            fresh=ExecutionWorkspace(ROOT,[],folder=Path(folder)/'registry',output=Path(folder)/'output')
            form=fresh.form(saved['id']);self.assertEqual(form['config'],config);self.assertEqual(form['config_schema'],schema)
            self.assertTrue(form['definition_only'])
            with self.assertRaisesRegex(ValueError,'연결'):fresh.check_form_config(form['id'],config)
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


class PartPropertySchemaTests(unittest.TestCase):
    def test_definitions_blank_values_and_inherit_preset_values_by_part_name(self):
        from cfd_studio.form_schema import blank_schema,apply_initial_geometry
        from cfd_studio.form_wizard import make_schema
        c={'geometry':{'regions':[{'name':'A','shape':'box','unit':'m','min':[0,0,0],'max':[1,2,3],'role':'user role','properties':{'voltage':{'name':'Potential','type':'number','unit':'V','value':24}}}]},'coil':{'x0':1,'x1':2,'properties':{'enabled':{'name':'Enable','type':'boolean','unit':'','value':True}}}}
        before=copy.deepcopy(c);schema=blank_schema(c,make_schema(c));blank=config_from_schema(schema)
        self.assertIsNone(blank['geometry']['regions'][0]['properties']['voltage']['value'])
        self.assertEqual(blank['geometry']['regions'][0]['properties']['voltage']['name'],'Potential')
        self.assertIsNone(blank['coil']['properties']['enabled']['value'])
        restored=apply_initial_geometry(c,schema)
        self.assertEqual(restored['geometry']['regions'][0]['properties']['voltage']['value'],24)
        self.assertEqual(restored['coil']['properties']['enabled']['value'],True)
        self.assertEqual(c,before)
        material=blank_schema({'materials':{'properties':{'density':999}}})
        self.assertIsNone(config_from_schema(material)['materials']['properties']['density'])

    def test_template_property_definition_survives_registry_restart(self):
        from cfd_studio.form_schema import blank_schema
        source={'geometry':{'regions':[{'name':'Part A','role':'custom role','shape':'sphere','unit':'m','center':[0,0,0],'radius':1,'properties':{'density':{'name':'Density','type':'number','unit':'kg/m³','value':950}}}]}}
        schema=blank_schema(source);config=config_from_schema(schema)
        with tempfile.TemporaryDirectory() as folder:
            options={'folder':Path(folder)/'registry','output':Path(folder)/'output'}
            workspace=ExecutionWorkspace(ROOT,[],**options)
            saved=workspace.save_form('Custom parts','solver_definition','simpleFoam',config,input_schema=schema)
            restored=ExecutionWorkspace(ROOT,[],**options).form(saved['id'])
            part=restored['config']['geometry']['regions'][0]
            self.assertEqual(part['role'],'custom role')
            self.assertEqual(part['properties']['density'],{'name':'Density','type':'number','unit':'kg/m³','value':None})

class InspectorStateTests(unittest.TestCase):
    def test_state_scale_and_property_definition_persist_with_blank_template_values(self):
        from cfd_studio.form_schema import blank_schema, is_geometry_path
        from cfd_studio.form_wizard import make_schema
        config={'board':{'x0':0,'x1':2,'y0':0,'y1':3,'z0':0,'z1':1,
                         'material_state':'solid','_transform_reference':[1,3,1],
                         'properties':{'density':{'name':'Density','catalog_key':'density','type':'number','unit':'kg/m³','value':7800}}}}
        original=copy.deepcopy(config)
        blank=config_from_schema(blank_schema(config,make_schema(config)))
        self.assertEqual(blank['board']['material_state'],'solid')
        self.assertEqual(blank['board']['_transform_reference'],[1,3,1])
        self.assertEqual(blank['board']['properties']['density']['catalog_key'],'density')
        self.assertIsNone(blank['board']['properties']['density']['value'])
        self.assertFalse(is_geometry_path(('board','properties','density','value')))
        self.assertEqual(config,original)

class ComponentTemplateTests(unittest.TestCase):
    def test_component_values_blank_without_erasing_shape_or_definition(self):
        from cfd_studio.form_schema import blank_schema
        for regions in ([{'name':'Liquid','shape':'box','unit':'m','min':[0,0,0],'max':[1,1,1],'components':{'vapour':{'rho':1.2,'unit':'kg/m³'},'phase_change':{'model':'UserModel','enabled':True}}}], {'liquid':{'shape':'sphere','radius':1,'components':{'vapour':{'rho':1.2,'unit':'kg/m³'},'phase_change':{'model':'UserModel','enabled':True}}}}):
            config={'geometry':{'regions':regions}}
            original=copy.deepcopy(config)
            blank=config_from_schema(blank_schema(config))
            part=blank['geometry']['regions'][0] if isinstance(regions,list) else blank['geometry']['regions']['liquid']
            self.assertIsNone(part['components']['vapour']['rho'])
            self.assertEqual(part['components']['vapour']['unit'],'kg/m³')
            self.assertEqual(part['components']['phase_change']['model'],'UserModel')
            self.assertIsNone(part['components']['phase_change']['enabled'])
            self.assertEqual(config,original)

if __name__=='__main__':unittest.main()
