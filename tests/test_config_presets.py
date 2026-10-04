"""운영 앱을 시작하지 않고 임시 폴더에서 프리셋 저장과 HTTP 입력을 검사한다."""
import ast
import copy
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
import unittest
from unittest.mock import Mock
from urllib.parse import urlparse

from cfd_studio.config_presets import finite_number, save_new_preset, validate_numerics

ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT/'cfd_studio/app.py').read_text(encoding='utf-8'))


def app_functions(folder):
    # Load only preset routes; keep the user environment and agent server isolated.
    namespace = dict(json=json, math=math, os=os, re=re, time=time,
                     BaseHTTPRequestHandler=BaseHTTPRequestHandler, urlparse=urlparse,
                     finite_number=finite_number, validate_numerics=validate_numerics,
                     save_new_preset=save_new_preset, CFGDIR=str(folder),
                     SILO_CONFIG=str(ROOT/'silo_reproduction/config.json'),
                     _read_json_file=lambda p: json.loads(Path(p).read_text(encoding='utf-8')),
                     get_status=lambda: {'running': False}, warehouse_post=lambda *a: False,
                     agent_activity_route=lambda *a, **kw: False,
                     WAREHOUSE_WORKSPACE=None, _apply_board_floor_revision=lambda c: (c, False),
                     saved_configs=lambda: sorted(p.stem for p in Path(folder).glob('*.json')),
                     saved_config_types=lambda: {})
    nodes = [n for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))
             and n.name in ('cfg_safe', '_normalize_silo_config', 'H')]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<config-test>', 'exec'), namespace)
    return namespace


def preset(kind='immersion'):
    return json.loads((ROOT/f'cfd_studio/configs/{kind}.json').read_text(encoding='utf-8'))


class ConfigPresetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)/'configs'
        self.app = app_functions(self.folder)

    def post(self, config=None, name='new preset', body=None):
        data = json.dumps(body if body is not None else {'name': name, 'config': config}).encode()
        handler = Mock(path='/api/config-save', headers={'Content-Length': str(len(data))}, rfile=io.BytesIO(data))
        self.app['H']._do_POST(handler)
        args = handler._json.call_args.args
        return (args[1] if len(args) > 1 else 200), args[0]

    def test_numeric_types_and_nonfinite_values(self):
        for value in (None, True, False, '', ' ', 'NaN', 'Infinity', float('inf'), [], {}, 10**400):
            with self.subTest(value=str(value)[:30]), self.assertRaises(ValueError):
                finite_number(value, '값')
        self.assertEqual(finite_number('1e-3', '값'), .001)
        self.assertEqual(finite_number('20', '값', integer=True), 20)
        with self.assertRaises(ValueError):
            finite_number(20.4, '값', integer=True)

    def test_current_presets_save_without_rewriting_originals(self):
        for kind in ('immersion', 'grain_silo'):
            config = preset(kind)
            before = copy.deepcopy(config)
            status, result = self.post(config, kind)
            self.assertEqual(status, 200, result)
            self.assertEqual(config, before)
            self.assertFalse(result['applied'])
            saved = json.loads((self.folder/(kind+'.json')).read_text(encoding='utf-8'))
            self.assertEqual(saved['_설정이름'], kind)
            validate_numerics(saved)

    def test_duplicate_names_and_case_variants_do_not_overwrite(self):
        self.assertEqual(self.post(preset(), 'Original')[0], 200)
        path = self.folder/'Original.json'
        before = path.read_bytes()
        changed = preset(); changed['run']['end_time_s'] = 100
        for name in ('Original', 'original', 'ORIGINAL'):
            self.assertEqual(self.post(changed, name)[0], 409)
            self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(list(self.folder.iterdir())), 1)

    def test_invalid_names_and_serialization_create_nothing(self):
        for name in ('CON', 'nul.json', 'COM1', '../outside', '', 'name.', 'name '):
            with self.subTest(name=name), self.assertRaises(ValueError):
                save_new_preset(self.folder, name, {})
        with self.assertRaises(ValueError):
            save_new_preset(self.folder, 'bad', {'value': float('nan')})
        self.assertFalse(self.folder.exists())

    def test_concurrent_requests_create_exactly_one_file(self):
        def save(_):
            try:
                save_new_preset(self.folder, 'parallel', {'value': 1})
                return True
            except FileExistsError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(save, range(16))), 1)
        self.assertEqual(json.loads((self.folder/'parallel.json').read_text()), {'value': 1})

    def test_running_and_unsupported_profiles_cannot_save(self):
        self.app['get_status'] = lambda: {'running': True}
        self.assertEqual(self.post(preset())[0], 409)
        self.assertFalse(self.folder.exists())
        self.app['get_status'] = lambda: {'running': False}
        _, response = self.post({'_해석유형': 'gas_transport', 'run': {}, 'tank': {}})
        self.assertFalse(response['ok'])
        self.assertFalse(self.folder.exists())

    def test_empty_fractional_and_nonfinite_silo_settings_rejected(self):
        for section, key, value in (
            ('mesh', 'target_cells', 1000.5), ('mesh', 'target_cells', True),
            ('mesh', 'target_cells', float('inf')), ('published', 'darcy_d_1_m2', ''),
            ('published', 'outer_diameter_m', True), ('run', 'max_iterations', float('inf')),
            ('run', 'max_iterations', 10.5), ('run', 'write_interval_iterations', 10000),
            ('solver_controls', 'convergence_tolerance', float('nan')),
        ):
            with self.subTest(section=section, key=key, value=value):
                config = preset('grain_silo'); config[section][key] = value
                status, result = self.post(config)
                self.assertEqual(status, 400, result)
        self.assertFalse(self.folder.exists())

    def test_silo_section_types_rejected(self):
        for section in ('mesh', 'run', 'published', 'silo', 'solver_controls', 'openfoam_mapping'):
            config = preset('grain_silo'); config[section] = ['wrong type']
            self.assertEqual(self.post(config)[0], 400)
        self.assertFalse(self.folder.exists())
        for value in ([], None, False):
            config = preset('grain_silo'); config['silo']['design'] = value
            self.assertEqual(self.post(config)[0], 400)

    def test_immersion_time_mesh_and_storage_domains_rejected(self):
        for section, key, value in (
            ('run', 'max_dt_s', 0), ('run', 'max_dt_s', True),
            ('run', 'maxCo', -1), ('run', 'write_interval_s', 0),
            ('run', 'viz_interval_s', 1000), ('run', 'viz_interval_s', float('nan')),
            ('run', 'time_step_mode', 'unknown'), ('mesh', 'dx_mm', -2),
        ):
            with self.subTest(section=section, key=key, value=value):
                config = preset(); config[section][key] = value
                status, result = self.post(config)
                self.assertEqual(status, 400, result)
        self.assertFalse(self.folder.exists())

    def test_valid_transient_silo_keeps_physical_time(self):
        config = preset('grain_silo')
        config['openfoam_mapping']['solver'] = 'pimpleFoam'
        config['run'] = {'end_time_s': 2.5, 'time_step_s': .01, 'write_interval_s': .2}
        status, result = self.post(config)
        self.assertEqual(status, 200, result)
        self.assertEqual(result['config']['run']['time_basis'], 'physical_time')
        self.assertEqual(result['config']['run']['end_time_s'], 2.5)
        self.assertEqual(result['config']['run']['time_step_s'], .01)
        config['run'] = {'end_time_s': .05, 'time_step_s': .001, 'write_interval_s': .01}
        status, result = self.post(config, 'short transient')
        self.assertEqual(status, 200, result)
        self.assertEqual(result['config']['run']['end_time_s'], .05)


if __name__ == '__main__':
    unittest.main()
