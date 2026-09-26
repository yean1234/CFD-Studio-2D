"""버전이 고정된 수치 검증 입력. 예제 계수는 실제 훈증제 물성이 아니다."""
import copy
import hashlib
import json
import math
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'study-v1'
VARIABLES = {
    'K_porous_m2_s': {'label': '다공성 유효 확산 계수', 'unit': 'm2/s', 'role': 'environment', 'bounds': [1e-5, .1]},
    'D_air_m2_s': {'label': '자유 공간 확산 계수', 'unit': 'm2/s', 'role': 'environment', 'bounds': [1e-5, .1]},
    'porosity': {'label': '다공성 공극률', 'unit': '1', 'role': 'environment', 'bounds': [.05, 1]},
}
CAPABILITIES = {'profile': 'sealed_tracer_benchmark_v1', 'represented_model': 'normalized_inert_tracer',
    'research_target': 'ClO2', 'units': 'pore C/C_ref', 'time_basis': 'physical_seconds',
    'flow': 'U=0', 'geometry': 'orthogonal_benchmark_only', 'mpi': False, 'gpu': False,
    'physical_ClO2': False, 'temperature': False, 'leakage': False, 'bag_resistance': False,
    'insects': False, 'sampling': ['manual', 'grid', 'latin_hypercube_1d'],
    'safe_live_pause': False, 'queue_pause': True, 'checkpoint_restart': True,
    'experimental_validation': False}


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(obj):
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('유한한 숫자를 입력해 주세요')
    return value


def base_input():
    cfg = json.loads((ROOT/'tracer_transport/block3d_test.json').read_text(encoding='utf-8'))
    return {'profile': CAPABILITIES['profile'], 'represented_model': CAPABILITIES['represented_model'],
            'research_target': 'ClO2', 'legacy_target_metadata': 'PH3 (not simulated chemistry)',
            'nx': 20, 'dt': .005, 'kind': 'porous', 'parameters': cfg}


def candidates(design):
    if isinstance(design, dict) and design.get('profile') == 'warehouse_joint_v1':
        from .research_design import preview
        return preview(design)
    if not isinstance(design, dict) or set(design)-{'variable', 'method', 'values', 'low', 'high', 'count', 'seed'}:
        raise ValueError('실험 설계 필드가 올바르지 않습니다')
    key = design.get('variable')
    if key not in VARIABLES:
        raise ValueError('검증 예제에서 지원하는 변수만 선택할 수 있습니다')
    method = design.get('method')
    seed = design.get('seed', 0)
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**32-1:
        raise ValueError('시드는 0~4294967295 정수여야 합니다')
    if method == 'manual':
        values = design.get('values')
        if not isinstance(values, list) or not 1 <= len(values) <= 32:
            raise ValueError('후보값은 1~32개로 입력해 주세요')
    elif method in ('grid', 'latin_hypercube_1d'):
        low, high, count = number(design.get('low')), number(design.get('high')), design.get('count')
        if isinstance(count, bool) or not isinstance(count, int) or not 2 <= count <= 32 or low >= high:
            raise ValueError('범위와 후보 수(2~32)를 확인해 주세요')
        if method == 'grid':
            values = [low+(high-low)*i/(count-1) for i in range(count)]
        else:
            rng = random.Random(seed)
            values = [low+(high-low)*(i+rng.random())/count for i in range(count)]
            rng.shuffle(values)
    else:
        raise ValueError('지원하지 않는 후보 생성 방식입니다')
    baseline = base_input()
    baseline_value = baseline['parameters'][key]
    rows, seen = [], set()
    for value in [baseline_value]+values:
        number(value)
        spec = copy.deepcopy(baseline)
        spec['parameters'][key] = value
        lower, upper = VARIABLES[key]['bounds']
        hash_value = digest(spec)
        reasons = []
        if not lower <= value <= upper:
            reasons.append(f'허용 범위: {lower}~{upper} {VARIABLES[key]["unit"]}')
        if hash_value in seen:
            reasons.append('동일 입력 중복')
        seen.add(hash_value)
        rows.append({'value': value, 'input': spec, 'input_hash': hash_value,
                     'baseline': len(rows) == 0, 'valid': not reasons, 'violations': reasons})
    preview = {'design': copy.deepcopy(design), 'sampler_version': VERSION,
               'variable_definition': {**VARIABLES[key], 'key': key, 'dtype': 'float',
                    'mode': 'search', 'evidence': 'numerical_test_assumption_not_rice_properties'},
               'baseline_included': True, 'candidates': rows}
    return {**preview, 'preview_hash': digest(preview)}
