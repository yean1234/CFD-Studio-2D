# -*- coding: utf-8 -*-
"""2D section results -> coarse inputs for the bubble-field research pipeline.

  python3 tools/export_coarse_2d.py [--out export_2d] [--skip-initial 0.3] [--stride 1]
                                    [--coarse-dx-mm 6] [--case-id NAME]

Reads reconstructed time directories of a case built with build_case_2d.py and the
grid map constant/section2d.json; OpenFOAM utilities are not needed.

Outputs (SI units):
  fields_2d.h5 (or .npz)       temperature, velx, vely, alpha_vapour, alpha_water, mask,
                               x, y, time — BubbleML-style (frame, y, x); solid cells NaN
  heater_wall_2d.csv           per frame and heater face: q'', cell T, wall T, vapour fraction
  coarse_inputs.csv            time-averaged, same columns as Cooper-relation coarse_inputs.csv
  coarse_inputs_extended.csv   adds wall temperature, superheat and subcooling
  export_manifest.json         section, scaling, fluid values, frames and assumptions

The wall temperature is the solver's own CPU patch value (faces in ascending height,
the blockMesh order written by build_case_2d.py). On a 2-3 mm grid it is a
boundary-model output, not a resolved superheat; when the patch values are missing
the conduction estimate T_cell + q'' * delta / kappa_mix is used and labelled.
"""
import argparse
import csv
import gzip
import json
import math
import os
import re
import sys

import numpy as np

try:
    import h5py
except ImportError:
    h5py = None

MANIFEST = os.path.join('constant', 'section2d.json')
COOPER_COLUMNS = ('case_id', 'coarse_cell', 'x_m', 'q_W_m2', 'vapor_fraction')


# ---------------------------------------------------------------- OpenFOAM field reader
def _open_field(path):
    if os.path.exists(path):
        with open(path, 'rb') as fh:
            return fh.read()
    if os.path.exists(path + '.gz'):
        with gzip.open(path + '.gz', 'rb') as fh:
            return fh.read()
    return None


def _format(raw):
    # The OpenFOAM banner can exceed 600 bytes; the header ends before internalField.
    end = raw.find(b'internalField')
    head = raw[:end if end > 0 else 4096]
    binary = re.search(rb'format\s+binary', head) is not None
    m = re.search(rb'scalar=(\d+)', head)
    size = int(m.group(1)) // 8 if m else 8
    return binary, size


def _read_entry(raw, pos, ncomp, binary, size):
    """Parse 'uniform v' or 'nonuniform List<T> N (...)' at pos. Returns (value, end)."""
    m = re.compile(rb'\s*(uniform|nonuniform)\s+').match(raw, pos)
    if not m:
        raise ValueError('필드 항목 형식을 읽을 수 없음')
    pos = m.end()
    if m.group(1) == b'uniform':
        if ncomp == 1:
            u = re.compile(rb'([-+0-9.eE]+)').match(raw, pos)
            return float(u.group(1)), u.end()
        u = re.compile(rb'\(\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\)').match(raw, pos)
        return tuple(float(v) for v in u.groups()), u.end()
    h = re.compile(rb'List<(?:scalar|vector)>\s*(\d+)\s*\(').match(raw, pos)
    if not h:
        raise ValueError('nonuniform List 형식을 읽을 수 없음')
    n, start = int(h.group(1)), h.end()
    if binary:
        dtype = '<f8' if size == 8 else '<f4'
        count = n * ncomp
        data = np.frombuffer(raw, dtype=dtype, count=count, offset=start).astype(np.float64)
        return data.reshape(n, ncomp) if ncomp > 1 else data, start + count * (size)
    end = raw.index(b';', start)
    body = raw[start:end].rsplit(b')', 1)[0]
    try:
        nums = np.array(body.replace(b'(', b' ').replace(b')', b' ').split(), dtype=np.float64)
    except ValueError:
        raise ValueError('ASCII 목록을 숫자로 읽을 수 없음 (format 헤더 확인)') from None
    if nums.size != n * ncomp:
        raise ValueError(f'ASCII 목록 길이 불일치 ({nums.size} != {n * ncomp})')
    return (nums.reshape(n, ncomp) if ncomp > 1 else nums), end


