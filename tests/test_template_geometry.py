"""Editable initial layout and independent project Config persistence."""
import copy
import tempfile
import unittest
from pathlib import Path
from cfd_studio.form_schema import blank_schema,config_from_schema,validate_values,apply_initial_geometry
from cfd_studio.form_wizard import make_schema
from cfd_studio.execution_workspace import ExecutionWorkspace
ROOT=Path(__file__).resolve().parents[1]

def fixture():
    return {'geometry':{'regions':[{'name':'A','shape':'box','unit':'m','min':[0,0,0],'max':[1,2,3],'config_bindings':[['materials','fluid']]}]},'materials':{'fluid':{'density':1000.0}},'coil':{'x0':0,'x1':1,'h_W_m2K':20.0}}

class TemplateGeometryTests(unittest.TestCase):
    def test_layout_is_editable_and_operating_values_are_blank(self):
        config=fixture();before=copy.deepcopy(config);schema=blank_schema(config);blank=config_from_schema(schema)
        self.assertEqual(blank['geometry'],config['geometry']);self.assertEqual(blank['coil']['x1'],1)
        self.assertIsNone(blank['coil']['h_W_m2K']);self.assertIsNone(blank['materials']['fluid']['density'])
        changed=copy.deepcopy(config);changed['geometry']['regions'][0]['max'][0]=5
        changed['geometry']['regions'].append(copy.deepcopy(changed['geometry']['regions'][0]))
        validate_values(schema,changed);changed['geometry']['regions'].pop(0);validate_values(schema,changed)
        self.assertEqual(config,before)

    def test_legacy_schema_recovers_geometry_but_new_empty_layout_stays_empty(self):
        c=fixture();old=make_schema(c);old['fields'][0]['fields'][0]['value']=[];old['fields'][0]['label']='Custom geometry'
        migrated=blank_schema(c,old);self.assertEqual(migrated['fields'][0]['label'],'Custom geometry');self.assertEqual(config_from_schema(migrated)['geometry'],c['geometry'])
        migrated['fields'][0]['fields'][0]['value']=[]
        self.assertEqual(config_from_schema(blank_schema(c,migrated))['geometry']['regions'],[])

    def test_apply_layout_does_not_replace_operating_preset(self):
        c=fixture();schema=blank_schema(c);schema['fields'][0]['fields'][0]['value'][0]['max'][0]=4
        changed=apply_initial_geometry(c,schema)
        self.assertEqual(changed['geometry']['regions'][0]['max'][0],4);self.assertEqual(changed['coil']['h_W_m2K'],20)
        self.assertEqual(changed['materials'],c['materials']);self.assertEqual(c['geometry']['regions'][0]['max'][0],1)

    def test_invalid_primitive_dimensions_cannot_be_saved_as_project_values(self):
        c=fixture();schema=blank_schema(c)
        for dims in ([0,2,3],[None,2,3],['1',2,3]):
            bad=copy.deepcopy(c);bad['geometry']['regions'][0]['max']=dims
            with self.assertRaises(ValueError):validate_values(schema,bad)

    def test_connected_template_changes_initial_layout_without_replacing_physical_preset(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);w=ExecutionWorkspace(ROOT,[],folder=root/'registry',output=root/'output')
            original=w.form('immersion');schema=copy.deepcopy(original['input_schema'])
            tank=next(f for f in schema['fields'] if f['key']=='tank')
            next(f for f in tank['fields'] if f['key']=='width_mm')['value']=500
            saved=w.save_form(original['name'],original['model'],original['solver'],original['config'],form_id=original['id'],revision=original['revision'],input_schema=schema)
            self.assertEqual(saved['config']['tank']['width_mm'],500)
            self.assertEqual(saved['config']['heater']['total_W'],original['config']['heater']['total_W'])
            self.assertEqual(original['config']['tank']['width_mm'],456)

    def test_template_and_project_geometry_are_independent_after_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);w=ExecutionWorkspace(ROOT,[],folder=root/'registry',output=root/'output')
            schema=blank_schema(fixture());config=config_from_schema(schema)
            form=w.save_form('Geometry test','solver_definition','simpleFoam',config,input_schema=schema)
            project_config=fixture();project_config['geometry']['regions'][0]['max'][0]=7
            project=w.create_project('Geometry project',form_id=form['id'],initial_config=project_config,storage_path=str(root/'project'))
            project_config['geometry']['regions'][0]['max'][0]=99
            new=ExecutionWorkspace(ROOT,[],folder=root/'registry',output=root/'output')
            self.assertEqual(new.form(form['id'])['blank_config']['geometry']['regions'][0]['max'][0],1)
            p=next(p for p in new.snapshot()['projects'] if p['id']==project['id'])
            self.assertEqual(p['initial_config']['geometry']['regions'][0]['max'][0],7)
            next_schema=copy.deepcopy(schema);next_schema['fields'][0]['fields'][0]['value'][0]['max'][0]=3
            new.save_form('Geometry test','solver_definition','simpleFoam',config_from_schema(next_schema),form_id=form['id'],revision=1,input_schema=next_schema)
            self.assertEqual(next(p for p in new.snapshot()['projects'] if p['id']==project['id'])['initial_config']['geometry']['regions'][0]['max'][0],7)

if __name__=='__main__':unittest.main()
