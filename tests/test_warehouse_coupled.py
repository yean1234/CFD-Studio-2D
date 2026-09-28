"""Coupled result shape, raw-field integrity and temporal interpolation contracts."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from cfd_studio.warehouse_results import WarehouseResults
from tracer_transport.warehouse_coupled import validate

ROOT = Path(__file__).resolve().parents[1]


class CoupledTests(unittest.TestCase):
    def test_invalid_thermal_controls_fail_before_case_creation(self):
        spec = json.loads((ROOT/'tracer_transport/warehouse_coupled_pilot.json').read_text())
        self.assertEqual(validate(spec)['cells'], 22308)
        for key, value in [('permeability_m2', 0), ('solid_rhoCp_J_m3_K', float('nan')),
                           ('max_Co', 2), ('initial_temperature_C', 45), ('basis', '')]:
            changed = copy.deepcopy(spec)
            changed['coupled'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(changed)

    def fixture(self, root):
        case = root/'warehouse_transport_coupled_test'
        case.mkdir()
        for name, payload in {
            'state.json': {'status':'complete'},
            'model_contract.json': {'kind':'clo2_coupled_scenario', 'initial_unit':'kg/m3', 'field_dimensions':'1 -3 0 0 0 0 0', 'geometry':{'cells':2}},
            'checks.json': {'execution_checks_pass':True,'cells':2,'frames':2},
            'transport_input.json': {'geometry_spec':{'geometry':{'length_m':2,'width_m':2,'eaves_m':2,'roof_rise_m':1}}}
        }.items():
            (case/name).write_text(json.dumps(payload))
        temps = np.array([[293.15,294.15],[295.15,296.15]])
        velocities = np.array([[[0.,0.,0.],[1.,0.,0.]],[[2.,0.,0.],[0.,3.,4.]]])
        np.savez_compressed(case/'concentration.npz',times_s=[0.,10.],concentration=[[1e-6,2e-6],[3e-6,4e-6]],
            cell_centres_m=[[.5,.5,.5],[1.5,1.5,.5]],concentration_unit='kg/m3',temperature_K=temps,velocity_m_s=velocities)
        for i,t in enumerate((0,10)):
            (case/str(t)).mkdir()
            for name,dims,kind,values in [('T','0 0 0 1 0 0 0','scalar',' '.join(map(str,temps[i]))),
                ('C','1 -3 0 0 0 0 0','scalar','1e-6 2e-6' if i==0 else '3e-6 4e-6'),
                ('U','0 1 -1 0 0 0 0','vector',' '.join('('+' '.join(map(str,row))+')' for row in velocities[i]))]:
                (case/str(t)/name).write_text(f'dimensions [{dims}]; internalField nonuniform List<{kind}> 2 ({values}); boundaryField {{}}')
        return case

    def test_all_three_fields_query_matches_raw_and_uses_correct_units(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); case=self.fixture(root); reader=WarehouseResults(root)
            frame=reader.frame(case.name,1)
            self.assertEqual(frame['concentration'],[3.,4.])
            self.assertEqual(frame['temperature_field_C'],[22.,23.])
            self.assertEqual(frame['speed_m_s'],[2.,5.])
            query=reader.sample(case.name,[.5,.5,.5],5.,.1)
            self.assertAlmostEqual(query['temperature'],21.)
            self.assertEqual(query['velocity_m_s'],[1.,0.,0.])
            self.assertEqual(query['temperature_status'],'solved_energy_C')
            self.assertEqual(len(query['source_files']),6)

    def test_temperature_and_velocity_tampering_rejects_both_frame_and_query(self):
        for name in ('T','U'):
            with self.subTest(field=name), tempfile.TemporaryDirectory() as temp:
                root=Path(temp);case=self.fixture(root);reader=WarehouseResults(root)
                p=case/'10'/name
                p.write_text(p.read_text().replace('295.15','305.15') if name=='T' else p.read_text().replace('(2.0 0.0 0.0)','(9.0 0.0 0.0)'))
                with self.assertRaisesRegex(ValueError,'일치하지'):
                    reader.frame(case.name,1)
                with self.assertRaisesRegex(ValueError,'일치하지'):
                    reader.sample(case.name,[.5,.5,.5],5.,.1)


if __name__ == '__main__':
    unittest.main()
