# -*- coding: utf-8 -*-
"""2D vertical-section generator for the TMC-49 immersion tank (research mode).

The 3D tank config stays the single source of geometry, fluids and run settings.
This module cuts the tank along the y-z plane at x = section_2d.x_mm, the only
plane in which the CPU heated face is still a wall, and writes a one-cell-thick
OpenFOAM case with empty front/back patches.

Axis mapping at this boundary (mm):
  OpenFOAM x = tank depth z  (0 = back wall, depth_mm = front wall)
  OpenFOAM y = tank height y (gravity -y, unchanged)
  OpenFOAM z = extrusion of thickness_mm, patch frontAndBack = empty

3D -> 2D scaling (per metre of extrusion, W/m and W/(m K)):
  local_flux     keep the CPU heat flux and heated height (default)
  width_average  keep heated height, spread the tank power over represented width
  flux_and_power keep the CPU heat flux and power per width, shrink heated height
The coil UA target is scaled with the 2D heat input so that the equilibrium
upper-liquid temperature Ta + Q/UA equals the 3D value; the grid cap still applies.
"""
import copy
import json
import math
import os
import re
import sys

try:
    from . import build_case as base
    from .mesh_refinement import refinement_boxes, refined_axis
except ImportError:
    import build_case as base
    from mesh_refinement import refinement_boxes, refined_axis

HEAT_RULES = ('local_flux', 'width_average', 'flux_and_power')
MANIFEST = 'constant/section2d.json'
G = 9.81


# ---------------------------------------------------------------- settings
def section_settings(c):
    """Resolve section_2d defaults without changing the config dict."""
    raw = c.get('section_2d') or {}
    if not isinstance(raw, dict):
        sys.exit("[검증 실패]\n  - section_2d 는 객체여야 함")
    cpus = c['heater']['cpus']
    try:
        cpu_index = int(raw.get('cpu_index', 0))
        for key in ('x_mm', 'thickness_mm', 'represented_width_mm', 'coil_UA_W_mK'):
            if raw.get(key) is not None:
                float(raw[key])
    except (TypeError, ValueError):
        sys.exit("[검증 실패]\n  - section_2d 의 cpu_index·x_mm·thickness_mm·represented_width_mm·coil_UA_W_mK 는 숫자여야 함")
    x_mm = raw.get('x_mm')
    if x_mm is None:
        if not 0 <= cpu_index < len(cpus):
            sys.exit(f"[검증 실패]\n  - section_2d.cpu_index {cpu_index} 가 heater.cpus 범위 밖")
        cpu = cpus[cpu_index]
        x_mm = 0.5 * (cpu['x0'] + cpu['x1'])
    thickness = raw.get('thickness_mm')
    if thickness is None:
        thickness = c['mesh']['dx_mm']
    width = raw.get('represented_width_mm')
    if width is None:
        width = c['tank']['width_mm']
    return {
        'x_mm': float(x_mm),
        'cpu_index': cpu_index,
        'heat_rule': str(raw.get('heat_rule', 'local_flux')),
        'represented_width_mm': float(width),
        'thickness_mm': float(thickness),
        'coil_UA_W_mK': raw.get('coil_UA_W_mK'),
    }


def _inside(v, lo, hi):
    return lo < v < hi


