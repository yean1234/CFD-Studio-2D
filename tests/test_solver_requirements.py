import copy
import unittest
from cfd_studio.form_wizard import generate,profile
from cfd_studio.solver_catalog import CATALOG,catalog
from cfd_studio.solver_requirements import DEFINITIONS,inspect_config,rules

def config(solver='icoFoam',**changes):
    a={k:v[0]['value'] for k,v in profile(solver)['options'].items()};a.update(changes)
    return generate(solver,a)

def put(obj,path,value):
    for key in path[:-1]:obj=obj.setdefault(key,{})
    obj[path[-1]]=value

class SolverRequirementTests(unittest.TestCase):
    def test_all_solvers_have_individual_usage_required_and_optional_definitions(self):
        self.assertEqual(set(DEFINITIONS),{x['id'] for x in CATALOG})
        for entry in catalog():
            for key in ('uses','required','optional','fields','algorithm','limit'):self.assertTrue(entry['requirements'][key])
            generated=config(entry['id']);review=inspect_config(entry['id'],generated['config'])
            self.assertGreater(review['missing_count'],0)
            self.assertGreater(review['required_count'],0)
            self.assertTrue(any(field.get('required') for field in generated['config_schema']['fields'][2]['fields']))

    def test_initial_fields_and_interface_methods_differ(self):
        for solver in ('interFoam','interIsoFoam'):
            c=config(solver)['config'];self.assertNotIn('p',c['initial_conditions']['fields']);self.assertNotIn('alpha.phase_2',c['initial_conditions']['fields'])
        self.assertEqual(config('interFoam')['config']['numerics']['phase_fraction']['method'],'MULES')
        self.assertEqual(config('interIsoFoam')['config']['numerics']['phase_fraction']['method'],'isoAdvector')
        self.assertIn('thermophysical_properties',config('rhoPimpleFoam')['config']['materials']['fluids']['fluid'])
        self.assertIn('regions',config('chtMultiRegionFoam')['config']['numerics'])

    def test_missing_required_path_cannot_be_hidden_by_deleting_its_parent(self):
        c=config()['config'];del c['materials'];result=inspect_config('icoFoam',c)
        self.assertTrue(any(x['path']==['materials','fluids','fluid','kinematic_viscosity','value'] for x in result['issues']))
        c['physics']='wrong';c['initial_conditions']=[];c['termination']=None
        self.assertGreater(inspect_config('icoFoam',c)['missing_count'],0)

    def test_required_values_complete_but_not_physical_validation_or_execution(self):
        c=config()['config'];original=copy.deepcopy(c)
        for rule in rules('icoFoam',original,c):
            kind=rule['kind'];value={'number':0,'positive':1,'integer':1,'text':'userInput','boolean':False,'object':{},'choice':rule['unit'],'mapping':{'default':'userInput'},'sequence':['userInput'],'filled':{'custom':1},'unit':rule['unit']}[kind]
            put(c,rule['path'],value)
        result=inspect_config('icoFoam',c)
        self.assertEqual(result['issues'],[]);self.assertEqual(result['status'],'specified')
        self.assertFalse(result['physical_validation']);self.assertFalse(result['executable'])
        c['materials']['fluids']['fluid']['kinematic_viscosity']['value']=-1
        self.assertTrue(any('kinematic_viscosity' in x['path'] for x in inspect_config('icoFoam',c)['issues']))

    def test_fixed_value_and_turbulence_add_conditional_requirements(self):
        c=config('pimpleFoam',regime='RAS')['config']
        c['physics']['turbulence']['model']='kOmegaSST'
        c['boundary_conditions']['inlet']['fields']['U']['type']='fixedValue'
        paths=[x['path'] for x in inspect_config('pimpleFoam',c)['issues']]
        self.assertIn(['physics','turbulence','initial_fields','omega'],paths)
        self.assertIn(['boundary_conditions','inlet','fields','U','value','x'],paths)
        c['boundary_conditions']['inlet']['fields']['U']['type']='zeroGradient'
        paths=[x['path'] for x in inspect_config('pimpleFoam',c)['issues']]
        self.assertNotIn(['boundary_conditions','inlet','fields','U','value','x'],paths)

    def test_phase_fraction_units_and_stopping_time_are_checked(self):
        c=config('interFoam')['config'];c['initial_conditions']['fields']['alpha.phase_1']['value']=2
        c['initial_conditions']['fields']['p_rgh']['unit']='m^2/s^2'
        c['termination']['end_time']['value']=10;c['termination']['max_time']['value']=5
        messages=[x['message'] for x in inspect_config('interFoam',c)['issues']]
        self.assertIn('상분율은 0~1 범위',messages);self.assertIn('단위 확인: Pa',messages)
        self.assertIn('최대 시간은 종료 시간 이상이어야 합니다',messages)

if __name__=='__main__':unittest.main()
