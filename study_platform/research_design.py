"""연구 설계의 변수·기하 제약 검사. 실제 ClO2 계산기로 사용하지 않는다."""
import copy
import itertools
import math

from .contracts import canonical, digest, number

GROUPS = {
    'design': {'label': '설계변수', 'keys': ['layout', 'spacing_m', 'supply_positions', 'total_supply']},
    'environment': {'label': '환경·물성', 'keys': ['temperature_K', 'leakage', 'bag_resistance', 'porosity', 'diffusion', 'reaction']},
    'numerical': {'label': '수치 설정', 'keys': ['mesh_m', 'dt_s', 'evaluation_s', 'write_interval_s', 'convergence']},
}
KEYS = {key for group in GROUPS.values() for key in group['keys']}
LOCKED = {'total_supply', 'temperature_K', 'leakage', 'bag_resistance', 'porosity', 'diffusion',
          'reaction', 'mesh_m', 'dt_s', 'evaluation_s', 'write_interval_s', 'convergence'}


def variable_schema():
    """값·범위를 채우지 않은 입력 사전. 문헌 근거와 사용자 가정을 구분한다."""
    units = {'spacing_m': 'm', 'temperature_K': 'K', 'porosity': '1', 'diffusion': 'm2/s',
             'mesh_m': 'm', 'dt_s': 's', 'evaluation_s': 's', 'write_interval_s': 's'}
    return {'profile': 'warehouse_joint_v1', 'represented_model': 'geometry_design_only',
            'research_target': 'ClO2', 'solver_ready': False, 'groups': GROUPS,
            'variables': {key: {'mode': 'fixed', 'value': None, 'unit': units.get(key),
                               'evidence': None} for key in sorted(KEYS)},
            'sampling': {'method': 'cartesian_choices', 'seed': 0},
            'locked_in_initial_comparison': sorted(LOCKED),
            'derived_rules': {'spacing_m': 'minimum_horizontal_clearance'},
            'required_fixed_conditions': ['geometry', 'stored_mass_kg', 'source_count', 'supply_duration_s', 'total_supply']}


def vector(value, label):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(label+'는 x,y,z 세 값이 필요합니다')
    return [number(x) for x in value]


def box(value):
    if not isinstance(value, dict) or not {'min', 'max'} <= set(value):
        raise ValueError('영역의 min/max 좌표가 필요합니다')
    lo, hi = vector(value['min'], 'min'), vector(value['max'], 'max')
    if any(b <= a for a, b in zip(lo, hi)):
        raise ValueError('영역 크기는 양수여야 합니다')
    return lo, hi


def overlap(a, b):
    return all(min(a[1][i], b[1][i]) > max(a[0][i], b[0][i]) for i in range(3))


def inside(point, bounds):
    return all(bounds[0][i] <= point[i] <= bounds[1][i] for i in range(3))


