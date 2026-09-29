import itertools
import tempfile
import unittest
from pathlib import Path
from cfd_studio.form_wizard import profiles,profile,generate
from cfd_studio.form_schema import config_from_schema
from cfd_studio.execution_workspace import ExecutionWorkspace,get_route,post_route

ROOT=Path(__file__).resolve().parents[1]
def answers(solver,**changes):
    result={k:v[0]['value'] for k,v in profile(solver)['options'].items()};result.update(changes);return result

class FormWizardTests(unittest.TestCase):
    def test_every_supported_combination_builds_matching_schema(self):
        self.assertEqual(len(profiles()),12)
        for p in profiles():
            keys=list(p['options'])
            for selected in itertools.product(*[[o['value'] for o in p['options'][k]] for k in keys]):
                a=dict(zip(keys,selected))
                with self.subTest(solver=p['solver'],answers=a):
                    result=generate(p['solver'],a)
                    self.assertEqual(config_from_schema(result['config_schema']),result['config'])
                    self.assertTrue(result['definition_only'])
                    self.assertEqual(result['config']['analysis']['choices'],a)
                    self.assertIsNone(result['config']['materials']['fluids'][next(iter(result['config']['materials']['fluids']))]['density']['value'])

    def test_solver_specific_fields_and_termination(self):
        flow=generate('icoFoam',answers('icoFoam'))['config']
        self.assertNotIn('T',flow['initial_conditions']['fields'])
        self.assertEqual(flow['initial_conditions']['fields']['p']['unit'],'m^2/s^2')
        steady=generate('simpleFoam',answers('simpleFoam'))['config']
        self.assertNotIn('time_step',steady['numerics']);self.assertIn('max_iterations',steady['termination'])
        thermal=generate('buoyantPimpleFoam',answers('buoyantPimpleFoam',medium='gas'))['config']
        self.assertIn('T',thermal['outputs']['fields']);self.assertEqual(thermal['initial_conditions']['fields']['p']['unit'],'Pa')
        multi=generate('interFoam',answers('interFoam',medium='liquid_liquid'))['config']
        self.assertEqual(len(multi['materials']['fluids']),2);self.assertIn('alpha.phase_1',multi['outputs']['fields'])
        cht=generate('chtMultiRegionFoam',answers('chtMultiRegionFoam'))['config']
        self.assertIn('solid_regions',cht['geometry']);self.assertIn('solid',cht['materials'])
        frames=generate('pimpleFoam',answers('pimpleFoam',termination='frames'))['config']
        self.assertIsNone(frames['termination']['saved_frames']);self.assertIsNone(frames['termination']['include_initial_frame'])

    def test_invalid_choices_do_not_generate(self):
        for solver,a in [('icoFoam',answers('icoFoam',medium='liquid_gas')),('icoFoam',answers('icoFoam',regime='RAS')),('simpleFoam',answers('simpleFoam',termination='physical_time')),('icoFoam',{}),('invalid',{})]:
            with self.subTest(solver=solver),self.assertRaises(ValueError):generate(solver,a)

    def test_generated_form_roundtrip_preserves_inputs_and_nullable_fields(self):
        solver='buoyantPimpleFoam';result=generate(solver,answers(solver,medium='gas'))
        with tempfile.TemporaryDirectory() as tmp:
            kw=dict(folder=Path(tmp)/'registry',output=Path(tmp)/'output')
            workspace=ExecutionWorkspace(ROOT,[],**kw)
            saved=workspace.save_form('Guided','solver_definition',solver,result['config'],config_schema=result['config_schema'])
            restored=ExecutionWorkspace(ROOT,[],**kw).form(saved['id'])
            self.assertEqual(restored['config_schema'],result['config_schema'])
            self.assertEqual(restored['config'],result['config'])
            import copy
            wrong=copy.deepcopy(result['config']);wrong['analysis']['solver']='icoFoam'
            from cfd_studio.form_wizard import make_schema
            with self.assertRaisesRegex(ValueError,'솔버'):
                workspace.save_form('Bad solver','solver_definition',solver,wrong,config_schema=make_schema(wrong))
            with self.assertRaises(ValueError):workspace.check_form_config(saved['id'],restored['config'])

    def test_generate_api_and_invalid_request(self):
        class Handler:
            path='/api/executions/form-generate'
            def _json(self,value,code=200):self.value=value;self.code=code
        h=Handler();post_route(h,None,{'solver':'icoFoam','answers':answers('icoFoam')})
        self.assertEqual(h.code,200);self.assertTrue(h.value['ok'])
        post_route(h,None,{'solver':'icoFoam','answers':{}});self.assertEqual(h.code,400)
        h.path='/api/executions/form-profiles';get_route(h,None);self.assertEqual(len(h.value['profiles']),12)

if __name__=='__main__':unittest.main()
