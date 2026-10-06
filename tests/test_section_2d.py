"""2D research section: mesh topology, 3D->2D scaling and coarse-input export.

OpenFOAM is not required; blockMesh input is checked geometrically and the
exporter reads synthetic field files written in OpenFOAM ascii/binary layout.
"""
import copy
import csv
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from tmc49_full_tank.tools import build_case_2d as b2
from tmc49_full_tank.tools import export_coarse_2d as ex

ROOT = Path(__file__).resolve().parents[1]
PRESET = ROOT / 'cfd_studio/configs/immersion_2d.json'


def preset(**section):
    c = json.loads(PRESET.read_text(encoding='utf-8'))
    c['section_2d'].update(section)
    return c


def build(c):
    s = b2.section_settings(c)
    geo = b2.section_geometry(c, s)
    return s, geo, b2.build_mesh_2d(c, s, geo)


def parse_block_mesh(text):
    verts = re.search(r'vertices \((.*?)\n\);', text, re.S).group(1)
    pts = np.array([[float(v) for v in m] for m in re.findall(r'\(([-\d.e]+) ([-\d.e]+) ([-\d.e]+)\)', verts)])
    blocks = [tuple(map(int, m.split())) for m in re.findall(r'hex \(([\d ]+)\)', text)]
    patches = {}
    for name, kind, body in re.findall(r'    (\w+) \{ type (\w+); faces \((.*?)\); \}', text, re.S):
        patches[name] = (kind, [tuple(map(int, f.split())) for f in re.findall(r'\(([\d ]+)\)', body)])
    return pts, blocks, patches


def read_csv(path):
    with open(path, encoding='utf-8', newline='') as fh:
        return list(csv.DictReader(fh))


def write_field(path, values, binary, patch=None, ncomp=1):
    """Write a minimal OpenFOAM volField with an optional nonuniform cpu patch value."""
    kind = 'scalar' if ncomp == 1 else 'vector'

    def entry(arr):
        arr = np.asarray(arr, dtype='<f8')
        n = arr.shape[0]
        if binary:
            return b'nonuniform List<' + kind.encode() + b'> \n%d\n(' % n + arr.tobytes() + b')\n'
        rows = [(' '.join(f'{v:.10g}' for v in r) if ncomp > 1 else f'{r:.10g}') for r in arr]
        rows = [f'({r})' if ncomp > 1 else r for r in rows]
        return (f'nonuniform List<{kind}> \n{n}\n(\n' + '\n'.join(rows) + '\n)\n').encode()

    head = ('FoamFile\n{\n    version     2.0;\n    format      %s;\n'
            '    arch        "LSB;label=32;scalar=64";\n    class       vol%sField;\n}\n'
            'dimensions      [0 0 0 1 0 0 0];\n\n' % ('binary' if binary else 'ascii',
                                                     'Scalar' if ncomp == 1 else 'Vector')).encode()
    body = head + b'internalField   ' + entry(values) + b';\n\nboundaryField\n{\n'
    if patch is not None:
        body += (b'    cpu\n    {\n        type            externalWallHeatFluxTemperature;\n'
                 b'        mode            flux;\n        q               uniform 72010.9;\n'
                 b'        value           ' + entry(patch) + b';\n    }\n')
    body += b'    board\n    {\n        type            zeroGradient;\n    }\n}\n'
    Path(path).write_bytes(body)