def section_geometry(c, s):
    """Project 3D boxes onto the section and apply the selected heat rule.

    Returns rectangles in section coordinates (x = tank z, y = tank y), the heater
    segments and the scaling record that is written to the manifest.
    """
    W, D, H = c['tank']['width_mm'], c['tank']['depth_mm'], c['tank']['liquid_height_mm']
    err = []
    xs = s['x_mm']
    if not _inside(xs, 0, W):
        err.append(f"section_2d.x_mm({xs}) 는 0~{W} mm 사이여야 함")
    if s['heat_rule'] not in HEAT_RULES:
        err.append(f"section_2d.heat_rule 은 {', '.join(HEAT_RULES)} 중 하나여야 함")
    if not s['thickness_mm'] > 0:
        err.append("section_2d.thickness_mm 는 0보다 커야 함")
    if not s['represented_width_mm'] > 0:
        err.append("section_2d.represented_width_mm 는 0보다 커야 함")
    b, k = c['board'], c['coil']
    board = None
    if _inside(xs, b['x0'], b['x1']):
        board = {'x0': b['z0'], 'x1': b['z1'], 'y0': b['y0'], 'y1': b['y1']}
    coil = None
    if _inside(xs, k['x0'], k['x1']):
        coil = {'x0': k['z0'], 'x1': k['z1'], 'y0': k['y0'], 'y1': k['y1']}
    cpus = c['heater']['cpus']
    hit = [u for u in cpus if _inside(xs, u['x0'], u['x1'])]
    if not hit:
        ranges = ', '.join(f"{u['x0']}~{u['x1']}" for u in cpus)
        err.append(f"section_2d.x_mm({xs}) 가 CPU를 지나지 않음 — 발열면 없음 (CPU x 범위: {ranges})")
    if hit and board is None:
        err.append("CPU 단면이 보드 밖 — 보드 x 범위 확인 필요")
    if err:
        sys.exit("[검증 실패]\n  - " + "\n  - ".join(err))

    Q = float(c['heater']['total_W'])
    area_3d = sum((u['x1'] - u['x0']) * (u['y1'] - u['y0']) for u in cpus) * 1e-6
    q_3d = Q / area_3d                                  # W/m^2 on the 3D CPU faces
    heights = [(u['y0'], u['y1']) for u in hit]
    sum_l = sum(y1 - y0 for y0, y1 in heights) / 1000.0  # heated height in the section [m]
    p_width = Q / (s['represented_width_mm'] / 1000.0)   # tank power per metre of width [W/m]
    rule = s['heat_rule']
    shrink = 1.0
    notes = []
    if rule == 'local_flux':
        q_2d = q_3d
    elif rule == 'width_average':
        q_2d = p_width / sum_l
    else:
        q_2d = q_3d
        shrink = p_width / (q_3d * sum_l)
        if shrink > 1.0:
            notes.append("flux_and_power: 폭당 전력이 CPU 높이 전체 발열보다 커서 높이 축소 불가 — local_flux와 동일하게 처리")
            shrink = 1.0
    segments = []
    for y0, y1 in heights:
        mid, half = 0.5 * (y0 + y1), 0.5 * (y1 - y0) * shrink
        segments.append((round(mid - half, 3), round(mid + half, 3)))
    heated = sum(y1 - y0 for y0, y1 in segments) / 1000.0
    q_width = q_2d * heated                               # W per metre of extrusion
    scaling = {
        'heat_rule': rule,
        'q_3d_W_m2': q_3d,
        'q_2d_W_m2': q_2d,
        'heated_height_3d_m': sum_l,
        'heated_height_2d_m': heated,
        'height_scale': shrink,
        'power_per_width_2d_W_m': q_width,
        'power_per_width_3d_tank_W_m': p_width,
        'concentration_vs_tank': q_width / p_width,
        'represented_width_m': s['represented_width_mm'] / 1000.0,
        'notes': notes,
    }
    return {'board': board, 'coil': coil, 'segments': segments, 'scaling': scaling,
            'cpus_cut': [cpus.index(u) for u in hit], 'W': W, 'D': D, 'H': H}


# ---------------------------------------------------------------- mesh
def _project_refinements(c, s):
    """Keep tank refinement boxes that intersect the section, mapped to (x=z, y=y)."""
    W, D, H = c['tank']['width_mm'], c['tank']['depth_mm'], c['tank']['liquid_height_mm']
    boxes = refinement_boxes(c['mesh'], [W, H, D], c)
    out = []
    for lo, hi, size in boxes:
        if lo[0] <= s['x_mm'] <= hi[0]:
            out.append(([lo[2], lo[1]], [hi[2], hi[1]], size))
    return out


