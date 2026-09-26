"""Contract checks for supply-start, steady stopping and Studio export."""
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from tracer_transport.run import generate, read_field
from tracer_transport.protocol import contract
from tracer_transport.export_studio import export_case

ROOT=Path(__file__).resolve().parents[1]


class SupplyTests(unittest.TestCase):
    def config(self):
        return json.loads((ROOT/'tracer_transport/supply_test.json').read_text())

    def test_supply_zero_initial_state_and_free_air_source(self):
        with tempfile.TemporaryDirectory() as temp:
            case=Path(temp)/'case'
            cfg,eps,c=generate(case,20,.05,'porous',self.config())
            n=len(c)
            self.assertTrue(np.all(c==0))
            self.assertTrue(np.all(read_field(case/'0/Q',n)==0))
            rate=read_field(case/'0/sourceRate',n)
            self.assertGreater(rate.sum(),0)
            self.assertTrue(np.all(rate[eps<1]==0))
            manifest=json.loads((case/'inputs.sha256.json').read_text())
            self.assertIn('constant/transportControl',manifest)
            self.assertIn('0/sourceRate',manifest)

    def test_invalid_initial_supply_and_stopping_contract(self):
        for changes in [{'initial_mean':1},{'termination':{'mode':'steady'}},
                        {'termination':{**self.config()['termination'],'hold_s':float('nan')}}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                contract({**self.config(),**changes},'porous',.05)

    def test_supply_box_cannot_silently_shift(self):
        cfg=self.config();cfg['source']['box_m']['min'][0]=.003
        with tempfile.TemporaryDirectory() as temp,self.assertRaises(ValueError):
            generate(Path(temp)/'bad',20,.05,'porous',cfg)

    def test_export_preserves_zero_planes_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            case=Path(temp)/'case';project=Path(temp)/'project'
            cfg,eps,c=generate(case,20,.05,'porous',self.config())
            arrays=np.stack([c,np.arange(len(c))/len(c)])
            np.savez(case/'concentration.npz',times=[0,1],concentration=arrays,sorbed_bulk=arrays*.1,
                     shape_xyz=cfg['shape_xyz'],lengths_m=cfg['lengths_m'])
            (case/'checks.json').write_text(json.dumps({'pass':True,'physical_duration_s':1,'saved_frames':2}))
            result=export_case(case,project)
            self.assertEqual(result['frames'],2)
            raw=(project/'concentration_0.bin').read_bytes()
            self.assertEqual(raw[:4],b'CON1')
            self.assertEqual(len(raw),40+len(c)*4)
            self.assertTrue(np.all(np.frombuffer(raw[40:],dtype='<f4')==0))
            before=(project/'concentration_1.bin').stat().st_mtime_ns
            export_case(case,project)
            self.assertEqual(before,(project/'concentration_1.bin').stat().st_mtime_ns)
            cfg['dt_s']=.025;(case/'config.json').write_text(json.dumps(cfg))
            with self.assertRaises(ValueError):export_case(case,project)


if __name__=='__main__':unittest.main()
