import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cfd_studio.config_assets import store_definitions
from cfd_studio.execution_workspace import ExecutionWorkspace, read_json

ROOT=Path(__file__).resolve().parents[1]

class ConfigAssetsTests(unittest.TestCase):
    def test_definitions_are_immutable_and_paths_cannot_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);config={'geometry':{'regions':[]},'mesh':{'cell_size':1},'../../outside':{'x':2}}
            a=store_definitions(root,config);base=root/a['root']
            self.assertEqual(read_json(base/a['sections']['../../outside']),{'x':2})
            self.assertFalse((root.parent/'outside.json').exists())
            self.assertFalse(read_json(base/'manifest.json')['solver_mesh_generated'])
            changed=copy.deepcopy(config);changed['mesh']['cell_size']=2
            b=store_definitions(root,changed)
            self.assertNotEqual(a['root'],b['root'])
            self.assertEqual(read_json(base/'mesh.json')['mesh']['cell_size'],1)
            self.assertEqual(store_definitions(root,config),a)
            (base/'mesh.json').write_text('{}')
            with self.assertRaises(ValueError):store_definitions(root,config)

    def test_owner_local_template_project_case_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);w=ExecutionWorkspace(ROOT,[],folder=root/'registry',output=root/'output')
            builtin=w.form('immersion')
            template=w.save_form('Example',builtin['model'],builtin['solver'],builtin['config'])
            troot=root/'registry/Templates'/template['id']/template['definition_assets']['root']
            self.assertTrue((troot/'geometry.json').is_file())
            p=w.create_project('Example',form_id=template['id'],default_preset='form:'+template['id'],storage_path=str(root/'project'))
            project=read_json(root/'project/project.cfdproj')
            self.assertTrue((root/'project'/project['definition_assets']['root']/'geometry.json').is_file())
            c=copy.deepcopy(template['config']);c['run']['output_fields']=['flow']
            saved=w.save_case(p['id'],'A',c)
            fresh=ExecutionWorkspace(ROOT,[],folder=root/'registry',output=root/'output')
            case=fresh.queue_data()['cases'][saved['run_key']]
            case_root=root/'project/Cases'/saved['run_key'].removeprefix('case:')/case['definition_assets']['root']
            self.assertEqual(read_json(case_root/'config.json'),case['config'])
            old=copy.deepcopy(case)
            c['heater']['total_W']+=1
            with patch.object(w,'save_queue',side_effect=OSError('save failed')):
                with self.assertRaises(OSError):w.save_case(p['id'],'A',c,case_id=saved['run_key'],revision=case['revision'])
            self.assertEqual(fresh.queue_data()['cases'][saved['run_key']],old)
            self.assertEqual(read_json(troot/'config.json'),template['config'])


class GeneratedGeometryTests(unittest.TestCase):
    def test_generated_geometry_uses_inline_definition_not_required_path(self):
        from cfd_studio.form_wizard import generate,profile
        from cfd_studio.solver_requirements import inspect_config
        answers={key:items[0]['value'] for key,items in profile('icoFoam')['options'].items()}
        answers['mesh']='generate'
        value=generate('icoFoam',answers)['config']
        self.assertNotIn('source',value['geometry'])
        value['geometry']['regions']=[{'name':'domain','shape':'box','unit':'m','min':[0,0,0],'max':[1,1,1]}]
        issues=inspect_config('icoFoam',value)['issues']
        self.assertFalse(any(i['path'][:1]==['geometry'] for i in issues))

if __name__=='__main__':unittest.main()
