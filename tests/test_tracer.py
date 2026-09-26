"""No solver or production data is required for these contract tests."""
import json
from pathlib import Path
import tempfile
import unittest
try:
    import numpy as np
except ImportError:
    np = None
if np is not None:
    from tracer_transport.run import generate, read_field
    from tracer_transport.sample import ConcentrationField


@unittest.skipIf(np is None, 'Install tracer_transport/requirements.txt for tracer checks')
class TracerTests(unittest.TestCase):
    def test_generated_fields_and_existing_case_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'case'
            cfg,eps,c=generate(case,20,.01,'porous')
            np.testing.assert_allclose(read_field(case/'0/C',320),c)
            self.assertEqual(set(eps),{.4,1.})
            with self.assertRaises(FileExistsError):
                generate(case,20,.01,'porous')
            self.assertEqual(json.loads((case/'config.json').read_text())['shape_xyz'],cfg['shape_xyz'])

    def test_sampling_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'field.npz'
            np.savez(p,times=[0,1],concentration=[[1,2],[3,4]],region_id=[0,1],shape_xyz=[2,1,1],lengths_m=[1,1,1])
            f=ConcentrationField(p)
            self.assertEqual(f.sample_concentration([.2,.5,.5],.5,0)['concentration'],2)
            for pos,t,r in [([-.1,0,0],0,None),([1,0,0],0,None),([0,0,0],2,None),([0,0,0],0,1),([float('nan'),0,0],0,None)]:
                self.assertFalse(f.sample_concentration(pos,t,r)['valid'])

    def test_three_dimensional_block_and_mesh_alignment(self):
        cfg=json.loads((Path(__file__).parents[1]/'tracer_transport/block3d_test.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'case'
            _,eps,_=generate(path,40,.005,'porous',cfg)
            self.assertEqual(int(np.count_nonzero(eps<1)),320)
            cfg['porous_boxes_m'][0]['min'][1]=.051
            with self.assertRaises(ValueError):
                generate(Path(tmp)/'bad',40,.005,'porous',cfg)
            self.assertFalse((Path(tmp)/'bad').exists())

    def test_ph3_and_unsupported_conditions_are_not_silently_ignored(self):
        from tracer_transport.protocol import contract
        base=json.loads((Path(__file__).parents[1]/'tracer_transport/benchmark.json').read_text())
        for extra in [{'model_kind':'PH3'},{'source':'pulse'},{'leakage':True},
                      {'adsorption':True},{'supply_location':[0,0,0]}]:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                contract({**base,**extra},'porous',.005)

    def test_protocol_written_before_solver_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'case'
            generate(case,20,.01,'diffusion')
            spec=json.loads((case/'conditions.json').read_text())
            self.assertEqual(spec['target_species'],'PH3')
            self.assertEqual(spec['represented_species'],'normalized_inert_tracer')
            self.assertFalse(spec['experimental_reproduction'])
            self.assertTrue((case/'criteria.json').is_file())
            self.assertFalse((case/'log.porousTracerFoam').exists())

    def test_sorption_contract_and_region_mask(self):
        from tracer_transport.protocol import sorption_parameters
        base=json.loads((Path(__file__).parents[1]/'tracer_transport/block3d_test.json').read_text())
        ads={'model':'linear_reversible','k_ads_s_inv':.2,'k_des_s_inv':.1,
             'initial_bulk_Q':.3,'evidence':'numerical_test_assumption'}
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'case'
            _,eps,_=generate(case,40,.005,'porous',{**base,'adsorption':ads})
            q=read_field(case/'0/Q',len(eps))
            rates=read_field(case/'0/kAds',len(eps))
            np.testing.assert_allclose(q[eps==1],0)
            np.testing.assert_allclose(rates[eps==1],0)
            np.testing.assert_allclose(q[eps<1],.3)
        for change in [{'k_ads_s_inv':-1},{'k_des_s_inv':float('nan')},
                       {'evidence':'rice_measurement'},{'extra_parameter':1}]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                sorption_parameters({'adsorption':{**ads,**change}})


if __name__=='__main__':
    unittest.main()