class SectionMeshTests(unittest.TestCase):
    def test_blockmesh_faces_close_outward_and_cover_heater(self):
        c = preset()
        s, geo, (text, cells, grid, coil_faces) = build(c)
        pts, blocks, patches = parse_block_mesh(text)
        self.assertEqual(patches['frontAndBack'][0], 'empty')
        self.assertEqual(patches['top'][0], 'patch')
        self.assertEqual(sum(int(a) * int(b) for a, b in re.findall(r'\((\d+) (\d+) 1\) simpleGrading', text)), cells)
        total = np.zeros(3)
        owners = {frozenset(h): h for h in blocks}
        seen = set()
        for name, (kind, faces) in patches.items():
            for f in faces:
                key = frozenset(f)
                self.assertNotIn(key, seen, name)
                seen.add(key)
                a, b, c4, d = pts[list(f)]
                normal = 0.5 * np.cross(c4 - a, d - b)
                total += normal
                hexes = [h for h in blocks if key <= set(h)]
                self.assertEqual(len(hexes), 1, f'{name} face must border exactly one block')
                centre = pts[list(hexes[0])].mean(axis=0)
                self.assertGreater(np.dot(normal, pts[list(f)].mean(axis=0) - centre), 0, name)
        np.testing.assert_allclose(total, 0, atol=1e-6)
        # Heater faces: CPU front face of the board, heated height equals the scaling record
        heated = sum(f['y1_mm'] - f['y0_mm'] for f in grid['heater_faces'])
        self.assertAlmostEqual(heated / 1000, geo['scaling']['heated_height_2d_m'], places=9)
        self.assertTrue(all(abs(f['x_face_mm'] - c['board']['z1']) < 1e-9 for f in grid['heater_faces']))

    def test_cell_map_is_a_bijection_onto_fluid_cells(self):
        c = preset()
        s, geo, (text, cells, grid, _) = build(c)
        pairs = set(zip(grid['cell_ix'], grid['cell_iy']))
        self.assertEqual(len(pairs), cells)
        xe, ye = np.array(grid['x_edges_mm']), np.array(grid['y_edges_mm'])
        xc, yc = (xe[1:] + xe[:-1]) / 2, (ye[1:] + ye[:-1]) / 2
        for ix, iy in pairs:
            for r in (geo['board'], geo['coil']):
                self.assertFalse(r['x0'] < xc[ix] < r['x1'] and r['y0'] < yc[iy] < r['y1'])
        solid = sum(1 for i in range(len(xc)) for j in range(len(yc))
                    if any(r['x0'] < xc[i] < r['x1'] and r['y0'] < yc[j] < r['y1'] for r in (geo['board'], geo['coil'])))
        self.assertEqual(cells + solid, len(xc) * len(yc))
        # The heater-adjacent cell sits right of the board face in the heated rows
        for f in grid['heater_faces']:
            self.assertAlmostEqual(xe[grid['cell_ix'][f['cell']]], c['board']['z1'])
            self.assertTrue(ye[grid['cell_iy'][f['cell']]] - 1e-9 <= f['y0_mm'])

    def test_coarse_grid_stays_near_requested_spacing(self):
        c = preset()
        _, _, (_, cells, grid, _) = build(c)
        dy = np.diff(grid['y_edges_mm'])
        self.assertLess(abs(np.median(dy) - c['mesh']['dx_mm']), 0.2)
        self.assertLess(cells, 10000)


