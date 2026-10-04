"""Mesh refinement must preserve grain geometry and the initial physical problem."""
import copy
import json
from pathlib import Path
import unittest
import numpy as np
from tracer_transport.porous_warehouse_mesh import generate_mesh,initial_average,restrict_to_base,layout,mesh_plan
from tracer_transport.assess_porous_convergence import gci,signature
from tracer_transport.assess_time_refinement import time_signature

ROOT=Path(__file__).resolve().parents[1]


class PorousMeshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=json.loads((ROOT/'tracer_transport/warehouse_porous_convergence.json').read_text())
        cls.meshes=[]
        for r in (1,2,4):
            s=copy.deepcopy(cls.spec);s['porous_mesh']['refinement']=r
            _,a=generate_mesh(s);cls.meshes.append(a)

    def test_grain_bulk_pore_and_building_volumes_are_identical(self):
        for i,a in enumerate(self.meshes):
            with self.subTest(refinement=2**i):
                self.assertEqual(len(a['cell_centres_m']),1860*(2**i)**3)
                volume=a['cell_volumes_m3'];grain=a['loaded_region']
                self.assertAlmostEqual(volume.sum(),17452.5,places=8)
                self.assertAlmostEqual((volume*grain).sum(),4129.65,places=8)
                self.assertAlmostEqual((volume*grain*.4).sum(),1651.86,places=8)
                self.assertTrue(np.all(volume>0))

    def test_same_initial_cell_averages_restrict_conservatively(self):
        base=self.meshes[0];expected=initial_average(self.spec,base)
        base_mass=np.sum(expected*np.where(base['loaded_region'],.4,1)*base['cell_volumes_m3'])
        for a in self.meshes[1:]:
            initial=initial_average(self.spec,a)
            restricted=restrict_to_base(initial,a['cell_volumes_m3'],a['base_parent'])
            np.testing.assert_allclose(restricted,expected,rtol=1e-9,atol=1e-18)
            mass=np.sum(initial*np.where(a['loaded_region'],.4,1)*a['cell_volumes_m3'])
            self.assertAlmostEqual(mass/base_mass,1.,places=10)
            # Refined cell moments recover exact coarse geometric centroids.
            centres=restrict_to_base(a['cell_centres_m'],a['cell_volumes_m3'],a['base_parent'])
            np.testing.assert_allclose(centres,base['cell_centres_m'],atol=1e-12,rtol=0)

    def test_invalid_mesh_budget_and_stack_planes_rejected(self):
        for change in ('budget','height','refinement'):
            s=copy.deepcopy(self.spec)
            if change=='budget':s['porous_mesh']['maximum_cells']=10
            elif change=='height':s['loading']['blocks'][0]['max_m'][2]=2.5
            else:s['porous_mesh']['refinement']=1.5
            with self.subTest(change=change),self.assertRaises(ValueError):layout(s)

    def test_small_geometry_respects_physical_edges_including_roof(self):
        s=copy.deepcopy(self.spec)
        # Scale only geometry to keep a true 3 mm mesh affordable for this test.
        for key in ('length_m','width_m','eaves_m','roof_rise_m'):
            s['geometry_spec']['geometry'][key]*=.001
        for block in s['loading']['blocks']:
            for key in ('min_m','max_m'):
                block[key]=[v*.001 for v in block[key]]
        s['porous_mesh']['maximum_cell_edge_m']=.003
        original=copy.deepcopy(s)
        plan=mesh_plan(s)
        _,data=generate_mesh(s)
        b=data['bounds']
        edges=np.column_stack((b[:,1]-b[:,0],
            (b[:,3]-b[:,2])*np.sqrt(1+(b[:,6]*b[:,8])**2),
            (b[:,6]-b[:,5])*(b[:,7]+abs(b[:,8])*(b[:,3]-b[:,2])/2)))
        self.assertLessEqual(float(edges.max()),.003*(1+1e-12))
        self.assertAlmostEqual(float(edges.max()),plan['maximum_cell_edge_m'])
        self.assertEqual(len(b),plan['cells'])
        self.assertEqual(s,original)

    def test_whole_warehouse_mm_plan_rejects_allocation(self):
        from unittest.mock import patch
        s=copy.deepcopy(self.spec)
        s['porous_mesh']['maximum_cell_edge_m']=.003
        with patch('numpy.meshgrid',side_effect=AssertionError('Must not allocate cells')):
            plan=mesh_plan(s)
            self.assertTrue(plan['planned_edge_requirement_met'])
            self.assertFalse(plan['within_cell_budget'])
            self.assertGreater(plan['cells'],600_000_000_000)
            self.assertEqual(plan['five_components_float64_bytes'],plan['cells']*40)
            with self.assertRaisesRegex(ValueError,'No mesh allocated'):
                generate_mesh(s)

    def test_invalid_target_edges_are_rejected(self):
        for value in (0,-1,True,float('nan'),float('inf'),'0.003'):
            s=copy.deepcopy(self.spec)
            s['porous_mesh']['maximum_cell_edge_m']=value
            with self.subTest(value=value),self.assertRaises(ValueError):mesh_plan(s)

    def test_gci_rejects_oscillation_and_growing_error(self):
        good=gci(1.04,1.02,1.01)
        self.assertAlmostEqual(good['observed_order'],1.)
        self.assertTrue(good['pass'])
        for values in ((1.2,1.,1.1),(1.1,1.2,1.4),(1.,1.,1.)):
            self.assertFalse(gci(*values)['eligible'])
        changed=copy.deepcopy(self.spec);changed['coupled']['processes']=8
        self.assertEqual(signature(self.spec),signature(changed))
        changed['numerics']['dt_s']*=.5
        self.assertNotEqual(signature(self.spec),signature(changed))

    def test_fine_cells_partition_immediate_parent(self):
        fine,medium=self.meshes[2],self.meshes[1]
        mapped=restrict_to_base(fine['cell_centres_m'],fine['cell_volumes_m3'],fine['half_parent'])
        np.testing.assert_allclose(mapped,medium['cell_centres_m'],atol=1e-12,rtol=0)

    def test_time_comparison_requires_same_processes_and_physics(self):
        changed=copy.deepcopy(self.spec)
        changed['numerics']['dt_s']*=.5
        self.assertEqual(time_signature(self.spec),time_signature(changed))
        changed['coupled']['processes']=4
        self.assertNotEqual(time_signature(self.spec),time_signature(changed))
        changed=copy.deepcopy(self.spec)
        changed['loading']['porosity']=.5
        self.assertNotEqual(time_signature(self.spec),time_signature(changed))


if __name__=='__main__':unittest.main()
