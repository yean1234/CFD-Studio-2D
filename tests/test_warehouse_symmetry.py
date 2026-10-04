"""Reduced domains preserve represented geometry and reject asymmetric inputs"""
import copy
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch
import numpy as np
from tracer_transport.porous_warehouse_mesh import generate_mesh, mesh_plan, initial_average, layout
from tracer_transport.warehouse_symmetry import symmetry_domain, apply_field_boundaries
from tracer_transport.warehouse_coupled import validate

ROOT = Path(__file__).resolve().parents[1]


class SymmetryTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT/'tracer_transport/warehouse_porous_convergence.json').read_text())

    def test_half_volume_inventory_and_complementary_centres(self):
        _,full = generate_mesh(self.spec)
        halves=[]
        for mode in ('symmetry_y_min','symmetry_y_max'):
            spec=copy.deepcopy(self.spec)
            spec['porous_mesh']['domain_mode']=mode
            text,half=generate_mesh(spec)
            self.assertEqual(text.count('type symmetryPlane;'),1)
            self.assertEqual(len(half['cell_centres_m'])*2,len(full['cell_centres_m']))
            self.assertAlmostEqual(half['cell_volumes_m3'].sum()*2,full['cell_volumes_m3'].sum())
            self.assertAlmostEqual(validate(spec)['volume_m3'],half['cell_volumes_m3'].sum())
            inventory=lambda data:np.sum(initial_average(spec,data)*np.where(data['loaded_region'],.4,1)*data['cell_volumes_m3'])
            self.assertAlmostEqual(inventory(half)*2/inventory(full),1.,places=10)
            halves.extend(map(tuple,half['cell_centres_m']))
        self.assertEqual(set(halves),set(map(tuple,full['cell_centres_m'])))

    def test_asymmetry_and_unknown_reduction_fail(self):
        for error,change in [
            ('MESH-S002',lambda s:s['loading']['blocks'][0]['max_m'].__setitem__(1,11.4)),
            ('MESH-S003',lambda s:s['initial']['centre_m'].__setitem__(1,10)),
            ('MESH-S001',lambda s:s['porous_mesh'].__setitem__('domain_mode','symmetry_x'))]:
            s=copy.deepcopy(self.spec);s['porous_mesh']['domain_mode']='symmetry_y_min';change(s)
            with self.assertRaisesRegex(ValueError,error):symmetry_domain(s)

    def test_large_mesh_is_planned_and_rejected_before_allocation(self):
        self.spec['porous_mesh'].update(domain_mode='symmetry_y_min',maximum_cell_edge_m=.03)
        with patch('numpy.meshgrid',side_effect=AssertionError('allocation')):
            plan=mesh_plan(self.spec)
            self.assertEqual(plan['cells'],404078304)
            self.assertFalse(plan['within_cell_budget'])
            with self.assertRaisesRegex(ValueError,'cell budget'):layout(self.spec)

    def test_plan_without_solver_python_dependencies(self):
        code = """
import json
from tracer_transport.porous_warehouse_mesh import mesh_plan
spec=json.load(open('tracer_transport/warehouse_porous_convergence.json'))
spec['porous_mesh'].update(domain_mode='symmetry_y_min', maximum_cell_edge_m=.03)
assert mesh_plan(spec)['cells']==404078304
"""
        result = subprocess.run([sys.executable, '-S', '-c', code], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_all_initial_fields_get_symmetry_and_no_wall_function(self):
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name)
            for field in ('U','C','T','epsilon'):
                (folder/field).write_text('boundaryField { symmetryPlane { type epsilonWallFunction; value uniform 1; } wall { type zeroGradient; } }')
            apply_field_boundaries(folder)
            for path in folder.iterdir():
                self.assertIn('symmetryPlane { type symmetryPlane; }',path.read_text())
                self.assertNotIn('epsilonWallFunction',path.read_text())
            (folder/'missing').write_text('boundaryField {}')
            with self.assertRaisesRegex(ValueError,'MESH-S004'):apply_field_boundaries(folder)