def build_mesh_2d(c, s, geo):
    """blockMeshDict text, cell count, grid map and coil faces for the section."""
    D, H = geo['D'], geo['H']
    dx = c['mesh']['dx_mm']
    t = s['thickness_mm']
    board, coil = geo['board'], geo['coil']
    rects = [r for r in (board, coil) if r]
    xs = base.breakpoints([v for r in rects for v in (r['x0'], r['x1'])], 0, D)
    ys = base.breakpoints([v for r in rects for v in (r['y0'], r['y1'])]
                          + [c['layers']['dielectric_mm']]
                          + [v for seg in geo['segments'] for v in seg], 0, H)
    boxes = _project_refinements(c, s)
    xs, nx = refined_axis(xs, 0, dx, boxes)
    ys, ny = refined_axis(ys, 1, dx, boxes)
    zs, nz = [0.0, t], [1]
    NC, NR, NZ = len(xs) - 1, len(ys) - 1, 1

    def spans(lines, a0, a1):
        return [i for i in range(len(lines) - 1) if lines[i] >= a0 - 1e-9 and lines[i + 1] <= a1 + 1e-9]

    holes = {}
    for name, r in (('board', board), ('coil', coil)):
        if not r:
            continue
        for i in spans(xs, r['x0'], r['x1']):
            for j in spans(ys, r['y0'], r['y1']):
                holes[(i, j)] = name
    heater_rows = set(j for y0, y1 in geo['segments'] for j in spans(ys, y0, y1))

    def vid(i, j, kk):
        return kk * (NC + 1) * (NR + 1) + j * (NC + 1) + i

    def face(i, j, kk, side):
        # Same vertex order as the 3D generator so blockMesh sees outward normals.
        if side == 'W': return (vid(i, j, kk), vid(i, j, kk + 1), vid(i, j + 1, kk + 1), vid(i, j + 1, kk))
        if side == 'E': return (vid(i + 1, j, kk), vid(i + 1, j + 1, kk), vid(i + 1, j + 1, kk + 1), vid(i + 1, j, kk + 1))
        if side == 'S': return (vid(i, j, kk), vid(i + 1, j, kk), vid(i + 1, j, kk + 1), vid(i, j, kk + 1))
        if side == 'N': return (vid(i, j + 1, kk), vid(i, j + 1, kk + 1), vid(i + 1, j + 1, kk + 1), vid(i + 1, j + 1, kk))
        if side == 'B': return (vid(i, j, kk), vid(i, j + 1, kk), vid(i + 1, j + 1, kk), vid(i + 1, j, kk))
        return (vid(i, j, kk + 1), vid(i + 1, j, kk + 1), vid(i + 1, j + 1, kk + 1), vid(i, j + 1, kk + 1))

    lines = ['/*--------------------------------*- C++ -*----------------------------------*/',
             'FoamFile { version 2.0; format ascii; class dictionary; object blockMeshDict; }',
             f'// config.json 2D 단면 자동 생성 (탱크 x={s["x_mm"]} mm, dx={dx} mm, 두께 {t} mm) — tools/build_case_2d.py',
             '// 축 대응: OpenFOAM x = 탱크 깊이 z, y = 높이 y, z = 1셀 두께(empty)',
             'scale 0.001;', 'vertices (']
    for kk in range(NZ + 1):
        for j in range(NR + 1):
            for i in range(NC + 1):
                lines.append(f'    ({xs[i]} {ys[j]} {zs[kk]})')
    lines += [');', 'blocks (']
    # Global (ix, iy) of every OpenFOAM cell. blockMesh numbers cells block by block
    # in the listed order and, inside a block, with x fastest, then y.
    x_off = [sum(nx[:i]) for i in range(NC + 1)]
    y_off = [sum(ny[:j]) for j in range(NR + 1)]
    cell_ix, cell_iy, block_first = [], [], {}
    for j in range(NR):
        for i in range(NC):
            if (i, j) in holes:
                continue
            block_first[(i, j)] = len(cell_ix)
            for jj in range(ny[j]):
                for ii in range(nx[i]):
                    cell_ix.append(x_off[i] + ii)
                    cell_iy.append(y_off[j] + jj)
            h8 = [vid(i, j, 0), vid(i + 1, j, 0), vid(i + 1, j + 1, 0), vid(i, j + 1, 0),
                  vid(i, j, 1), vid(i + 1, j, 1), vid(i + 1, j + 1, 1), vid(i, j + 1, 1)]
            lines.append(f'    hex ({" ".join(map(str, h8))}) ({nx[i]} {ny[j]} 1) simpleGrading (1 1 1)')
    lines.append(');')

    open_top = bool((c.get('run') or {}).get('open_top', True))
    groups = {'cpu': [], 'board': [], 'coil': [], 'outerWalls': [], 'top': [], 'frontAndBack': []}
    nbr = {'W': (-1, 0), 'E': (1, 0), 'S': (0, -1), 'N': (0, 1)}
    heater_faces = []
    for j in range(NR):
        for i in range(NC):
            if (i, j) in holes:
                continue
            groups['frontAndBack'] += [face(i, j, 0, 'B'), face(i, j, 0, 'F')]
            for side, (di, dj) in nbr.items():
                ii, jj = i + di, j + dj
                outside = not (0 <= ii < NC and 0 <= jj < NR)
                hole = holes.get((ii, jj))
                if not outside and hole is None:
                    continue
                f = face(i, j, 0, side)
                if hole == 'board' and side == 'W' and j in heater_rows:
                    groups['cpu'].append(f)
                    dy = (ys[j + 1] - ys[j]) / ny[j]
                    half = (xs[i + 1] - xs[i]) / nx[i] / 2.0
                    first = block_first[(i, j)]
                    for jj in range(ny[j]):
                        heater_faces.append({
                            'cell': first + jj * nx[i],
                            'y0_mm': ys[j] + jj * dy, 'y1_mm': ys[j] + (jj + 1) * dy,
                            'x_face_mm': xs[i], 'delta_mm': half,
                        })
                elif hole:
                    groups[hole].append(f)
                elif open_top and side == 'N' and jj >= NR:
                    groups['top'].append(f)       # open top absorbs phase-change volume
                else:
                    groups['outerWalls'].append(f)
    lines.append('boundary (')
    for name in ('cpu', 'board', 'coil', 'outerWalls', 'top', 'frontAndBack'):
        if not groups[name]:
            continue
        kind = 'patch' if name == 'top' else ('empty' if name == 'frontAndBack' else 'wall')
        lines.append(f'    {name} {{ type {kind}; faces (')
        for f in groups[name]:
            lines.append(f'        ({f[0]} {f[1]} {f[2]} {f[3]})')
        lines.append('    ); }')
    lines.append(');')

    x_edges = [xs[i] + (xs[i + 1] - xs[i]) * m / nx[i] for i in range(NC) for m in range(nx[i])] + [xs[-1]]
    y_edges = [ys[j] + (ys[j + 1] - ys[j]) * m / ny[j] for j in range(NR) for m in range(ny[j])] + [ys[-1]]
    heater_faces.sort(key=lambda f: f['y0_mm'])

    coil_faces = []
    if coil:
        # Per metre of extrusion: (face length [m] x 1 m, half-cell distance [m]).
        def adj(lines_, counts, val, up):
            for q in range(len(lines_) - 1):
                if up and abs(lines_[q] - val) < 1e-9:
                    return (lines_[q + 1] - lines_[q]) / counts[q]
                if not up and abs(lines_[q + 1] - val) < 1e-9:
                    return (lines_[q + 1] - lines_[q]) / counts[q]
            return dx
        lx = (coil['x1'] - coil['x0']) / 1000.0
        ly = (coil['y1'] - coil['y0']) / 1000.0
        coil_faces = [
            (lx, adj(ys, ny, coil['y0'], False) / 2000.0),
            (lx, adj(ys, ny, coil['y1'], True) / 2000.0),
            (ly, adj(xs, nx, coil['x0'], False) / 2000.0),
            (ly, adj(xs, nx, coil['x1'], True) / 2000.0),
        ]
    grid = {
        'x_edges_mm': x_edges, 'y_edges_mm': y_edges,
        'cell_ix': cell_ix, 'cell_iy': cell_iy,
        'heater_faces': heater_faces,
        'patch_face_counts': {k: len(v) for k, v in groups.items()},
    }
    return '\n'.join(lines), len(cell_ix), grid, coil_faces


