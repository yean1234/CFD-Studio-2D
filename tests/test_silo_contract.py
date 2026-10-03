"""Exercise silo preflight without starting OpenFOAM or changing user Cases."""
import ast
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from cfd_studio.config_presets import finite_number
from cfd_studio.execution_workspace import ExecutionWorkspace
from tmc49_full_tank.tools.silo_contract import validate_runtime
from tmc49_full_tank.tools.build_silo_runtime import build, dictionaries, mesh_plan

ROOT = Path(__file__).resolve().parents[1]


def draft():
    config = json.loads((ROOT/'cfd_studio/configs/grain_silo.json').read_text())
    config['mesh']['require_external_mesh'] = False
    config['silo'] = {'kind': 'original', 'design': {'A': 10, 'B': 7, 'C': 0, 'D': 0},
                      'geometry_model': 'equivalent_boundary_ports_v1',
                      'geometry_assumptions': {
                          'reviewed': True, 'source': 'Synthetic test fixture, not approved physical input',
                          'domain_model': 'cylinder_full_height',
                          'central_inlet_model': 'equal_area_square',
                          'flow_distribution': 'nominal_area_proportional',
                          'ports_per_layer': 4, 'layer_z_min_m': .25, 'layer_z_max_m': .75,
                          'bottom_outlets_enabled': False}}
    return config


def normalizer():
    tree = ast.parse((ROOT/'cfd_studio/app.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_normalize_silo_config')
    env = {'json': json, 'math': math, 'finite_number': finite_number,
           'SILO_CONFIG': ROOT/'silo_reproduction/config.json',
           '_read_json_file': lambda p: json.loads(Path(p).read_text())}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<normalizer>', 'exec'), env)
    return env['_normalize_silo_config']


class SiloContractTests(unittest.TestCase):
    def test_original_survives_normalization_and_keeps_review_metadata(self):
        config = draft(); config['_studio'] = {'goals': 'draft review'}
        before = copy.deepcopy(config)
        ok, result, message = normalizer()(config)
        self.assertTrue(ok, message)
        self.assertEqual(result['silo'], config['silo'])
        self.assertEqual(result['_studio'], config['_studio'])
        self.assertEqual(config, before)
        validate_runtime(result)

    def test_original_missing_optimization_dimensions_becomes_zero_not_defaults(self):
        config = draft(); config['silo']['design'] = {'A': 10, 'B': 7}
        ok, result, _ = normalizer()(config)
        self.assertTrue(ok)
        self.assertEqual(result['silo']['design'], {'A': 10, 'B': 7, 'C': 0, 'D': 0})

    def test_original_rejects_mixed_and_malformed_design(self):
        for key, value in [('A', 20), ('B', 13), ('C', 6), ('D', 7), ('B', True)]:
            config = draft(); config['silo']['design'][key] = value
            ok, _, message = normalizer()(config)
            self.assertFalse(ok)
            self.assertIn('[CFG-G003]', message)

    def test_absent_or_unreviewed_geometry_does_not_touch_output(self):
        for transform, code in [(lambda c: c['silo'].pop('geometry_model'), 'CFG-G004'),
                                (lambda c: c['silo']['geometry_assumptions'].pop('reviewed'), 'CFG-G005')]:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory); (root/'0.orig').mkdir(); sentinel = root/'0.orig/U'
                sentinel.write_text('original')
                config = draft(); transform(config)
                with self.assertRaisesRegex(ValueError, code): build(root, config)
                self.assertEqual(sentinel.read_text(), 'original')
                self.assertFalse((root/'system').exists())

    def test_external_mesh_requirement_is_not_silently_ignored(self):
        config = draft(); config['mesh']['require_external_mesh'] = True
        with self.assertRaisesRegex(ValueError, 'CFG-G004'):
            validate_runtime(config)

    def test_missing_assumptions_never_fall_back_to_hidden_defaults(self):
        for key in ('domain_model', 'central_inlet_model', 'flow_distribution', 'ports_per_layer',
                    'layer_z_min_m', 'layer_z_max_m', 'bottom_outlets_enabled', 'source'):
            config = draft(); del config['silo']['geometry_assumptions'][key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'CFG-G005'):
                validate_runtime(config)

    def test_invalid_layers_and_original_bottom_ports_are_rejected(self):
        for key, value in [('layer_z_max_m', .25), ('layer_z_min_m', float('nan')),
                           ('ports_per_layer', True), ('ports_per_layer', 2.5),
                           ('bottom_outlets_enabled', True)]:
            config = draft(); config['silo']['geometry_assumptions'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): validate_runtime(config)

    def test_reviewed_surrogate_generates_no_optimization_bottom_ports(self):
        config = draft(); before = copy.deepcopy(config)
        plan = mesh_plan(config); files = dictionaries(config, plan)
        self.assertIn('sideInlets', files['0.orig/U'])
        self.assertNotIn('bottomInlets', files['0.orig/U'])
        self.assertEqual(plan['inlet_flow_m3_s']['bottom'], 0)
        self.assertEqual(config, before)
        with tempfile.TemporaryDirectory() as directory:
            build(directory, config)
            manifest = json.loads((Path(directory)/'case_manifest.json').read_text())
            self.assertEqual(manifest['reproduction_status'], 'reviewed_surrogate_not_paper_geometry')
            self.assertEqual(manifest['geometry_assumptions'], config['silo']['geometry_assumptions'])

    def test_http_start_rejects_before_hardware_or_solver_changes(self):
        tree = ast.parse((ROOT/'cfd_studio/app.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'H')
        node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_run_legacy')
        hardware = Mock(side_effect=AssertionError('hardware must not be changed'))
        env = {'_normalize_silo_config': normalizer(), 'project_config': lambda _: {},
               '_project_key': lambda _: '', '_active_rid': lambda: '', '_prepare_run_hardware': hardware}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<http-start>', 'exec'), env)
        config = draft(); config['silo'].pop('geometry_model')
        handler = Mock()
        env['_run_legacy'](handler, {'mode': 'fresh', 'config': config})
        response, status = handler._json.call_args.args
        self.assertEqual(status, 400)
        self.assertIn('CFG-G004', response['msg'])
        hardware.assert_not_called()

    def test_geometry_failure_is_not_offered_as_blind_retry(self):
        from cfd_studio.run_management import RunManagement
        for code in ('CFG-G003', 'CFG-G004', 'CFG-G005', 'CFG-G006'):
            result = RunManagement.recovery(object(), {'status': 'failed', 'error': '['+code+'] detail'}, {})
            self.assertFalse(result['retry'])
            self.assertEqual(result['category'], 'config')

    def test_enqueue_checks_entire_batch_before_mutating_any_case(self):
        good = draft(); bad = draft(); bad['silo'].pop('geometry_model')
        queue = {'cases': {'a': {'kind': 'grain_silo', 'status': 'draft', 'config': good},
                           'b': {'kind': 'grain_silo', 'status': 'draft', 'config': bad}}, 'order': []}
        import threading
        from types import SimpleNamespace
        host = SimpleNamespace(lock=threading.RLock(), queue_data=lambda: queue, save_queue=Mock())
        before = copy.deepcopy(queue)
        with self.assertRaisesRegex(ValueError, 'CFG-G004'):
            ExecutionWorkspace.queue_action(host, 'enqueue', ids=['a', 'b'])
        self.assertEqual(queue, before)
        host.save_queue.assert_not_called()


if __name__ == '__main__':
    unittest.main()