def read_field(path, ncomp, ncells, patch=None):
    """Internal field (ncells[,ncomp]) and, optionally, one patch's face values."""
    raw = _open_field(path)
    if raw is None:
        return None, None
    binary, size = _format(raw)
    i = raw.find(b'internalField')
    if i < 0:
        raise ValueError(f'internalField 없음: {path}')
    value, end = _read_entry(raw, i + len(b'internalField'), ncomp, binary, size)
    if not isinstance(value, np.ndarray):
        value = np.tile(np.asarray(value, dtype=np.float64), (ncells, 1)) if ncomp > 1 \
            else np.full(ncells, value, dtype=np.float64)
    if value.shape[0] != ncells:
        raise ValueError(f'{path}: 셀 수 {value.shape[0]} 가 격자 대응표 {ncells} 와 다름')
    faces = None
    if patch:
        # Patches follow internalField in mesh order; the heater patch is listed first.
        m = re.compile(rb'\n\s*' + re.escape(patch.encode()) + rb'\s*\n\s*\{').search(raw, end)
        if m:
            v = re.compile(rb'\bvalue\s+(?=uniform|nonuniform)').search(raw, m.end())
            if v:
                faces, _ = _read_entry(raw, v.end(), ncomp, binary, size)
    return value, faces


def time_dirs(case):
    out = []
    for name in os.listdir(case):
        full = os.path.join(case, name)
        if not os.path.isdir(full):
            continue
        try:
            t = float(name)
        except ValueError:
            continue
        out.append((t, name))
    return [name for t, name in sorted(out)]


# ---------------------------------------------------------------- physics helpers
def interp_table(T, xs, ys):
    """Linear table lookup with end-value clamping, matching build_case.table_value."""
    return np.interp(T, np.asarray(xs, dtype=float), np.asarray(ys, dtype=float))


def kappa_liquid(fluid, T):
    if fluid.get('kappa_table_K'):
        return interp_table(T, fluid['kappa_table_K'], fluid['kappa_table_W_mK'])
    return np.full_like(np.asarray(T, dtype=float), fluid['k_liquid'])