# ---------------------------------------------------------------- fields
def zero_T_2d(c, q_2d, h, open_top, Tw):
    Ta = c['coil']['Ta_C'] + 273.15
    top = (f'    top          {{ type inletOutlet; inletValue uniform {Tw:.2f}; '
           f'value uniform {Tw:.2f}; }}\n') if open_top else ''
    return f'''/*--------------------------------*- C++ -*----------------------------------*/
FoamFile {{ version 2.0; format ascii; class volScalarField; object T; }}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
// config.json 2D 단면 자동 생성 — tools/build_case_2d.py
dimensions [0 0 0 1 0 0 0];
internalField uniform 305;      // setFields가 층별 초기 온도 설정

boundaryField
{{
    cpu         // CPU 발열면 — 2D 열유속 {q_2d/1000:.2f} kW/m² (두께와 무관한 flux 모드)
    {{
        type            externalWallHeatFluxTemperature;
        mode            flux;
        q               uniform {q_2d:.6g};
        kappaMethod     fluidThermo;
        value           uniform 320;
    }}
    board       {{ type zeroGradient; }}     // 기판 단열 근사
    coil        // 냉각 코일 — h(T-Ta), h는 2D 폭당 UA 목표에서 역산
    {{
        type            externalWallHeatFluxTemperature;
        mode            coefficient;
        h               uniform {h};
        Ta              constant {Ta:.2f};
        kappaMethod     fluidThermo;
        value           uniform 300;
    }}
    outerWalls  {{ type zeroGradient; }}     // 외벽 단열 근사
    frontAndBack {{ type empty; }}           // 2D 단면 앞뒤면
{top}}}
'''