class SectionScalingTests(unittest.TestCase):
    def test_heat_rules(self):
        c = preset()
        Q = c['heater']['total_W']
        W = c['tank']['width_mm'] / 1000
        cpu = c['heater']['cpus'][0]
        L = (cpu['y1'] - cpu['y0']) / 1000
        q3 = Q / sum((u['x1'] - u['x0']) * (u['y1'] - u['y0']) * 1e-6 for u in c['heater']['cpus'])
        local = b2.section_geometry(c, b2.section_settings(c))['scaling']
        self.assertAlmostEqual(local['q_2d_W_m2'], q3)
        self.assertAlmostEqual(local['power_per_width_2d_W_m'], q3 * L)
        c['section_2d']['heat_rule'] = 'width_average'
        avg = b2.section_geometry(c, b2.section_settings(c))['scaling']
        self.assertAlmostEqual(avg['power_per_width_2d_W_m'], Q / W)
        self.assertAlmostEqual(avg['heated_height_2d_m'], L)
        c['section_2d']['heat_rule'] = 'flux_and_power'
        geo = b2.section_geometry(c, b2.section_settings(c))
        both = geo['scaling']
        self.assertAlmostEqual(both['q_2d_W_m2'], q3)
        # Heater ends are rounded to 1 micrometre in blockMeshDict
        self.assertLess(abs(both['power_per_width_2d_W_m'] / (Q / W) - 1), 1e-4)
        y0, y1 = geo['segments'][0]
        self.assertAlmostEqual((y0 + y1) / 2, (cpu['y0'] + cpu['y1']) / 2, places=3)

    def test_coil_target_preserves_equilibrium_ratio(self):
        root = ROOT / 'tmc49_full_tank'
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / 'case'
            shutil.copytree(root, case)
            c = preset(heat_rule='flux_and_power')
            (case / 'config.json').write_text(json.dumps(c, ensure_ascii=False), encoding='utf-8')
            r = subprocess.run([sys.executable, str(case / 'tools/build_case.py')],
                               capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(r.returncode, 0, r.stderr)
            man = json.loads((case / 'constant/section2d.json').read_text(encoding='utf-8'))
            coil, sc = man['coil'], man['scaling']
            ratio_2d = coil['UA_target_W_mK'] / sc['power_per_width_2d_W_m']
            ratio_3d = c['coil']['UA_target_W_K'] / c['heater']['total_W']
            self.assertAlmostEqual(ratio_2d, ratio_3d)
            self.assertLessEqual(coil['UA_effective_W_mK'], 0.9 * coil['UA_cap_W_mK'] + 1e-6)
            t_text = (case / '0.orig/T').read_text(encoding='utf-8')
            self.assertIn('mode            flux;', t_text)
            self.assertIn(f"q               uniform {sc['q_2d_W_m2']:.6g};", t_text)
            for name in ('U', 'p', 'p_rgh', 'alpha.vapour', 'alpha.water', 'alpha.liquid', 'T'):
                self.assertIn('frontAndBack { type empty; }', (case / '0.orig' / name).read_text(encoding='utf-8'))
            ctrl = (case / 'system/controlDict').read_text(encoding='utf-8')
            self.assertIn(f"({c['probes_mm']['points'][0][2] / 1000} {c['probes_mm']['points'][0][1] / 1000}", ctrl)


class SectionValidationTests(unittest.TestCase):
    def test_section_must_cut_a_cpu_and_rules_must_exist(self):
        c = preset(x_mm=230)
        with self.assertRaises(SystemExit) as err:
            b2.section_geometry(c, b2.section_settings(c))
        self.assertIn('CPU', str(err.exception))
        c = preset(heat_rule='volume')
        with self.assertRaises(SystemExit):
            b2.section_geometry(c, b2.section_settings(c))

    def test_dimension_switch_and_3d_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / 'case'
            shutil.copytree(ROOT / 'tmc49_full_tank', case)
            shutil.copy2(PRESET, case / 'config.json')
            tool = str(case / 'tools/build_case.py')
            run = lambda *a: subprocess.run([sys.executable, tool, *a], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(run('--check').returncode, 0)
            self.assertFalse((case / 'constant/section2d.json').exists())
            self.assertEqual(run().returncode, 0)
            self.assertTrue((case / 'constant/section2d.json').exists())
            r = run('--dimension', '3D')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse((case / 'constant/section2d.json').exists())
            self.assertNotIn('frontAndBack', (case / 'system/blockMeshDict').read_text(encoding='utf-8'))
            r = run('--dimension', '4D')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('case_dimension', r.stdout + r.stderr)


class CoarseExportTests(unittest.TestCase):
    def make_case(self, tmp, binary, with_patch):
        case = Path(tmp) / 'case'
        shutil.copytree(ROOT / 'tmc49_full_tank', case)
        shutil.copy2(PRESET, case / 'config.json')
        r = subprocess.run([sys.executable, str(case / 'tools/build_case.py')], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(r.returncode, 0, r.stderr)
        man = json.loads((case / 'constant/section2d.json').read_text(encoding='utf-8'))
        n, faces = man['cells'], man['grid']['heater_faces']
        fcell = [f['cell'] for f in faces]
        Tsat = man['fluid']['T_sat_K']
        # '0' is the initial condition and must not enter the statistics by default
        for k, t in enumerate(('0', '0.5', '1', '1.5', '2')):
            d = case / t
            d.mkdir()
            T = np.full(n, Tsat - 0.5)
            T[fcell] = Tsat + k                          # heater cells warm over time
            av = np.zeros(n)
            av[fcell] = 0.2 if t != '0' else 0.9
            write_field(d / 'T', T, binary, patch=(T[fcell] + 2.0 + np.arange(len(fcell))) if with_patch else None)
            write_field(d / 'alpha.vapour', av, binary)
            write_field(d / 'alpha.water', np.zeros(n), binary)
            write_field(d / 'U', np.zeros((n, 3)), binary, ncomp=3)
        return case, man

    def check_export(self, binary, with_patch):
        with tempfile.TemporaryDirectory() as tmp:
            case, man = self.make_case(tmp, binary, with_patch)
            out = Path(tmp) / 'out'
            rep = ex.export(str(case), str(out), skip_initial=0.5)
            self.assertEqual(rep['frames_with_T'], 4)
            self.assertEqual(rep['frames_averaged'], 2)
            rows = read_csv(out / 'coarse_inputs.csv')
            self.assertEqual(list(rows[0]), list(ex.COOPER_COLUMNS))
            self.assertEqual(len(rows), len(man['grid']['heater_faces']))
            for row in rows:
                self.assertAlmostEqual(float(row['vapor_fraction']), 0.2)
                self.assertAlmostEqual(float(row['q_W_m2']), man['scaling']['q_2d_W_m2'], places=3)
            ext = read_csv(out / 'coarse_inputs_extended.csv')
            fl = man['fluid']
            tc = float(ext[0]['T_cell_K'])
            self.assertAlmostEqual(tc, fl['T_sat_K'] + 3.5)          # frames 3 and 4 after skipping half
            if with_patch:
                # Solver patch values are taken as written, in ascending face height
                self.assertEqual(rep['T_wall_source_frames'], {'solver_patch': 4, 'conduction_estimate': 0})
                for k, row in enumerate(ext):
                    self.assertAlmostEqual(float(row['T_wall_cfd_K']) - float(row['T_cell_K']), 2.0 + k)
            else:
                # Fallback: T_wall - T_cell = q delta / kappa_mix with kappa_mix = 0.8 k_l(T) + 0.2 k_v
                self.assertEqual(rep['T_wall_source_frames'], {'solver_patch': 0, 'conduction_estimate': 4})
                f = man['grid']['heater_faces'][0]
                rise = [man['scaling']['q_2d_W_m2'] * f['delta_mm'] / 1000
                        / (0.8 * np.interp(t, fl['kappa_table_K'], fl['kappa_table_W_mK']) + 0.2 * fl['k_vapor'])
                        for t in (fl['T_sat_K'] + 3, fl['T_sat_K'] + 4)]
                self.assertAlmostEqual(float(ext[0]['T_wall_cfd_K']) - tc, np.mean(rise), places=6)
            self.assertAlmostEqual(float(ext[0]['dT_sub_K']), 0.5, places=6)
            coarse = ex.export(str(case), str(Path(tmp) / 'coarse'), skip_initial=0.5, coarse_dx_mm=6.2)
            self.assertEqual(coarse['coarse_block_faces'], 2)
            rows = read_csv(Path(tmp) / 'coarse/coarse_inputs.csv')
            self.assertEqual(len(rows), len(man['grid']['heater_faces']) // 2)
            report = json.loads((out / 'export_manifest.json').read_text(encoding='utf-8'))
            self.assertIsNone(report['fluid']['p_critical_Pa'])
            fields = out / report['fields_file']
            if fields.suffix == '.h5':
                import h5py
                with h5py.File(fields) as h5:
                    temp, mask = h5['temperature'][...], h5['mask'][...]
            else:
                with np.load(fields) as z:
                    temp, mask = z['temperature'], z['mask']
            self.assertEqual(temp.shape[0], 4)
            self.assertTrue(np.isnan(temp[0][mask == 0]).all())
            self.assertFalse(np.isnan(temp[0][mask == 1]).any())
            with_zero = ex.export(str(case), str(Path(tmp) / 'zero'), skip_initial=0.0, include_zero=True)
            self.assertEqual(with_zero['frames_with_T'], 5)

    def test_binary_fields_with_solver_patch(self):
        self.check_export(binary=True, with_patch=True)

    def test_ascii_fields_without_patch(self):
        self.check_export(binary=False, with_patch=False)


if __name__ == '__main__':
    unittest.main()
