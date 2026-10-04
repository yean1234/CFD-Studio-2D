"""Read-only warehouse results using the Windows embedded Python standard library."""
import ast
import json
import math
from pathlib import Path
import re
import struct
from zipfile import ZipFile, BadZipFile

CASE_NAME = re.compile(r'warehouse_transport_[A-Za-z0-9_-]+\Z')


def npy_member(archive, name):
    payload = archive.read(name+'.npy')
    if payload[:6] != b'\x93NUMPY' or len(payload) < 10:
        raise ValueError(f'잘못된 NPY 형식: {name}')
    major, minor = payload[6:8]
    if (major, minor) == (1, 0):
        length_size, start = 2, 10
    elif major in (2, 3):
        length_size, start = 4, 12
    else:
        raise ValueError(f'지원하지 않는 NPY 버전: {name}')
    header_length = int.from_bytes(payload[8:8+length_size], 'little')
    if header_length <= 0 or start+header_length > len(payload):
        raise ValueError(f'손상된 NPY 머리말: {name}')
    try:
        header = ast.literal_eval(payload[start:start+header_length].decode('utf-8' if major == 3 else 'latin1'))
    except (ValueError, SyntaxError, UnicodeDecodeError) as error:
        raise ValueError(f'손상된 NPY 머리말: {name}') from error
    if not isinstance(header, dict) or set(header) != {'descr', 'fortran_order', 'shape'} or header['fortran_order'] is not False:
        raise ValueError(f'지원하지 않는 NPY 배열: {name}')
    shape, descr = header['shape'], header['descr']
    if not isinstance(shape, tuple) or any(type(d) is not int or d < 0 for d in shape):
        raise ValueError(f'잘못된 NPY 배열 크기: {name}')
    count, data = math.prod(shape), payload[start+header_length:]
    if descr in ('<f8', '<f4'):
        width, code = (8, 'd') if descr == '<f8' else (4, 'f')
        if len(data) != count*width:
            raise ValueError(f'잘못된 NPY 데이터 크기: {name}')
        values = struct.unpack('<'+str(count)+code, data)
        if not all(math.isfinite(v) for v in values):
            raise ValueError(f'유한하지 않은 NPY 값: {name}')
        return shape, values
    if isinstance(descr, str) and re.fullmatch(r'<U[1-9]\d*', descr) and shape == ():
        if len(data) != int(descr[2:])*4:
            raise ValueError(f'잘못된 NPY 문자열 크기: {name}')
        return shape, data.decode('utf-32le').rstrip('\x00')
    raise ValueError(f'지원하지 않는 NPY 자료형: {name}')


def raw_field(path, cells, dimensions, components=1):
    source = path.read_text(encoding='ascii')
    if ('boundaryField' not in source or source.count('{') != source.count('}')
            or source.count('(') != source.count(')')):
        raise ValueError(f'불완전한 OpenFOAM 원본장: {path}')
    found = re.search(r'\bdimensions\s*\[([^]]+)\]', source)
    if dimensions and (not found or found.group(1).strip() != dimensions):
        raise ValueError(f'원본장 단위가 모델 계약과 다릅니다: {path}')
    uniform = re.search(r'\binternalField\s+uniform\s+' +
                       (r'([\deE.+-]+)' if components == 1 else r'\(([^)]+)\)') + r'\s*;', source)
    if uniform:
        row = tuple(float(v) for v in uniform.group(1).split())
        if len(row) != components:
            raise ValueError(f'잘못된 OpenFOAM 성분 수: {path}')
        values = row*cells
    else:
        kind = 'scalar' if components == 1 else 'vector'
        match = re.search(r'\binternalField\s+nonuniform\s+List<' + kind + r'>\s+(\d+)\s*\((.*?)\)\s*;', source, re.S)
        if not match or int(match.group(1)) != cells:
            raise ValueError(f'잘못된 OpenFOAM 원본장: {path}')
        values = tuple(float(x) for x in match.group(2).replace('(', ' ').replace(')', ' ').split())
    if len(values) != cells*components or not all(math.isfinite(v) for v in values):
        raise ValueError(f'잘못된 OpenFOAM 스칼라값: {path}')
    return values