def drop_function(text, name):
    """Remove one top-level functionObject block (name + balanced braces) from controlDict."""
    start = re.search(r'^\s*' + re.escape(name) + r'\b[^\n]*\n\s*\{', text, re.M)
    if not start:
        return text
    depth, i = 0, text.index('{', start.start())
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[:start.start()] + text[i + 1:]
        i += 1
    return text


def add_empty_patch(text):
    """Insert the empty front/back entry before the closing brace of boundaryField."""
    end = text.rstrip().rfind('}')
    return text[:end] + '    frontAndBack { type empty; }\n' + text[end:]


def liquid_density_at(d, T):
    mp = d.get('manual_properties')
    if mp:
        return float(mp['rho_kg_m3']) * (1.0 - float(mp['beta_1_K']) * (T - (float(mp['T_ref_C']) + 273.15)))
    if d.get('property_tables'):
        return base.table_value(d['property_tables']['rho'], T)
    return base.poly(d['rho_poly'], T)


def liquid_kappa_at(d, T):
    mp = d.get('manual_properties')
    if mp:
        return float(mp['kappa_W_mK'])
    if d.get('property_tables'):
        return base.table_value(d['property_tables']['kappa'], T)
    return base.poly(d['kappa_poly'], T)


def fluid_record(c):
    """Dielectric fluid values the exporter and Cooper inversion need, with gaps marked."""
    d = c['dielectric_fluid']
    Tsat = float(d['Tsat_C']) + 273.15
    rho_l = liquid_density_at(d, Tsat)
    rho_v = base.P_ATM * float(d['molWeight']) * 1e-3 / base.R_GAS / Tsat
    sigma = float(d['sigma_lv'])
    l0 = math.sqrt(sigma / (G * max(rho_l - rho_v, 1.0)))
    t0 = math.sqrt(l0 / G)
    props = d.get('property_tables') or {}
    mp = d.get('manual_properties') or {}
    cp = float(mp['cp_J_kgK']) if mp else (base.table_value(props['cp'], Tsat) if 'cp' in props else None)
    mu = float(mp['mu_Pa_s']) if mp else (base.table_value(props['mu'], Tsat) if 'mu' in props else None)
    return {
        'name': d.get('name', 'TMC-49'),
        'molar_mass_g_mol': float(d['molWeight']),
        'T_sat_K': Tsat,
        'p_operating_Pa': base.P_ATM,
        'p_critical_Pa': None,
        'p_critical_note': 'config.json에 임계압 근거 없음 — Cooper p_r 계산 전 확인 필요',
        'k_liquid': liquid_kappa_at(d, Tsat),
        'k_vapor': float(c['vapour']['kappa']),
        'k_upper_liquid': float((c['water'].get('manual_properties') or {}).get('kappa_W_mK')
                                or c['water'].get('kappa_30C') or 0.615),
        'rho_liquid': rho_l,
        'rho_vapor': rho_v,
        'cp_liquid': cp,
        'mu_liquid': mu,
        'h_fg': float(d['h_fg_J_kg']),
        'sigma': sigma,
        'kappa_table_K': (props.get('kappa') or {}).get('T_K'),
        'kappa_table_W_mK': (props.get('kappa') or {}).get('values'),
        'nondim_l0_m': l0, 'nondim_t0_s': t0, 'nondim_u0_m_s': l0 / t0,
        'source': 'tmc49_full_tank/config.json (vapour cp/mu/kappa analogous)',
    }


