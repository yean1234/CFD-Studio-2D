"""Read-only access to completed warehouse transport cases for Studio.

The displayed points are cell centres, not a reconstructed volume field.
"""
import json
import math
from pathlib import Path
import re
from zipfile import BadZipFile

import numpy as np

from tracer_transport.run import read_field


CASE_NAME = re.compile(r'warehouse_transport_[A-Za-z0-9_-]+\Z')


class WarehouseResults:
    def __init__(self, output_root):
        self.output_root = Path(output_root)

    def _case(self, name):
        if not isinstance(name, str) or not CASE_NAME.fullmatch(name):
            raise ValueError('올바른 저장고 결과 이름이 아닙니다')
        case = self.output_root/name
        if not case.is_dir() or case.is_symlink():
            raise ValueError('저장고 결과를 찾을 수 없습니다')
        return case

    def _load(self, name):
        case = self._case(name)
        state = json.loads((case/'state.json').read_text(encoding='utf-8'))
        if state.get('status') != 'complete':
            raise ValueError('완료된 계산 결과만 조회할 수 있습니다')
        model = json.loads((case/'model_contract.json').read_text(encoding='utf-8'))
        checks = json.loads((case/'checks.json').read_text(encoding='utf-8'))
        config = json.loads((case/'transport_input.json').read_text(encoding='utf-8'))
        if not checks.get('numerical_pass') or model.get('kind') not in ('normalized_gable_verification', 'clo2_gas_in_air'):
            raise ValueError('검사된 저장고 수송 결과가 아닙니다')
        with np.load(case/'concentration.npz', allow_pickle=False) as archive:
            times = archive['times_s'].copy()
            fields = archive['concentration'].copy()
            centres = archive['cell_centres_m'].copy()
            unit = str(archive['concentration_unit'])
        cells = model['geometry']['cells']
        if (times.ndim != 1 or len(times) < 2 or not np.isfinite(times).all()
                or times[0] != 0 or not np.all(np.diff(times) > 0)
                or fields.shape != (len(times), cells) or not np.isfinite(fields).all()
                or centres.shape != (cells, 3) or not np.isfinite(centres).all()
                or unit != model['initial_unit'] or checks.get('cells') != cells
                or checks.get('frames') != len(times)):
            raise ValueError('저장 배열 또는 모델 계약이 일치하지 않습니다')
        return case, model, checks, config, times, fields, centres, unit

    def list(self):
        if not self.output_root.is_dir():
            return []
        results = []
        for path in sorted(self.output_root.iterdir()):
            if not CASE_NAME.fullmatch(path.name) or not path.is_dir() or path.is_symlink():
                continue
            try:
                case, model, checks, config, times, fields, centres, unit = self._load(path.name)
                results.append({'id': path.name, 'model': model['kind'], 'unit': unit,
                                'frames': len(times), 'cells': len(centres),
                                'numerical_pass': True, 'experimental_validation': False})
            except (OSError, ValueError, KeyError, TypeError, BadZipFile, EOFError):
                continue
        return results

    def metadata(self, name):
        case, model, checks, config, times, fields, centres, unit = self._load(name)
        return {'id': name, 'model': model['kind'], 'model_validation': model['model_validation'],
                'concentration_unit': unit, 'temperature_field': 'unavailable',
                'numerical_pass': True, 'experimental_validation': False,
                'times_s': times.tolist(), 'cells': len(centres),
                'geometry': config['geometry_spec']['geometry'],
                'geometry_basis': checks['geometry_basis'],
                'relative_balance_error': checks['relative_balance_error'],
                'diffusivity_source': model.get('diffusivity_source'),
                'raw_folder': str(case), 'array_file': str(case/'concentration.npz')}

    def frame(self, name, index, maximum_points=25000):
        case, model, checks, config, times, fields, centres, unit = self._load(name)
        if isinstance(index, bool) or not isinstance(index, int) or index < 0 or index >= len(times):
            raise ValueError('저장된 프레임 범위를 벗어났습니다')
        raw = read_field(case/f'{times[index]:g}'/'C', len(centres))
        if raw.shape != fields[index].shape or not np.array_equal(raw, fields[index]):
            raise ValueError('원본장과 조회 배열이 일치하지 않습니다')
        stride = max(1, math.ceil(len(centres)/maximum_points))
        selected = np.arange(0, len(centres), stride)
        values = fields[index, selected]
        scale = 1e6 if unit == 'kg/m3' else 1
        display_unit = 'mg/m3' if unit == 'kg/m3' else 'C/C_ref'
        return {'index': index, 'time_s': float(times[index]), 'total_cells': len(centres),
                'displayed_cells': len(selected), 'sampling_stride': stride,
                'cell_centres_m': centres[selected].tolist(),
                'concentration': (values*scale).tolist(), 'concentration_unit': display_unit,
                'minimum': float(fields[index].min()*scale), 'maximum': float(fields[index].max()*scale),
                'raw_file': str(case/f'{times[index]:g}'/'C'), 'raw_npz_match': True}

    def sample(self, name, xyz, time_s, max_cell_distance_m):
        case, model, checks, config, times, fields, centres, unit = self._load(name)
        xyz = np.asarray(xyz, dtype=float)
        if (xyz.shape != (3,) or not np.isfinite(xyz).all() or not math.isfinite(time_s)
                or not math.isfinite(max_cell_distance_m) or max_cell_distance_m <= 0):
            raise ValueError('유한한 좌표·시간·최대 셀 거리가 필요합니다')
        geometry = config['geometry_spec']['geometry']
        length, width = geometry['length_m'], geometry['width_m']
        roof = geometry['eaves_m'] + geometry['roof_rise_m']*(1-abs(2*xyz[1]/width-1))
        if not (0 <= xyz[0] <= length and 0 <= xyz[1] <= width and 0 <= xyz[2] <= roof):
            raise ValueError('좌표가 저장동 계산 영역 밖입니다')
        if time_s < times[0] or time_s > times[-1]:
            raise ValueError('시간이 저장된 프레임 범위 밖입니다')
        distances = np.linalg.norm(centres-xyz, axis=1)
        index = int(np.argmin(distances))
        if distances[index] > max_cell_distance_m:
            raise ValueError('가장 가까운 셀 중심까지 허용 거리를 초과합니다')
        left = max(0, int(np.searchsorted(times, time_s, side='right')-1))
        right = left if times[left] == time_s else min(left+1, len(times)-1)
        raw_files = [case/f'{times[i]:g}'/'C' for i in sorted({left, right})]
        for i, raw_path in zip(sorted({left, right}), raw_files):
            raw = read_field(raw_path, len(centres))
            if not np.array_equal(raw, fields[i]):
                raise ValueError('원본장과 조회 배열이 일치하지 않습니다')
        scale = 1e6 if unit == 'kg/m3' else 1
        return {'requested_xyz_m': xyz.tolist(), 'time_s': float(time_s),
                'cell_index': index, 'cell_centre_m': centres[index].tolist(),
                'cell_centre_distance_m': float(distances[index]),
                'sampling': 'nearest_cell_linear_time',
                'concentration': float(np.interp(time_s, times, fields[:, index])*scale),
                'concentration_unit': 'mg/m3' if unit == 'kg/m3' else 'C/C_ref',
                'temperature': None, 'temperature_status': 'not_calculated',
                'source_files': [str(p) for p in raw_files], 'raw_npz_match': True}