class WarehouseResults:
    def __init__(self, output_root, resolve_case=None, case_paths=None):
        self.output_root = Path(output_root)
        self.resolve_case = resolve_case
        self.case_paths = case_paths

    def _case(self, name):
        if not isinstance(name, str) or not CASE_NAME.fullmatch(name):
            raise ValueError('올바른 저장고 결과 이름이 아닙니다')
        case = (self.resolve_case(name) if self.resolve_case else None) or self.output_root/name
        if not case.is_dir() or case.is_symlink():
            raise ValueError('저장고 결과를 찾을 수 없습니다')
        return case

    @staticmethod
    def _raw_path(case,times,index,field):
        manifest=case/'frame_sources.json'
        folder=f'{times[index]:g}'
        if manifest.exists():
            frames=json.loads(manifest.read_text(encoding='utf-8'))
            if not isinstance(frames,list) or len(frames)!=len(times):
                raise ValueError('원본 프레임 목록이 시간 배열과 다릅니다')
            entry=frames[index]
            if not isinstance(entry,dict):
                raise ValueError('원본 프레임 항목 형식이 올바르지 않습니다')
            folder=entry.get('directory')
            if (entry.get('time_s')!=times[index] or not isinstance(folder,str)
                    or not re.fullmatch(r'\d+(?:\.\d+)?',folder)
                    or not math.isclose(float(folder),times[index],rel_tol=0,abs_tol=1e-7)):
                raise ValueError('원본 프레임 경로·시간이 올바르지 않습니다')
        if (case/folder).resolve().parent!=case.resolve():
            raise ValueError('원본 프레임 경로가 계산 폴더 밖입니다')
        return case/folder/field

    def _load(self, name):
        case = self._case(name)
        state = json.loads((case/'state.json').read_text(encoding='utf-8'))
        if state.get('status') != 'complete':
            raise ValueError('완료된 계산 결과만 조회할 수 있습니다')
        model = json.loads((case/'model_contract.json').read_text(encoding='utf-8'))
        checks = json.loads((case/'checks.json').read_text(encoding='utf-8'))
        config = json.loads((case/'transport_input.json').read_text(encoding='utf-8'))
        if not (checks.get('numerical_pass') or checks.get('execution_checks_pass')) or model.get('kind') not in ('normalized_gable_verification', 'clo2_gas_in_air', 'clo2_plan_scenario', 'clo2_coupled_scenario'):
            raise ValueError('검사된 저장고 수송 결과가 아닙니다')
        with ZipFile(case/'concentration.npz') as archive:
            time_shape, times = npy_member(archive, 'times_s')
            field_shape, fields = npy_member(archive, 'concentration')
            centre_shape, centres = npy_member(archive, 'cell_centres_m')
            _, unit = npy_member(archive, 'concentration_unit')
        cells = model['geometry']['cells']
        expected_unit = 'C/C_ref' if model['kind'] == 'normalized_gable_verification' else 'kg/m3'
        if (len(time_shape) != 1 or len(times) < 2 or times[0] != 0
                or any(b <= a for a, b in zip(times, times[1:]))
                or field_shape != (len(times), cells) or centre_shape != (cells, 3)
                or unit != expected_unit or unit != model['initial_unit'] or checks.get('cells') != cells
                or checks.get('frames') != len(times)):
            raise ValueError('저장 배열 또는 모델 계약이 일치하지 않습니다')
        return case, model, checks, config, times, fields, centres, unit

    def list(self):
        results = []
        paths = list(self.case_paths()) if self.case_paths else []
        if self.output_root.is_dir():
            paths += sorted(self.output_root.iterdir())
        seen = set()
        for path in paths:
            path = Path(path)
            if path.name in seen:
                continue
            seen.add(path.name)
            if not CASE_NAME.fullmatch(path.name) or not path.is_dir() or path.is_symlink():
                continue
            try:
                case, model, checks, config, times, fields, centres, unit = self._load(path.name)
                results.append({'id': path.name, 'model': model['kind'], 'unit': unit,
                                'frames': len(times), 'cells': len(centres)//3,
                                'numerical_pass': bool(checks.get('numerical_pass')), 'experimental_validation': False})
            except (OSError, ValueError, KeyError, TypeError, BadZipFile, EOFError, struct.error):
                continue
        return results

    def metadata(self, name):
        case, model, checks, config, times, fields, centres, unit = self._load(name)
        temperatures = self._temperatures(case, model, times)
        return {'id': name, 'model': model['kind'], 'model_validation': model['model_validation'],
                'concentration_unit': unit, 'temperature_field': model.get('temperature_representation', 'unavailable'),
                'temperature_timeseries_C': temperatures, 'loading': model.get('loading'),
                'velocity_field': model.get('velocity_representation', 'unavailable'),
                'available_fields': ['concentration', 'temperature', 'velocity'] if model['kind'] == 'clo2_coupled_scenario' else ['concentration'],
                'relative_energy_balance_error': checks.get('relative_energy_balance_error'),
                'leakage': model.get('leakage', 'not_modeled'),
                'porous_grain': model.get('porous_grain'),
                'coordinate_representation': model.get('coordinate_representation','arithmetic_mean_of_six_face_centres'),
                'grain_volume_report': json.loads((case/'loading_report.json').read_text(encoding='utf-8')) if (case/'loading_report.json').exists() else None,
                'grid_assessment': json.loads((case/'grid_assessment.json').read_text(encoding='utf-8')) if (case/'grid_assessment.json').exists() else None,
                'assumptions': model.get('assumptions', []),
                'numerical_pass': bool(checks.get('numerical_pass')), 'experimental_validation': False,
                'times_s': list(times), 'cells': len(centres)//3,
                'geometry': config['geometry_spec']['geometry'],
                'computational_domain': model.get('computational_domain'),
                'geometry_basis': checks['geometry_basis'],
                'relative_balance_error': checks['relative_balance_error'],
                'diffusivity_source': model.get('diffusivity_source'),
                'raw_folder': str(case), 'array_file': str(case/'concentration.npz')}

    @staticmethod
    def _temperatures(case, model, times):
        if model['kind'] != 'clo2_plan_scenario':
            return None
        with ZipFile(case/'concentration.npz') as archive:
            shape, values = npy_member(archive, 'temperature_C')
        if shape != (len(times),):
            raise ValueError('온도 입력 시계열 크기가 프레임과 다릅니다')
        return list(values)

    @staticmethod
    def _coupled_frame(case, model, times, index):
        if model['kind'] != 'clo2_coupled_scenario':
            return None
        cells = model['geometry']['cells']
        with ZipFile(case/'concentration.npz') as archive:
            tshape, temperatures = npy_member(archive, 'temperature_K')
            ushape, velocities = npy_member(archive, 'velocity_m_s')
        if tshape != (len(times), cells) or ushape != (len(times), cells, 3):
            raise ValueError('연결 계산의 온도·유속 배열 크기가 다릅니다')
        temperatures = temperatures[index*cells:(index+1)*cells]
        velocities = velocities[index*cells*3:(index+1)*cells*3]
        sources = {name: str(WarehouseResults._raw_path(case,times,index,name)) for name in ('T','U')}
        for name, values, dims, count in [('T', temperatures, '0 0 0 1 0 0 0', 1),
                                           ('U', velocities, '0 1 -1 0 0 0 0', 3)]:
            if raw_field(Path(sources[name]), cells, dims, count) != values:
                raise ValueError(f'{name} 원본장과 조회 배열이 일치하지 않습니다')
        return temperatures, velocities, sources

    def frame(self, name, index, maximum_points=25000):
        if type(maximum_points) is not int or maximum_points < 1:
            raise ValueError('표시 셀 수는 양의 정수여야 합니다')
        case, model, checks, config, times, fields, centres, unit = self._load(name)
        if type(index) is not int or index < 0 or index >= len(times):
            raise ValueError('저장된 프레임 범위를 벗어났습니다')
        cells = len(centres)//3
        values = fields[index*cells:(index+1)*cells]
        raw_path = self._raw_path(case,times,index,'C')
        if raw_field(raw_path, cells, model.get('field_dimensions')) != values:
            raise ValueError('원본장과 조회 배열이 일치하지 않습니다')
        stride = max(1, math.ceil(cells/maximum_points))
        selected = range(0, cells, stride)
        scale = 1e6 if unit == 'kg/m3' else 1
        temperatures = self._temperatures(case, model, times)
        result = {'index': index, 'time_s': times[index], 'total_cells': cells,
                'temperature_C': temperatures[index] if temperatures else None,
                'displayed_cells': len(selected), 'sampling_stride': stride,
                'cell_centres_m': [list(centres[i*3:i*3+3]) for i in selected],
                'concentration': [values[i]*scale for i in selected],
                'concentration_unit': 'mg/m3' if scale != 1 else 'C/C_ref',
                'minimum': min(values)*scale, 'maximum': max(values)*scale,
                'raw_file': str(raw_path), 'raw_npz_match': True}
        coupled = self._coupled_frame(case, model, times, index)
        if coupled:
            temp, velocity, sources = coupled
            speeds = [math.hypot(*velocity[i*3:i*3+3]) for i in range(cells)]
            result.update(temperature_field_C=[temp[i]-273.15 for i in selected],
                          velocity_m_s=[list(velocity[i*3:i*3+3]) for i in selected],
                          speed_m_s=[speeds[i] for i in selected],
                          temperature_range_C=[min(temp)-273.15,max(temp)-273.15],
                          speed_range_m_s=[min(speeds),max(speeds)],
                          source_files={'C':str(raw_path), **sources})
        return result

    def sample(self, name, xyz, time_s, max_cell_distance_m):
        case, model, checks, config, times, fields, centres, unit = self._load(name)
        if (len(xyz) != 3 or not all(math.isfinite(v) for v in xyz)
                or not math.isfinite(time_s) or not math.isfinite(max_cell_distance_m)
                or max_cell_distance_m <= 0):
            raise ValueError('유한한 좌표·시간·최대 셀 거리가 필요합니다')
        geometry = config['geometry_spec']['geometry']
        length, width = geometry['length_m'], geometry['width_m']
        roof = geometry['eaves_m'] + geometry['roof_rise_m']*(1-abs(2*xyz[1]/width-1))
        if not (0 <= xyz[0] <= length and 0 <= xyz[1] <= width and 0 <= xyz[2] <= roof):
            raise ValueError('좌표가 저장동 계산 영역 밖입니다')
        domain = model.get('computational_domain')
        if domain and any(not lo<=v<=hi for v,(lo,hi) in zip(xyz,domain['bounds_m'])):
            raise ValueError('좌표가 저장동 계산 영역 밖입니다')
        if time_s < times[0] or time_s > times[-1]:
            raise ValueError('시간이 저장된 프레임 범위 밖입니다')
        cells = len(centres)//3
        cell = min(range(cells), key=lambda i: sum((centres[i*3+k]-xyz[k])**2 for k in range(3)))
        distance = math.dist(centres[cell*3:cell*3+3], xyz)
        if distance > max_cell_distance_m:
            raise ValueError('가장 가까운 셀 중심까지 허용 거리를 초과합니다')
        left = max(i for i, t in enumerate(times) if t <= time_s)
        right = left if times[left] == time_s else left+1
        indices = sorted({left, right})
        source_files = [self._raw_path(case,times,i,'C') for i in indices]
        for i, path in zip(indices, source_files):
            if raw_field(path, cells, model.get('field_dimensions')) != fields[i*cells:(i+1)*cells]:
                raise ValueError('원본장과 조회 배열이 일치하지 않습니다')
        fraction = 0 if right == left else (time_s-times[left])/(times[right]-times[left])
        value = fields[left*cells+cell]*(1-fraction)+fields[right*cells+cell]*fraction
        scale = 1e6 if unit == 'kg/m3' else 1
        temperatures = self._temperatures(case, model, times)
        temperature = temperatures[left]*(1-fraction)+temperatures[right]*fraction if temperatures else None
        velocity = None
        temperature_status = 'prescribed_uniform_C' if temperatures else 'not_calculated'
        if model['kind'] == 'clo2_coupled_scenario':
            frames = {i:self._coupled_frame(case, model, times, i) for i in indices}
            temperature = frames[left][0][cell]*(1-fraction)+frames[right][0][cell]*fraction-273.15
            velocity = [frames[left][1][3*cell+k]*(1-fraction)+frames[right][1][3*cell+k]*fraction for k in range(3)]
            temperature_status = 'solved_energy_C'
            source_files.extend(Path(path) for v in frames.values() for path in v[2].values())
        return {'requested_xyz_m': list(xyz), 'time_s': time_s,
                'cell_index': cell, 'cell_centre_m': list(centres[cell*3:cell*3+3]),
                'cell_centre_distance_m': distance, 'sampling': 'nearest_cell_linear_time',
                'concentration': value*scale,
                'concentration_unit': 'mg/m3' if scale != 1 else 'C/C_ref',
                'temperature': temperature, 'temperature_status': temperature_status,
                'velocity_m_s': velocity, 'speed_m_s': math.hypot(*velocity) if velocity is not None else None,
                'source_files': [str(p) for p in source_files], 'raw_npz_match': True}