def constraints(common, layout, sources, spacing):
    """값을 이동·보정하지 않고 위반 객체와 이유를 반환한다."""
    reasons = []
    geometry = common['geometry']
    length, width, height = [number(geometry[k]) for k in ('length_m', 'width_m', 'eaves_m')]
    if min(length, width, height) <= 0:
        raise ValueError('저장동 치수는 양수여야 합니다')
    clearance = number(common['wall_clearance_m'])
    maximum_height = number(common['maximum_stack_height_m'])
    minimum_gap = number(spacing)
    if clearance < 0 or maximum_height <= 0 or minimum_gap < 0:
        raise ValueError('벽·블록 간격과 적재 높이를 확인해 주세요')
    if not isinstance(layout, dict):
        raise ValueError('배치 객체가 필요합니다')
    blocks = layout.get('blocks')
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= 200:
        raise ValueError('배치별 블록은 1~200개여야 합니다')
    boxes, mass, ids = [], 0., set()
    for block in blocks:
        key = block.get('id')
        if not isinstance(key, str) or not key or key in ids:
            raise ValueError('블록 ID는 비어 있지 않은 고유 문자열이어야 합니다')
        ids.add(key)
        bounds = box(block)
        weight = number(block.get('mass_kg'))
        if weight <= 0:
            raise ValueError('블록 저장량은 양수여야 합니다')
        mass += weight
        lo, hi = bounds
        if (lo[0] < clearance or hi[0] > length-clearance or lo[1] < clearance or hi[1] > width-clearance
                or lo[2] < 0 or hi[2] > min(height, maximum_height)):
            reasons.append({'code': 'BLOCK_OUTSIDE', 'object': key, 'message': '벽 간격·영역 또는 적재 높이 위반'})
        for other, other_bounds in boxes:
            if overlap(bounds, other_bounds):
                reasons.append({'code': 'BLOCK_COLLISION', 'object': [key, other], 'message': '적재 블록 충돌'})
            # 바닥 투영의 축별 이격을 사용한다. 통로 자체는 별도 영역으로 검사한다.
            gap = max(max(other_bounds[0][i]-hi[i], lo[i]-other_bounds[1][i], 0) for i in (0, 1))
            if gap < minimum_gap:
                reasons.append({'code': 'BLOCK_CLEARANCE', 'object': [key, other], 'message': '블록 간격 부족'})
        boxes.append((key, bounds))
    target, tolerance = number(common['stored_mass_kg']), number(common['mass_tolerance_kg'])
    if target <= 0 or tolerance < 0:
        raise ValueError('공통 저장량과 허용오차를 확인해 주세요')
    if abs(mass-target) > tolerance:
        reasons.append({'code': 'STORAGE_MASS', 'message': '공통 저장량 불일치', 'actual_kg': mass, 'required_kg': target})
    aisles = common.get('aisles')
    if not isinstance(aisles, list) or not aisles:
        reasons.append({'code': 'AISLE_UNDEFINED', 'message': '유지할 작업 통로 영역을 지정해 주세요'})
    else:
        for aisle in aisles:
            bounds = box(aisle)
            axis = aisle.get('width_axis')
            if axis not in (0, 1) or isinstance(axis, bool):
                raise ValueError('통로 폭 기준 축은 0(x) 또는 1(y)입니다')
            required = number(aisle.get('minimum_width_m'))
            if required <= 0:
                raise ValueError('통로 최소 폭은 양수여야 합니다')
            if bounds[1][axis]-bounds[0][axis] < required:
                reasons.append({'code': 'AISLE_WIDTH', 'message': '통로 폭 부족'})
            if not inside(bounds[0], ([0, 0, 0], [length, width, height])) or not inside(bounds[1], ([0, 0, 0], [length, width, height])):
                reasons.append({'code': 'AISLE_OUTSIDE', 'message': '통로가 저장동 밖에 있습니다'})
            for key, block_bounds in boxes:
                if overlap(bounds, block_bounds):
                    reasons.append({'code': 'AISLE_BLOCKED', 'object': key, 'message': '통로에 적재물이 있습니다'})
    count = common['source_count']
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError('공통 공급원 수는 양의 정수여야 합니다')
    if not isinstance(sources, list) or len(sources) != count:
        reasons.append({'code': 'SOURCE_COUNT', 'message': '공통 공급원 수 불일치'})
    if not isinstance(sources, list):
        return reasons
    allowed = [box(region) for region in common.get('allowed_source_regions', [])]
    seen_sources = set()
    for index, point in enumerate(sources):
        point = vector(point, '공급 좌표')
        if tuple(point) in seen_sources:
            reasons.append({'code': 'SOURCE_DUPLICATE', 'object': index, 'message': '공급 위치가 중복됩니다'})
        seen_sources.add(tuple(point))
        if not inside(point, ([0, 0, 0], [length, width, height])) or not any(inside(point, region) for region in allowed):
            reasons.append({'code': 'SOURCE_OUTSIDE', 'object': index, 'message': '공급 허용 영역 밖입니다'})
        if any(inside(point, block_bounds) for _, block_bounds in boxes):
            reasons.append({'code': 'SOURCE_IN_BLOCK', 'object': index, 'message': '공급 위치가 적재물 내부·경계에 있습니다'})
    return reasons


