import copy
import unittest
from cfd_studio.form_wizard import recommend,generate_from_survey,profiles,survey_options
from cfd_studio.execution_workspace import get_route,post_route


def base(**changes):
    a=dict(medium='gas',purpose='flow',regime='laminar',time_mode='transient',domain='internal',mesh='import',termination='physical_time')
    a.update(changes);return a

class SolverRecommendationTests(unittest.TestCase):
    def test_common_flow_filters_time_and_turbulence(self):
        ids=lambda a:[c['solver'] for c in recommend(a)['candidates']]
        self.assertEqual(ids(base()),['icoFoam','pimpleFoam','pisoFoam'])
        self.assertEqual(ids(base(regime='RAS')),['pimpleFoam','pisoFoam'])
        self.assertEqual(ids(base(time_mode='steady',termination='convergence',regime='RAS')),['simpleFoam'])
        self.assertEqual(ids(base(time_mode='steady',regime='LES',termination='convergence')),[])

    def test_thermal_multiphase_and_incompatible_combinations(self):
        for a,expected in [(base(purpose='heat_flow'),['buoyantPimpleFoam']),
                           (base(purpose='interface',medium='liquid_gas'),['interFoam','interIsoFoam','icoReactingMultiphaseInterFoam']),
                           (base(purpose='conjugate_heat'),['chtMultiRegionFoam']),
                           (base(purpose='interface',medium='gas'),[])]:
            self.assertEqual([c['solver'] for c in recommend(a)['candidates']],expected)
        self.assertTrue(recommend(base(time_mode='steady'))['message'])

    def test_all_registered_profiles_are_reachable_and_generate_blank_inputs(self):
        for p in profiles():
            a={k:v[0]['value'] for k,v in p['options'].items()};a['time_mode']=p['time_mode']
            original=copy.deepcopy(a);r=recommend(a)
            self.assertIn(p['solver'],[c['solver'] for c in r['candidates']])
            generated=generate_from_survey(p['solver'],a)['config']
            self.assertEqual(generated['analysis']['solver'],p['solver'])
            self.assertEqual(generated['analysis']['time_mode'],a['time_mode'])
            self.assertIsNone(next(iter(generated['materials']['fluids'].values()))['density']['value'])
            self.assertEqual(a,original)

    def test_forged_solver_and_malformed_survey_are_rejected(self):
        for a in [None,{},base(time_mode='random'),base(regime=[]),dict(base(),extra='value')]:
            with self.assertRaises(ValueError):recommend(a)
        with self.assertRaises(ValueError):generate_from_survey('simpleFoam',base())
        with self.assertRaises(ValueError):generate_from_survey('not-installed-custom-solver',base())

    def test_none_of_these_is_valid_but_unsupported_for_every_question(self):
        options=survey_options()
        for key,choices in options.items():
            self.assertEqual(choices[-1],{'value':'not_listed','label':'여기에 없음'})
            a=base(**{key:'not_listed'});before=copy.deepcopy(a)
            result=recommend(a)
            self.assertEqual(result['status'],'unsupported')
            self.assertEqual(result['unsupported_fields'],[key])
            self.assertEqual(result['candidates'],[])
            self.assertEqual(a,before)
            with self.assertRaises(ValueError):generate_from_survey('icoFoam',a)
        result=recommend(base(medium='not_listed',regime='not_listed'))
        self.assertEqual(set(result['unsupported_fields']),{'medium','regime'})
        self.assertEqual(recommend(base())['status'],'supported')

    def test_api_rechecks_compatibility_before_generation(self):
        class Handler:
            path='/api/executions/form-survey'
            def _json(self,value,code=200):self.value=value;self.code=code
        h=Handler();get_route(h,None);self.assertEqual(h.value['options'],survey_options())
        h.path='/api/executions/form-recommend';post_route(h,None,{'answers':base()});self.assertEqual(h.code,200)
        h.path='/api/executions/form-from-survey';post_route(h,None,{'answers':base(),'solver':'icoFoam'});self.assertEqual(h.code,200)
        post_route(h,None,{'answers':base(),'solver':'interFoam'});self.assertEqual(h.code,400)

        h.path='/api/executions/form-recommend';post_route(h,None,{'answers':base(mesh='not_listed')});self.assertEqual(h.code,200);self.assertEqual(h.value['result']['status'],'unsupported')
        h.path='/api/executions/form-from-survey';post_route(h,None,{'answers':base(mesh='not_listed'),'solver':'icoFoam'});self.assertEqual(h.code,400)

    def test_general_multiphase_intentions_keep_solver_physics(self):
        a=base(medium='liquid_gas',purpose='flow')
        self.assertEqual([c['solver'] for c in recommend(a)['candidates']],['interFoam','interIsoFoam','icoReactingMultiphaseInterFoam'])
        config=generate_from_survey('interFoam',a)['config']
        self.assertEqual(config['analysis']['choices']['purpose'],'flow')
        self.assertEqual(len(config['materials']['fluids']),2)
        self.assertIn('alpha.phase_1',config['outputs']['fields'])
        self.assertIn('interfaces',config['physics'])
        thermal=base(medium='liquid_liquid_gas',purpose='heat_flow')
        self.assertEqual([c['solver'] for c in recommend(thermal)['candidates']],['icoReactingMultiphaseInterFoam'])
        config=generate_from_survey('icoReactingMultiphaseInterFoam',thermal)['config']
        self.assertEqual(len(config['materials']['fluids']),3)
        self.assertIn('T',config['outputs']['fields'])
        self.assertIn('phase_transfer',config['physics'])

    def test_mismatches_are_explicit_and_only_proposals_are_changed(self):
        a=base(time_mode='steady');before=copy.deepcopy(a);r=recommend(a)
        self.assertEqual(r['candidates'],[])
        best=r['alternatives'][0]
        self.assertEqual(best['solver'],'simpleFoam')
        self.assertEqual(best['changes'],[{'field':'termination','from':'physical_time','to':'convergence'}])
        self.assertEqual(a,before)
        with self.assertRaises(ValueError):generate_from_survey('simpleFoam',a)
        for item in r['alternatives']:
            self.assertIn(item['solver'],[c['solver'] for c in recommend(item['answers'])['candidates']])
        self.assertEqual(recommend(base(medium='not_listed'))['alternatives'],[])