def block_mean(values, block):
    """Same rule as Cooper-relation coarsen._block_mean: drop the partial tail block."""
    n = (values.size // block) * block
    if n == 0:
        return np.array([float(np.nanmean(values))])
    return np.nanmean(values[:n].reshape(-1, block), axis=1)


def clean(obj):
    """JSON without NaN: unknown numbers become null instead of 0."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        return float(obj) if math.isfinite(obj) else None
    if isinstance(obj, np.integer):
        return int(obj)
    return obj


# ---------------------------------------------------------------- export
class FieldWriter:
    """Stream frames to HDF5 when h5py exists, otherwise collect for one .npz."""

    def __init__(self, path_stem, n, ny, nx, names, attrs, grid):
        self.names = names
        self.h5 = None
        if h5py is not None:
            self.path = path_stem + '.h5'
            self.h5 = h5py.File(self.path, 'w')
            for name in names:
                self.h5.create_dataset(name, shape=(n, ny, nx), dtype='f4',
                                       chunks=(1, ny, nx), compression='gzip', compression_opts=4)
            self.h5.create_dataset('time', shape=(n,), dtype='f8')
            for key, arr in grid.items():
                self.h5.create_dataset(key, data=arr)
            for key, val in attrs.items():
                self.h5.attrs[key] = val
        else:
            self.path = path_stem + '.npz'
            self.data = {name: np.full((n, ny, nx), np.nan, dtype=np.float32) for name in names}
            self.data['time'] = np.zeros(n)
            self.grid, self.attrs = grid, attrs

    def put(self, i, t, arrays):
        for name in self.names:
            if name in arrays:
                if self.h5 is not None:
                    self.h5[name][i] = arrays[name]
                else:
                    self.data[name][i] = arrays[name]
        if self.h5 is not None:
            self.h5['time'][i] = t
        else:
            self.data['time'][i] = t

    def close(self):
        if self.h5 is not None:
            self.h5.close()
        else:
            np.savez_compressed(self.path, **self.data, **self.grid,
                                attrs=json.dumps(clean(self.attrs), ensure_ascii=False))


def export(case, out, skip_initial=0.3, stride=1, coarse_dx_mm=None, case_id=None, include_zero=False):
    mpath = os.path.join(case, MANIFEST)
    if not os.path.exists(mpath):
        sys.exit(f"[오류] {MANIFEST} 없음 — 2D 단면 케이스가 아님 (MODE=2D ./Allrun 먼저 실행)")
    with open(mpath, encoding='utf-8') as fh:
        man = json.load(fh)
    grid, fluid = man['grid'], man['fluid']
    ncells = int(man['cells'])
    ix, iy = np.asarray(grid['cell_ix']), np.asarray(grid['cell_iy'])
    xe = np.asarray(grid['x_edges_mm']) / 1000.0
    ye = np.asarray(grid['y_edges_mm']) / 1000.0
    nx, ny = xe.size - 1, ye.size - 1
    xc, yc = 0.5 * (xe[1:] + xe[:-1]), 0.5 * (ye[1:] + ye[:-1])
    area = np.diff(xe)[ix] * np.diff(ye)[iy]
    mask = np.zeros((ny, nx), dtype=np.uint8)
    mask[iy, ix] = 1
    faces = grid['heater_faces']
    fcell = np.array([f['cell'] for f in faces])
    fdelta = np.array([f['delta_mm'] for f in faces]) / 1000.0
    fy = np.array([0.5 * (f['y0_mm'] + f['y1_mm']) for f in faces]) / 1000.0
    q = float(man['scaling']['q_2d_W_m2'])
    Tsat = float(fluid['T_sat_K'])
    k_v, k_w = float(fluid['k_vapor']), float(fluid['k_upper_liquid'])
    dielectric = man['tank_mm']['dielectric_height'] / 1000.0
    pool = (yc[iy] < dielectric)
    case_id = case_id or man.get('condition') or os.path.basename(os.path.abspath(case))

    names = [t for t in time_dirs(case) if include_zero or float(t) > 0]   # 0 = initial condition
    names = [t for t in names if os.path.exists(os.path.join(case, t, 'alpha.vapour'))
             or os.path.exists(os.path.join(case, t, 'alpha.vapour.gz'))]
    names = names[::max(1, stride)]
    if not names:
        sys.exit("[오류] alpha.vapour가 있는 재조립 시간 폴더 없음 — reconstructPar 결과 확인")
    os.makedirs(out, exist_ok=True)
    attrs = {
        'format': 'BubbleML-style 2D section v1 (SI units, solid cells NaN)',
        'axes': 'arrays (frame, y, x); x = tank depth z, y = height; mask=1 fluid',
        'fluid': fluid['name'], 'Tsat_K': Tsat,
        'rho_liquid': fluid['rho_liquid'], 'rho_vapour': fluid['rho_vapor'],
        'sigma_lv': fluid['sigma'], 'h_fg_J_kg': fluid['h_fg'],
        'nondim_l0_m': fluid['nondim_l0_m'], 'nondim_t0_s': fluid['nondim_t0_s'],
        'nondim_u0_m_s': fluid['nondim_u0_m_s'],
        'section_x_m': man['section']['x_mm'] / 1000.0,
        'heat_rule': man['scaling']['heat_rule'], 'q_heater_W_m2': q,
    }
    field_names = ['temperature', 'velx', 'vely', 'alpha_vapour', 'alpha_water']
    writer = FieldWriter(os.path.join(out, 'fields_2d'), len(names), ny, nx, field_names, attrs,
                         {'x': xc, 'y': yc, 'x_edges': xe, 'y_edges': ye, 'mask': mask})
    wall_rows, per_frame = [], []
    sources = {'solver_patch': 0, 'conduction_estimate': 0}
    assumed_no_water = False
    for i, name in enumerate(names):
        d = os.path.join(case, name)
        t = float(name)
        av, _ = read_field(os.path.join(d, 'alpha.vapour'), 1, ncells)
        aw, _ = read_field(os.path.join(d, 'alpha.water'), 1, ncells)
        T, Tpatch = read_field(os.path.join(d, 'T'), 1, ncells, patch='cpu')
        U, _ = read_field(os.path.join(d, 'U'), 3, ncells)
        arrays = {}
        for key, val in (('alpha_vapour', av), ('alpha_water', aw), ('temperature', T)):
            if val is not None:
                g = np.full((ny, nx), np.nan, dtype=np.float32)
                g[iy, ix] = val
                arrays[key] = g
        if U is not None:
            for key, comp in (('velx', 0), ('vely', 1)):
                g = np.full((ny, nx), np.nan, dtype=np.float32)
                g[iy, ix] = U[:, comp]
                arrays[key] = g
        writer.put(i, t, arrays)
        if T is None:
            continue                      # wall model needs temperature (output_fields 'therm')
        if aw is None:
            assumed_no_water = True
            aw = np.zeros(ncells)
        al = np.clip(1.0 - av - aw, 0.0, 1.0)
        tc, avc, awc, alc = T[fcell], av[fcell], aw[fcell], al[fcell]
        kmix = alc * kappa_liquid(fluid, tc) + avc * k_v + awc * k_w
        if isinstance(Tpatch, np.ndarray) and Tpatch.size == len(faces):
            twall, source = np.asarray(Tpatch, dtype=float), 'solver_patch'
        else:
            twall, source = tc + q * fdelta / kmix, 'conduction_estimate'
        sources[source] += 1
        liquid = pool & (al >= 0.9)
        tbulk = float(np.sum(T[liquid] * area[liquid]) / np.sum(area[liquid])) if liquid.any() else float('nan')
        per_frame.append((t, avc, twall, tc, tbulk))
        for k, f in enumerate(faces):
            wall_rows.append({'time_s': t, 'face': k, 'y_m': fy[k], 'q_W_m2': q,
                              'T_cell_K': tc[k], 'T_wall_K': twall[k], 'T_wall_source': source,
                              'dT_wall_sat_K': twall[k] - Tsat, 'vapor_fraction': avc[k],
                              'kappa_mix_W_mK': kmix[k], 'T_bulk_K': tbulk})
    writer.close()
    if not per_frame:
        sys.exit("[오류] T가 저장된 프레임 없음 — run.output_fields에 therm 포함 필요")

    with open(os.path.join(out, 'heater_wall_2d.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(wall_rows[0]))
        w.writeheader()
        w.writerows(wall_rows)

    # Time average after the initial transient: one value per condition (9/20 rule).
    first = int(math.floor(len(per_frame) * skip_initial))
    use = per_frame[first:] or per_frame[-1:]
    alpha_t = np.mean([r[1] for r in use], axis=0)
    twall_t = np.mean([r[2] for r in use], axis=0)
    tcell_t = np.mean([r[3] for r in use], axis=0)
    tbulk_t = float(np.nanmean([r[4] for r in use]))
    native = np.array([f['y1_mm'] - f['y0_mm'] for f in faces]).mean() / 1000.0
    block = 1
    if coarse_dx_mm:
        block = max(1, int(round(coarse_dx_mm / 1000.0 / native)))
    # Blocks never cross heater segments.
    seg_id = np.zeros(len(faces), dtype=int)
    for k in range(1, len(faces)):
        gap = faces[k]['y0_mm'] - faces[k - 1]['y1_mm']
        seg_id[k] = seg_id[k - 1] + (1 if gap > 1e-6 else 0)
    rows, ext = [], []
    cell = 0
    for s in np.unique(seg_id):
        sel = seg_id == s
        b = min(block, int(sel.sum()))
        ys = block_mean(fy[sel], b)
        av = block_mean(alpha_t[sel], b)
        tw = block_mean(twall_t[sel], b)
        tcl = block_mean(tcell_t[sel], b)
        for y_m, a, tw_k, tc_k in zip(ys, av, tw, tcl):
            rows.append({'case_id': case_id, 'coarse_cell': cell, 'x_m': y_m, 'q_W_m2': q,
                         'vapor_fraction': a})
            ext.append({**rows[-1], 'segment': int(s), 'T_cell_K': tc_k, 'T_wall_cfd_K': tw_k,
                        'dT_sup_cfd_K': tw_k - Tsat, 'T_bulk_K': tbulk_t,
                        'dT_sub_K': Tsat - tbulk_t, 'frames': len(use)})
            cell += 1
    for fname, data, cols in (('coarse_inputs.csv', rows, COOPER_COLUMNS),
                              ('coarse_inputs_extended.csv', ext, list(ext[0]))):
        with open(os.path.join(out, fname), 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=list(cols))
            w.writeheader()
            w.writerows(data)

    assumptions = [
        'T_wall = 솔버가 쓴 cpu 패치 면 온도(높이 오름차순). 2~3 mm 격자의 벽 경계 모델 출력이며 해상된 과열도가 아님 '
        '— 기포 명세서의 ΔT_sup는 Cooper 역산 또는 벽함수 경로로 구할 것',
        '패치 값이 없는 프레임만 T_cell + q″·δ/κ_mix(산술 혼합 κ) 전도 추정값 사용 — T_wall_source 열로 구분',
        'T_bulk = 하단 액체층(y < 계면 높이)에서 액상 분율 0.9 이상 셀의 면적 가중 평균',
        'x_m = 히터를 따라 잰 위치이며 이 케이스는 높이 y [m]',
        '2D 단면은 탱크 x 방향 유동·기포 확산을 표현하지 않음',
    ]
    if assumed_no_water:
        assumptions.append('alpha.water 미저장 프레임 — 히터 셀 상단 액체 분율을 0으로 가정')
    report = {
        'case': os.path.abspath(case), 'case_id': case_id,
        'frames_total': len(names), 'frames_with_T': len(per_frame), 'frames_averaged': len(use),
        'skip_initial_fraction': skip_initial, 'stride': stride,
        'time_range_s': [per_frame[0][0], per_frame[-1][0]],
        'coarse_block_faces': block, 'native_face_height_m': native,
        'heater_mean': {'q_W_m2': q, 'vapor_fraction': float(np.mean(alpha_t)),
                        'T_wall_cfd_K': float(np.mean(twall_t)), 'dT_sup_cfd_K': float(np.mean(twall_t)) - Tsat,
                        'T_bulk_K': tbulk_t, 'dT_sub_K': Tsat - tbulk_t},
        'T_wall_source_frames': sources,
        'fields_file': os.path.basename(writer.path),
        'section': man['section'], 'scaling': man['scaling'], 'coil': man.get('coil'),
        'fluid': fluid, 'assumptions': assumptions,
    }
    with open(os.path.join(out, 'export_manifest.json'), 'w', encoding='utf-8') as fh:
        json.dump(clean(report), fh, ensure_ascii=False, indent=1, allow_nan=False)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--case', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument('--out', default='export_2d')
    ap.add_argument('--skip-initial', type=float, default=0.3, help='시간 평균에서 버릴 앞쪽 프레임 비율')
    ap.add_argument('--stride', type=int, default=1)
    ap.add_argument('--coarse-dx-mm', type=float, default=None,
                    help='히터 면을 이 길이로 묶어 평균 (원 격자보다 굵을 때만 의미)')
    ap.add_argument('--case-id', default=None)
    ap.add_argument('--include-zero', action='store_true', help='초기조건 0 폴더도 프레임에 포함')
    a = ap.parse_args(argv)
    if not 0 <= a.skip_initial < 1:
        sys.exit('[오류] --skip-initial 은 0 이상 1 미만')
    out = a.out if os.path.isabs(a.out) else os.path.join(a.case, a.out)
    r = export(a.case, out, a.skip_initial, a.stride, a.coarse_dx_mm, a.case_id, a.include_zero)
    hm = r['heater_mean']
    print(f"[export_2d] {r['frames_averaged']}/{r['frames_with_T']} 프레임 평균 → {out}")
    print(f"[export_2d] 히터 평균 q″ {hm['q_W_m2']/1000:.2f} kW/m² · 증기분율 {hm['vapor_fraction']:.3f} · "
          f"서브쿨 {hm['dT_sub_K']:.2f} K")
    print(f"[export_2d] 참고: CFD 벽면 온도 기준 과열도 {hm['dT_sup_cfd_K']:.1f} K 는 거친 격자 벽 경계 모델 값 "
          f"(물리 과열도 아님 · 출처 {r['T_wall_source_frames']})")


if __name__ == '__main__':
    main()