def preview(design):
    required = {'profile', 'variables', 'common', 'sampling', 'baseline'}
    if not isinstance(design, dict) or set(design) != required or design['profile'] != 'warehouse_joint_v1':
        raise ValueError('연구 설계 스키마를 확인해 주세요')
    variables, common = design['variables'], design['common']
    if not isinstance(variables, dict) or set(variables) != KEYS:
        raise ValueError('세 그룹의 변수 정의를 모두 제공해 주세요')
    duration = number(common.get('supply_duration_s'))
    if duration <= 0:
        raise ValueError('공통 공급시간이 필요합니다')
    choices, derived = {}, []
    for key, entry in variables.items():
        if not isinstance(entry, dict):
            raise ValueError('변수 정의는 객체여야 합니다: '+key)
        if set(entry)-{'mode', 'value', 'choices', 'bounds', 'count', 'unit', 'evidence', 'rule'}:
            raise ValueError('알 수 없는 변수 설정: '+key)
        mode = entry.get('mode')
        if mode not in ('fixed', 'search', 'derived'):
            raise ValueError('고정·탐색·자동 계산 중 선택해 주세요: '+key)
        if key in LOCKED and mode != 'fixed':
            raise ValueError('초기 공동 비교에서는 고정해야 합니다: '+key)
        if mode == 'derived':
            if key != 'spacing_m' or entry.get('rule') != 'minimum_horizontal_clearance':
                raise ValueError('지원하지 않는 자동 계산 규칙: '+key)
            derived.append(key); continue
        if mode == 'fixed':
            values = [entry.get('value')]
        else:
            values = entry.get('choices')
            if values is None and key == 'spacing_m':
                lo, hi = entry.get('bounds', [None, None]); lo, hi = number(lo), number(hi)
                count = entry.get('count')
                if isinstance(count, bool) or not isinstance(count, int) or not 2 <= count <= 32 or lo >= hi:
                    raise ValueError('간격 범위·후보 수를 확인해 주세요')
                values = [lo+(hi-lo)*i/(count-1) for i in range(count)]
            if not isinstance(values, list) or not values:
                raise ValueError('탐색 후보 목록이 필요합니다: '+key)
        if values == [None] and key in ('layout', 'spacing_m', 'supply_positions', 'total_supply'):
            raise ValueError('설계값을 먼저 확정해 주세요: '+key)
        choices[key] = values
    supply = choices['total_supply'][0]
    if not isinstance(supply, dict) or not supply.get('unit') or not supply.get('evidence') or number(supply.get('value')) <= 0:
        raise ValueError('총 공급량은 값·단위·근거를 명시해야 합니다. 자동 추천하지 않습니다')
    sampling = design['sampling']
    if set(sampling) != {'method', 'seed'} or sampling['method'] != 'cartesian_choices' or isinstance(sampling['seed'], bool) or not isinstance(sampling['seed'], int):
        raise ValueError('공동 비교는 명시된 후보의 Cartesian 조합입니다. 정수 시드를 기록해 주세요')
    if math.prod(len(values) for values in choices.values()) > 128:
        raise ValueError('한 버전의 조합 수는 128개 이하로 나누어 주세요')
    baseline = copy.deepcopy(design['baseline'])
    rows, seen = [], set()
    combinations = [baseline]+[dict(zip(choices, values)) for values in itertools.product(*choices.values())]
    for index, resolved in enumerate(combinations):
        resolved = copy.deepcopy(resolved)
        # 간격 탐색은 사용자가 지정한 축의 단일 열 배치에만 적용한다.
        # 기존 블록 크기·질량·첫 블록 위치는 유지하며 임의 배치 최적화는 하지 않는다.
        if index and variables['spacing_m']['mode'] == 'search':
            layout = resolved['layout']
            axis = layout.get('spacing_axis')
            if isinstance(axis, bool) or axis not in (0, 1):
                raise ValueError('간격 탐색 배치에는 spacing_axis 0(x) 또는 1(y)를 명시해 주세요')
            blocks = layout['blocks']
            gap = number(resolved['spacing_m'])
            if gap < 0:
                raise ValueError('간격은 음수가 될 수 없습니다')
            for previous, block in zip(blocks, blocks[1:]):
                size = block['max'][axis]-block['min'][axis]
                block['min'][axis] = previous['max'][axis]+gap
                block['max'][axis] = block['min'][axis]+size
        if 'spacing_m' in derived:
            boxes = [box(block) for block in resolved['layout']['blocks']]
            if len(boxes) < 2:
                raise ValueError('간격 자동 계산은 블록이 2개 이상이어야 합니다')
            resolved['spacing_m'] = min(max(max(b[0][i]-a[1][i], a[0][i]-b[1][i], 0) for i in (0, 1))
                                       for a, b in itertools.combinations(boxes, 2))
        if set(resolved) != KEYS:
            raise ValueError('기준안은 실제 적용 변수 전체가 필요합니다')
        for key in LOCKED:
            if canonical(resolved[key]) != canonical(choices[key][0]):
                raise ValueError('기준안과 공통 고정 조건이 다릅니다: '+key)
        if index == 0:
            baseline = copy.deepcopy(resolved)
        reasons = constraints(common, resolved['layout'], resolved['supply_positions'], resolved['spacing_m'])
        spec = {'profile': 'warehouse_joint_v1', 'represented_model': 'geometry_design_only',
                'research_target': 'ClO2', 'common': common, 'variables': resolved,
                'supply': {'total': supply, 'duration_s': duration,
                           'mean_rate': supply['value']/duration, 'rate_unit': supply['unit']+'/s',
                           'time_function': 'unspecified', 'airflow': 'not_defined_by_gas_supply'},
                'solver_ready': False, 'blocked_reason': '실제 저장고 열·유동·반응 수송 어댑터 미연결'}
        hash_value = digest(spec)
        if hash_value in seen:
            reasons.append({'code': 'DUPLICATE', 'message': '동일 입력 중복'})
        seen.add(hash_value)
        rows.append({'baseline': index == 0, 'input': spec, 'input_hash': hash_value, 'valid': not reasons,
                     'violations': reasons, 'changed': {key: {'before': baseline[key], 'after': value}
                         for key, value in resolved.items() if canonical(value) != canonical(baseline[key])}})
    result = {'design': copy.deepcopy(design), 'sampler_version': 'warehouse_joint_v1',
              'candidates': rows, 'baseline_included': True, 'solver_ready': False,
              'variable_definition': {'groups': GROUPS}, 'seed': sampling['seed']}
    return {**result, 'preview_hash': digest(result)}
