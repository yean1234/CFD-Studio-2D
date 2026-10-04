"""Axis transitions preserve geometry, reflection and nested refinement"""
import json
from pathlib import Path
import unittest
import numpy as np
from tracer_transport.mesh_transition import smooth_counts, interval_ratio, transition_ratio
from tracer_transport.porous_warehouse_mesh import mesh_plan, generate_mesh, restrict_to_base, layout

ROOT = Path(__file__).resolve().parents[1]


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT/'tracer_transport/warehouse_porous_convergence.json').read_text())

    def test_invalid_inputs_and_default_compatibility(self):
        self.assertEqual(mesh_plan(self.spec)['cells'], 1860)
        for value in (True, '1.2', 0, 1, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'MESH-R010'):
                transition_ratio({'max_axis_spacing_ratio':value})

    def test_no_coarsening_and_no_directional_bias(self):
        lengths = [1, 4, 10, 4, 1]
        before = [20, 4, 5, 4, 20]
        after = smooth_counts(lengths, before, 1.2)
        self.assertTrue(all(a >= b for a,b in zip(after,before)))
        self.assertEqual(after, after[::-1])
        self.assertLessEqual(interval_ratio(lengths, after), 1.2*(1+1e-12))
        self.assertEqual(before, [20,4,5,4,20])

    def test_explicit_toggle_preserves_ratio_and_legacy_behavior(self):
        mesh = self.spec['porous_mesh']
        mesh['max_axis_spacing_ratio'] = 1.2
        legacy = mesh_plan(self.spec)
        mesh['mesh_transition_enabled'] = False
        disabled = mesh_plan(self.spec)
        self.assertEqual(disabled['cells'], 1860)
        self.assertFalse(disabled['mesh_transition']['enabled'])
        self.assertEqual(mesh['max_axis_spacing_ratio'], 1.2)
        mesh['mesh_transition_enabled'] = True
        self.assertEqual(mesh_plan(self.spec)['cells'], legacy['cells'])
        for invalid in ({'mesh_transition_enabled': True},
                        {'mesh_transition_enabled': 'false', 'max_axis_spacing_ratio': 1.2}):
            with self.assertRaisesRegex(ValueError, 'MESH-R010'):
                transition_ratio(invalid)

    def test_budget_and_half_domain_plan(self):
        self.spec['porous_mesh'].update(max_axis_spacing_ratio=1.2, maximum_cells=1000)
        full = mesh_plan(self.spec)
        self.spec['porous_mesh']['domain_mode'] = 'symmetry_y_min'
        half = mesh_plan(self.spec)
        self.assertEqual(full['cells'], half['cells']*2)
        self.assertTrue(half['mesh_transition']['requirement_met'])
        self.assertFalse(half['within_cell_budget'])
        with self.assertRaisesRegex(ValueError, 'cell budget'):
            layout(self.spec)

    def test_real_geometry_and_grain_inventory_preserved(self):
        _, original = generate_mesh(self.spec)
        self.spec['porous_mesh']['max_axis_spacing_ratio'] = 1.2
        _, changed = generate_mesh(self.spec)
        for key in (None, 'loaded_region'):
            total=lambda m:np.sum(m['cell_volumes_m3']*(m[key] if key else 1))
            self.assertAlmostEqual(total(original), total(changed), places=8)
        self.assertGreater(len(changed['cell_volumes_m3']), len(original['cell_volumes_m3']))

    def test_nested_refinement_with_transition(self):
        self.spec['porous_mesh'].update(max_axis_spacing_ratio=1.2, maximum_cells=1000000, domain_mode='symmetry_y_min')
        _, base = generate_mesh(self.spec)
        self.spec['porous_mesh']['refinement'] = 2
        _, fine = generate_mesh(self.spec)
        reduced = restrict_to_base(fine['cell_centres_m'],fine['cell_volumes_m3'],fine['base_parent'])
        np.testing.assert_allclose(reduced,base['cell_centres_m'],atol=1e-10,rtol=0)