def map_probes(c, s, geo):
    """Project tank probes [x,y,z] onto the section (x = z, y = y, z = mid-thickness)."""
    out, err = [], []
    for p in c['probes_mm']['points']:
        x2, y2 = float(p[2]), float(p[1])
        for name in ('board', 'coil'):
            r = geo[name]
            if r and r['x0'] < x2 < r['x1'] and r['y0'] < y2 < r['y1']:
                err.append(f"프로브 {p} 가 2D 단면에서 {name} 내부로 투영됨")
        out.append([x2, y2, s['thickness_mm'] / 2.0])
    if err:
        sys.exit("[검증 실패]\n  - " + "\n  - ".join(err))
    return out


def fix_reference_point(root, s, geo, open_top):
    """A closed 2D domain needs pRefPoint inside the slab; open top needs no reference."""
    if open_top:
        return None
    path = os.path.join(root, 'system/fvSolution')
    with open(path, encoding='utf-8') as fh:
        text = fh.read()
    m = re.search(r'pRefPoint\s*\(\s*([-0-9.eE+]+)\s+([-0-9.eE+]+)\s+([-0-9.eE+]+)\s*\)', text)
    if not m:
        return None
    x, y, z = (float(v) for v in m.groups())
    t = s['thickness_mm'] / 1000.0
    if 0 < x < geo['D'] / 1000.0 and 0 < y < geo['H'] / 1000.0 and 0 < z < t:
        return None
    point = f'pRefPoint           ({0.02:g} {(geo["H"] - 10) / 1000.0:g} {t / 2:g});'
    text = text[:m.start()] + point + text[m.end():]
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return point


# ---------------------------------------------------------------- main entry
def build(root, c, check=False):
    """Generate the 2D section case from an already validated 3D config."""
    s = section_settings(c)
    geo = section_geometry(c, s)
    sc = geo['scaling']
    bmd, cells, grid, coil_faces = build_mesh_2d(c, s, geo)
    print(f"[build_case_2d] 2D 단면 x={s['x_mm']:g} mm (CPU {geo['cpus_cut']}) | 셀 {cells:,} | "
          f"두께 {s['thickness_mm']:g} mm (empty)", file=sys.stderr)
    print(f"[build_case_2d] 스케일링 {sc['heat_rule']}: q″ {sc['q_2d_W_m2']/1000:.2f} kW/m² "
          f"(3D {sc['q_3d_W_m2']/1000:.2f}) · 발열 높이 {sc['heated_height_2d_m']*1000:.2f} mm "
          f"(3D {sc['heated_height_3d_m']*1000:.2f}) · 폭당 {sc['power_per_width_2d_W_m']:.1f} W/m "
          f"= 탱크 폭 평균의 {sc['concentration_vs_tank']:.2f}배", file=sys.stderr)
    for note in sc['notes']:
        print(f"[build_case_2d] 참고: {note}", file=sys.stderr)

    # Coil: keep Ta + Q/UA of the 3D model by scaling UA with the 2D heat input.
    upper = c['water']
    kw = float((upper.get('manual_properties') or {}).get('kappa_W_mK') or upper.get('kappa_30C') or 0.615)
    Q3 = float(c['heater']['total_W'])
    Ta = float(c['coil']['Ta_C'])
    coil = {'present': bool(coil_faces)}
    h = float(c['coil']['h_W_m2K'])
    if coil_faces:
        UA3 = float(c['coil'].get('UA_target_W_K') or 0) or None
        if s['coil_UA_W_mK'] is not None:
            target = float(s['coil_UA_W_mK'])
            origin = 'section_2d.coil_UA_W_mK'
        elif UA3:
            target = UA3 * sc['power_per_width_2d_W_m'] / Q3
            origin = 'UA_target × (2D 폭당 입열 / 3D 입열)'
        else:
            target = None
            origin = 'coil.h_W_m2K (UA 목표 없음)'
        cap = base.coil_UA_cap(coil_faces, kw)
        if target:
            use = min(target, 0.90 * cap)
            h_new = base.coil_h_for(coil_faces, use, kw)
            if h_new:
                h = round(h_new, 1)
        ua = base.coil_UA(coil_faces, h, kw)
        q_w = sc['power_per_width_2d_W_m']
        equilibrium = Ta + q_w / ua
        Tsat = float(c['dielectric_fluid']['Tsat_C'])
        coil.update({'UA_target_W_mK': target, 'UA_target_origin': origin, 'UA_cap_W_mK': cap,
                     'UA_effective_W_mK': ua, 'h_W_m2K': h,
                     'equilibrium_upper_C': equilibrium,
                     'equilibrium_upper_3d_target_C': (Ta + Q3 / UA3) if UA3 else None})
        target_text = f"{target:.2f}" if target else "없음"
        print(f"[build_case_2d] 코일: 목표 UA {target_text} W/(m·K) ({origin}) · 격자 상한 {cap:.2f} · "
              f"실효 {ua:.2f} → 상단 액체 평형 {equilibrium:.1f} °C", file=sys.stderr)
        if target and target > 0.90 * cap:
            print("[build_case_2d] 참고: 코일 UA 목표가 격자 상한의 90%를 넘어 90%로 제한함 (3D 생성기와 같은 규칙)",
                  file=sys.stderr)
        if target and equilibrium > Tsat:
            water_area = (geo['H'] - c['layers']['dielectric_mm']) * geo['D'] * 1e-6
            water_area -= (geo['coil']['x1'] - geo['coil']['x0']) * (geo['coil']['y1'] - geo['coil']['y0']) * 1e-6
            wp = upper.get('manual_properties') or {}
            rho_cp = (float(wp.get('rho_kg_m3') or upper.get('rho_30C') or 995.6)
                      * float(wp.get('cp_J_kgK') or upper.get('cp_30C') or 4180.0))
            Tw0 = float(c['layers'].get('init_T_water_C', Ta))
            drift = (q_w - ua * (Tw0 - Ta)) / (rho_cp * water_area)
            coil['upper_drift_K_s'] = drift
            # Above Tsat the upper liquid can no longer condense rising vapour.
            to_sat = (Tsat - Tw0) / drift if drift > 0 and Tw0 < Tsat else None
            coil['upper_to_Tsat_s'] = to_sat
            budget = f", 기화점 {Tsat:g} °C 도달까지 약 {to_sat:.0f} s" if to_sat else ""
            remedy = ("heat_rule=flux_and_power 또는 코일 주변 격자 세분화"
                      if sc['heat_rule'] == 'local_flux' else "코일 주변 격자 세분화 또는 section_2d.coil_UA_W_mK 확인")
            end = float(c['run']['end_time_s'])
            print(f"[build_case_2d] ★경고: 2D 폭당 입열을 이 격자의 코일이 다 배출하지 못함 — 장기 평형 "
                  f"{equilibrium:.1f} °C 가 기화점 {Tsat:g} °C 초과. 상단 액체가 초기 약 {drift:.4f} K/s 로 "
                  f"가열됨(계산 {end:g} s 동안 약 {drift*end:.1f} K{budget}). 장시간 계산이 필요하면 {remedy} 사용",
                  file=sys.stderr)
    else:
        print("[build_case_2d] ★경고: 단면이 코일을 지나지 않음 — 2D 열 배출 경계 없음", file=sys.stderr)
    if check:
        print("[--check] 2D 생성 생략, 검증만 통과", file=sys.stderr)
        return

    open_top = bool(c['run'].get('open_top', True))
    zf, Tw = base.zero_fields(c, open_top)
    zf = {k: add_empty_patch(v) for k, v in zf.items()}
    c2 = copy.deepcopy(c)
    c2['probes_mm']['points'] = map_probes(c, s, geo)
    c2['heater']['total_W'] = round(sc['power_per_width_2d_W_m'] * s['thickness_mm'] / 1000.0, 6)
    c2['coil']['h_W_m2K'] = h
    coil_len = 2.0 * ((geo['coil']['x1'] - geo['coil']['x0']) + (geo['coil']['y1'] - geo['coil']['y0'])) \
        if geo['coil'] else 0.0
    coil_area = coil_len * s['thickness_mm'] * 1e-6
    liq, vap, wat = base.thermo_files(c)
    control = base.control_dict(c2, coil_area)
    if not geo['coil']:
        control = drop_function(control, 'coilT')    # the patch does not exist in this section
    out = {
        'system/blockMeshDict': bmd + '\n',
        'system/setFieldsDict': base.set_fields(c),
        'system/controlDict': control,
        '0.orig/T': zero_T_2d(c, sc['q_2d_W_m2'], h, open_top, Tw),
        **zf,
        'constant/phaseProperties': base.phase_properties(c),
        'constant/thermophysicalProperties.liquid': liq,
        'constant/thermophysicalProperties.vapour': vap,
        'constant/thermophysicalProperties.water': wat,
    }
    manifest = {
        'format': 'cfd-studio section2d v1',
        'axis_mapping': {'x': 'tank depth z [m]', 'y': 'tank height y [m]', 'z': 'extrusion (empty)'},
        'section': s,
        'scaling': sc,
        'coil': coil,
        'segments_mm': geo['segments'],
        'board_mm': geo['board'], 'coil_mm': geo['coil'],
        'tank_mm': {'depth': geo['D'], 'height': geo['H'], 'width': geo['W'],
                    'dielectric_height': c['layers']['dielectric_mm']},
        'fluid': fluid_record(c),
        'condition': c.get('_condition'),
        'cells': len(grid['cell_ix']),
        'grid': grid,
    }
    out[MANIFEST] = json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=1)
    for rel, txt in out.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as fh:
            fh.write(txt)
    point = fix_reference_point(root, s, geo, open_top)
    if point:
        print(f"[build_case_2d] 밀폐 2D 단면용 기준점 갱신: {point}", file=sys.stderr)
    print(f"[build_case_2d] {len(out)}개 파일 생성 완료 (격자 대응표 {MANIFEST})", file=sys.stderr)
